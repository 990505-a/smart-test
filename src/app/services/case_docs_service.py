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

from src.app.core.config import settings
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

# 附录标题：`附录…` / `附注…` / `Appendix…`。**这不是节点，是正文段。**
#
# 为什么必须专门识别：格式契约里标题只有两种含义——`#` 根标题、`##`+ 分组、
# 叶子标题 = 用例，**没有"不是用例的正文段"这个位置**。而写覆盖对照表是完全正当
# 的需求。当 agent 写成 `## 附录：覆盖对照` 时，它是个"无子标题、body 里只有项目
# 符号"的叶子，于是被判成一条缺元数据的用例：
#
#     CASE_METADATA_MISSING   line 178  用例缺少 CASE/REQ/RISK 元数据
#     STEP_EXPECTED_MISSING   line 178  步骤缺少可观察的预期结果
#
# 而它**怎么写都修不掉**：格式里没有附录这种东西，写不写元数据都错。实测 agent
# 为此反复重写全文约 20 分钟（一度误判成"传输层损坏"），最后自己猜到"只能不用
# 标题"——把 `##` 换成 `---` + 粗体。那条路能过，但不该靠猜。
#
# 现在附录连同其子树一起整段跳过：不建节点、不进导图、不参与 lint。
_APPENDIX_RE = re.compile(r"^(?:附录|附注|appendix)", re.IGNORECASE)


def _is_appendix_title(name: str, level: int) -> bool:
    """标题是否表示「这是附录正文，不是分组/用例」。

    ``level`` 必须 >= 2：``#`` 是**文档根标题**（格式契约里"/" 根标题 → "##"+ 分组），
    根标题以"附录"开头只是文档碰巧这么叫，不是附录段。实测踩过：一篇标题为
    「# 附录回归验证」的文档，被按附录整篇置空，``case_count`` 变成 0、lint 全红。
    """
    return level >= 2 and bool(name) and _APPENDIX_RE.match(name.strip()) is not None


def _strip_appendix_regions(lines: list[str]) -> list[str]:
    """把附录区块整段置空后返回（行号保持不变）。

    为什么是"置空"而不是"跳过"或"删行"：

    * **必须是置空而不能只跳过块**——块的 body 是从自己到下一个块之间的原文，跳过
      附录块会让**前一个真用例的 body 一直延伸到文件末尾**，把附录里的项目符号当成
      没有 `⇒` 的步骤，于是报出一条指向用例行的 ``STEP_EXPECTED_MISSING``（实测复现）。
    * **必须保留行号**——lint 报错和人工定位都以行号为锚，删行会让后面所有报错错位。

    置空之后，附录的标题、项目符号都不再参与用例识别，而 `parse_cases_md` 与
    `lint_case_document` 共用这一个入口，两边行为自然一致。
    """
    out = list(lines)
    skip_below: int | None = None
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match is None:
            if skip_below is not None:
                out[index] = ""
            continue
        level = len(match.group(1))
        if skip_below is not None and level <= skip_below:
            skip_below = None  # 回到同级或更浅：附录结束
        if skip_below is None:
            name, _priority, _annotation, _marked = _clean_title(match.group(2))
            if _is_appendix_title(name, level):
                skip_below = level
        if skip_below is not None:
            out[index] = ""
    return out


# Steps use an arrow to separate the QA action from its observable result.
_STEP_SEP_RE = re.compile(r"\s*(?:⇒|=>|→|->)\s*")
_STEP_MARK_RE = re.compile(r"\s+([√Xx])$")

