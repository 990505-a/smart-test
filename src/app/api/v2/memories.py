"""Memory routes (EverOS 文件化记忆).

记忆系统的存储是 EverOS 管理的 Markdown 文件（单一事实源），不再是
memories 表。本路由提供：
- status：EverOS 服务健康 + 能力（embedding 是否解锁）
- files / file：浏览、读、写（人工编辑由 EverOS watcher 自动回灌索引）、删
- search：检索代理（hybrid/keyword 自动选择）
- save：手动写入一条显式记忆（等价于 Agent 的 save_memory 工具）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.middleware.memory_injection import invalidate_memory_cache
from src.app.services import everos_service
from src.app.services.everos_service import EverosError

router = APIRouter(prefix="/memories")


class FileWriteBody(BaseModel):
    path: str
    content: str


class SearchBody(BaseModel):
    query: str
    top_k: int = 8


class SaveBody(BaseModel):
    key: str
    content: str
    category: str | None = None


def _everos_error(exc: EverosError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/status", response_model=SuccessResponse, summary="EverOS 服务状态与能力")
async def status(user: CurrentUserDep):
    data = await everos_service.everos_health()
    data["files"] = len(everos_service.list_memory_files())
    return SuccessResponse(success=True, data=data)


@router.get("/files", response_model=SuccessResponse, summary="记忆文件列表")
async def list_files(user: CurrentUserDep):
    return SuccessResponse(success=True, data=everos_service.list_memory_files())


@router.get("/file", response_model=SuccessResponse, summary="读取记忆文件内容")
async def read_file(user: CurrentUserDep, path: str):
    try:
        content = everos_service.read_memory_file(path)
    except EverosError as exc:
        raise _everos_error(exc) from exc
    return SuccessResponse(success=True, data={"path": path, "content": content})


@router.put("/file", response_model=SuccessResponse, summary="写入记忆文件（watcher 自动回灌索引）")
async def write_file(user: CurrentUserDep, body: FileWriteBody):
    try:
        everos_service.write_memory_file(body.path, body.content)
    except EverosError as exc:
        raise _everos_error(exc) from exc
    invalidate_memory_cache()
    return SuccessResponse(success=True, data={"path": body.path, "saved": True})


@router.delete("/file", response_model=SuccessResponse, summary="删除记忆文件")
async def delete_file(user: CurrentUserDep, path: str):
    try:
        everos_service.delete_memory_file(path)
    except EverosError as exc:
        raise _everos_error(exc) from exc
    invalidate_memory_cache()
    return SuccessResponse(success=True, data={"path": path, "deleted": True})


@router.post("/search", response_model=SuccessResponse, summary="检索记忆")
async def search(user: CurrentUserDep, body: SearchBody):
    try:
        hits = await everos_service.search_memory(body.query, top_k=body.top_k)
    except EverosError as exc:
        raise _everos_error(exc) from exc
    return SuccessResponse(success=True, data=hits)


@router.post("/save", response_model=SuccessResponse, summary="手动写入一条长期记忆")
async def save(user: CurrentUserDep, body: SaveBody):
    try:
        result = await everos_service.save_fact(body.key, body.content, body.category)
    except EverosError as exc:
        raise _everos_error(exc) from exc
    invalidate_memory_cache()
    return SuccessResponse(success=True, data={
        "key": body.key,
        "flush_status": (result.get("flush") or {}).get("status"),
    })
