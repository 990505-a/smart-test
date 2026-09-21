"""Agent 记忆（harness 风格）：一组可开关、可编辑的 Markdown 记忆模块。

设计参照当前主流 harness（dsh / Claude Code / Codex）的做法：记忆不是数据库，
而是**工作区里几个固定名字的 Markdown 文件**——

    AGENTS.md    工作区指令：agent 每次都要遵守的规则与约定（等价 CLAUDE.md）
    MEMORY.md    长期记忆：跨会话沉淀的结论、领域知识
    USER.md      用户画像：偏好、称呼、输出习惯
    failures.md  失败教训：被否定的做法、返工原因、踩过的坑
    PROJECT.md   项目上下文：被测项目/端口/模块/环境约定
    DECISIONS.md 决策记录：需求裁决与用例评审结论

为什么不用向量库：这些文件是人可读、可直接编辑、可进 git 的，检索用关键词就是
够的（文件总量在几十 KB 量级），而注入的是**启用模块的全文、不做截断**（官方
MemoryMiddleware 的语义）——这才是 harness 的做法：把记忆当作提示词的一部分，
而不是一个外部服务。因为它每轮都占上下文，**内容要精炼**；旧版 EverOS
（本地服务 + SQLite + LanceDB + Windows 垫片）随之移除。

单一事实源是文件本身；``manifest.json`` 只记录"哪些模块启用、顺序、显示名"。
磁盘上多出来的 ``*.md`` 会自动成为一个模块（用户直接丢文件进来也能用）。
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.app.core.config import settings
from src.app.core.workspace import safe_segment

logger = logging.getLogger(__name__)

#: 记忆模块目录名（在 space 目录下），相对项目根解析
MEMORY_DIRNAME = "memory"
MANIFEST_NAME = "manifest.json"

_BEIJING = timezone(timedelta(hours=8))


@dataclass
class MemoryModule:
    """一个记忆模块（一个 Markdown 文件）。"""

    id: str
    file: str
    label: str
    description: str = ""
    enabled: bool = True
    builtin: bool = True
    order: int = 100
    #: 默认正文（文件不存在时写入；用户清空后不再覆盖）
    seed: str = ""
    updated_at: float = 0.0
    chars: int = 0


_BUILTIN: list[MemoryModule] = [
    MemoryModule(
        id="agents", file="AGENTS.md", label="工作区指令 (AGENTS.md)", order=10,
        description="每次对话都注入、优先级最高的规则与约定：输出语言、命名、禁止事项、交付标准",
        seed=(
            "# AGENTS.md — 工作区指令\n\n"
            "> 这里是每次对话都会被读到的**规则**。写「必须怎么做」，不要写「做过什么」。\n"
            "> 平台侧可在 /memories 页开关或直接编辑本文件。\n\n"
            "## 通用\n\n"
            "- 所有输出使用中文；结论先给答案，再给依据。\n"
            "- 产物（用例文档、报告、脚本）保存到工作区，不改动被测仓库。\n"
            "- 不确定的需求不要猜：逐条列出来问。\n"
        ),
    ),
    MemoryModule(
        id="memory", file="MEMORY.md", label="长期记忆 (MEMORY.md)", order=20,
        description="跨会话沉淀的领域知识与结论（agent 用 save_memory 追加，也可人工整理）",
        seed=(
            "# MEMORY.md — 长期记忆\n\n"
            "> 跨会话仍然成立的结论。每条带上日期与来源，便于判断是否过期。\n"
        ),
    ),
    MemoryModule(
        id="user", file="USER.md", label="用户画像 (USER.md)", order=30,
        description="用户偏好与习惯：称呼、详略程度、常用项目、明确表达过的好恶",
        seed=(
            "# USER.md — 用户画像\n\n"
            "> 只写用户明确表达过的偏好，不要从一次对话里推断性格。\n"
        ),
    ),
    MemoryModule(
        id="failures", file="failures.md", label="失败教训 (failures.md)", order=40,
        description="被否定的做法、返工原因、工具踩坑——避免同一个错误犯第二次",
        seed=(
            "# failures.md — 失败教训\n\n"
            "> 每条写清：当时做了什么 → 为什么不行 → 下次怎么做。\n"
        ),
    ),
    MemoryModule(
        id="project", file="PROJECT.md", label="项目上下文 (PROJECT.md)", order=50,
        description="被测项目的固定信息：仓库路径、模块划分、环境端口、已知约束",
        seed=(
            "# PROJECT.md — 项目上下文\n\n"
            "> 项目级的固定事实（路径、端口、环境）。会变的信息别写这里。\n"
        ),
    ),
    MemoryModule(
        id="decisions", file="DECISIONS.md", label="决策记录 (DECISIONS.md)", order=60,
        description="需求裁决与用例评审结论：谁在什么时候定了什么，为什么",
        seed=(
            "# DECISIONS.md — 决策记录\n\n"
            "> 记录\"已定\"的事：需求歧义怎么裁的、哪些用例被评审打回。\n"
        ),
    ),
]

#: 旧 EverOS 记忆的位置（用于一次性迁移到 USER.md / MEMORY.md）
_LEGACY_PROFILE_GLOB = ("**/user.md",)
#: 迁移标记：出现过就不再重复搬运
_LEGACY_MARKER = "从旧版记忆迁移"


def memory_root(space_id: str = "default") -> Path:
    """记忆模块目录。默认跟随 ``settings.workspace_dir``（容器里是共享卷）。

    ``space_id`` 会被当作**单层目录名**校验（``safe_segment``）：它来自请求参数
    ``/api/v2/memories?space=``，过去是裸拼进路径的——传 ``..`` 就能读写 workspace
    之外的任意目录（包括覆盖别处的 ``*/memory/*.md``）。
    """
    space = safe_segment(space_id or "default", field="space_id")
    return (settings.workspace_dir / space / MEMORY_DIRNAME).resolve()


def _manifest_path(space_id: str = "default") -> Path:
    return memory_root(space_id) / MANIFEST_NAME


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or f"module-{int(time.time())}"


def _safe_file(name: str) -> str:
    """模块文件名：只允许普通文件名，天然挡住目录穿越。"""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.md", name or ""):
        raise ValueError("模块文件名只能是字母数字._- 组成的 *.md")
    return name


# ---------------------------------------------------------------------------
# manifest：只存"哪些模块、是否启用、显示名"，正文永远在 .md 里
# ---------------------------------------------------------------------------

def _builtin_by_id() -> dict[str, MemoryModule]:
    return {m.id: m for m in _BUILTIN}


def _load_manifest(space_id: str = "default") -> dict:
    path = _manifest_path(space_id)
    if not path.exists():
        return {"version": 1, "modules": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "modules": []}
    except (ValueError, OSError) as exc:
        logger.warning("memory manifest 解析失败（按默认处理）: %s", exc)
        return {"version": 1, "modules": []}


def _write_manifest(space_id: str, data: dict) -> None:
    root = memory_root(space_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / MANIFEST_NAME
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    # manifest 也是用户状态（哪些模块启用、顺序、显示名），一样要留副本
    _refresh_snapshot(space_id, MANIFEST_NAME, text)


# ---------------------------------------------------------------------------
# 记忆快照：让「仓库更新」永远弄不丢用户自己的记忆
# ---------------------------------------------------------------------------
# 记忆是**用户数据**，但它住在仓库的工作区里——于是有一类很危险的时刻：这些文件
# 曾经被 git 跟踪过，某次提交把它们删掉（或改了内容），`git pull` 就会把本地那份
# 真实记忆一起抹掉。2026-09「记忆不再进 git」那次改动正是这种情况：新 clone 拿到
# 的是初始化记忆（对的），但**已有的 clone 一拉就会删文件**（不能接受）。
#
# 所以每次写正文都顺手在 `.snapshot/` 留一份副本；文件不见了就先从副本恢复，
# 只有从来没有过副本（= 真正第一次）才写内置种子。于是：
#   * 第一次拉取 → 没有快照 → 得到**初始化的记忆**；
#   * 之后的任何更新 → 文件即使被删，下一次启动就从快照原样恢复，**不覆盖、不丢**。
#
# 目录名带点号、且是子目录：list_modules 只 glob 根目录的 *.md，不会把它当成模块；
# 而整个 memory/ 已在 .gitignore 里，仓库更新碰不到它。

_SNAPSHOT_DIR = ".snapshot"


def _snapshot_path(space_id: str, filename: str) -> Path:
    return memory_root(space_id) / _SNAPSHOT_DIR / filename


def _refresh_snapshot(space_id: str, filename: str, text: str) -> None:
    """留一份副本。尽力而为：快照失败不该影响正常的读写。"""
    try:
        path = _snapshot_path(space_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # noqa: BLE001
        logger.warning("记忆快照写入失败 %s: %s", filename, exc)


def _read_snapshot(space_id: str, filename: str) -> str | None:
    path = _snapshot_path(space_id, filename)
    try:
        return path.read_text(encoding="utf-8") if path.exists() else None
    except OSError:
        return None


def _write_module_text(space_id: str, filename: str, text: str) -> None:
    """写模块正文的**唯一入口**：落盘与刷新快照成对出现，避免漏掉一处。"""
    root = memory_root(space_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / filename).write_text(text, encoding="utf-8")
    _refresh_snapshot(space_id, filename, text)


def _missing_text(space_id: str, filename: str) -> str:
    """文件不见了时该写什么：快照优先，没有快照才用内置种子。"""
    restored = _read_snapshot(space_id, filename)
    if restored is not None:
        logger.info("记忆模块 %s 缺失，已从快照恢复", filename)
        return restored
    return next((m.seed for m in _BUILTIN if m.file == filename), "")


def _overlay(module: MemoryModule, saved: dict | None) -> MemoryModule:
    if not saved:
        return module
    return MemoryModule(
        id=module.id,
        file=module.file,
        label=str(saved.get("label") or module.label),
        description=str(saved.get("description") or module.description),
        enabled=bool(saved.get("enabled", module.enabled)),
        builtin=module.builtin,
        order=int(saved.get("order", module.order)),
        seed=module.seed,
    )


def ensure_seeded(space_id: str = "default") -> None:
    """首次使用时落盘内置模块（幂等）。**已存在的文件绝不覆盖。**

    文件缺失时的顺序是「快照 → 内置种子」：有快照就原样恢复，没有才写种子。于是
    第一次拉取仓库（本地还没攒过东西、也就没有快照）拿到的是**初始化的记忆**，
    而之后的升级/拉取即使把文件删掉，下一次启动也会把用户自己的内容原样恢复回来
    —— 不覆盖、不丢。详见上面「记忆快照」那一段。
    """
    root = memory_root(space_id)
    root.mkdir(parents=True, exist_ok=True)
    # manifest 一起曾被跟踪，也可能被一次 pull 删掉。它存的是"哪些模块启用/顺序"，
    # 同样是用户状态：先尝试从快照恢复，恢复不了才由下面的逻辑按默认重建。
    manifest_path = _manifest_path(space_id)
    if not manifest_path.exists():
        saved_manifest = _read_snapshot(space_id, MANIFEST_NAME)
        if saved_manifest is not None:
            try:
                manifest_path.write_text(saved_manifest, encoding="utf-8")
            except OSError as exc:  # noqa: BLE001
                logger.warning("manifest 恢复失败: %s", exc)
    manifest = _load_manifest(space_id)
    known = {m.get("id") for m in manifest.get("modules") or []}
    changed = False
    for module in _BUILTIN:
        if module.id in known:
            continue
        manifest.setdefault("modules", []).append({
            "id": module.id, "file": module.file, "label": module.label,
            "description": module.description, "enabled": module.enabled,
            "order": module.order,
        })
        changed = True
    if changed:
        _write_manifest(space_id, manifest)

    # 一、先把现存正文全部存档（不只是内置模块：用户手写的 .md 同样要保住）。
    #     这一步让「升级后第一次启动」就把当前记忆都留了底，之后仓库怎么改都不怕。
    for path in sorted(root.glob("*.md")):
        try:
            _refresh_snapshot(space_id, path.name, path.read_text(encoding="utf-8"))
        except OSError:
            continue
    # manifest 也要存档，且要**无条件**存一次：它只在内容变化时才被 _write_manifest
    # 重写，光靠那条路径的话，一个内容早已稳定的部署升级上来时根本没有 manifest 副本
    # ——偏偏这个时候最需要它（接下来那个"停止跟踪"的提交会把它一起删掉）。
    if manifest_path.exists():
        try:
            _refresh_snapshot(space_id, MANIFEST_NAME,
                              manifest_path.read_text(encoding="utf-8"))
        except OSError:
            pass

    # 二、再补齐缺失的模块。三类都算"该在的"：
    #     * 内置模块 —— 没快照也要写种子（第一次拉取的情形）；
    #     * manifest 登记过的自定义模块；
    #     * 快照目录里有副本的文件（含用户手写丢进来的 .md：它们不在 manifest 里，
    #       但一样是用户数据，一样要能恢复）。
    #     主动删除的模块之所以不会被复活，是因为 delete_module 把快照一起删了。
    wanted = [m.file for m in _BUILTIN]
    for saved in manifest.get("modules") or []:
        file = str(saved.get("file") or "").strip()
        try:
            _safe_file(file)
        except ValueError:
            continue
        if file and file not in wanted:
            wanted.append(file)
    snapshot_dir = root / _SNAPSHOT_DIR
    if snapshot_dir.is_dir():
        for snapshot in sorted(snapshot_dir.glob("*.md")):
            try:
                _safe_file(snapshot.name)
            except ValueError:
                continue
            if snapshot.name not in wanted:
                wanted.append(snapshot.name)
    for filename in wanted:
        path = root / filename
        if path.exists():
            continue
        text = _missing_text(space_id, filename)
        if not text:
            continue
        try:
            _write_module_text(space_id, filename, text)
        except OSError as exc:  # noqa: BLE001 — 只读挂载时不该拦住对话
            logger.warning("记忆模块 %s 初始化失败: %s", filename, exc)
    _migrate_legacy_profile(space_id)
    _migrate_legacy_episodes(space_id)


def _migrate_legacy_profile(space_id: str = "default") -> None:
    """旧 EverOS 的 user.md → USER.md（只搬一次，且只在 USER.md 还是种子时）。"""
    root = memory_root(space_id)
    target = root / "USER.md"
    if not target.exists():
        return
    body = target.read_text(encoding="utf-8", errors="replace")
    if "只写用户明确表达过的偏好" not in body:  # 已被编辑过，不动
        return
    if _LEGACY_MARKER in body:  # 已经迁过：种子文字还在，标记才是"迁过了"的证据
        return
    for legacy in root.glob(_LEGACY_PROFILE_GLOB[0]):
        if legacy.name.lower() == "user.md" and "users" in legacy.parts:
            text = legacy.read_text(encoding="utf-8", errors="replace").strip()
            if len(text) > 40:
                _write_module_text(
                    space_id, "USER.md",
                    body.rstrip() + "\n\n## 从旧版记忆迁移（画像）\n\n"
                    + "> 来源：EverOS user.md（自动迁移，可自行整理或删除）\n\n"
                    + text + "\n")
            return


def _migrate_legacy_episodes(space_id: str = "default") -> None:
    """旧 EverOS 的 episodes 主题 → MEMORY.md（各搬一次，有标记就不重复）。

    只搬"主题"这一层：它是当时沉淀下来的结论，episode 正文是过程流水账，
    整段搬进长期记忆只会把提示词预算吃光。
    """
    root = memory_root(space_id)
    memory_md = root / "MEMORY.md"
    if not memory_md.exists():
        return
    current = memory_md.read_text(encoding="utf-8", errors="replace")
    if _LEGACY_MARKER in current:
        return
    summaries: list[str] = []
    for episode in sorted(root.glob("**/episodes/*.md")):
        try:
            lines = episode.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for index, line in enumerate(lines):
            if line.strip().startswith("### Subject"):
                for follow in lines[index + 1:]:
                    text = follow.strip()
                    if text and not text.startswith("#"):
                        if text not in summaries:
                            summaries.append(text)
                        break
                break
    if not summaries:
        return
    _write_module_text(
        space_id, "MEMORY.md",
        current.rstrip() + "\n\n## 从旧版记忆迁移（经历）\n\n"
        + "> 来源：EverOS episodes（自动迁移，可自行整理或删除）\n\n"
        + "\n".join(f"- {text}" for text in summaries[:200]) + "\n")


def list_modules(space_id: str = "default") -> list[MemoryModule]:
    """全部模块：内置（manifest 覆盖）+ 目录里多出来的自定义 md。"""
    ensure_seeded(space_id)
    root = memory_root(space_id)
    manifest = _load_manifest(space_id)
    saved_by_id = {m.get("id"): m for m in manifest.get("modules") or []}
    modules = [_overlay(m, saved_by_id.get(m.id)) for m in _BUILTIN]
    known_files = {m.file.lower() for m in modules}
    for saved in manifest.get("modules") or []:
        if saved.get("id") in {m.id for m in modules}:
            continue
        file = str(saved.get("file") or "")
        try:
            _safe_file(file)
        except ValueError:
            continue
        modules.append(MemoryModule(
            id=str(saved.get("id") or _slug(file)), file=file,
            label=str(saved.get("label") or file), description=str(saved.get("description") or ""),
            enabled=bool(saved.get("enabled", True)), builtin=False,
            order=int(saved.get("order", 100)),
        ))
        known_files.add(file.lower())
    # 目录里手写的 md 自动成为模块（不写 manifest 也认）
    for path in sorted(root.glob("*.md")):
        if path.name.lower() in known_files or path.name == MANIFEST_NAME:
            continue
        modules.append(MemoryModule(
            id=_slug(path.stem), file=path.name, label=path.name,
            description="目录中的自定义记忆模块", enabled=True, builtin=False, order=200,
        ))
    for module in modules:
        path = root / module.file
        if path.exists():
            module.chars = path.stat().st_size
            module.updated_at = path.stat().st_mtime
    modules.sort(key=lambda m: (m.order, m.label))
    return modules


def get_module(module_id: str, space_id: str = "default") -> MemoryModule | None:
    for module in list_modules(space_id):
        if module.id == module_id or module.file.lower() == module_id.lower():
            return module
    return None


def read_module(module_id: str, space_id: str = "default") -> str:
    module = get_module(module_id, space_id)
    if module is None:
        raise FileNotFoundError(f"记忆模块不存在: {module_id}")
    path = memory_root(space_id) / module.file
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_module(module_id: str, content: str, space_id: str = "default") -> MemoryModule:
    module = get_module(module_id, space_id)
    if module is None:
        raise FileNotFoundError(f"记忆模块不存在: {module_id}")
    root = memory_root(space_id)
    root.mkdir(parents=True, exist_ok=True)
    _write_module_text(space_id, module.file, content)
    return get_module(module.id, space_id) or module


def set_enabled(module_id: str, enabled: bool, space_id: str = "default") -> MemoryModule:
    module = get_module(module_id, space_id)
    if module is None:
        raise FileNotFoundError(f"记忆模块不存在: {module_id}")
    manifest = _load_manifest(space_id)
    entries = manifest.setdefault("modules", [])
    for entry in entries:
        if entry.get("id") == module.id:
            entry["enabled"] = bool(enabled)
            break
    else:
        entries.append({
            "id": module.id, "file": module.file, "label": module.label,
            "description": module.description, "enabled": bool(enabled), "order": module.order,
        })
    _write_manifest(space_id, manifest)
    return get_module(module.id, space_id) or module


def update_module_meta(module_id: str, *, label: str | None = None,
                       description: str | None = None,
                       space_id: str = "default") -> MemoryModule | None:
    """改显示名/说明（只动 manifest，不动正文）。"""
    module = get_module(module_id, space_id)
    if module is None:
        return None
    manifest = _load_manifest(space_id)
    entries = manifest.setdefault("modules", [])
    for entry in entries:
        if entry.get("id") == module.id:
            if label:
                entry["label"] = label
            if description is not None:
                entry["description"] = description
            break
    else:
        entries.append({
            "id": module.id, "file": module.file, "label": label or module.label,
            "description": description if description is not None else module.description,
            "enabled": module.enabled, "order": module.order,
        })
    _write_manifest(space_id, manifest)
    return get_module(module.id, space_id)


def create_module(label: str, file: str | None = None, content: str = "",
                  description: str = "", space_id: str = "default") -> MemoryModule:
    file = _safe_file(file or f"{_slug(label)}.md")
    root = memory_root(space_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / file
    if path.exists():
        raise FileExistsError(f"{file} 已存在")
    _write_module_text(space_id, file, content or f"# {label}\n\n")
    module_id = _slug(Path(file).stem)
    manifest = _load_manifest(space_id)
    manifest.setdefault("modules", []).append({
        "id": module_id, "file": file, "label": label, "description": description,
        "enabled": True, "order": 150,
    })
    _write_manifest(space_id, manifest)
    module = get_module(module_id, space_id)
    if module is None:
        raise RuntimeError("模块创建后读取失败")
    return module


def delete_module(module_id: str, space_id: str = "default") -> bool:
    """删除自定义模块（含文件）。内置模块只能停用，不能删。"""
    module = get_module(module_id, space_id)
    if module is None:
        return False
    if module.builtin:
        raise PermissionError("内置记忆模块不能删除，可以停用")
    manifest = _load_manifest(space_id)
    manifest["modules"] = [m for m in manifest.get("modules") or [] if m.get("id") != module.id]
    _write_manifest(space_id, manifest)
    path = memory_root(space_id) / module.file
    if path.exists():
        path.unlink()
    # 快照也要一起删：否则下次启动会"文件缺失 → 从快照恢复"，把刚删掉的模块复活。
    # 这是用户明确的删除动作，不是仓库更新导致的缺失，两者要区分开。
    snapshot = _snapshot_path(space_id, module.file)
    if snapshot.exists():
        snapshot.unlink()
    return True


# ---------------------------------------------------------------------------
# 写入与检索
# ---------------------------------------------------------------------------

def append_entry(module_id: str, content: str, *, category: str = "",
                 space_id: str = "default", source: str = "agent") -> MemoryModule:
    """往模块尾部追加一条带日期的条目（agent 与页面都走这里）。"""
    module = get_module(module_id, space_id)
    if module is None:
        raise FileNotFoundError(f"记忆模块不存在: {module_id}")
    root = memory_root(space_id)
    path = root / module.file
    body = path.read_text(encoding="utf-8") if path.exists() else (
        f"# {module.label}\n\n")
    stamp = datetime.now(_BEIJING).strftime("%Y-%m-%d %H:%M")
    head = f"- **{stamp}**" + (f" · {category}" if category else "") + \
           (f" · _{source}_" if source and source != "user" else "")
    text = body.rstrip() + f"\n\n{head}\n\n  " + content.strip().replace("\n", "\n  ") + "\n"
    root.mkdir(parents=True, exist_ok=True)
    _write_module_text(space_id, module.file, text)
    return get_module(module.id, space_id) or module


@dataclass
class MemoryHit:
    module_id: str
    file: str
    label: str
    line: int
    text: str
    score: float = 0.0


_STOPWORDS = {"的", "了", "和", "是", "在", "我", "你", "the", "a", "of", "to", "and"}


def _terms(query: str) -> list[str]:
    raw = re.split(r"[\s,，。;；:：/\\()（）\[\]\"'`]+", query.strip())
    terms = [t for t in raw if t and t.lower() not in _STOPWORDS]
    if not terms and query.strip():
        terms = [query.strip()]
    return terms


def search(query: str, limit: int = 8, space_id: str = "default",
           include_disabled: bool = False) -> list[MemoryHit]:
    """关键词检索：按行匹配，命中的行连同标题上下文一起返回。

    文件总量在几十 KB 量级，逐行扫描比维护索引更可靠（也不会出现索引过期）。
    """
    terms = _terms(query)
    if not terms:
        return []
    hits: list[MemoryHit] = []
    for module in list_modules(space_id):
        if not module.enabled and not include_disabled:
            continue
        path = memory_root(space_id) / module.file
        if not path.exists():
            continue
        heading = ""
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                heading = stripped.lstrip("# ").strip()
                continue
            lowered = stripped.lower()
            matched = [t for t in terms if t.lower() in lowered]
            if not matched:
                continue
            hits.append(MemoryHit(
                module_id=module.id, file=module.file, label=module.label,
                line=index, text=stripped[:400],
                score=len(matched) / len(terms) + min(len(matched), 3) * 0.1,
            ))
    hits.sort(key=lambda h: (-h.score, h.file, h.line))
    return hits[:limit]


# ---------------------------------------------------------------------------
# 注入：给 agent 的 <agent_memories> 块
# ---------------------------------------------------------------------------

def status(space_id: str = "default") -> dict:
    modules = list_modules(space_id)
    return {
        "root": str(memory_root(space_id)),
        "enabled_modules": sum(1 for m in modules if m.enabled),
        "total_modules": len(modules),
        "chars": sum(m.chars for m in modules if m.enabled),
    }
