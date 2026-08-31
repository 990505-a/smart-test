"""Case documents stored as plain Markdown files (用例 MD 文档存储).

2026-08 重构：用例不再入关系库（test_cases/test_steps/case_groups 五张表
已删），一个项目 = 一份 MD 文件，存于 ``workspace/default/cases/``，
作为唯一事实源贯穿全生命周期：

- 智能体生成后经 ``save_case_document`` 工具落盘
- 用户在 /cases 页（或任意编辑器）直接在源文件上标注（✅/❌/⚠️ + `>` 批注）
- 自进化按文件内容 hash 增量读取标注原文喂给 LLM 反思
- 飞书导出：MD 解析成树（剥离标注）→ 现有 mindnote 链路

MD 格式约定（标题层级 = 导图节点层级）::

    # 文档标题（根节点）
    ## 分组（任意层级嵌套）
    #### 用例标题 [P1] ✅          # [Px] 优先级；✅/❌/⚠️ 为人工标注，导出时剥离
    前置：前置条件
    - 操作 ⇒ 预期结果              # 步骤；2 空格缩进一级，支持嵌套子步骤
      - 子条件 ⇒ 子预期 √          # 叶子可带执行标记 √ / X
    > 人工批注（好/不好/漏测原因）   # 引用块 = 批注，导出时剥离

判定规则：标题节点下有步骤列表或「前置」行 → 用例；否则 → 分组。
带子标题的节点一律视为分组（用例的步骤必须是列表，不能是子标题）。
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from src.app.core.workspace import get_workspace_dir

# ---------------------------------------------------------------------------
# 文件布局
# ---------------------------------------------------------------------------

_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def cases_dir() -> Path:
    """用例 MD 文档目录（固定 default 工作区，与 /cases 页、自进化共用）。"""
    d = get_workspace_dir("default") / "cases"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sanitize_name(name: str) -> str:
    """项目名 → 安全文件名主干（Windows 非法字符过滤）。"""
    cleaned = _ILLEGAL.sub("_", str(name)).strip().strip(". ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        raise ValueError("项目名不能为空")
    if cleaned.split(".")[0].upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:120]


def doc_path(name: str) -> Path:
    """项目名 → MD 文件路径；拒绝越出 cases 目录的名字。"""
    stem = sanitize_name(name)
    path = (cases_dir() / f"{stem}.md").resolve()
    if path.parent != cases_dir().resolve():
        raise ValueError(f"非法项目名: {name}")
    return path


# ---------------------------------------------------------------------------
# MD 解析：文档 → 分组树（与飞书导图同构，标注已剥离）
# ---------------------------------------------------------------------------

# 人工标注符号：打分 ✅（好）❎ ✅ 变体；❌（坏）；⚠️（漏测/警告）
_GOOD_MARKS = "✅❎"
_BAD_MARKS = "❌"
_WARN_MARKS = "⚠️⚠"
_ANNOTATION_RE = re.compile(f"[{re.escape(_GOOD_MARKS + _BAD_MARKS + _WARN_MARKS)}]+\\s*$")

_PRIORITY_RE = re.compile(r"\[(P[0-3])\]")
_PRIORITY_MAP = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_RE = re.compile(r"^(\s*)[-*+]\s+(.+?)\s*$")
_PRECOND_RE = re.compile(r"^前置\s*[：:]\s*(.+)$")
# Steps use an arrow to separate the QA action from its observable result.
_STEP_SEP_RE = re.compile(r"\s*(?:⇒|=>|→|->)\s*")
_STEP_MARK_RE = re.compile(r"\s+([√Xx])$")

# Hidden, machine-readable traceability metadata.  It deliberately stays out
# of headings and list items so the existing Feishu tree remains unchanged.
_METADATA_COMMENT_RE = re.compile(r"^\s*<!--(?P<body>.*?)-->\s*$")
_METADATA_ID_RE = re.compile(r"^(?:CASE|REQ|RISK)-[A-Z0-9]+(?:-[A-Z0-9]+)+$")
_METADATA_KEYS = ("CASE", "REQ", "RISK")
_PLACEHOLDER_RE = re.compile(r"(?:TODO|待补充|待确认|正常处理|适当提示|按实际情况|参见)", re.IGNORECASE)


def _clean_title(raw: str) -> tuple[str, str | None, str | None, bool]:
    """标题原文 → (纯标题, 优先级, 标注符号, 是否标注)。

    顺序：先取 [Px]，再剥尾部标注符号，剩余即纯业务标题。
    """
    title = raw.strip()
    priority: str | None = None
    m = _PRIORITY_RE.search(title)
    if m:
        priority = _PRIORITY_MAP[m.group(1).upper()]
        title = title.replace(m.group(0), "").strip()
    ann = _ANNOTATION_RE.search(title)
    marked = ann is not None
    if marked:
        title = title[:ann.start()].strip()
    return title, priority, (ann.group(0).strip() if ann else None), marked


def _parse_metadata_comment(line: str) -> dict[str, list[str]] | None:
    """Parse one valid traceability comment, returning normalized values."""
    match = _METADATA_COMMENT_RE.match(line)
    if not match:
        return None
    body = match.group("body").strip()
    if not body:
        return None
    result: dict[str, list[str]] = {}
    parts = [part.strip() for part in body.split(";") if part.strip()]
    if not parts:
        return None
    for part in parts:
        field = re.fullmatch(r"([A-Z]+)\s*:\s*(.*?)", part)
        if not field or field.group(1) not in _METADATA_KEYS:
            return None
        key = field.group(1)
        values = [value.strip() for value in field.group(2).split(",")]
        if not values or any(not value for value in values):
            return None
        if key in result:
            return None
        result[key] = values
    return result


def _metadata_for_body(body: list[str]) -> dict[str, list[str]] | None:
    """Return the first valid metadata comment in a heading's body."""
    for line in body:
        parsed = _parse_metadata_comment(line)
        if parsed is not None:
            return parsed
    return None


