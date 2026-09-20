"""Incremental impact analysis (代码图谱 · 增量影响分析).

索引成功后，可选地用**无头智能体**回答一个问题：这一轮增量索引吃进去的
变更，会影响什么？报告只落库 + 落盘，绝不影响索引本身的成败。

变更来源分两级，主路径刻意不依赖 git：

1. **文件清单快照**（对任何目录都成立）。每次成功索引后把仓库文件清单
   ``{相对路径: [mtime, size]}`` 写到 ``.manifests/<repo_id>.json``；下一轮
   与之对比得到精确的 added / modified / deleted。为什么不用纯 git：
   ``E:/m72-publish/m72`` 这类"发布目录"往往根本没有 .git，而它正是本平台
   最常见的分析对象。
2. **git 增强**（可选）。目录是 git 仓库且上一轮记了 HEAD 时，再附
   ``--name-status`` 与 ``--stat``，让智能体拿到行级改动而不只是文件名
   （``codebase_repos.last_commit`` 就是这份基线）。

过滤口径与 exe 实际索引范围对齐：复用仓库自己的 ``file_type_mode`` /
``file_types``（和写 .cbmignore 代管块用的是同一套语义）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete as sa_delete, select, update as sa_update

from src.app.core.config import settings
from src.app.core.workspace import get_space_id
from src.app.db.database import async_session_factory
from src.app.db.models.codebase import CodebaseImpactReport, CodebaseRepo
from src.app.services.agent_runner import run_agent_once
from src.app.services.codebase_service import normalize_extensions, project_name

logger = logging.getLogger(__name__)

REPORTS_DIRNAME = "codebase-reports"
MANIFEST_VERSION = 1

#: 每类（新增/修改/删除）在提示词里最多列出的文件名数，超出只给数量。
PROMPT_LIST_CAP = 200
#: 清单扫描上限。超限截断并如实标注——宁可少列也不要把仓库走爆。
MANIFEST_MAX_FILES = 50_000
#: git 命令超时（秒）。
_GIT_TIMEOUT = 30.0

#: 与索引无关的目录，扫描时直接跳过（.git 自己也算）。
_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "Library", "Temp", "obj", "Build", "Builds", "Logs", "UserSettings",
    ".idea", ".vscode", "dist", "build", "target", "coverage", ".next",
})

ANALYSIS_TRIGGERS = ("manual", "scheduled")
AGENT_ID = "codebase_agent"


# ===========================================================================
# 路径：报告目录与清单目录
# ===========================================================================

def reports_root() -> Path:
    """报告与变更清单的根目录（平台工作区内，可随工作区整体备份/清理）。"""
    root = settings.workspace_dir / get_space_id() / REPORTS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _manifest_path(repo_id: str | UUID) -> Path:
    directory = reports_root() / ".manifests"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{repo_id}.json"


def _ext_matches(name: str, mode: str, exts: list[str]) -> bool:
    """按仓库的文件类型规则判断文件是否在索引范围内（语义同 .cbmignore 代管块）。"""
    if mode == "all":
        return True
    suffix = Path(name).suffix.lower()
    if mode == "include":
        return suffix in exts
    if mode == "exclude":
        return suffix not in exts
    return True


# ===========================================================================
# 文件清单快照
# ===========================================================================

def scan_manifest(repo_path: str, *, mode: str = "all", file_types: list | None = None,
                  limit: int = MANIFEST_MAX_FILES) -> tuple[dict[str, list], bool]:
    """扫描仓库文件清单 → ``({相对路径: [mtime秒, size]}, truncated)``。

    只读元数据（stat），不读文件内容：大仓库也能秒级完成。
    """
    exts = normalize_extensions(list(file_types or []))
    files: dict[str, list] = {}
    truncated = False
    root = Path(repo_path)
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    if entry.name in _SKIP_DIRS:
                        continue
                    stack.append(entry)
                    continue
                if not entry.is_file():
                    continue
                rel = entry.relative_to(root).as_posix()
                if not _ext_matches(rel, mode, exts):
                    continue
                stat = entry.stat()
            except OSError:
                continue
            if len(files) >= limit:
                truncated = True
                return files, truncated
            files[rel] = [int(stat.st_mtime), stat.st_size]
    return files, truncated


def diff_manifests(previous: dict[str, list], current: dict[str, list]) -> dict[str, list[str]]:
    """两份清单的差集（新增 / 内容或时间变化 / 删除）。"""
    prev_keys = set(previous)
    cur_keys = set(current)
    added = sorted(cur_keys - prev_keys)
    deleted = sorted(prev_keys - cur_keys)
    modified = sorted(k for k in cur_keys & prev_keys if current[k] != previous[k])
    return {"added": added, "modified": modified, "deleted": deleted}


def load_manifest(repo_id: str | UUID) -> dict | None:
    path = _manifest_path(repo_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    files = payload.get("files")
    return files if isinstance(files, dict) else None


def save_manifest(repo_id: str | UUID, repo_path: str,
                  files: dict[str, list], truncated: bool) -> None:
    path = _manifest_path(repo_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "version": MANIFEST_VERSION,
        "root": repo_path,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "truncated": truncated,
        "files": files,
    }, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ===========================================================================
# git 增强（可选）
# ===========================================================================

async def _git(args: list[str], cwd: str) -> tuple[bool, str]:
    """跑一条 git 命令；非 git 环境/超时/失败都返回 (False, 原因) 而不是抛。"""
    git = shutil.which("git")
    if not git:
        return False, "git 不可用"
    try:
        proc = await asyncio.create_subprocess_exec(
            git, "-C", cwd, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return False, f"git 启动失败: {exc}"
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_GIT_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, f"git 超时 ({_GIT_TIMEOUT}s)"
    if proc.returncode != 0:
        return False, (err.decode("utf-8", errors="replace")[:200] or "git 返回非零")
    return True, out.decode("utf-8", errors="replace")


async def git_head(repo_path: str) -> str | None:
    """当前 HEAD；非 git 仓库返回 None。"""
    ok, out = await _git(["rev-parse", "HEAD"], repo_path)
    return out.strip() if ok and out.strip() else None


async def git_snapshot(repo_path: str, base_commit: str | None) -> dict | None:
    """相对基线的行级变更（name-status + stat）；拿不到就返回 None。"""
    head = await git_head(repo_path)
    if not head:
        return None
    snapshot: dict = {"head": head, "base": base_commit or "", "name_status": [], "stat": ""}
    if base_commit and base_commit != head:
        ok, out = await _git(["diff", "--name-status", f"{base_commit}..{head}"], repo_path)
        if ok:
            snapshot["name_status"] = [line for line in out.splitlines() if line.strip()][:500]
        ok, out = await _git(["diff", "--stat", f"{base_commit}..{head}"], repo_path)
        if ok:
            snapshot["stat"] = out[-4000:]
    elif base_commit == head:
        snapshot["note"] = "HEAD 未变（工作区可能有未提交改动）"
    return snapshot


# ===========================================================================
# 变更收集
# ===========================================================================

async def collect_changes(repo: CodebaseRepo, previous: dict[str, list] | None) -> dict:
    """收集本轮变更集：清单差集（主）+ git 行级变更（增强）。"""
    current, truncated = scan_manifest(
        repo.repo_path, mode=repo.file_type_mode, file_types=repo.file_types or [])
    changes: dict = {
        "counts": {"added": 0, "modified": 0, "deleted": 0, "files_total": len(current)},
        "added": [], "modified": [], "deleted": [],
        "truncated": truncated,
        "first_round": previous is None,
        "git": None,
    }
    if previous is not None:
        delta = diff_manifests(previous, current)
        changes["added"] = delta["added"]
        changes["modified"] = delta["modified"]
        changes["deleted"] = delta["deleted"]
        changes["counts"].update({
            "added": len(delta["added"]),
            "modified": len(delta["modified"]),
            "deleted": len(delta["deleted"]),
        })
    git_info = await git_snapshot(repo.repo_path, repo.last_commit)
    if git_info:
        changes["git"] = git_info
    changes["_manifest"] = current  # 调用方落盘用，不写进 DB
    return changes


def has_changes(changes: dict) -> bool:
    counts = changes.get("counts") or {}
    return any(counts.get(k) for k in ("added", "modified", "deleted"))


# ===========================================================================
# 提示词
# ===========================================================================

def _bullets(names: list[str], cap: int = PROMPT_LIST_CAP) -> str:
    shown = names[:cap]
    lines = [f"- {name}" for name in shown]
    if len(names) > cap:
        lines.append(f"- …另有 {len(names) - cap} 个未列出")
    return "\n".join(lines)


def build_prompt(repo: CodebaseRepo, changes: dict) -> str:
    """增量影响分析提示词。报告正文 = 智能体最后一条回复。"""
    counts = changes.get("counts") or {}
    name = repo.display_name or repo.repo_path
    sections: list[str] = [
        f"仓库：{name}",
        f"仓库绝对路径：{repo.repo_path}",
        f"图谱项目名：{project_name(repo.repo_path)}",
        "",
        "刚刚完成一轮**增量索引**（只重新解析变更文件）。本轮涉及的变更如下——",
        "请分析这些变更对系统的影响。",
        "",
        "## 变更统计",
        f"- 新增 {counts.get('added', 0)} 个文件",
        f"- 修改 {counts.get('modified', 0)} 个文件",
        f"- 删除 {counts.get('deleted', 0)} 个文件",
        f"- 仓库纳入索引的文件总数 {counts.get('files_total', 0)}",
    ]
    if changes.get("truncated"):
        sections.append("- ⚠️ 文件清单扫描触顶被截断，下面的列表不完整")

    if changes.get("added"):
        sections += ["", "## 新增文件", _bullets(changes["added"])]
    if changes.get("modified"):
        sections += ["", "## 修改文件", _bullets(changes["modified"])]
    if changes.get("deleted"):
        sections += ["", "## 删除文件", _bullets(changes["deleted"])]

    git = changes.get("git") or {}
    if git.get("name_status"):
        sections += [
            "", f"## git 行级变更（{git.get('base', '')[:8]}..{git.get('head', '')[:8]}）",
            "```", "\n".join(git["name_status"][:300]), "```",
        ]
    if git.get("stat"):
        sections += ["", "### git diffstat", "```", git["stat"], "```"]
    if not git:
        sections.append("\n（该目录不是 git 仓库，或无可用基线，只有文件级变更）")

    sections += [
        "",
        "## 请输出",
        "一份中文 Markdown 分析报告，至少覆盖：",
        "1. **变更性质**：这批改动整体在做什么（功能新增/重构/缺陷修复/配置调整…），按模块归类。",
        "2. **受影响面**：对改动涉及的核心符号，用 `graph_search` + `trace_symbol` 查出调用方，"
        "区分「直接调用方」与「间接影响」，逐条标注 `文件路径:行号` 或符号名。",
        "3. **风险点**：兼容性、协议/存档格式、并发与状态机、边界条件等具体风险，说明理由。",
        "4. **建议回归范围**：按优先级列出建议回归的模块/用例方向，并说明为什么。",
        "5. **不确定项**：证据不足的地方明确说明，并给出下一步该查什么。",
        "",
        "要求：结论先行；每个结论都要有证据（文件:行号 或 图谱符号）；**不要修改仓库里的"
        "任何文件**；把报告正文完整写在回复里。",
    ]
    return "\n".join(sections)


# ===========================================================================
# 报告持久化
# ===========================================================================

def _summarize(content: str, limit: int = 300) -> str:
    """取正文里第一段有信息量的文字当一句话结论。

    两个坑都踩过：`**结论**：…` 是加粗开场白，不能当成列表项跳过（报告基本
    都以它开头）；``` 围栏内的代码/表格要整段忽略，否则摘要会变成 diff 片段。
    """
    in_fence = False
    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line or line.startswith(("#", ">", "|")):
            continue
        if len(line) > 1 and line[0] in "-*+" and line[1] in " \t":
            continue
        if line.startswith(("---", "***", "___")):
            continue
        line = line.replace("**", "").replace("`", "")
        return line[:limit]
    return content.strip()[:limit]


