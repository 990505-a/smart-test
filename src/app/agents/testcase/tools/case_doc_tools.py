"""Case document tools for the testcase agent (用例 MD 文档存取)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from src.app.services import case_docs_service, case_workflow_service
from src.app.services.case_review_service import review_case_document as run_case_review


@tool
def get_beijing_timestamp() -> str:
    """Get the current Beijing time (UTC+8) formatted as YYYY.MM.DD.HH.MM."""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y.%m.%d.%H.%M")


@tool
def save_case_document(
    project_name: str,
    content: str,
    expected_revision: int | None = None,
) -> dict:
    """把整份测试用例集保存为平台的 Markdown 草稿。

    同名文档是整体覆盖；续传前必须先读取原文。保存不会因 lint 失败
    丢失草稿，但不通过 lint/review 的文档不能由平台批准或发布。
    """
    try:
        result = case_docs_service.save_doc(
            project_name, content, expected_revision=expected_revision
        )
        return {
            "success": True,
            "name": result["name"],
            "path": result["path"],
            "case_count": result["case_count"],
            "revision": result["revision"],
            "content_hash": result["content_hash"],
            "lifecycle_status": result["lifecycle_status"],
            "lint_status": result["lint_status"],
            "review_status": result["review_status"],
            "lint_report": result.get("lint_report"),
        }
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        return {"success": False, "error": str(exc)}


@tool
def save_requirement_package(project_name: str, package: dict) -> dict:
    """保存需求摘要、验收例子、风险、未知项和覆盖计划。"""
    try:
        metadata = case_workflow_service.save_requirement_package(project_name, package)
        return {
            "success": True,
            "name": project_name,
            "lifecycle_status": metadata["lifecycle_status"],
            "requirements": len(metadata.get("requirements", [])),
            "coverage_items": len(metadata.get("coverage_plan", [])),
            "unresolved_questions": len(metadata.get("unresolved_questions", [])),
        }
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        return {"success": False, "error": str(exc)}


@tool
def lint_case_document(project_name: str, strict: bool = True) -> dict:
    """对用例文档执行确定性质量检查，不调用模型。"""
    doc = case_docs_service.read_doc(project_name)
    if doc is None:
        return {"success": False, "error": "用例文档不存在"}
    try:
        metadata = case_workflow_service.load_metadata(project_name)
        report = case_docs_service.lint_case_document(
            doc["content"], metadata, strict=strict
        )
        saved = case_workflow_service.record_lint(project_name, report, strict=strict)
        public = case_workflow_service.public_metadata(saved)
        return {
            "success": True,
            "name": project_name,
            "ok": report["ok"],
            "errors": report["errors"][:50],
            "warnings": report["warnings"][:50],
            "stats": report["stats"],
            "revision": saved["revision"],
            "lifecycle_status": saved["lifecycle_status"],
            "lint_status": saved["lint_status"],
            "content_hash": public["content_hash"],
        }
    except case_workflow_service.WorkflowError as exc:
        return {"success": False, "error": str(exc)}


@tool
async def review_case_document(project_name: str) -> dict:
    """用隔离上下文的评审模型检查已通过 Lint 的用例文档。"""
    try:
        report = await run_case_review(project_name)
        metadata = case_workflow_service.record_review(project_name, report)
        public = case_workflow_service.public_metadata(metadata)
        return {
            "success": True,
            "name": project_name,
            "verdict": report["verdict"],
            "issues": report["issues"][:50],
            "summary": report.get("summary", ""),
            "review_status": metadata["review_status"],
            "lifecycle_status": metadata["lifecycle_status"],
            "revision": metadata["revision"],
            "content_hash": public["content_hash"],
        }
    except (ValueError, case_workflow_service.WorkflowError, RuntimeError) as exc:
        return {"success": False, "error": str(exc)}


@tool
def get_case_workflow_status(project_name: str) -> dict:
    """读取用例文档当前的草稿、Lint、评审和发布状态。"""
    doc = case_docs_service.read_doc(project_name)
    if doc is None:
        return {"success": False, "error": "用例文档不存在"}
    metadata = case_workflow_service.public_metadata(
        case_workflow_service.load_metadata(project_name)
    )
    return {
        "success": True,
        "name": project_name,
        "revision": metadata["revision"],
        "content_hash": metadata["content_hash"] or case_workflow_service.content_hash(doc["content"]),
        "lifecycle_status": metadata["lifecycle_status"],
        "lint_status": metadata["lint_status"],
        "review_status": metadata["review_status"],
        "lint_report": metadata.get("lint_report"),
        "review_report": metadata.get("review_report"),
    }


@tool
def read_case_document(project_name: str) -> dict:
    """读取已保存的用例 Markdown 原文和工作流状态。"""
    doc = case_docs_service.read_doc(project_name)
    if doc is None:
        return {"success": False, "not_found": True, "project_name": project_name}
    return {"success": True, **doc}


@tool
def list_case_documents() -> dict:
    """列出平台全部用例文档、统计和工作流状态。"""
    docs = case_docs_service.list_docs()
    return {"success": True, "documents": docs, "count": len(docs)}