# Hidden, machine-readable traceability metadata.  It deliberately stays out
# of headings and list items so the existing Feishu tree remains unchanged.
_METADATA_COMMENT_RE = re.compile(r"^\s*<!--(?P<body>.*?)-->\s*$")
# 元数据里的 ID 形状：字母开头、至少一段连字符、全大写字母数字（如 REQ-AUTH-001、EDGE-011）。
# 这里**不硬编码前缀**——编号空间由用户的需求文档定义，不是平台规定的。过去只认
# CASE|REQ|RISK，生成侧为了让文档里的 EDGE-011 过校验，只能改写成 REQ-EDGE-011，
# 结果用例文档的编号和「唯一事实源」对不上，追溯链自己断了。
_METADATA_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
_METADATA_KEYS = ("CASE", "REQ", "RISK")
_PLACEHOLDER_RE = re.compile(r"(?:TODO|待补充|待确认|正常处理|适当提示|按实际情况|参见)", re.IGNORECASE)

# 规范性语句粗筛（第一层规则，不靠模型）：命中这些词就当作"硬性规定"候选。
# 这是反向覆盖的分母来源——只靠正向覆盖（包里的需求→用例）永远发现不了"整条被漏掉"。
_NORMATIVE_RE = re.compile(
    r"(必须|应当|不得|不允许|禁止|仅允许|不超过|至少|最多|唯一|不能|必填|限定|只能)"
)

# 断言里的「数值 + 量词」。只有紧挨着量词的数字才算"对着规格做断言"，
# 这样能自然排除 2026-09-17 这类日期、CASE-RY-037 这类编号。
_NUMERIC_ASSERT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(位|条|个|次|秒|分钟|小时|天|元|%|字节|KB|MB|GB|页|项|档|级)"
)

# HTTP 状态码等通用语义数字，不参与"是否出自需求文档"的核对
_NUMERIC_STOPWORDS = {"200", "201", "204", "400", "401", "403", "404", "409", "500", "502", "503"}

# 文档自我说明不属于"产品规定"，不该进反向覆盖的分母（否则每份文档都会
# 因为前言里的一句"本文件是唯一事实源"而虚低召回率）
_NORMATIVE_SKIP_RE = re.compile(r"(唯一事实源|本文件是|本文档|用例应逐条追溯|需求变更记录|修订记录)")


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

    lines = _strip_appendix_regions(content.splitlines())
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
    """Collect heading bodies and parent relationships without changing parsing.

    入口统一把附录区块置空（``_strip_appendix_regions``）：附录是正文段，不参与
    用例识别，所以也不该被 lint 检查——否则覆盖对照表必然报 CASE_METADATA_MISSING。
    """
    lines = _strip_appendix_regions(content.splitlines())
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


def _normalize_for_match(text: str) -> str:
    """核对引文时忽略空白差异：文档里的换行/缩进不该影响"是否同一句话"。"""
    return re.sub(r"\s+", "", text or "")


def _package_items(workflow_meta: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    """取出需求包里的原始条目（需要读 id 之外的字段时用，如 source_quote）。"""
    if not workflow_meta:
        return []
    values = workflow_meta.get(key, workflow_meta.get(key.lower(), []))
    if isinstance(values, dict):
        values = values.get(key.lower() + "s", values.get(key, []))
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def _requirement_quotes(item: dict[str, Any]) -> list[str]:
    """取出一条需求的全部引文：source_quote（单条）与 source_quotes（多条）都支持。"""
    quotes: list[str] = []
    single = str(item.get("source_quote") or "").strip()
    if single:
        quotes.append(single)
    many = item.get("source_quotes")
    if isinstance(many, list):
        quotes.extend(str(q).strip() for q in many if str(q or "").strip())
    # 去重但保持顺序
    seen: set[str] = set()
    result: list[str] = []
    for quote in quotes:
        if quote not in seen:
            seen.add(quote)
            result.append(quote)
    return result


def _normative_sentences(text: str) -> list[str]:
    """从需求文档里抽出规范性语句（粗筛，宁多勿漏）。

    按句号/分号切分，去掉 markdown 的列表符与表格管道；过短片段丢掉，
    避免把标题和表格边框当成规定条款。
    """
    found: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for seg in re.split(r"[。；;]", line):
            seg = seg.strip(" \t-|*>·")
            if len(seg) >= 6 and _NORMATIVE_RE.search(seg) and not _NORMATIVE_SKIP_RE.search(seg):
                found.append(seg)
    return found


def _quote_covers(quote: str, sentence: str) -> bool:
    """引文是否覆盖到这句话：任一方向包含即算命中（一对一是常见形态）。"""
    q = _normalize_for_match(quote)
    s = _normalize_for_match(sentence)
    if not q or not s:
        return False
    return q in s or s in q


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _load_source_text(workflow_meta: dict[str, Any] | None) -> str:
    """把 source_manifest 指向的需求文档正文读进来，用于核对编号是否真实存在。

    编号空间由需求文档定义，所以「这个 REQ 编号是否真的写在事实源里」只能靠原文核对。
    条目可能是「会话消息（无文件）」这类非文件来源，跳过；文件缺失或过大也跳过——
    读不到就整体跳过这项检查，并在 stats 里标出来，绝不假装检查过了。
    """
    manifest = (workflow_meta or {}).get("source_manifest") or []
    chunks: list[str] = []
    for item in manifest:
        raw = item.get("path") if isinstance(item, dict) else item
        if not isinstance(raw, str) or not raw.strip():
            continue
        path = Path(raw)
        try:
            if not path.is_file() or path.stat().st_size > 2_000_000:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks)


