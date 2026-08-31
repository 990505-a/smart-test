"""Feishu integration routes (飞书模块): CLI status, mindnote export, doc fetch."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.services import feishu_service

router = APIRouter(prefix="/feishu")


class ExportMindnoteRequest(BaseModel):
    root_text: str | None = None
    project_name: str
    mindnote_id: str | None = None
    parent_node_id: str | None = None


class FetchDocRequest(BaseModel):
    doc_url: str
    scope: str | None = None


class DeviceCodeRequest(BaseModel):
    device_code: str


@router.get("/status", response_model=SuccessResponse, summary="lark-cli 状态")
async def status(user: CurrentUserDep):
    return SuccessResponse(success=True, data=await feishu_service.auth_status())


@router.post("/auth/start", response_model=SuccessResponse,
             summary="发起飞书设备码登录（返回授权链接）")
async def auth_start(user: CurrentUserDep):
    """lark-cli 未登录时的引导入口：设备码流第一步。

    返回 verification_url（用户浏览器打开授权）与 device_code（前端暂存，
    授权完成后调 /auth/complete 完成绑定），600 秒有效。
    """
    result = await feishu_service.start_device_login()
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "发起登录失败"))
    return SuccessResponse(success=True, data=result)


@router.post("/auth/complete", response_model=SuccessResponse,
             summary="完成飞书设备码登录")
async def auth_complete(data: DeviceCodeRequest, user: CurrentUserDep):
    result = await feishu_service.complete_device_login(data.device_code)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "登录未完成"))
    return SuccessResponse(success=True, data=result)


@router.post("/docs/fetch", response_model=SuccessResponse, summary="拉取飞书文档内容")
async def fetch_doc(data: FetchDocRequest, user: CurrentUserDep):
    result = await feishu_service.fetch_doc(data.doc_url, scope=data.scope)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "飞书文档拉取失败"))
    return SuccessResponse(success=True, data=result)


@router.get("/mindnote/nodes", response_model=SuccessResponse, summary="思维导图节点列表")
async def mindnote_nodes(user: CurrentUserDep, mindnote_id: str | None = None):
    result = await feishu_service.list_mindnote_nodes(mindnote_id)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "获取节点失败"))
    return SuccessResponse(success=True, data=result)


@router.post("/mindnote/export", response_model=SuccessResponse,
             summary="将用例 MD 文档导出到飞书思维导图")
async def export_mindnote(data: ExportMindnoteRequest, user: CurrentUserDep):
    """树形导出：按项目名读用例 MD 文档（人工标注自动剥离）→ 飞书导图。"""
    if not data.project_name or not data.project_name.strip():
        raise HTTPException(status_code=400, detail="必须提供 project_name")

    loaded = await feishu_service.load_doc_tree(data.project_name.strip())
    if not loaded.get("success"):
        raise HTTPException(status_code=404, detail=loaded.get("error", "用例文档不存在"))
    if not loaded.get("case_count"):
        raise HTTPException(status_code=404, detail="没有可导出的用例")

    root = (data.root_text or "").strip() or loaded["root_text"]
    result = await feishu_service.save_tree_to_mindnote(
        root, loaded["tree"],
        mindnote_id=data.mindnote_id, parent_node_id=data.parent_node_id,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "导出失败"))
    return SuccessResponse(success=True, data={**result, "exported_cases": loaded["case_count"]})
