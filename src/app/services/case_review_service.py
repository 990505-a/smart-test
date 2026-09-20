"""Isolated AI review for generated case documents.

The reviewer is deliberately separate from the testcase agent's conversation.
It returns a bounded, machine-readable issue list; deterministic lint and the
human approval gate remain authoritative for release decisions.

成本与长任务治理（2026-09）：
- 用例文档动辄几万字，整篇塞进单次调用既慢又贵，一处超时整轮白跑。
  现在按**用例边界**切片、并发复核，再合并结论（原设计是单次调用 + 硬截断，
  截断还会让后半篇用例实际没被审到）。
- 评审模型可配（settings.case_review_model），支持换成不同模型家族做异构复核。
- 返回的问题数有上限，并记录片数/输入规模/耗时，让成本可见。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from src.app.agents.testcase.model_factory import build_chat_model
from src.app.core.config import settings
from src.app.services import case_docs_service, case_workflow_service

_MAX_ISSUES = 100

_REVIEW_PROMPT = """你是独立的测试用例评审员。不要相信生成者的自评，只依据给定的需求包、覆盖计划、用例文档和证据进行检查。

请检查：需求覆盖、未解决假设、业务规则矛盾、不可执行步骤、不可观察预期、重复用例、边界/异常/权限/并发/恢复漏测。无法从证据确认的规则必须标记为 UNSUPPORTED_ASSERTION，不要替产品猜测规则。

只输出一个 JSON 对象，不要输出 Markdown：
{{
  "verdict": "pass" 或 "needs_revision",
  "summary": "不超过200字",
  "issues": [
    {{
      "severity": "blocker|high|medium|low",
      "code": "MISSING_COVERAGE|UNSUPPORTED_ASSERTION|UNEXECUTABLE_STEP|CONTRADICTION|DUPLICATE|OTHER",
      "case_id": "CASE-... 或 null",
      "requirement_id": "REQ-... 或 null",
      "evidence": "具体证据",
      "recommendation": "可执行的修复建议"
    }}
  ]
}}

需求包：
{package}

用例文档：
{document}
"""

_SLICE_NOTE = """

