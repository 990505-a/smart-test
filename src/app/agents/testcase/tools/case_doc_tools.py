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
    """保存需求摘要、验收例子、风险、未知项和覆盖计划。

    返回里的 ``validation`` 是**写用例之前**的确定性校验：引文是否逐字来自需求文档、
    编号是否在文档里存在、规范性语句召回率多少。出现 ``quote_not_found`` /
    ``quote_missing`` / ``requirement_id_not_in_source`` 就先改需求包再动手写用例——
    等整篇写完才被 lint 拦下，等于白写一遍。
    """
    try:
        metadata = case_workflow_service.save_requirement_package(project_name, package)
        return {
            "success": True,
            "name": project_name,
            "lifecycle_status": metadata["lifecycle_status"],
            "requirements": len(metadata.get("requirements", [])),
            "coverage_items": len(metadata.get("coverage_plan", [])),
            "unresolved_questions": len(metadata.get("unresolved_questions", [])),
            "validation": case_docs_service.validate_requirement_package(package),
        }
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        return {"success": False, "error": str(exc)}


@tool
def lint_case_document(project_name: str) -> dict:
    """对用例文档执行确定性质量检查，不调用模型。

    严格程度由平台配置决定（settings.case_lint_strict），**不接受调用方传入**——
    判分标准不能由被检对象选择。返回里除 errors/warnings 外还有 stats：
    证据绑定率、规范性语句召回率、未核实数值数，这三个是对外交付时要引用的数字。
    """
    doc = case_docs_service.read_doc(project_name)
    if doc is None:
        return {"success": False, "error": "用例文档不存在"}
    try:
        metadata = case_workflow_service.load_metadata(project_name)
        report = case_docs_service.lint_case_document(doc["content"], metadata)
        saved = case_workflow_service.record_lint(project_name, report)
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
def approve_case_document(project_name: str, reason: str | None = None) -> dict:
    """批准用例文档（**必须先由用户在对话中确认**）。

    调用本工具会在对话里弹出审批卡片，用户点「允许」后状态才真正变为 approved。
    平台仍保留「智能体不得自行批准」的约束：这条工具只是把人工批准搬到对话里，
    批准人依旧是用户。前置条件由工作流强制：Lint 通过 + 复核通过且无 blocker/high
    + 没有 blocking 的未决问题。
    """
    return _transition(project_name, "approved", reason)


@tool
def release_case_document(project_name: str, reason: str | None = None) -> dict:
    """发布已批准（approved）的用例文档（**必须先由用户在对话中确认**）。

    只有 approved 版本可以发布；发布后视为内部正式版本。
    """
    return _transition(project_name, "released", reason)


def _transition(project_name: str, target: str, reason: str | None) -> dict:
    try:
        metadata = case_workflow_service.transition(
            project_name, target, actor=_local_actor(), reason=reason
        )
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        return {"success": False, "error": str(exc)}
    public = case_workflow_service.public_metadata(metadata)
    return {
        "success": True,
        "name": project_name,
        "lifecycle_status": public["lifecycle_status"],
        "approved_by": public.get("approved_by"),
        "approved_at": public.get("approved_at"),
        "released_at": public.get("released_at"),
    }


def _local_actor() -> str:
    """审批人标识：本地单机模式下的内置管理员用户 id。

    直接读 SQLite（工作流元数据是文件、但用户表在库里），取不到时退回固定 UUID，
    保证审计字段始终有值而不是 None。
    """
    import sqlite3

    from src.app.core.config import settings
    from src.app.db.models.project import DEFAULT_USER_ID

    try:
        # 复用 database_url 这一唯一来源，避免路径算法与 ORM 侧不一致
        db_path = settings.database_url.split("///", 1)[-1]
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if row and row[0]:
            return str(row[0])
    except Exception:  # noqa: BLE001 — 审计字段取不到不应阻断审批
        pass
    return str(DEFAULT_USER_ID)


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
