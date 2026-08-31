"""RAG module routes: manage the LightRAG knowledge base (本体管理).

LightRAG server (:5014) is the resident 本体 started by the launcher;
these routes wrap it for the /rag platform page: health, document list,
text/file ingestion, and a query console.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from src.app.api.v2.auth import CurrentUserDep
from src.app.core.config import settings
from src.app.db.schemas.common import SuccessResponse
from src.app.services import lightrag_service

router = APIRouter(prefix="/rag")


class IngestTextRequest(BaseModel):
    text: str
    file_source: str | None = None


class QueryRequest(BaseModel):
    question: str
    mode: str = "hybrid"
    top_k: int = 6


@router.get("/status", response_model=SuccessResponse, summary="LightRAG 服务状态")
async def rag_status(user: CurrentUserDep):
    health = await lightrag_service.health()
    return SuccessResponse(success=True, data={
        "reachable": "error" not in health,
        "health": health,
        "base_url": settings.lightrag_base_url,
        "webui_url": f"{settings.lightrag_base_url.rstrip('/')}/webui",
    })


@router.get("/documents", response_model=SuccessResponse, summary="已入库文档列表（分页）")
async def rag_documents(user: CurrentUserDep, page: int = 1, page_size: int = 20):
    return SuccessResponse(success=True,
                           data=await lightrag_service.list_documents(page, page_size))


@router.post("/ingest-text", response_model=SuccessResponse, summary="文本入库")
async def rag_ingest_text(req: IngestTextRequest, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await lightrag_service.ingest_text(req.text, req.file_source))


@router.post("/ingest-file", response_model=SuccessResponse, summary="文件上传入库")
async def rag_ingest_file(user: CurrentUserDep, file: UploadFile):
    suffix = Path(file.filename or "upload.txt").suffix
    tmp_path: str | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix, prefix="rag_") as tmp:
            tmp_path = tmp.name
            tmp.write(await file.read())
        return SuccessResponse(success=True,
                               data=await lightrag_service.ingest_file(tmp_path))
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@router.post("/query", response_model=SuccessResponse, summary="检索测试")
async def rag_query(req: QueryRequest, user: CurrentUserDep):
    return SuccessResponse(success=True,
                           data=await lightrag_service.query(
                               req.question, mode=req.mode, top_k=req.top_k))
