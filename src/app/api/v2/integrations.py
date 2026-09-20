"""外部依赖就绪状态（就绪中心）。

一个依赖一行：能不能用、缺什么、怎么补。页面（设置页顶部 / 各模块页）读同一份
``fix_hint``，不再各自写"请打开启动器 http://localhost:5010"这类文案。

描述的唯一来源是 ``core/integrations.py``；这里只负责 HTTP 与动作转发。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Awaitable, Callable

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
        # 必选依赖缺了才算"平台不可用"，选填的缺了只是少一块能力；
        # 已标记「不适用」的不算缺（那是这台机器的定位，不是故障）
        "blocking": [i["key"] for i in items
                     if not i.get("ready") and not i.get("optional")
                     and not i.get("not_applicable")],
    })


class ApplicabilityRequest(BaseModel):
    applicable: bool = True


@router.post("/{key}/applicability", response_model=SuccessResponse,
             summary="标记/取消「这台机器不跑它」（降级成中性状态，不进 blocking）")
async def set_applicability(key: str, body: ApplicabilityRequest, user: CurrentUserDep):
    result = await integrations.set_applicability(key, body.applicable)
    if result.get("success") is False:
        raise HTTPException(status_code=404, detail=result.get("error"))
    return SuccessResponse(success=True, data=result)


class InstallRequest(BaseModel):
    force: bool = False
    version: str | None = None
    #: 仅 playwright 用：要装哪些浏览器（留空 = chromium）与是否带系统依赖
    browsers: list[str] | None = None
    with_deps: bool | None = None


async def _install_codebase_memory(body: InstallRequest) -> dict:
    from src.app.services import cbm_install

    return await cbm_install.install_async(body.version, force=body.force)


async def _install_playwright(body: InstallRequest) -> dict:
    from src.app.services import playwright_service

    return await playwright_service.install_browsers(
        browsers=body.browsers, with_deps=body.with_deps)


#: 注册表的 ``install`` 键 → 实现。
#:
#: 做成表而不是一串 if，是为了能被测试断言：注册表那边声明了 ``install="xxx"``，
#: 这里就必须有同名实现。反例是本次修掉的 —— 注册表给 playwright 填了 install，
#: 而 API 还是 ``if item.install != "codebase-memory"`` 的写死判断：前端按钮会出现
#: （它只看 item.install 有没有值），点了却回"不支持平台内安装"。这种"UI 有按钮、
#: 后端没接线"正是这个模块要消灭的错位，见 tests/test_wiring.py。
INSTALLERS: dict[str, Callable[[InstallRequest], Awaitable[dict]]] = {
    "codebase-memory": _install_codebase_memory,
    "playwright": _install_playwright,
}


async def _run_installer(name: str, body: InstallRequest) -> dict:
    """把注册表里的 ``install`` 键分派到具体安装器。"""
    installer = INSTALLERS.get(name)
    if installer is None:
        return {"success": False, "error": f"未实现的安装器: {name}"}
    return await installer(body)


@router.post("/{key}/install", response_model=SuccessResponse,
             summary="平台自管安装/升级（codebase-memory 二进制 / playwright 浏览器）")
async def install_integration(key: str, body: InstallRequest, user: CurrentUserDep):
    item = integrations.BY_KEY.get(key)
    if item is None:
        raise HTTPException(status_code=404, detail=f"未知的外部依赖: {key}")
    if not item.install:
        return SuccessResponse(success=False, data={
            "error": f"{item.label} 不支持平台内安装",
            "hint": item.fix_hint})
    result = await _run_installer(item.install, body)
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
