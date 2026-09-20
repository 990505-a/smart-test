"""Agent 记忆 API（harness 风格 Markdown 记忆模块）。

记忆是一组可开关、可编辑的 Markdown 文件（AGENTS.md / MEMORY.md / USER.md /
failures.md / PROJECT.md / DECISIONS.md + 用户自建），落在
``workspace/{space}/memory/``。文件是唯一事实源：页面直接读写文件，
``manifest.json`` 只记「哪些模块启用、顺序、显示名」。

（2026-08-31 的 EverOS 版本已移除：记忆不再需要外部服务与向量索引。旧
EverOS 的 user.md 在首次启动时自动并入 USER.md，见 memory_service。）
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import AfterValidator, BaseModel, Field

from src.app.api.v2.auth import CurrentUserDep
from src.app.core.workspace import safe_segment
from src.app.db.schemas.common import SuccessResponse
from src.app.services import memory_service

router = APIRouter(prefix="/memories")


def _validate_space(value: str) -> str:
    return safe_segment(value, field="space_id")


#: 记忆的 ``space`` 参数。它会成为落盘路径的一层目录名
#: （``workspace/{space}/memory/``），过去是无校验裸串——传 ``..`` 就能读写
#: workspace 之外的任意目录（含覆盖别处的 ``*/memory/*.md``）。
#: 校验挂在参数类型上，非法值由 FastAPI 直接 422。
SpaceQuery = Annotated[str, Query(), AfterValidator(_validate_space)]


class ModuleWriteRequest(BaseModel):
    content: str


class ModulePatchRequest(BaseModel):
    enabled: bool | None = None
    label: str | None = None
    description: str | None = None


class ModuleCreateRequest(BaseModel):
    label: str
    file: str | None = None
    content: str = ""
    description: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=8, ge=1, le=50)


class EntryRequest(BaseModel):
    module: str = "memory"
    content: str
    category: str = ""


def _module_dict(module: memory_service.MemoryModule) -> dict:
    return {
        "id": module.id,
        "file": module.file,
        "label": module.label,
        "description": module.description,
        "enabled": module.enabled,
        "builtin": module.builtin,
        "chars": module.chars,
        "updated_at": module.updated_at or None,
    }


def _get_or_404(module_id: str, space: str) -> memory_service.MemoryModule:
    module = memory_service.get_module(module_id, space_id=space)
    if module is None:
        raise HTTPException(status_code=404, detail=f"记忆模块不存在: {module_id}")
    return module


@router.get("/status", response_model=SuccessResponse, summary="记忆模块状态")
async def memory_status(user: CurrentUserDep, space: SpaceQuery = "default"):
    return SuccessResponse(success=True, data=memory_service.status(space))


@router.get("/modules", response_model=SuccessResponse, summary="记忆模块列表")
async def list_modules(user: CurrentUserDep, space: SpaceQuery = "default"):
    modules = memory_service.list_modules(space_id=space)
    return SuccessResponse(success=True, data=[_module_dict(m) for m in modules])


@router.post("/modules", response_model=SuccessResponse, status_code=201,
             summary="新建自定义记忆模块")
async def create_module(data: ModuleCreateRequest, user: CurrentUserDep,
                        space: SpaceQuery = "default"):
    if not data.label.strip():
        raise HTTPException(status_code=400, detail="label 不能为空")
    try:
        module = memory_service.create_module(
            data.label.strip(), file=(data.file or None), content=data.content,
            description=data.description, space_id=space)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SuccessResponse(success=True, data=_module_dict(module))


@router.get("/modules/{module_id}", response_model=SuccessResponse, summary="读取模块正文")
async def read_module(module_id: str, user: CurrentUserDep,
                      space: SpaceQuery = "default"):
    module = _get_or_404(module_id, space)
    return SuccessResponse(success=True, data={
        **_module_dict(module),
        "content": memory_service.read_module(module.id, space_id=space),
    })


@router.put("/modules/{module_id}", response_model=SuccessResponse, summary="保存模块正文")
async def write_module(module_id: str, data: ModuleWriteRequest, user: CurrentUserDep,
                       space: SpaceQuery = "default"):
    module = _get_or_404(module_id, space)
    saved = memory_service.write_module(module.id, data.content, space_id=space)
    return SuccessResponse(success=True, data=_module_dict(saved))


@router.patch("/modules/{module_id}", response_model=SuccessResponse,
              summary="启用/停用或改名")
async def patch_module(module_id: str, data: ModulePatchRequest, user: CurrentUserDep,
                       space: SpaceQuery = "default"):
    module = _get_or_404(module_id, space)
    if data.enabled is not None:
        module = memory_service.set_enabled(module.id, data.enabled, space_id=space)
    if data.label or data.description is not None:
        updated = memory_service.update_module_meta(
            module.id, label=data.label, description=data.description, space_id=space)
        if updated is not None:
            module = updated
    return SuccessResponse(success=True, data=_module_dict(module))


@router.delete("/modules/{module_id}", response_model=SuccessResponse, summary="删除自定义模块")
async def delete_module(module_id: str, user: CurrentUserDep,
                        space: SpaceQuery = "default"):
    module = _get_or_404(module_id, space)
    try:
        deleted = memory_service.delete_module(module.id, space_id=space)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="记忆模块不存在")
    return SuccessResponse(success=True, data={"deleted": module.file})


@router.post("/search", response_model=SuccessResponse, summary="检索记忆")
async def search_memory(data: SearchRequest, user: CurrentUserDep,
                        space: SpaceQuery = "default"):
    hits = memory_service.search(data.query, limit=data.limit, space_id=space)
    return SuccessResponse(success=True, data={
        "count": len(hits),
        "hits": [
            {"module_id": h.module_id, "file": h.file, "label": h.label,
             "line": h.line, "text": h.text, "score": round(h.score, 3)}
            for h in hits
        ],
    })


@router.post("/entries", response_model=SuccessResponse, status_code=201,
             summary="手动追加一条记忆")
async def append_entry(data: EntryRequest, user: CurrentUserDep,
                       space: SpaceQuery = "default"):
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    try:
        module = memory_service.append_entry(
            data.module, data.content, category=data.category, space_id=space, source="user")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SuccessResponse(success=True, data=_module_dict(module))