【本次评审范围】这是第 {index}/{total} 片，请**只评审本片中出现的用例**。
不要因为别的用例不在这里就报"缺失覆盖"——跨片的覆盖与一致性问题由汇总阶段负责。
"""


def _text_response(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _decode_report(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("评审结果不是有效 JSON")
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ValueError("评审结果不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("评审结果必须是 JSON 对象")
    verdict = value.get("verdict")
    if verdict not in {"pass", "needs_revision"}:
        raise ValueError("评审 verdict 必须是 pass 或 needs_revision")
    issues = value.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("评审 issues 必须是数组")
    normalized: list[dict[str, Any]] = []
    valid_severities = {"blocker", "high", "medium", "low"}
    for issue in issues[:_MAX_ISSUES]:
        if not isinstance(issue, dict):
            raise ValueError("评审 issue 必须是对象")
        severity = str(issue.get("severity", "")).lower()
        if severity not in valid_severities:
            raise ValueError(f"非法评审严重度: {severity}")
        normalized.append({
            "severity": severity,
            "code": str(issue.get("code") or "OTHER"),
            "case_id": issue.get("case_id"),
            "requirement_id": issue.get("requirement_id"),
            "evidence": str(issue.get("evidence") or ""),
            "recommendation": str(issue.get("recommendation") or ""),
        })
    if any(i["severity"] in {"blocker", "high"} for i in normalized):
        verdict = "needs_revision"
    return {
        "verdict": verdict,
        "summary": str(value.get("summary") or "")[:200],
        "issues": normalized,
    }


def _bounded_package(metadata: dict[str, Any]) -> dict[str, Any]:
    """给复核员的需求包视图：只保留判断覆盖所需的信息。

    ``source_quotes`` 是**平台侧**核对证据用的（一条需求常常挂六到八句引文），
    整包喂给复核员会把输入撑到 35KB 以上——复核员的判断依据是"编号、摘要、风险
    等级、覆盖计划"，引文只留一句供抽查即可。
    """
    requirements: list[dict[str, Any]] = []
    for item in (metadata.get("requirements") or [])[:100]:
        if not isinstance(item, dict):
            continue
        quotes = item.get("source_quotes") or []
        quote = str(item.get("source_quote") or (quotes[0] if quotes else "")).strip()
        requirements.append({
            "id": item.get("id"),
            "risk": item.get("risk"),
            "summary": item.get("summary"),
            "source_quote": quote[:120],
        })
    return {
        "requirements": requirements,
        "risks": metadata.get("risks", [])[:100],
        "coverage_plan": metadata.get("coverage_plan", [])[:100],
        "scope": metadata.get("scope", {}),
        "assumptions": metadata.get("assumptions", [])[:100],
        "unresolved_questions": metadata.get("unresolved_questions", [])[:100],
        "source_manifest": metadata.get("source_manifest", [])[:50],
    }


def _split_document(content: str, limit: int) -> list[str]:
    """按用例边界切片：先按标题切块，再贪心拼到不超过 limit。

    绝不从用例中间断开——半条用例喂给评审员只会产生假问题。单个块本身超限时
    保持完整（宁可这片大一点，也不要切断一条用例）。
    """
    blocks: list[str] = []
    buffer: list[str] = []
    for line in content.splitlines(keepends=True):
        if re.match(r"^#{1,6}\s", line) and buffer:
            blocks.append("".join(buffer))
            buffer = []
        buffer.append(line)
    if buffer:
        blocks.append("".join(buffer))

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if current and len(current) + len(block) > limit:
            chunks.append(current)
            current = block
        else:
            current += block
    if current:
        chunks.append(current)
    return chunks or [content]


async def _review_chunk(prompt: str, model: Any) -> dict[str, Any]:
    """callbacks=[]：从父 run 的流式回调中剥离这次嵌套调用。否则评审员的
    原始 JSON 输出（含 reasoning）会被 messages 流当作主对话消息推给前端，
    在聊天里出现大段莫名其妙的 JSON。隔离上下文评审也理应隔离流。
    """
    response = await model.ainvoke(
        prompt,
        config={"callbacks": [], "metadata": {"lc_source": "case_review"}},
    )
    return _decode_report(_text_response(response))


def _merge_reports(reports: list[dict[str, Any]], total_chunks: int) -> dict[str, Any]:
    """合并分片结论：任一票 needs_revision 或出现 blocker/high 即整体不通过。"""
    issues: list[dict[str, Any]] = []
    needs_revision = False
    for index, report in enumerate(reports, 1):
        if report.get("verdict") == "needs_revision":
            needs_revision = True
        for issue in report.get("issues", []):
            if total_chunks > 1:
                issue = {**issue, "chunk": index}
            issues.append(issue)

    severity_rank = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    issues.sort(key=lambda i: severity_rank.get(i.get("severity"), 9))
    if any(i.get("severity") in {"blocker", "high"} for i in issues):
        needs_revision = True
    issues = issues[: settings.case_review_max_issues]

    summaries = [r.get("summary", "") for r in reports if r.get("summary")]
    summary = "；".join(summaries)[:200]
    if total_chunks > 1:
        summary = f"[分 {total_chunks} 片评审] {summary}"[:200]
    return {
        "verdict": "needs_revision" if needs_revision else "pass",
        "summary": summary,
        "issues": issues,
    }


async def review_case_document(document_name: str) -> dict[str, Any]:
    """Review the current document with isolated model calls (chunked if long)."""
    document = case_docs_service.read_doc(document_name)
    if document is None:
        raise ValueError("用例文档不存在")
    metadata = case_workflow_service.load_metadata(document_name)
    # 在花一次模型调用之前先挡住超限复核（写入侧 record_review 还有权威校验）。
    if int(metadata.get("review_calls_total", 0)) >= case_workflow_service.MAX_REVIEW_CALLS:
        raise case_workflow_service.WorkflowTransitionError(
            f"累计复核已达 {case_workflow_service.MAX_REVIEW_CALLS} 轮上限：剩余问题需要人工决策，"
            "请整理后交给用户处理；用户补充需求答复后可重新复核。"
        )
    report = case_docs_service.lint_case_document(document["content"], metadata)
    if not report["ok"]:
        raise ValueError("Lint 未通过，不能进行 AI 评审")

    content = document["content"]
    package = json.dumps(_bounded_package(metadata), ensure_ascii=False)
    limit = max(4_000, settings.case_review_chunk_chars)
    chunks = _split_document(content, limit) if len(content) > limit else [content]

    prompts = []
    for index, chunk in enumerate(chunks, 1):
        prompt = _REVIEW_PROMPT.format(package=package, document=chunk)
        if len(chunks) > 1:
            prompt += _SLICE_NOTE.format(index=index, total=len(chunks))
        prompts.append(prompt)

    model = build_chat_model(effort="high", model_name=settings.case_review_model or None)
    started = time.monotonic()
    # 分片并发：墙钟时间取决于最慢的一片，而不是各片之和。
    # 并发上限 3，避免把网关的速率限制打满导致整体失败。
    semaphore = asyncio.Semaphore(3)

    async def run(prompt: str) -> dict[str, Any]:
        async with semaphore:
            return await _review_chunk(prompt, model)

    reports = await asyncio.gather(*(run(p) for p in prompts))
    merged = _merge_reports(list(reports), len(chunks))
    merged["metrics"] = {
        "chunks": len(chunks),
        "input_chars": len(content),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "review_model": settings.case_review_model or "(平台默认)",
    }
    return merged