def _report_file(repo: CodebaseRepo, report_id: UUID, content: str) -> str | None:
    """把报告落盘到 reports_root/<project>/<时间戳>-<短id>.md；失败返回 None。"""
    try:
        directory = reports_root() / project_name(repo.repo_path)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = directory / f"{stamp}-{str(report_id)[:8]}.md"
        path.write_text(
            f"# 增量影响分析 · {repo.display_name or repo.repo_path}\n\n"
            f"- 仓库：`{repo.repo_path}`\n"
            f"- 生成时间：{datetime.now(timezone.utc).isoformat()}\n\n---\n\n{content}\n",
            encoding="utf-8")
        return str(path)
    except OSError as exc:
        logger.warning("impact report write failed: %s", exc)
        return None


def _impact_thread_id(repo_id: UUID, run_id: UUID | None) -> str:
    """由 (仓库, 索引运行) 确定性推导线程 id。

    必须是合法 UUID（服务端校验）；用 uuid5 而不是随机值，这样同一轮索引
    重复分析会落回同一个线程，不会每跑一次就多一堆孤儿会话。
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"smart-test:impact:{repo_id}:{run_id or 'manual'}"))


async def _create_report(repo_id: UUID, *, index_run_id: UUID | None,
                         trigger: str, changes: dict) -> UUID:
    async with async_session_factory() as db:
        report = CodebaseImpactReport(
            repo_id=repo_id, index_run_id=index_run_id, trigger=trigger,
            status="running", changes={k: v for k, v in changes.items()
                                      if not k.startswith("_")})
        db.add(report)
        await db.commit()
        return report.id


async def _finish_report(report_id: UUID, status: str, *, content: str | None = None,
                         summary: str | None = None, model: str | None = None,
                         file_path: str | None = None, error: str | None = None) -> None:
    async with async_session_factory() as db:
        await db.execute(
            sa_update(CodebaseImpactReport).where(CodebaseImpactReport.id == report_id)
            .values(status=status, content_md=content, summary=summary, model=model,
                    file_path=file_path, error=error))
        await db.commit()


async def _advance_commit_base(repo_id: UUID, commit: str | None) -> None:
    """把 git 基线推进到当前 HEAD（无论分析成败——索引确实已经吃进去了）。"""
    if not commit:
        return
    async with async_session_factory() as db:
        await db.execute(sa_update(CodebaseRepo).where(CodebaseRepo.id == repo_id)
                         .values(last_commit=commit))
        await db.commit()


# ===========================================================================
# 主入口
# ===========================================================================

async def run_impact_analysis(repo_id: str | UUID, *, index_run_id: str | UUID | None = None,
                              trigger: str = "scheduled",
                              force: bool = False) -> dict:
    """对单个仓库跑一次增量影响分析。

    ``force=True``（手动点「分析一次」）时即使没有文件变更也照跑。定时路径
    用默认值：没有变更就记 skipped 直接返回，不为零变更烧 token。
    """
    repo_uuid = repo_id if isinstance(repo_id, UUID) else UUID(str(repo_id))
    async with async_session_factory() as db:
        repo = (await db.execute(select(CodebaseRepo)
                                 .where(CodebaseRepo.id == repo_uuid))).scalars().first()
    if repo is None:
        return {"success": False, "error": "仓库不存在"}
    if not Path(repo.repo_path).is_dir():
        return {"success": False, "error": f"仓库目录不存在: {repo.repo_path}"}

    run_uuid = None
    if index_run_id:
        try:
            run_uuid = UUID(str(index_run_id))
        except (ValueError, TypeError):
            run_uuid = None

    previous = load_manifest(repo_uuid)
    changes = await collect_changes(repo, previous)
    manifest = changes.pop("_manifest", {})

    # 基线先落盘：无论后面 LLM 成不成，索引确实已经推进到"当前这批文件"了，
    # 下一轮必须与它对比，否则会把同一批变更反复报出来。
    try:
        save_manifest(repo_uuid, repo.repo_path, manifest, bool(changes.get("truncated")))
    except OSError as exc:
        logger.warning("manifest save failed (%s): %s", repo.repo_path, exc)
    await _advance_commit_base(repo_uuid, (changes.get("git") or {}).get("head"))

    # 跳过也要留一行记录：用户打开了定时开关，就得能看到"这轮跑了、为什么没报告"。
    # 否则报告列表空着，分不清是没触发还是没变更。
    skipped: str | None = None
    if changes.get("first_round"):
        skipped = "首次分析：仅建立变更基线，下一轮起才有对比"
    elif not force and not has_changes(changes):
        skipped = "本轮无文件变更，未调用智能体"
    if skipped:
        report_id = await _create_report(repo_uuid, index_run_id=run_uuid,
                                        trigger=trigger, changes=changes)
        await _finish_report(report_id, "skipped", summary=skipped)
        return {"success": True, "status": "skipped", "reason": skipped,
                "report_id": str(report_id), "counts": changes.get("counts")}

    report_id = await _create_report(repo_uuid, index_run_id=run_uuid,
                                     trigger=trigger, changes=changes)
    prompt = build_prompt(repo, changes)
    result = await run_agent_once(
        prompt,
        assistant_id=AGENT_ID,
        # 无人值守：完全访问档，否则文件/shell 调用会挂起等审批卡。
        configurable={"space_id": get_space_id(), "workspace_path": repo.repo_path,
                      "permission_mode": "full_access"},
        thread_id=_impact_thread_id(repo_uuid, run_uuid),
        metadata={"repo_id": str(repo_uuid), "repo_path": repo.repo_path,
                  "report_id": str(report_id), "trigger": trigger},
    )
    if not result.get("success"):
        await _finish_report(report_id, "failed", error=str(result.get("error"))[:4000])
        logger.warning("impact analysis failed for %s: %s", repo.repo_path, result.get("error"))
        return {"success": False, "report_id": str(report_id),
                "error": result.get("error")}

    content = result["output"]
    path = _report_file(repo, report_id, content)
    await _finish_report(report_id, "success", content=content,
                         summary=_summarize(content), model=result.get("model"),
                         file_path=path)
    return {"success": True, "status": "success", "report_id": str(report_id),
            "counts": changes.get("counts"), "file_path": path}


async def analyze_after_round(results: list[dict], *, trigger: str = "scheduled") -> list[dict]:
    """定时一轮索引结束后，对"索引成功且开启分析"的仓库逐个跑影响分析。

    必须在**索引锁之外**调用：LLM 调用慢，占着锁会让手动索引排不进来。
    两级开关都要开：全局 ``codebase_analyze_enabled``（默认关）+ 每仓库
    ``auto_analyze``（默认关）。
    """
    if not getattr(settings, "codebase_analyze_enabled", False):
        return []
    outcomes: list[dict] = []
    seen: set[str] = set()
    for item in results:
        repo_id = item.get("repo_id")
        if (not repo_id or repo_id in seen
                or not item.get("success") or not item.get("auto_analyze")):
            continue
        seen.add(repo_id)
        outcomes.append(await run_impact_analysis(
            repo_id, index_run_id=item.get("run_id"), trigger=trigger))
    return outcomes


# ===========================================================================
# 查询（API 用）
# ===========================================================================

def _report_payload(report: CodebaseImpactReport, repo: CodebaseRepo | None) -> dict:
    changes = report.changes or {}
    return {
        "id": str(report.id),
        "repo_id": str(report.repo_id),
        "repo_path": repo.repo_path if repo else "",
        "repo_name": (repo.display_name or repo.repo_path) if repo else "",
        "index_run_id": str(report.index_run_id) if report.index_run_id else None,
        "trigger": report.trigger,
        "status": report.status,
        "model": report.model,
        "summary": report.summary,
        "counts": changes.get("counts") or {},
        "changes": {"added": changes.get("added") or [],
                    "modified": changes.get("modified") or [],
                    "deleted": changes.get("deleted") or [],
                    "truncated": bool(changes.get("truncated")),
                    "git": changes.get("git")},
        "file_path": report.file_path,
        "error": report.error,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def list_reports(repo_id: str | None = None, limit: int = 50) -> dict:
    limit = max(1, min(int(limit), 200))
    async with async_session_factory() as db:
        stmt = (select(CodebaseImpactReport, CodebaseRepo)
                .join(CodebaseRepo, CodebaseRepo.id == CodebaseImpactReport.repo_id,
                      isouter=True)
                .order_by(CodebaseImpactReport.created_at.desc()).limit(limit))
        if repo_id:
            try:
                stmt = stmt.where(CodebaseImpactReport.repo_id == UUID(str(repo_id)))
            except (ValueError, TypeError):
                return {"success": False, "error": f"无效 repo_id: {repo_id}"}
        rows = (await db.execute(stmt)).all()
    return {"success": True,
            "reports": [_report_payload(r, repo) for r, repo in rows]}


async def get_report(report_id: str) -> dict:
    try:
        rid = UUID(str(report_id))
    except (ValueError, TypeError):
        return {"success": False, "error": f"无效 report_id: {report_id}"}
    async with async_session_factory() as db:
        row = (await db.execute(
            select(CodebaseImpactReport, CodebaseRepo)
            .join(CodebaseRepo, CodebaseRepo.id == CodebaseImpactReport.repo_id, isouter=True)
            .where(CodebaseImpactReport.id == rid))).first()
    if row is None:
        return {"success": False, "error": "报告不存在"}
    report, repo = row
    payload = _report_payload(report, repo)
    payload["content_md"] = report.content_md or ""
    return {"success": True, "report": payload}


async def delete_report(report_id: str) -> dict:
    try:
        rid = UUID(str(report_id))
    except (ValueError, TypeError):
        return {"success": False, "error": f"无效 report_id: {report_id}"}
    async with async_session_factory() as db:
        result = await db.execute(
            sa_delete(CodebaseImpactReport).where(CodebaseImpactReport.id == rid))
        await db.commit()
        return {"success": True, "deleted": result.rowcount or 0}


async def mark_stale_reports_failed() -> int:
    """服务启动时把上一进程遗留的 running 报告标记为失败（同索引 run 的处理）。"""
    async with async_session_factory() as db:
        result = await db.execute(
            sa_update(CodebaseImpactReport)
            .where(CodebaseImpactReport.status == "running")
            .values(status="failed", error="服务重启，任务中断"))
        await db.commit()
        return result.rowcount or 0
