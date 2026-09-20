"""外部依赖就绪状态（就绪中心）。

一个依赖一行：能不能用、缺什么、怎么补。页面（设置页顶部 / 各模块页）读同一份
``fix_hint``，不再各自写"请打开启动器 http://localhost:5010"这类文案。

描述的唯一来源是 ``core/integrations.py``；这里只负责 HTTP 与动作转发。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.app.api.v2.auth import CurrentUserDep
from src.app.core import integrations
from src.app.db.schemas.common import SuccessResponse

router = APIRouter(prefix="/integrations")


@router.get("", response_model=SuccessResponse, summary="全部外部依赖的就绪状态")
async def list_integrations(user: CurrentUserDep):
    items = await integrations.probe_all()
    return SuccessResponse(success=True, data={
        "items": items,
        "ready": sum(1 for i in items if i.get("ready")),
        "total": len(items),
        # 必选依赖缺了才算"平台不可用"，选填的缺了只是少一块能力
        "blocking": [i["key"] for i in items
                     if not i.get("ready") and not i.get("optional")],
    })


class InstallRequest(BaseModel):
    force: bool = False
    version: str | None = None


@router.post("/{key}/install", response_model=SuccessResponse,
             summary="平台自管安装/升级（目前仅 codebase-memory）")
async def install_integration(key: str, body: InstallRequest, user: CurrentUserDep):
    item = integrations.BY_KEY.get(key)
    if item is None:
        raise HTTPException(status_code=404, detail=f"未知的外部依赖: {key}")
    if item.install != "codebase-memory":
        return SuccessResponse(success=False, data={
            "error": f"{item.label} 不支持平台内安装",
            "hint": item.fix_hint})
    from src.app.services import cbm_install

    result = await cbm_install.install_async(body.version, force=body.force)
    if result.get("success") is False:
        return SuccessResponse(success=False, data=result)
    return SuccessResponse(success=True, data=result)


@router.post("/{key}/start", response_model=SuccessResponse,
             summary="让启动器启动该依赖（本机模式）")
async def start_integration(key: str, user: CurrentUserDep):
    item = integrations.BY_KEY.get(key)
    if item is None:
        raise HTTPException(status_code=404, detail=f"未知的外部依赖: {key}")
    if item.launch is None:
        return SuccessResponse(success=False, data={
            "error": f"{item.label} 不是平台能启动的服务",
            "hint": item.fix_hint})
    result = await integrations.launcher_action(item.launch, "start")
    if not result.get("success"):
        return SuccessResponse(success=False, data=result)
    return SuccessResponse(success=True, data={"service": item.launch, **result})