def _metadata_dict_to_public(metadata: dict[str, list[str]] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {
        "case_id": metadata.get("CASE", [None])[0],
        "requirements": metadata.get("REQ", []),
        "risks": metadata.get("RISK", []),
    }


def _parse_steps(lines: list[str]) -> list[dict[str, Any]]:
    """缩进列表 → 嵌套步骤树（2 空格一级，tab 按 2 计）。"""
    roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []  # (depth, node)
    for line in lines:
        m = _LIST_RE.match(line)
        if not m:
            continue
        indent, text = m.group(1).replace("\t", "  "), m.group(2)
        depth = len(indent) // 2

        mark = None
        km = _STEP_MARK_RE.search(text)
        if km:
            mark = "√" if km.group(1) == "√" else "X"
            text = text[:km.start()].strip()

        sep = _STEP_SEP_RE.search(text)
        if sep:
            action, expected = text[:sep.start()], text[sep.end():]
        else:
            action, expected = text, None
        node: dict[str, Any] = {
            "action": action.strip(),
            "expected": expected.strip() if expected else None,
        }
        if mark:
            node["mark"] = mark

        while stack and stack[-1][0] >= depth:
            stack.pop()
        if stack:
            stack[-1][1].setdefault("children", []).append(node)
        else:
            roots.append(node)
        stack.append((depth, node))
    return roots


def parse_cases_md(content: str) -> dict[str, Any]:
    """整份 MD → {title, tree, case_count, good, bad, warn, annotated}。

    两遍式：先按标题层级建原始树（收集正文/标注），再归类——有子标题
    → 分组；无子标题但有步骤或前置 → 用例；叶子空节点 → 空分组。
    tree 结构与原 save_cases_tree 同构：[{name, children, cases:[...]}]，
    供飞书导出（build_tree_nodes / build_tree_opml）直接消费；标注
    （标题 ✅❌⚠️ 与 `>` 批注行）在解析时剥离，不进导图。
    """
    good = bad = warn = 0
    has_notes = False

    # --- 第一遍：标题树 ---
    raw_roots: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    title: str | None = None

    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        hm = _HEADING_RE.match(line)
        if not hm:
            if line.lstrip().startswith(">"):
                has_notes = True
            continue

        level_n = len(hm.group(1))
        name, priority, ann, marked = _clean_title(hm.group(2))
        if marked and ann:
            for ch in ann:
                if ch in _GOOD_MARKS:
                    good += 1
                elif ch in _BAD_MARKS:
                    bad += 1
                elif ch != "️":  # 跳过 emoji 变体选择符 U+FE0F
                    warn += 1

        # 直属正文 = 到下一个标题行为止；其间引用块是批注
        body: list[str] = []
        while i < len(lines) and not _HEADING_RE.match(lines[i]):
            if lines[i].lstrip().startswith(">"):
                has_notes = True
            else:
                body.append(lines[i])
            i += 1

        precond = None
        for bl in body:
            pm = _PRECOND_RE.match(bl.strip())
            if pm:
                precond = pm.group(1).strip()
                break

        metadata = _metadata_for_body(body)
        node: dict[str, Any] = {
            "level": level_n,
            "name": name or "未命名节点",
            "priority": priority,
            "precond": precond,
            "steps": _parse_steps(body),
            "children": [],
        }
        if metadata is not None:
            node["metadata"] = _metadata_dict_to_public(metadata)
        while stack and stack[-1][0] >= level_n:
            stack.pop()
        if stack:
            stack[-1][1]["children"].append(node)
        else:
            raw_roots.append(node)
        stack.append((level_n, node))

    # --- 第二遍：归类为 分组/用例 ---
    def convert(nodes: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
        """[(groups, cases)]：同级原始节点 → 分组树 + 用例列表。"""
        groups: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        for node in nodes:
            if node["children"]:
                sub_groups, sub_cases = convert(node["children"])
                groups.append({"name": node["name"], "children": sub_groups,
                               "cases": sub_cases})
            elif node["steps"] or node["precond"]:
                cases.append({
                    "name": node["name"],
                    "priority": node["priority"] or "medium",
                    "preconditions": node["precond"],
                    "steps": node["steps"],
                    **({"metadata": node["metadata"]} if node.get("metadata") else {}),
                })
            else:
                groups.append({"name": node["name"], "children": [], "cases": []})
        return groups, cases

    # 顶层直接挂用例（无分组层）时兜底进「未分组」，不丢数据
    def convert_top(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups, cases = convert(nodes)
        if cases:
            groups.append({"name": "未分组", "children": [], "cases": cases})
        return groups

    # 唯一的顶层 H1 作为文档标题（导图根），其子树为顶层分组
    if len(raw_roots) == 1 and raw_roots[0]["level"] == 1:
        title = title or raw_roots[0]["name"]
        tree = convert_top(raw_roots[0]["children"])
        # H1 自带正文的极端情况：步骤丢弃，仅作标题
    else:
        tree = convert_top(raw_roots)

    def count_cases(nodes: list[dict[str, Any]]) -> int:
        return sum(len(n.get("cases") or []) + count_cases(n.get("children") or [])
                   for n in nodes)

    return {
        "title": title or "",
        "tree": tree,
        "case_count": count_cases(tree),
        "good": good,
        "bad": bad,
        "warn": warn,
        "annotated": bool(good or bad or warn or has_notes),
    }


# ---------------------------------------------------------------------------
# Deterministic quality checks
# ---------------------------------------------------------------------------


def _heading_blocks(content: str) -> list[dict[str, Any]]:
    """Collect heading bodies and parent relationships without changing parsing."""
    lines = content.splitlines()
    blocks: list[dict[str, Any]] = []
    stack: list[int] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        name, priority, annotation, marked = _clean_title(match.group(2))
        while stack and blocks[stack[-1]]["level"] >= level:
            stack.pop()
        block = {
            "line": index + 1,
            "end_line": len(lines) + 1,
            "level": level,
            "name": name,
            "priority": priority,
            "parent": stack[-1] if stack else None,
            "children": [],
            "body": [],
            "metadata": [],
            "annotation": annotation,
            "marked": marked,
        }
        blocks.append(block)
        block_index = len(blocks) - 1
        if stack:
            blocks[stack[-1]]["children"].append(block_index)
        stack.append(block_index)

    for position, block in enumerate(blocks):
        end = blocks[position + 1]["line"] - 1 if position + 1 < len(blocks) else len(lines)
        block["end_line"] = end
        block["body"] = lines[block["line"]:end]
    return blocks


def _is_metadata_candidate(line: str) -> bool:
    """Whether a line looks like it intends to carry workflow metadata."""
    return "<!--" in line and any(key in line.upper() for key in ("CASE", "REQ", "RISK"))


def _package_ids(workflow_meta: dict[str, Any] | None, key: str) -> set[str]:
    if not workflow_meta:
        return set()
    values = workflow_meta.get(key, workflow_meta.get(key.lower(), []))
    if isinstance(values, dict):
        values = values.get(key.lower() + "s", values.get(key, []))
    if not isinstance(values, list):
        return set()
    result: set[str] = set()
    for item in values:
        if isinstance(item, str):
            result.add(item)
        elif isinstance(item, dict):
            value = item.get("id") or item.get(f"{key.lower()}_id")
            if value:
                result.add(str(value))
    return result


def lint_case_document(
    content: str,
    workflow_meta: dict[str, Any] | None = None,
    *,
    strict: bool | None = None,
) -> dict[str, Any]:
    """Run deterministic checks without modifying or calling an LLM.

    Legacy Markdown remains readable and writable: by default missing
    traceability metadata and arrow-less historical steps are warnings.  A
    workflow package can pass ``strict=True`` to turn those quality gaps into
    release-blocking errors.
    """
    if not isinstance(content, str):
        return {
            "ok": False,
            "errors": [{"code": "CONTENT_NOT_TEXT", "line": 1,
                         "severity": "error", "message": "用例文档必须是文本"}],
            "warnings": [],
            "stats": {"case_count": 0},
            "content_hash": "",
        }

    strict_mode = bool(workflow_meta.get("strict", False)) if strict is None and workflow_meta else bool(strict)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add(target: list[dict[str, Any]], code: str, line: int, message: str) -> None:
        target.append({"code": code, "line": max(1, line),
                       "severity": "error" if target is errors else "warning",
                       "message": message})

    lines = content.splitlines()
    blocks = _heading_blocks(content)
    roots = [i for i, block in enumerate(blocks) if block["parent"] is None]
    h1_count = sum(1 for block in blocks if block["level"] == 1)
    if h1_count != 1:
        add(errors, "DOCUMENT_ROOT_INVALID", 1,
            "文档必须且只能有一个 H1 根标题")
    if any(len(re.match(r"^(#+)", line).group(1)) > 6
           for line in lines if re.match(r"^#+", line)):
        add(errors, "HEADING_LEVEL_INVALID", 1, "标题层级不能超过 H6")
    previous_level = 0
    for block in blocks:
        if previous_level and block["level"] > previous_level + 1:
            add(warnings, "HEADING_LEVEL_JUMP", block["line"],
                "标题层级存在跳级，建议补齐中间分组层级")
        previous_level = block["level"]
        if not block["name"]:
            add(errors, "EMPTY_HEADING", block["line"], "标题不能为空")

    # Locate comments while respecting fenced code blocks.  Comments in a
    # fenced example must not become real traceability metadata.
    fenced = False
    comment_lines: set[int] = set()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if _is_metadata_candidate(line):
            comment_lines.add(number)
            if not stripped.startswith("<!--") or not stripped.endswith("-->"):
                add(errors, "METADATA_MUST_BE_STANDALONE", number,
                    "CASE/REQ/RISK 元数据必须是独立的一行 HTML 注释")
            if re.match(r"^#{1,6}\s", stripped):
                add(errors, "METADATA_ON_HEADING", number,
                    "元数据不能与标题写在同一行")
            if _LIST_RE.match(line):
                add(errors, "METADATA_IN_LIST", number,
                    "元数据不能写在步骤列表中")

    case_ids: set[str] = set()
    case_names: dict[str, int] = {}
    referenced_requirements: set[str] = set()
    referenced_risks: set[str] = set()
    recognized_cases = 0
    metadata_count = 0

    for block in blocks:
        body = block["body"]
        metadata: list[dict[str, list[str]]] = []
        for offset, line in enumerate(body):
            line_number = block["line"] + offset + 1
            parsed = _parse_metadata_comment(line) if line_number in comment_lines else None
            if parsed is not None:
                metadata.append(parsed)
                metadata_count += 1
            elif line_number in comment_lines:
                add(errors, "METADATA_SYNTAX_INVALID", line_number,
                    "元数据必须使用 CASE/REQ/RISK: ID; 格式")
        block["metadata"] = metadata
        is_case = bool(block["children"] == [] and (
            _parse_steps(body) or any(_PRECOND_RE.match(item.strip()) for item in body)
        ))
        if not is_case:
            if metadata:
                add(errors, "METADATA_NOT_ON_CASE", block["line"],
                    "CASE 元数据只能挂在可识别的用例节点上")
            continue
        recognized_cases += 1
        name = block["name"] or "未命名节点"
        if name in case_names:
            add(warnings, "DUPLICATE_CASE_TITLE", block["line"],
                f"用例标题重复：{name}")
        case_names[name] = block["line"]
        if not block["priority"]:
            add(warnings, "PRIORITY_MISSING", block["line"],
                "用例未声明 [P0] 至 [P3] 优先级")

        if len(metadata) == 0:
            add(errors if strict_mode else warnings, "CASE_METADATA_MISSING", block["line"],
                "用例缺少 CASE/REQ/RISK 元数据")
        elif len(metadata) > 1:
            add(errors, "MULTIPLE_METADATA_COMMENTS", block["line"],
                "同一个用例只能有一条元数据注释")
        if metadata:
            data = metadata[0]
            if "CASE" not in data or len(data["CASE"]) != 1:
                add(errors, "CASE_ID_REQUIRED", block["line"],
                    "每个用例必须有且只有一个 CASE ID")
            if "REQ" not in data or not data["REQ"]:
                add(errors, "REQUIREMENT_ID_REQUIRED", block["line"],
                    "每个用例至少关联一个 REQ ID")
            if "RISK" not in data or not data["RISK"]:
                add(errors, "RISK_ID_REQUIRED", block["line"],
                    "每个用例至少关联一个 RISK ID")
            for key, values in data.items():
                if key not in _METADATA_KEYS:
                    add(errors, "METADATA_KEY_INVALID", block["line"],
                        f"不支持的元数据字段：{key}")
                if len(values) != len(set(values)):
                    add(errors, "METADATA_VALUE_DUPLICATE", block["line"],
                        f"{key} 元数据不能重复")
                for value in values:
                    if not _METADATA_ID_RE.fullmatch(value):
                        add(errors, "METADATA_ID_INVALID", block["line"],
                            f"非法 {key} ID：{value}")
                    if key == "CASE":
                        if value in case_ids:
                            add(errors, "CASE_ID_DUPLICATE", block["line"],
                                f"CASE ID 重复：{value}")
                        case_ids.add(value)
                    elif key == "REQ":
                        referenced_requirements.add(value)
                    elif key == "RISK":
                        referenced_risks.add(value)

        steps = _parse_steps(body)
        if not steps and not any(_PRECOND_RE.match(item.strip()) for item in body):
            add(errors, "CASE_CONTENT_MISSING", block["line"],
                "用例必须包含前置条件或步骤")

        def inspect_steps(items: list[dict[str, Any]]) -> None:
            for step in items:
                expected = step.get("expected")
                if not expected:
                    add(errors if strict_mode else warnings, "STEP_EXPECTED_MISSING",
                        block["line"], "步骤缺少可观察的预期结果")
                if _PLACEHOLDER_RE.search(step.get("action", "")) or _PLACEHOLDER_RE.search(expected or ""):
                    add(warnings, "VAGUE_STEP_TEXT", block["line"],
                        "步骤包含待补充或模糊占位描述")
                inspect_steps(step.get("children", []))
        inspect_steps(steps)

    if recognized_cases == 0:
        add(errors, "NO_CASES", 1, "文档中没有可识别的有效用例")

    package_requirement_ids = _package_ids(workflow_meta, "requirements")
    package_risk_ids = _package_ids(workflow_meta, "risks")
    if strict_mode and package_requirement_ids:
        for missing in sorted(package_requirement_ids - referenced_requirements):
            add(errors, "REQUIREMENT_NOT_COVERED", 1,
                f"需求未被任何用例覆盖：{missing}")
    if strict_mode and package_risk_ids:
        for missing in sorted(package_risk_ids - referenced_risks):
            add(errors, "RISK_NOT_COVERED", 1,
                f"风险未被任何用例覆盖：{missing}")

    parsed = parse_cases_md(content)
    stats = {
        "case_count": parsed["case_count"],
        "recognized_cases": recognized_cases,
        "metadata_count": metadata_count,
        "requirements_covered": len(referenced_requirements),
        "risks_covered": len(referenced_risks),
    }
    return {
        "ok": not errors,
        "errors": errors[:200],
        "warnings": warnings[:200],
        "stats": stats,
        "content_hash": digest,
    }


# ---------------------------------------------------------------------------
# 文档 CRUD（/cases 页与智能体工具共用）
# ---------------------------------------------------------------------------


def list_docs() -> list[dict[str, Any]]:
    """列出全部用例文档（含解析统计与工作流状态）。"""
    from src.app.services import case_workflow_service

    out: list[dict[str, Any]] = []
    for path in sorted(cases_dir().glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = parse_cases_md(content)
        st = path.stat()
        try:
            metadata = case_workflow_service.load_metadata(path.stem)
        except case_workflow_service.WorkflowError:
            metadata = case_workflow_service._default_metadata(path.stem)
        out.append({
            "name": path.stem,
            "title": parsed["title"] or path.stem,
            "size": st.st_size,
            "updated_at": st.st_mtime,
            "case_count": parsed["case_count"],
            "good": parsed["good"],
            "bad": parsed["bad"],
            "warn": parsed["warn"],
            "annotated": parsed["annotated"],
            "revision": metadata["revision"],
            "content_hash": metadata["content_hash"] or case_workflow_service.content_hash(content),
            "lifecycle_status": metadata["lifecycle_status"],
            "lint_status": metadata["lint_status"],
            "review_status": metadata["review_status"],
            "lint_report": case_workflow_service.public_metadata(metadata).get("lint_report"),
            "review_report": case_workflow_service.public_metadata(metadata).get("review_report"),
        })
    return out


def read_doc(name: str) -> dict[str, Any] | None:
    """读取一份用例文档；不存在返回 None。"""
    from src.app.services import case_workflow_service

    path = doc_path(name)
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    try:
        metadata = case_workflow_service.load_metadata(path.stem)
    except case_workflow_service.WorkflowError:
        metadata = case_workflow_service._default_metadata(path.stem)
    metadata = case_workflow_service.public_metadata(metadata)
    # Legacy files have no sidecar; expose their digest without pretending
    # they passed the new workflow gates.
    if not metadata["content_hash"]:
        metadata["content_hash"] = case_workflow_service.content_hash(content)
    return {
        "name": path.stem,
        "content": content,
        "updated_at": path.stat().st_mtime,
        **metadata,
    }


def _atomic_write_text(path: Path, content: str) -> None:
    """Write a document through a temporary file and atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def save_doc(
    name: str,
    content: str,
    *,
    expected_revision: int | None = None,
    expected_hash: str | None = None,
) -> dict[str, Any]:
    """写入（新建/覆盖）一份文档并记录为可审计草稿。"""
    from src.app.services import case_workflow_service

    path = doc_path(name)
    current = case_workflow_service.load_metadata(path.stem)
    actual_hash = ""
    if expected_hash is not None and not current.get("content_hash") and path.exists():
        try:
            actual_hash = case_workflow_service.content_hash(path.read_text(encoding="utf-8"))
        except OSError:
            actual_hash = ""
    case_workflow_service._check_expected(
        current, expected_revision, expected_hash, actual_hash
    )
    _atomic_write_text(path, content)
    metadata = case_workflow_service.record_content_save(
        path.stem,
        content,
        expected_revision=expected_revision,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
    )
    parsed = parse_cases_md(content)
    # Run strict lint for workflow documents and compatibility lint for legacy
    # documents.  Saving remains allowed, but the stored gate must never be
    # downgraded by a normal editor save.
    strict_mode = bool(current.get("package_strict", False))
    report = lint_case_document(content, current, strict=strict_mode)
    metadata = case_workflow_service.record_lint(
        path.stem, report, strict=strict_mode
    )
    public = case_workflow_service.public_metadata(metadata)
    return {
        "name": path.stem,
        "path": str(path),
        **parsed,
        "revision": public["revision"],
        "content_hash": public["content_hash"],
        "lifecycle_status": public["lifecycle_status"],
        "lint_status": public["lint_status"],
        "review_status": public["review_status"],
        "lint_report": public["lint_report"],
        "review_report": public["review_report"],
    }


def delete_doc(name: str) -> bool:
    """删除用例文档及其工作流 sidecar；返回是否确实删除了文件。"""
    from src.app.services import case_workflow_service

    path = doc_path(name)
    if path.exists():
        path.unlink()
        case_workflow_service.remove_metadata(path.stem)
        return True
    return False
