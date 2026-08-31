"""Durable workflow metadata for Markdown case documents.

The Markdown file remains the source of truth for the case tree.  This module
stores lifecycle, validation, review, and generation metadata in a hidden
sidecar so the existing Markdown/Feishu/evolution integrations remain
compatible while workflow state survives process restarts.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LIFECYCLE_STATUSES = {
    "draft",
    "needs_clarification",
    "generated",
    "in_review",
    "changes_requested",
    "approved",
    "released",
}
LINT_STATUSES = {"not_run", "passed", "failed"}
REVIEW_STATUSES = {"not_run", "passed", "failed"}

# 累计复核调用上限（跨内容版本，需求包更新时重置）：首次复核 + 2 轮修复复核。
MAX_REVIEW_CALLS = 3


class WorkflowError(ValueError):
    """Base error for workflow metadata and state operations."""


class WorkflowConflictError(WorkflowError):
    """The caller attempted to write an obsolete document revision."""


class WorkflowTransitionError(WorkflowError):
    """A lifecycle transition is not valid for the current document state."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(content: str) -> str:
    """Return the stable SHA-256 digest used by workflow gates."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def metadata_path(document_name: str) -> Path:
    """Return the hidden workflow sidecar path for a case document."""
    # Local import avoids a module cycle: case_docs_service enriches its CRUD
    # responses with this module, while this module reuses its safe path rules.
    from src.app.services import case_docs_service

    doc = case_docs_service.doc_path(document_name)
    return doc.with_name(f".{doc.stem}.workflow.json")


def _default_metadata(document_name: str) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": 1,
        "document_name": document_name,
        "revision": 0,
        "content_hash": "",
        "lifecycle_status": "draft",
        "lint_status": "not_run",
        "review_status": "not_run",
        "lint_report": None,
        "review_report": None,
        "review_round": 0,
        "review_calls_total": 0,
        "requirements": [],
        "coverage_plan": [],
        "risks": [],
        "source_manifest": [],
        "scope": {"in": [], "out": []},
        "assumptions": [],
        "unresolved_questions": [],
        "approved_by": None,
        "approved_at": None,
        "released_by": None,
        "released_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _merge_defaults(document_name: str, value: dict[str, Any]) -> dict[str, Any]:
    merged = _default_metadata(document_name)
    merged.update(value)
    merged["document_name"] = document_name
    if not isinstance(merged.get("scope"), dict):
        merged["scope"] = {"in": [], "out": []}
    return merged


def load_metadata(document_name: str) -> dict[str, Any]:
    """Load metadata, returning a safe legacy default when no sidecar exists."""
    path = metadata_path(document_name)
    if not path.exists():
        return _default_metadata(document_name)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"工作流元数据损坏: {path.name}") from exc
    if not isinstance(raw, dict):
        raise WorkflowError(f"工作流元数据格式错误: {path.name}")
    return _merge_defaults(document_name, raw)


def save_metadata(document_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Atomically persist workflow metadata and return the normalized value."""
    path = metadata_path(document_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _merge_defaults(document_name, metadata)
    normalized["updated_at"] = _now()

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return normalized


def remove_metadata(document_name: str) -> bool:
    """Remove a sidecar when its Markdown document is deleted."""
    path = metadata_path(document_name)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    return True


def _check_expected(
    current: dict[str, Any],
    expected_revision: int | None = None,
    expected_hash: str | None = None,
    actual_hash: str | None = None,
) -> None:
    if expected_revision is not None and int(current.get("revision", 0)) != expected_revision:
        raise WorkflowConflictError(
            f"用例文档版本冲突：当前 revision={current.get('revision', 0)}，"
            f"请求 revision={expected_revision}"
        )
    if expected_hash is not None:
        current_hash = current.get("content_hash") or actual_hash or ""
        if current_hash != expected_hash:
            raise WorkflowConflictError("用例文档内容已被其他窗口修改，请刷新后重试")


def record_content_save(
    document_name: str,
    content: str,
    *,
    expected_revision: int | None = None,
    expected_hash: str | None = None,
    actual_hash: str | None = None,
) -> dict[str, Any]:
    """Record a content revision and invalidate stale review decisions.

    Saving is intentionally always allowed as a draft.  Approval and release
    are the operations that enforce lint/review gates.
    """
    current = load_metadata(document_name)
    _check_expected(current, expected_revision, expected_hash, actual_hash)
    digest = content_hash(content)
    is_new = not current.get("content_hash")
    changed = current.get("content_hash") != digest
    if changed or is_new:
        current["revision"] = int(current.get("revision", 0)) + 1
        current["content_hash"] = digest
        current["lifecycle_status"] = "draft"
        current["lint_status"] = "not_run"
        current["review_status"] = "not_run"
        current["lint_report"] = None
        current["review_report"] = None
        current["review_round"] = 0
        current["approved_by"] = None
        current["approved_at"] = None
        current["released_by"] = None
        current["released_at"] = None
    return save_metadata(document_name, current)


def record_lint(
    document_name: str,
    report: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Persist a deterministic lint report without changing document content."""
    current = load_metadata(document_name)
    current["lint_report"] = report
    current["lint_status"] = "passed" if report.get("ok") else "failed"
    if report.get("content_hash") and not current.get("content_hash"):
        current["content_hash"] = report["content_hash"]
        current["revision"] = max(1, int(current.get("revision", 0)))
    if current["lifecycle_status"] == "released" and not report.get("ok"):
        current["lifecycle_status"] = "draft"
    # A strict workflow document may proceed to review only after lint passes.
    if strict and report.get("ok") and current["lifecycle_status"] == "draft":
        current["lifecycle_status"] = "generated"
    return save_metadata(document_name, current)


def save_requirement_package(
    document_name: str,
    package: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Attach a validated-enough requirement package to a case document."""
    if not isinstance(package, dict):
        raise WorkflowError("需求包必须是 JSON 对象")
    current = load_metadata(document_name)
    _check_expected(current, expected_revision)
    requirements = package.get("requirements", [])
    coverage_plan = package.get("coverage_plan", [])
    if not isinstance(requirements, list):
        raise WorkflowError("需求包 requirements 必须是数组")
    if not isinstance(coverage_plan, list):
        raise WorkflowError("需求包 coverage_plan 必须是数组")

    current.update({
        "requirements": requirements,
        "risks": package.get("risks", []),
        "coverage_plan": coverage_plan,
        "source_manifest": package.get("source_manifest", []),
        "scope": package.get("scope", {"in": [], "out": []}),
        "assumptions": package.get("assumptions", []),
        "unresolved_questions": package.get("unresolved_questions", []),
    })
    current["package_id"] = package.get("package_id")
    current["package_name"] = package.get("package_name", document_name)
    current["package_strict"] = bool(package.get("strict", True))
    # 新的需求包 = 新的输入（例如用户答复了未决问题），复核配额重新计。
    current["review_calls_total"] = 0
    blocking = any(
        isinstance(item, dict)
        and bool(item.get("blocking", item.get("severity") in {"blocker", "high"}))
        for item in current["unresolved_questions"]
    )
    current["lifecycle_status"] = "needs_clarification" if blocking else "draft"
    current["lint_status"] = "not_run"
    current["review_status"] = "not_run"
    current["review_report"] = None
    current["approved_by"] = None
    current["approved_at"] = None
    current["released_by"] = None
    current["released_at"] = None
    return save_metadata(document_name, current)


def _review_has_blocking(report: dict[str, Any] | None) -> bool:
    """Return whether a report contains a release-blocking issue."""
    if not report:
        return True
    issues = report.get("issues", [])
    if not isinstance(issues, list):
        return True
    return any(
        isinstance(issue, dict)
        and str(issue.get("severity", "")).lower() in {"blocker", "high"}
        for issue in issues
    )


def transition(
    document_name: str,
    target: str,
    *,
    actor: str | None = None,
    reason: str | None = None,
    expected_revision: int | None = None,
    expected_hash: str | None = None,
) -> dict[str, Any]:
    """Apply a guarded lifecycle transition and persist its audit fields."""
    if target not in LIFECYCLE_STATUSES:
        raise WorkflowTransitionError(f"未知的用例文档状态: {target}")
    current = load_metadata(document_name)
    _check_expected(current, expected_revision, expected_hash)
    current_status = current["lifecycle_status"]
    lint_ok = current.get("lint_status") == "passed"
    review_ok = current.get("review_status") == "passed" and not _review_has_blocking(
        current.get("review_report")
    )
    unresolved = current.get("unresolved_questions") or []
    blocking_unknown = any(
        isinstance(item, dict)
        and bool(item.get("blocking", item.get("severity") in {"blocker", "high"}))
        for item in unresolved
    )

    if target == "needs_clarification":
        current["lifecycle_status"] = target
    elif target == "generated":
        if not lint_ok:
            raise WorkflowTransitionError("Lint 未通过，不能进入 generated")
        current["lifecycle_status"] = target
    elif target == "in_review":
        if not lint_ok:
            raise WorkflowTransitionError("Lint 未通过，不能提交评审")
        if blocking_unknown:
            raise WorkflowTransitionError("存在未解决的高风险需求歧义")
        current["lifecycle_status"] = target
    elif target == "changes_requested":
        current["lifecycle_status"] = target
        current["review_status"] = "failed"
    elif target == "approved":
        if not lint_ok:
            raise WorkflowTransitionError("Lint 未通过，不能批准")
        if blocking_unknown:
            raise WorkflowTransitionError("存在未解决的高风险需求歧义，不能批准")
        if not review_ok:
            raise WorkflowTransitionError("评审未通过或仍有 blocker/high 问题")
        current["lifecycle_status"] = target
        current["approved_by"] = actor
        current["approved_at"] = _now()
    elif target == "released":
        if current_status != "approved":
            raise WorkflowTransitionError("只有 approved 版本可以发布")
        if not lint_ok or not review_ok:
            raise WorkflowTransitionError("发布前必须通过 Lint 和评审")
        current["lifecycle_status"] = target
        current["released_by"] = actor
        current["released_at"] = _now()
    elif target == "draft":
        current["lifecycle_status"] = target
    else:
        current["lifecycle_status"] = target

    if reason:
        current["last_transition_reason"] = reason
    return save_metadata(document_name, current)


def record_review(
    document_name: str,
    report: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Persist an isolated review report against the current revision."""
    current = load_metadata(document_name)
    _check_expected(current, expected_revision)
    # review_round 随内容保存清零（表示"当前版本的复核轮次"），不能作为
    # 总量限制——否则"改→存→复核"循环会永远绕开上限。review_calls_total
    # 只在需求包更新（拿到新答复/新输入）时重置。
    if int(current.get("review_calls_total", 0)) >= MAX_REVIEW_CALLS:
        raise WorkflowTransitionError(
            f"累计复核已达 {MAX_REVIEW_CALLS} 轮上限：剩余问题需要人工决策。"
            "请把未解决问题整理给用户，或让用户在用例页面退回修改/批准；"
            "用户补充需求答复后可重新复核。"
        )
    if current.get("lint_status") != "passed":
        raise WorkflowTransitionError("Lint 未通过，不能提交评审")
    current["review_report"] = report
    current["review_status"] = "passed" if not _review_has_blocking(report) else "failed"
    current["review_round"] = int(current.get("review_round", 0)) + 1
    current["review_calls_total"] = int(current.get("review_calls_total", 0)) + 1
    current["lifecycle_status"] = (
        "in_review" if current["review_status"] == "passed" else "changes_requested"
    )
    return save_metadata(document_name, current)


def public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded metadata view safe for API/tool responses."""
    result = dict(metadata)
    report = result.get("lint_report")
    if isinstance(report, dict):
        result["lint_report"] = {
            "ok": bool(report.get("ok")),
            "errors": list(report.get("errors", []))[:100],
            "warnings": list(report.get("warnings", []))[:100],
            "stats": report.get("stats", {}),
            "content_hash": report.get("content_hash", ""),
        }
    review = result.get("review_report")
    if isinstance(review, dict):
        result["review_report"] = {
            "verdict": review.get("verdict"),
            "issues": list(review.get("issues", []))[:100],
            "summary": review.get("summary", ""),
        }
    return result
