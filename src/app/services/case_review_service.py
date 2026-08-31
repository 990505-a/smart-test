"""Isolated AI review for generated case documents.

The reviewer is deliberately separate from the testcase agent's conversation.
It returns a bounded, machine-readable issue list; deterministic lint and the
human approval gate remain authoritative for release decisions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.app.agents.testcase.model_factory import build_chat_model
from src.app.services import case_docs_service, case_workflow_service

_MAX_INPUT_CHARS = 45_000
_MAX_ISSUES = 100

_REVIEW_PROMPT = """你是独立的游戏测试用例评审员。不要相信生成者的自评，只依据给定的需求包、覆盖计划、用例文档和证据进行检查。

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
    return {
        "requirements": metadata.get("requirements", [])[:100],
        "risks": metadata.get("risks", [])[:100],
        "coverage_plan": metadata.get("coverage_plan", [])[:100],
        "scope": metadata.get("scope", {}),
        "assumptions": metadata.get("assumptions", [])[:100],
        "unresolved_questions": metadata.get("unresolved_questions", [])[:100],
        "source_manifest": metadata.get("source_manifest", [])[:50],
    }


async def review_case_document(document_name: str) -> dict[str, Any]:
    """Review the current document with an isolated model call."""
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
    report = case_docs_service.lint_case_document(
        document["content"], metadata, strict=bool(metadata.get("package_strict"))
    )
    if not report["ok"]:
        raise ValueError("Lint 未通过，不能进行 AI 评审")

    package = json.dumps(_bounded_package(metadata), ensure_ascii=False)
    raw_document = document["content"][:_MAX_INPUT_CHARS]
    if len(document["content"]) > _MAX_INPUT_CHARS:
        raw_document += "\n…（文档过长，评审输入已截断）"
    prompt = _REVIEW_PROMPT.format(package=package, document=raw_document)
    model = build_chat_model(effort="high")
    # callbacks=[]：从父 run 的流式回调中剥离这次嵌套调用。否则评审员的
    # 原始 JSON 输出（含 reasoning）会被 messages 流当作主对话消息推给前端，
    # 在聊天里出现大段莫名其妙的 JSON。隔离上下文评审也理应隔离流。
    response = await model.ainvoke(
        prompt,
        config={"callbacks": [], "metadata": {"lc_source": "case_review"}},
    )
    return _decode_report(_text_response(response))
