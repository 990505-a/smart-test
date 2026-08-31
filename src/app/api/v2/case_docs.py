"""Case document API routes (用例 MD 文档).

2026-08 重构：用例不再入关系库，一个项目 = workspace/default/cases/ 下
一份 Markdown 文件。本路由提供文档的列表 / 读取 / 保存 / 删除，前端
/cases 页直接编辑源文件并在此标注（✅/❌ + `>` 批注）。
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.services import case_docs_service, case_workflow_service
from src.app.services.case_review_service import review_case_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/case-docs")


def _require_case_role(user, *, action: str) -> None:
    """Require a role allowed to mutate or approve case workflow state."""
    if getattr(user, "role", None) not in {"admin", "tester"}:
        raise HTTPException(status_code=403, detail=f"{action}需要测试人员或管理员权限")


class SaveDocRequest(BaseModel):
    content: str = Field(min_length=1, description="完整用例 MD 内容（整体覆盖）")
    expected_revision: int | None = Field(default=None, ge=0)
    expected_hash: str | None = Field(default=None, min_length=1)
    workflow_mode: bool = Field(
        default=False,
        description="是否按严格工作流模式校验；默认兼容旧文档保存",
    )


class WorkflowActionRequest(BaseModel):
    expected_revision: int | None = Field(default=None, ge=0)
    expected_hash: str | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, max_length=2000)


class RequirementPackageRequest(BaseModel):
    package: dict[str, object]
    expected_revision: int | None = Field(default=None, ge=0)


@router.get(
    "",
    response_model=SuccessResponse,
    summary="List case documents",
    description="列出全部用例 MD 文档（含用例数与人工标注统计）",
)
async def list_case_docs(user: CurrentUserDep):
    return SuccessResponse(success=True, data=case_docs_service.list_docs())


@router.get(
    "/{name}",
    response_model=SuccessResponse,
    summary="Get case document",
    description="读取用例 MD 原文（含人工标注）",
)
async def get_case_doc(name: str, user: CurrentUserDep):
    doc = case_docs_service.read_doc(name)
    if doc is None:
        raise HTTPException(status_code=404, detail="用例文档不存在")
    # Attach the parsed group/case tree for the structured review view.  This
    # stays in the API layer (not read_doc) so agent tools never balloon with
    # a full tree payload.
    parsed = case_docs_service.parse_cases_md(doc["content"])
    doc["parsed"] = {
        "title": parsed["title"],
        "tree": parsed["tree"],
        "case_count": parsed["case_count"],
    }
    return SuccessResponse(success=True, data=doc)


@router.put(
    "/{name}",
    response_model=SuccessResponse,
    summary="Save case document",
    description="整体覆盖保存用例 MD（新建或更新）",
)
async def save_case_doc(name: str, data: SaveDocRequest, user: CurrentUserDep):
    _require_case_role(user, action="保存用例")
    try:
        result = case_docs_service.save_doc(
            name,
            data.content,
            expected_revision=data.expected_revision,
            expected_hash=data.expected_hash,
        )
        if data.workflow_mode:
            # Re-run strict lint for new workflow callers while retaining the
            # draft on disk even when the gate fails.
            metadata = case_workflow_service.load_metadata(name)
            report = case_docs_service.lint_case_document(
                data.content, metadata, strict=True
            )
            metadata = case_workflow_service.record_lint(name, report, strict=True)
            result.update({
                "lint_status": metadata["lint_status"],
                "lifecycle_status": metadata["lifecycle_status"],
                "lint_report": case_workflow_service.public_metadata(metadata).get("lint_report"),
            })
    except case_workflow_service.WorkflowConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, case_workflow_service.WorkflowError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SuccessResponse(success=True, data=result)


@router.delete("/{name}", response_model=MessageResponse)
async def delete_case_doc(name: str, user: CurrentUserDep):
    _require_case_role(user, action="删除用例")
    deleted = case_docs_service.delete_doc(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="用例文档不存在")
    return MessageResponse(success=True, message=f"已删除用例文档: {name}")


@router.post(
    "/{name}/requirement-package",
    response_model=SuccessResponse,
    summary="Save requirement package",
)
async def save_requirement_package(
    name: str,
    data: RequirementPackageRequest,
    user: CurrentUserDep,
):
    _require_case_role(user, action="保存需求包")
    try:
        metadata = case_workflow_service.save_requirement_package(
            name,
            dict(data.package),
            expected_revision=data.expected_revision,
        )
    except case_workflow_service.WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SuccessResponse(
        success=True,
        data=case_workflow_service.public_metadata(metadata),
    )


@router.post(
    "/{name}/lint",
    response_model=SuccessResponse,
    summary="Lint case document",
)
async def lint_case_doc(
    name: str,
    user: CurrentUserDep,
    data: WorkflowActionRequest | None = None,
):
    _require_case_role(user, action="检查用例")
    doc = case_docs_service.read_doc(name)
    if doc is None:
        raise HTTPException(status_code=404, detail="用例文档不存在")
    metadata = case_workflow_service.load_metadata(name)
    strict = bool(metadata.get("package_strict", False))
    report = case_docs_service.lint_case_document(
        doc["content"], metadata, strict=strict
    )
    metadata = case_workflow_service.record_lint(name, report, strict=strict)
    return SuccessResponse(
        success=True,
        data={
            "name": name,
            "revision": metadata["revision"],
            "lifecycle_status": metadata["lifecycle_status"],
            "lint_status": metadata["lint_status"],
            "review_status": metadata["review_status"],
            "lint_report": case_workflow_service.public_metadata(metadata).get("lint_report"),
        },
    )


@router.post(
    "/{name}/review",
    response_model=SuccessResponse,
    summary="Review case document",
)
async def review_case_doc(
    name: str,
    user: CurrentUserDep,
    data: WorkflowActionRequest | None = None,
):
    _require_case_role(user, action="评审用例")
    metadata = case_workflow_service.load_metadata(name)
    if "package_strict" not in metadata:
        raise HTTPException(status_code=400, detail="请先保存需求包后再提交评审")
    try:
        report = await review_case_document(name)
        metadata = case_workflow_service.record_review(
            name,
            report,
            expected_revision=data.expected_revision if data else None,
        )
    except case_workflow_service.WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except case_workflow_service.WorkflowTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, RuntimeError) as exc:
        logger.exception("Case document review failed for %s", name)
        raise HTTPException(status_code=502, detail=str(exc))
    public = case_workflow_service.public_metadata(metadata)
    return SuccessResponse(
        success=True,
        data={
            "name": name,
            "revision": public["revision"],
            "lifecycle_status": public["lifecycle_status"],
            "lint_status": public["lint_status"],
            "review_status": public["review_status"],
            "review_report": public.get("review_report"),
        },
    )


@router.post(
    "/{name}/request-changes",
    response_model=SuccessResponse,
    summary="Request case document changes",
)
async def request_case_doc_changes(
    name: str,
    user: CurrentUserDep,
    data: WorkflowActionRequest | None = None,
):
    _require_case_role(user, action="退回用例")
    try:
        metadata = case_workflow_service.transition(
            name,
            "changes_requested",
            actor=str(user.id) if user is not None else None,
            reason=data.reason if data else None,
            expected_revision=data.expected_revision if data else None,
            expected_hash=data.expected_hash if data else None,
        )
    except case_workflow_service.WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SuccessResponse(success=True, data=case_workflow_service.public_metadata(metadata))


@router.post(
    "/{name}/approve",
    response_model=SuccessResponse,
    summary="Approve case document",
)
async def approve_case_doc(
    name: str,
    user: CurrentUserDep,
    data: WorkflowActionRequest | None = None,
):
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="批准用例需要管理员权限")
    try:
        metadata = case_workflow_service.transition(
            name,
            "approved",
            actor=str(user.id) if user is not None else None,
            reason=data.reason if data else None,
            expected_revision=data.expected_revision if data else None,
            expected_hash=data.expected_hash if data else None,
        )
    except case_workflow_service.WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SuccessResponse(success=True, data=case_workflow_service.public_metadata(metadata))


@router.post(
    "/{name}/release",
    response_model=SuccessResponse,
    summary="Release approved case document",
)
async def release_case_doc(
    name: str,
    user: CurrentUserDep,
    data: WorkflowActionRequest | None = None,
):
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status_code=403, detail="发布用例需要管理员权限")
    try:
        metadata = case_workflow_service.transition(
            name,
            "released",
            actor=str(user.id) if user is not None else None,
            reason=data.reason if data else None,
            expected_revision=data.expected_revision if data else None,
            expected_hash=data.expected_hash if data else None,
        )
    except case_workflow_service.WorkflowConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValueError, case_workflow_service.WorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return SuccessResponse(success=True, data=case_workflow_service.public_metadata(metadata))