def validate_requirement_package(package: dict[str, Any]) -> dict[str, Any]:
    """在**写用例之前**校验需求包。

    为什么必须提前：引文不是原文子串、编号是编的、规范性语句没被覆盖——这三类问题
    都在 lint 里报，而 lint 是在**整篇用例写完**之后才跑的。在保存需求包时就报出来，
    智能体当场就能改，不用白写一遍。

    返回结构刻意做成"可直接照做"：哪些编号缺引文、哪条引文对不上、召回率多少、
    以及一句下一步该干什么。
    """
    source_text = _load_source_text(
        {"source_manifest": package.get("source_manifest") or []}
    )
    requirements = [r for r in (package.get("requirements") or []) if isinstance(r, dict)]
    result: dict[str, Any] = {
        "source_checked": bool(source_text),
        "requirements_total": len(requirements),
    }
    if not source_text:
        result["hint"] = (
            "读不到需求文档正文（source_manifest 里的路径不存在或不可读），引文与编号无法核对。"
            "请把 source_manifest 指到真实存在的文件上。"
        )
        return result

    normalized_source = _normalize_for_match(source_text)
    quote_missing: list[str] = []
    quote_not_found: list[dict[str, str]] = []
    for item in requirements:
        req_id = str(item.get("id") or "<无编号>")
        quotes = _requirement_quotes(item)
        if not quotes:
            quote_missing.append(req_id)
            continue
        bad = [q for q in quotes if _normalize_for_match(q) not in normalized_source]
        if bad:
            quote_not_found.append({"id": req_id, "quote": bad[0][:60]})

    ids_not_in_source = [
        str(item["id"]) for item in requirements
        if item.get("id") and str(item["id"]) not in source_text
    ]

    normative = _normative_sentences(source_text)
    all_quotes = [q for item in requirements for q in _requirement_quotes(item)]
    uncovered = [s for s in normative if not any(_quote_covers(q, s) for q in all_quotes)]
    recall = (len(normative) - len(uncovered)) / len(normative) if normative else None

    result.update({
        "quote_missing": quote_missing,
        "quote_not_found": quote_not_found,
        "requirement_id_not_in_source": ids_not_in_source,
        "normative_total": len(normative),
        "normative_uncovered": len(uncovered),
        "normative_recall": round(recall, 4) if recall is not None else None,
        "uncovered_samples": uncovered[:5],
        "ready": not (quote_missing or quote_not_found or ids_not_in_source),
    })
    if quote_missing or quote_not_found:
        result["hint"] = (
            "先把 source_quote 修成需求文档里的原句（逐字复制，别改写、别去掉 ** 标记），"
            "再开始写用例——引文对不上的需求，它下面的用例也过不了 lint。"
        )
    elif ids_not_in_source:
        result["hint"] = (
            "有编号在需求文档里搜不到：编号要沿用文档原文的写法，不要自己发明；"
            "确有新增请先把需求补进文档。"
        )
    elif recall is not None and recall < 0.95:
        result["hint"] = (
            "引文已就绪；但规范性语句召回率低于 95%，"
            "检查 uncovered_samples 里有没有被漏掉的规定条款。"
        )
    return result


