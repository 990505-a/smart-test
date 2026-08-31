"""Feishu (Lark) integration via lark-cli (飞书模块).

Two capabilities used across the platform:

1. 思维导图保存 — generated test cases are pushed into a Feishu mindnote.
   Two modes (first match wins):
   - 目录模式: feishu_folder_token 配置后，每次导出在该目录下自动新建
     一张思维导图（.opml 上传 + import_tasks 转换，lark-cli 1.0.70 的
     mindnotes 域不支持建文档，故走 drive +upload + 原始 API）。
   - 固定导图模式: feishu_mindnote_id 指定的导图内追加节点子树
     (``lark-cli mindnotes nodes create``)。
2. 文档拉取 — API docs / requirement docs are fetched as markdown
   (``lark-cli docs +fetch``).

Everything degrades gracefully: when lark-cli is missing, not logged in,
or the mindnote id is not configured, operations return
``{"success": False, "skipped": True, ...}`` instead of raising, so the
main flows (generation / DB persistence) are never blocked by Feishu.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from src.app.core.config import settings

logger = logging.getLogger(__name__)

_CLI_TIMEOUT = 60.0
_IMPORT_POLL_INTERVAL = 1.5
_IMPORT_POLL_MAX_TRIES = 120


def _cli_bin() -> str:
    return settings.lark_cli_bin or "lark-cli"


def lark_cli_available() -> bool:
    return shutil.which(_cli_bin()) is not None


def _resolve_cmd(args: list[str]) -> list[str]:
    """Resolve lark-cli into an executable command line.

    On Windows the npm shim is a .CMD batch file which CreateProcess
    cannot run directly — route it through cmd /c.
    """
    resolved = shutil.which(_cli_bin()) or _cli_bin()
    if sys.platform == "win32" and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", resolved, *args]
    return [resolved, *args]


async def _run_cli(args: list[str], *, timeout: float = _CLI_TIMEOUT) -> dict[str, Any]:
    """Run lark-cli and parse its JSON output."""
    cmd = _resolve_cmd(args)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except FileNotFoundError:
        return {"success": False, "skipped": True, "error": f"lark-cli 未安装: {_cli_bin()}"}
    except TimeoutError:
        return {"success": False, "error": f"lark-cli 超时({timeout}s): {' '.join(args[:3])}"}

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return {"success": False, "error": err or out or f"exit code {proc.returncode}"}
    # lark-cli prints pure JSON with --json, but some commands (e.g.
    # drive +upload) prefix a human progress line — parse from the first
    # "{" and fall back to raw text when nothing JSON-like is there.
    json_start = out.find("{")
    if json_start >= 0:
        try:
            return {"success": True, "data": json.loads(out[json_start:])}
        except json.JSONDecodeError:
            pass
    return {"success": True, "data": out}


async def auth_status() -> dict[str, Any]:
    """Check lark-cli login status."""
    if not lark_cli_available():
        return {"available": False, "logged_in": False, "error": "lark-cli 未安装",
                "install_hint": "npm install -g @larksuite/cli（需要 Node.js），然后在本页发起登录"}
    result = await _run_cli(["auth", "status", "--json"])
    if not result.get("success"):
        return {"available": True, "logged_in": False, "error": result.get("error")}
    data = result.get("data") or {}
    identity = data.get("identity") or {}
    return {
        "available": True,
        "logged_in": bool(data.get("verified", True)),
        "identity": data.get("identity"),
        "user": identity.get("userName") if isinstance(identity, dict) else None,
        "raw": data,
    }


async def start_device_login() -> dict[str, Any]:
    """Device-flow login, step 1: return the verification URL for the user.

    lark-cli blocks until browser authorization unless --no-wait is passed;
    the platform splits the flow so the settings page can show the URL and
    let the user complete /auth/complete afterwards.
    """
    if not lark_cli_available():
        return {"success": False, "skipped": True, "error": "lark-cli 未安装",
                "install_hint": "npm install -g @larksuite/cli（需要 Node.js）"}
    result = await _run_cli(["auth", "login", "--no-wait", "--json", "--recommend"])
    if not result.get("success"):
        return {"success": False, "error": result.get("error")}
    data = result.get("data")
    if not isinstance(data, dict) or not data.get("verification_url"):
        return {"success": False, "error": f"登录响应异常: {str(data)[:200]}"}
    return {
        "success": True,
        "verification_url": data.get("verification_url"),
        "device_code": data.get("device_code"),
        "expires_in": data.get("expires_in"),
    }


async def complete_device_login(device_code: str) -> dict[str, Any]:
    """Device-flow login, step 2: poll authorization with the device code."""
    if not lark_cli_available():
        return {"success": False, "skipped": True, "error": "lark-cli 未安装"}
    result = await _run_cli([
        "auth", "login", "--device-code", device_code, "--json", "--recommend",
    ], timeout=90.0)
    if not result.get("success"):
        return {"success": False, "error": result.get("error")}
    status = await auth_status()
    return {"success": True, "logged_in": status.get("logged_in"), "user": status.get("user")}


# ---------------------------------------------------------------------------
# 文档拉取 (API 文档 / 需求文档)
# ---------------------------------------------------------------------------

async def fetch_doc(doc_url_or_token: str, *, scope: str | None = None) -> dict[str, Any]:
    """Fetch a Feishu doc/wiki as markdown-ish text via lark-cli.

    Returns {"success": bool, "content": str, "title": str|None}.
    """
    args = ["docs", "+fetch", "--doc", doc_url_or_token, "--as", settings.lark_cli_identity, "--json"]
    if scope:
        args += ["--scope", scope]
    result = await _run_cli(args, timeout=120.0)
    if not result.get("success"):
        return {"success": False, "error": result.get("error"), "content": ""}
    data = result.get("data")
    if isinstance(data, dict):
        content = data.get("content") or data.get("markdown") or data.get("text") or ""
        title = data.get("title")
        if not content:
            content = json.dumps(data, ensure_ascii=False, indent=2)
        return {"success": True, "content": content, "title": title, "raw": data}
    return {"success": True, "content": str(data or ""), "title": None}


# ---------------------------------------------------------------------------
# 思维导图保存
# ---------------------------------------------------------------------------

def _text_elements(text: str) -> list[dict[str, Any]]:
    return [{"element_type": "text", "text": {"content": text}}]


def _node(node_id: str, parent_id: str | None, text: str,
          *, note: str | None = None, highlight: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"node_id": node_id, "texts": _text_elements(text)}
    if parent_id:
        node["parent_id"] = parent_id
    if note:
        node["notes"] = _text_elements(note)
    if highlight:
        node["highlight"] = highlight
    return node


# 优先级 → 导图高亮色。key 统一大写归一化后再查（DB 存枚举名、
# skill 教的是小写值，历史上两套约定不一致导致 [high] 拿不到颜色）。
PRIORITY_COLORS = {
    "CRITICAL": "red", "P0": "red", "高": "red",
    "HIGH": "yellow", "P1": "yellow", "中": "yellow",
    "MEDIUM": "cyan", "P2": "cyan",
    "LOW": "grey", "P3": "grey", "低": "grey",
}


def _priority_color(priority: Any) -> str | None:
    return PRIORITY_COLORS.get(str(priority or "").strip().upper())


def _step_label(step: dict[str, Any]) -> str:
    """节点文本 = 动作（⇒ 预期）（√/X 叶子标记）。不拼编号/优先级。"""
    action = str(step.get("action") or "").strip()
    expected = str(step.get("expected") or step.get("expected_result") or "").strip()
    mark = str(step.get("mark") or "").strip()
    label = f"{action} ⇒ {expected}" if expected else action
    return f"{label} {mark}" if mark else label


def _append_step_nodes(nodes: list[dict[str, Any]], parent_id: str,
                        steps: list[dict[str, Any]]) -> None:
    """递归把嵌套步骤树转成 mindnote 节点（条件→操作→预期逐层展开）。"""
    for step in steps or []:
        if not isinstance(step, dict):
            step = {"action": str(step)}
        node_id = uuid.uuid4().hex
        nodes.append(_node(node_id, parent_id, _step_label(step)))
        _append_step_nodes(nodes, node_id, step.get("children") or [])


def build_tree_levels(
    root_text: str,
    tree: list[dict[str, Any]],
    *,
    parent_id: str | None = None,
) -> list[list[dict[str, Any]]]:
    """用例树 → 按节点深度分层的批次（每批的父节点都已存在）。

    mindnotes nodes create 不允许同批内引用同批新建节点作父级
    （飞书返回 3411001 system internal error），必须按层级分批写：
    根（可选）→ 分组 → 子分组/用例 → 步骤 → 子步骤。
    root_text 为空时不建新根，整树挂到 parent_id 下（模板复制模式）。
    """
    levels: list[list[dict[str, Any]]] = []

    def emit(level: int, node: dict[str, Any]) -> None:
        while len(levels) <= level:
            levels.append([])
        levels[level].append(node)

    def walk_steps(steps: list[dict[str, Any]], pid: str, level: int) -> None:
        for step in steps or []:
            if not isinstance(step, dict):
                step = {"action": str(step)}
            sid = uuid.uuid4().hex
            emit(level, _node(sid, pid, _step_label(step)))
            walk_steps(step.get("children") or [], sid, level + 1)

    def walk_group(group: dict[str, Any], pid: str, level: int) -> None:
        gid = uuid.uuid4().hex
        emit(level, _node(gid, pid, str(group.get("name") or "未命名分组")))
        for child in group.get("children") or []:
            walk_group(child, gid, level + 1)
        for case in group.get("cases") or []:
            cid = uuid.uuid4().hex
            note = (f"前置: {case['preconditions']}"
                    if case.get("preconditions") else None)
            emit(level + 1, _node(
                cid, gid, str(case.get("name") or "未命名用例"),
                note=note,
                highlight=_priority_color(case.get("priority")),
            ))
            walk_steps(case.get("steps") or [], cid, level + 2)

    base_parent = parent_id
    first_level = 0
    if root_text:
        root_id = uuid.uuid4().hex
        emit(0, _node(root_id, parent_id, root_text))
        base_parent = root_id
        first_level = 1
    for group in tree or []:
        walk_group(group, base_parent, first_level)
    return levels


def _payload_relpath(name: str) -> Path:
    """lark-cli --data/@file 只收 cwd 相对路径：草稿放 workspace/.feishu_tmp。

    返回相对路径（posix 形式），调用方负责用完删除。
    """
    tmp_dir = settings.workspace_dir / ".feishu_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / name
    return Path(os.path.relpath(path, Path.cwd())).as_posix()


# 单批节点数上限：实测 135 个/批复 99992402 field validation failed，
# 50 个/批稳定通过（13/49/50 的批次全 OK）。
_NODES_PER_REQUEST = 50


async def _create_nodes_by_level(
    mindnote_id: str, levels: list[list[dict[str, Any]]],
) -> dict[str, Any]:
    """逐层调用 mindnotes nodes create（层内按 50 分块）。

    两个飞书侧约束决定了这里不能一把梭：
    - 同批节点的 parent 必须已存在（不能引用同批新建节点，3411001）
    - 单批节点数有上限（>100 报 99992402 field validation failed）
    """
    total = 0
    for level in levels:
        for i in range(0, len(level), _NODES_PER_REQUEST):
            chunk = level[i:i + _NODES_PER_REQUEST]
            payload = {"client_token": str(uuid.uuid4()), "nodes": chunk}
            rel = _payload_relpath(f"mindnote_nodes_{uuid.uuid4().hex}.json")
            abs_path = Path.cwd() / rel
            try:
                abs_path.write_text(json.dumps(payload, ensure_ascii=False),
                                    encoding="utf-8")
                result = await _run_cli([
                    "mindnotes", "nodes", "create",
                    "--mindnote-id", mindnote_id,
                    "--data", f"@{rel}",
                    "--as", settings.lark_cli_identity,
                    "--json",
                ], timeout=180.0)
            finally:
                abs_path.unlink(missing_ok=True)
            ok, data, err = _unwrap(result)
            if not ok:
                return {"success": False,
                        "error": err or "写入导图节点失败",
                        "node_count": total}
            total += len(chunk)
    return {"success": True, "node_count": total}


def build_tree_nodes(
    root_text: str,
    tree: list[dict[str, Any]],
    *,
    parent_id: str | None = None,
) -> list[dict[str, Any]]:
    """分组树（任意深）→ 用例（纯标题 + 优先级高亮）→ 嵌套步骤树。

    tree 结构同 save_cases_tree 工具：[{name, children, cases:[...]}]。
    """
    root_id = uuid.uuid4().hex
    nodes = [_node(root_id, parent_id, root_text)]

    def walk_group(nodes: list[dict[str, Any]], parent: str,
                   group: dict[str, Any]) -> None:
        group_id = uuid.uuid4().hex
        nodes.append(_node(group_id, parent, str(group.get("name") or "未命名分组")))
        for child in group.get("children") or []:
            walk_group(nodes, group_id, child)
        for case in group.get("cases") or []:
            title = str(case.get("name") or "未命名用例")
            note = (f"前置: {case['preconditions']}"
                    if case.get("preconditions") else None)
            case_id = uuid.uuid4().hex
            nodes.append(_node(
                case_id, group_id, title,
                note=note,
                highlight=_priority_color(case.get("priority")),
            ))
            _append_step_nodes(nodes, case_id, case.get("steps") or [])

    for group in tree or []:
        walk_group(nodes, root_id, group)
    return nodes


async def load_doc_tree(project_name: str) -> dict[str, Any]:
    """从用例 MD 文档载入用例树（2026-08 重构后唯一数据源）。

    解析时人工标注（标题 ✅❌⚠️ 与 `>` 批注行）已被剥离，导图为干净版本。
    Returns {"success": bool, "tree": [...], "case_count": N, "root_text": str}.
    """
    from src.app.services import case_docs_service

    doc = case_docs_service.read_doc(project_name)
    if doc is None:
        return {"success": False, "error": f"用例文档不存在: {project_name}"}
    parsed = case_docs_service.parse_cases_md(doc["content"])
    return {
        "success": True,
        "tree": parsed["tree"],
        "case_count": parsed["case_count"],
        "root_text": parsed["title"] or project_name,
    }


def _unwrap(result: dict[str, Any]) -> tuple[bool, dict[str, Any], str | None]:
    """Unwrap _run_cli's {"success", "data"} envelope → lark-cli's {"ok", "data"}."""
    if not result.get("success"):
        return False, {}, str(result.get("error") or "lark-cli 调用失败")
    outer = result.get("data")
    if not isinstance(outer, dict) or not outer.get("ok"):
        err = outer.get("error") if isinstance(outer, dict) else None
        msg = err.get("message") if isinstance(err, dict) else str(err or outer)[:300]
        return False, {}, f"lark-cli 返回错误: {msg}"
    data = outer.get("data")
    return True, data if isinstance(data, dict) else {}, None


def _attr(text: str) -> str:
    """XML 属性值转义：escape() 不处理引号，含 " 的文本会撕开属性
    （飞书导入报 xml.SyntaxError: attribute name without =）。"""
    return escape(str(text), {'"': "&quot;", "\r": " ", "\n": " "})


def _outline(text: str, children: list[str] | None = None) -> str:
    inner = "".join(children or [])
    return f'<outline text="{_attr(text)}">{inner}</outline>' if inner \
        else f'<outline text="{_attr(text)}"/>'


def _opml_steps(steps: list[dict[str, Any]]) -> list[str]:
    """嵌套步骤树 → OPML outline 子节点（条件→操作→预期逐层展开）。"""
    out: list[str] = []
    for step in steps or []:
        if not isinstance(step, dict):
            step = {"action": str(step)}
        children = _opml_steps(step.get("children") or [])
        out.append(_outline(_step_label(step), children))
    return out


def build_tree_opml(root_text: str, tree: list[dict[str, Any]]) -> str:
    """项目用例树 → OPML（目录模式新建导图的载体，层级任意深）。

    结构：root → 分组树 → 用例（纯标题；前置条件作首个子节点）→ 步骤树。
    """
    def group_outlines(groups: list[dict[str, Any]]) -> list[str]:
        out: list[str] = []
        for group in groups or []:
            inner = group_outlines(group.get("children") or [])
            for case in group.get("cases") or []:
                details: list[str] = []
                if case.get("preconditions"):
                    details.append(_outline(f"前置: {case['preconditions']}"))
                details.extend(_opml_steps(case.get("steps") or []))
                inner.append(_outline(str(case.get("name") or "未命名用例"), details))
            out.append(_outline(str(group.get("name") or "未命名分组"), inner))
        return out

    body = _outline(root_text, group_outlines(tree))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<opml version="2.0">\n  <head><title>{_attr(root_text)}</title></head>\n'
        f"  <body>{body}</body>\n</opml>\n"
    )


async def _create_mindnote_from_template(
    root_text: str,
    tree: list[dict[str, Any]],
    folder_token: str,
    template_id: str,
) -> dict[str, Any]:
    """复制预置样式的模板思维导图 → 改根节点标题 → 逐层写入用例树。

    连线样式（直线/曲线）是飞书导图文档自身的设置，开放 API 改不了；
    预先把一张调成目标样式的「干净」导图（只留一个根节点）设为模板
    （FEISHU_TEMPLATE_MINDNOTE_ID），副本即继承样式，追加节点同样继承。
    mindnotes API 无删节点能力，模板必须是干净的，不能拿业务导图充当。
    """
    token = settings.lark_cli_identity
    ok, data, err = _unwrap(await _run_cli([
        "drive", "+copy", "--token", template_id, "--type", "mindnote",
        "--name", root_text, "--folder-token", folder_token,
        "--as", token, "--json",
    ], timeout=120.0))
    if not ok or not data.get("file_token"):
        return {"success": False, "error": err or "复制模板导图失败"}
    new_id = data["file_token"]
    copy_url = data.get("url")  # 后续 _unwrap 会覆盖 data，先存副本链接

    # 看副本现有节点，决定树怎么挂：
    # - 空模板（0 节点，连根都删了）：直接写「自带根节点」的整树
    # - 有根模板：根节点改名，用例树挂到根下（不建新根）
    ok, data, err = _unwrap(await _run_cli([
        "mindnotes", "nodes", "list", "--mindnote-id", new_id,
        "--as", token, "--json",
    ], timeout=60.0))
    if not ok:
        return {"success": False, "error": err or "读取模板副本节点失败"}
    rootless = [n for n in data.get("nodes", []) if not n.get("parent_id")]

    if not rootless:
        levels = build_tree_levels(root_text, tree)
    else:
        root_node_id = rootless[0]["node_id"]
        # 根节点标题改为需求名（同 node_id 重发 = 更新）
        rename = {"client_token": str(uuid.uuid4()),
                  "nodes": [_node(root_node_id, None, root_text)]}
        rel = _payload_relpath(f"mindnote_root_{uuid.uuid4().hex}.json")
        abs_path = Path.cwd() / rel
        try:
            abs_path.write_text(json.dumps(rename, ensure_ascii=False),
                                encoding="utf-8")
            result = await _run_cli([
                "mindnotes", "nodes", "create", "--mindnote-id", new_id,
                "--data", f"@{rel}", "--as", token, "--json",
            ], timeout=60.0)
        finally:
            abs_path.unlink(missing_ok=True)
        ok, _data, err = _unwrap(result)
        if not ok:
            return {"success": False, "error": err or "更新根节点标题失败"}
        levels = build_tree_levels("", tree, parent_id=root_node_id)

    # 逐层分批写入用例树
    written = await _create_nodes_by_level(new_id, levels)
    if not written.get("success"):
        return written
    return {
        "success": True,
        "mode": "template",
        "mindnote_id": new_id,
        "url": copy_url or f"https://leiting.feishu.cn/mindnotes/{new_id}",
        "node_count": written["node_count"],
    }


async def create_mindnote_from_tree(
    root_text: str,
    tree: list[dict[str, Any]],
    folder_token: str,
) -> dict[str, Any]:
    """Create a NEW mindnote under a Drive folder for this case tree.

    Template mode (FEISHU_TEMPLATE_MINDNOTE_ID set): copy the pre-styled
    template (straight lines etc.) and append the tree level by level.

    Fallback OPML mode: build .opml → drive +upload into the folder → raw
    import_tasks API (opml → mindnote) → poll ticket → return URL.
    Note the imported doc always gets Feishu's default (curved) theme —
    that is exactly why template mode exists.
    lark-cli requires upload/import payloads as paths relative to cwd,
    so scratch files live under workspace/.feishu_tmp.
    """
    if not lark_cli_available():
        return {"success": False, "skipped": True, "error": "lark-cli 未安装"}

    template = (settings.feishu_template_mindnote_id or "").strip()
    if template:
        return await _create_mindnote_from_template(
            root_text, tree, folder_token, template)

    tmp_dir = settings.workspace_dir / ".feishu_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    opml_path = tmp_dir / f"cases_{uuid.uuid4().hex}.opml"
    body_path = tmp_dir / f"import_{uuid.uuid4().hex}.json"
    token = settings.lark_cli_identity
    file_token: str | None = None
    try:
        opml_path.write_text(build_tree_opml(root_text, tree), encoding="utf-8")
        rel_opml = Path(os.path.relpath(opml_path, Path.cwd())).as_posix()

        # --name carries the requirement title — the imported mindnote
        # inherits the uploaded file's name (Feishu strips the extension);
        # the ".opml" suffix is required or import_tasks rejects the file
        # with "file extension not match".
        ok, data, err = _unwrap(await _run_cli([
            "drive", "+upload", "--file", rel_opml,
            "--name", f"{root_text}.opml",
            "--folder-token", folder_token,
            "--as", token, "--json",
        ], timeout=120.0))
        if not ok or not data.get("file_token"):
            return {"success": False, "error": err or "上传 .opml 失败（未返回 file_token）"}
        file_token = data["file_token"]

        body_path.write_text(json.dumps({
            "file_extension": "opml",
            "file_token": file_token,
            "point": {"mount_type": 1, "mount_key": folder_token},
            "type": "mindnote",
        }, ensure_ascii=False), encoding="utf-8")
        rel_body = Path(os.path.relpath(body_path, Path.cwd())).as_posix()

        ok, data, err = _unwrap(await _run_cli([
            "api", "POST", "/open-apis/drive/v1/import_tasks",
            "--data", f"@{rel_body}", "--as", token, "--json",
        ]))
        if not ok or not data.get("ticket"):
            return {"success": False, "error": err or "创建导入任务失败"}
        ticket = data["ticket"]

        for _ in range(_IMPORT_POLL_MAX_TRIES):
            await asyncio.sleep(_IMPORT_POLL_INTERVAL)
            ok, data, err = _unwrap(await _run_cli([
                "api", "GET", f"/open-apis/drive/v1/import_tasks/{ticket}",
                "--as", token, "--json",
            ]))
            if not ok:
                return {"success": False, "error": err or "查询导入任务失败"}
            result = data.get("result") or {}
            status = result.get("job_status")
            if status == 0:
                # Best-effort cleanup: the uploaded .opml is just an
                # import vehicle — remove it so the folder stays clean.
                if file_token:
                    await _run_cli([
                        "drive", "+delete", "--file-token", file_token,
                        "--type", "file",
                        "--as", token, "--yes", "--json",
                    ])
                return {
                    "success": True,
                    "mode": "created",
                    "mindnote_id": result.get("token"),
                    "url": result.get("url"),
                }
            if status == 2:
                return {"success": False,
                        "error": f"飞书导入失败: {result.get('job_error_msg')}"}
            # status 1 = still running → keep polling
        return {"success": False, "error": f"飞书导入超时（ticket={ticket}）"}
    finally:
        opml_path.unlink(missing_ok=True)
        body_path.unlink(missing_ok=True)


async def save_tree_to_mindnote(
    root_text: str,
    tree: list[dict[str, Any]],
    *,
    mindnote_id: str | None = None,
    parent_node_id: str | None = None,
) -> dict[str, Any]:
    """Push a project case TREE into a Feishu mindnote（树形导出唯一入口）.

    Mode resolution: explicit mindnote_id → append into that mindnote;
    else feishu_folder_token → create a NEW mindnote in that folder
    (one document per requirement); else feishu_mindnote_id → append.
    """
    folder = (settings.feishu_folder_token or "").strip()
    if not mindnote_id and folder:
        # Folder mode wins over the fixed mindnote: one fresh document
        # per requirement is the intended workflow.
        return await create_mindnote_from_tree(root_text, tree, folder)

    target = mindnote_id or settings.feishu_mindnote_id
    if not target:
        return {"success": False, "skipped": True,
                "error": "未配置飞书目录或思维导图 ID（设置页 FEISHU_FOLDER_TOKEN / FEISHU_MINDNOTE_ID）"}
    if not lark_cli_available():
        return {"success": False, "skipped": True, "error": "lark-cli 未安装"}

    # 追加模式：整树（含新根）挂到 parent_node_id / 固定导图下。
    # 必须按层级分批写入——同批内引用同批新建节点作父级会被飞书拒绝。
    levels = build_tree_levels(
        root_text, tree,
        parent_id=parent_node_id or settings.feishu_mindnote_parent_node or None,
    )
    return await _create_nodes_by_level(target, levels) | {
        "mindnote_id": target,
    }


async def list_mindnote_nodes(mindnote_id: str | None = None) -> dict[str, Any]:
    """List existing nodes of a mindnote (for picking parent nodes)."""
    target = mindnote_id or settings.feishu_mindnote_id
    if not target:
        return {"success": False, "skipped": True, "error": "未配置飞书思维导图 ID"}
    if not lark_cli_available():
        return {"success": False, "skipped": True, "error": "lark-cli 未安装"}
    result = await _run_cli([
        "mindnotes", "nodes", "list", "--mindnote-id", target,
        "--as", settings.lark_cli_identity, "--json",
    ], timeout=120.0)
    if not result.get("success"):
        return {"success": False, "error": result.get("error")}
    data = result.get("data")
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    return {"success": True, "nodes": nodes, "count": len(nodes)}