def lint_case_document(
    content: str,
    workflow_meta: dict[str, Any] | None = None,
    *,
    strict: bool | None = None,
) -> dict[str, Any]:
    """Run deterministic checks without modifying or calling an LLM.

    严格程度由**平台**配置（``settings.case_lint_strict``）决定。``strict`` 参数只
    保留给人工/接口显式覆盖（例如编辑遗留文档时临时放宽），**不读文档里的任何
    自述字段**——曾经的 ``package_strict`` 让被检文档能自己声明"请宽松地检查我"，
    写一个 false 就能让需求覆盖率、风险覆盖率两道门禁整段不执行。

    返回的 ``stats`` 里带三个对外可交付的数字：证据绑定情况、规范性语句召回率、
    未核实数值数。
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

    # 严格程度由**平台**决定（settings.case_lint_strict）。显式传入的 strict 参数
    # 保留给人工/接口调用（例如编辑遗留文档时主动放宽），但不再读文档里的任何自述
    # 字段——被检文档不能影响自己的判分标准。
    strict_mode = settings.case_lint_strict if strict is None else bool(strict)
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
            # 提示里直接给出契约：模型读的是 lint 报错，这是最可能被它看到的地方。
            # 实测"写了一段说明性文字"是这条报错最常见的成因，而修法（放进「附录…」
            # 小节，或干脆别用标题）不看代码是猜不到的。
            add(errors if strict_mode else warnings, "CASE_METADATA_MISSING", block["line"],
                "用例缺少 CASE/REQ/RISK 元数据"
                "（标题只能用于分组与用例；说明性段落请放进标题以「附录」开头的小节）")
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
                            f"非法 {key} ID：{value}"
                            f"（形状应为「大写字母开头 + 至少一段连字符」，"
                            f"如 REQ-AUTH-001、EDGE-011；编号直接沿用需求文档里的写法）")
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

    # 编号可追溯性：用例引用的 REQ 编号应当能在需求文档正文里原样搜到。
    # 只在真的读到原文时才检查——读不到就置 source_checked=False，别让"没检查"
    # 看起来像"检查通过"（这正是"上传成功≠解析完成"要防的那类错觉）。
    source_text = _load_source_text(workflow_meta)
    source_checked = bool(source_text)
    if source_checked:
        for req_id in sorted(referenced_requirements):
            if req_id not in source_text:
                add(warnings, "REQUIREMENT_ID_NOT_IN_SOURCE", 1,
                    f"用例引用的编号在需求文档正文里找不到：{req_id}"
                    f"（编号应在事实源中原样出现；若确属新增请先补进需求文档）")

    # ① 证据绑定：需求包每条需求的 source_quote 必须是需求文档正文的精确子串。
    # 这是「正式用例证据绑定率 100% / 无证据用例 0%」的确定性实现——引文对不上，
    # 就说明这条需求不是从文档里读出来的。
    package_requirements = _package_items(workflow_meta, "requirements")
    evidence_bound = 0
    if source_checked:
        normalized_source = _normalize_for_match(source_text)
        for item in package_requirements:
            req_id = str(item.get("id") or "").strip() or "<无编号>"
            # 一条需求可以挂多条证据（描述 + 若干规则条目）：真实需求文档里
            # 一条需求通常由多句话共同约束，只允许一句引文会让覆盖率虚低。
            quotes = _requirement_quotes(item)
            if not quotes:
                if settings.case_evidence_required:
                    add(errors, "EVIDENCE_QUOTE_MISSING", 1,
                        f"需求 {req_id} 没有 source_quote：正式用例必须能指出依据需求文档的哪句话")
                continue
            bad = [q for q in quotes if _normalize_for_match(q) not in normalized_source]
            if bad:
                add(errors, "EVIDENCE_QUOTE_NOT_FOUND", 1,
                    f"需求 {req_id} 有 {len(bad)} 条引文在需求文档里找不到，"
                    f"例如：「{bad[0][:40]}」——引文必须逐字来自事实源")
                continue
            evidence_bound += 1

    # ② 反向覆盖审计：文档里的规范性语句，是否都被至少一条原子需求引用。
    # 正向覆盖只能发现"列了但没写用例"；这一层才能发现"整条被漏掉"。
    normative_note = ""
    normative_total = normative_covered = 0
    if source_checked and package_requirements:
        normative = _normative_sentences(source_text)
        quotes = [q for i in package_requirements for q in _requirement_quotes(i)]
        normative_total = len(normative)
        uncovered = [s for s in normative if not any(_quote_covers(q, s) for q in quotes)]
        normative_covered = normative_total - len(uncovered)
        if normative_total:
            recall = normative_covered / normative_total
            if recall < settings.case_normative_recall_floor:
                add(warnings, "NORMATIVE_RECALL_LOW", 1,
                    f"规范性语句召回率 {recall:.0%}（{normative_covered}/{normative_total}），"
                    f"低于目标 {settings.case_normative_recall_floor:.0%}：文档里有硬性规定没被拆成需求")
                for sentence in uncovered[:10]:
                    add(warnings, "NORMATIVE_NOT_COVERED", 1,
                        f"未被任何原子需求引用：{sentence[:80]}")
                if len(uncovered) > 10:
                    normative_note = f"另有 {len(uncovered) - 10} 条未覆盖语句未逐条列出"
                    add(warnings, "NORMATIVE_NOT_COVERED_TRUNCATED", 1, normative_note)

    # ③ 数值确定性比对：断言里的数值应当能在需求文档中找到；找不到就要求人工确认
    # 它是环境实测值还是臆造（"16 位"写成 19 位这类错误，一次字符串比对就能抓）。
    numeric_unverified: list[str] = []
    if source_checked and settings.case_numeric_check:
        source_numbers = _numbers_in(source_text)
        for match in _NUMERIC_ASSERT_RE.finditer(content):
            number, unit = match.group(1), match.group(2)
            if number in source_numbers or number in _NUMERIC_STOPWORDS or number in numeric_unverified:
                continue
            # 批注行（`>` 引用块）按平台约定是人工备注、导出时会剥离，不是断言；
            # 「10 条/页」这类分页粒度是界面设置，也不会写在需求里。
            line_start = content.rfind("\n", 0, match.start()) + 1
            line = content[line_start:content.find("\n", match.start())]
            if line.lstrip().startswith(">") or "条/页" in line or "行/页" in line:
                continue
            numeric_unverified.append(number)
            if len(numeric_unverified) > 20:
                break
        for number in numeric_unverified:
            add(warnings, "UNVERIFIED_NUMERIC_ASSERTION", 1,
                f"用例断言的数值 {number} 未在需求文档中出现："
                f"请确认它是环境实测值（记入假设）还是臆造")

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
        "source_checked": source_checked,
        # 证据绑定率与规范性召回率是这套流程对外可交付的两个核心数字
        "evidence_bound": evidence_bound,
        "evidence_total": len(package_requirements),
        "normative_total": normative_total,
        "normative_covered": normative_covered,
        "normative_recall": round(normative_covered / normative_total, 4) if normative_total else None,
        "numeric_unverified": len(numeric_unverified),
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
    # 保存一律走平台的 lint 配置（settings.case_lint_strict），不再看文档自述。
    # 保存行为本身不被门禁阻塞，但记录下来的 lint 结果必须是真实强度下的结果——
    # 否则一次"宽松保存"就能把已通过的门禁降级。
    report = lint_case_document(content, current)
    metadata = case_workflow_service.record_lint(path.stem, report)
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
