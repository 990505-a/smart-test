"""API automation routes (接口自动化模块)."""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from uuid import UUID
from pydantic import BaseModel
from sqlalchemy import select

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.db.models.api_doc import ApiDocImport
from src.app.db.models.api_script import ApiScript, ApiScriptRun
from src.app.db.schemas.common import SuccessResponse
from src.app.services import api_auto_service

router = APIRouter(prefix="/api-auto")


class ImportDocRequest(BaseModel):
    doc_url: str


class GenerateScriptRequest(BaseModel):
    import_id: str
    name: str
    base_url: str = "http://localhost:8080"
    module: str | None = None
    project_id: str | None = None


class RunScriptRequest(BaseModel):
    base_url: str | None = None
    auto_repair: bool = True


def _script_dict(s: ApiScript, *, full: bool = False) -> dict:
    data = {
        "id": str(s.id),
        "name": s.name,
        "module": s.module,
        "doc_url": s.doc_url,
        "language": s.language,
        "version": s.version,
        "status": s.status,
        "endpoints": json.loads(s.endpoints) if s.endpoints else [],
        "repair_history": json.loads(s.repair_history) if s.repair_history else [],
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
    if full:
        data["content"] = s.content
    return data


def _run_dict(r: ApiScriptRun) -> dict:
    return {
        "id": str(r.id),
        "script_id": str(r.script_id),
        "status": r.status,
        "exit_code": r.exit_code,
        "output": r.output,
        "duration_ms": r.duration_ms,
        "triggered_by": r.triggered_by,
        "repair_attempt": r.repair_attempt,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# --- Doc imports -------------------------------------------------------------

@router.post("/docs/import", response_model=SuccessResponse,
             summary="从飞书导入接口文档并解析接口")
async def import_doc(data: ImportDocRequest, user: CurrentUserDep):
    result = await api_auto_service.import_doc(data.doc_url)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "文档导入失败"))
    return SuccessResponse(success=True, data=result)


@router.get("/docs", response_model=SuccessResponse, summary="已导入文档列表")
async def list_docs(user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(ApiDocImport).order_by(ApiDocImport.created_at.desc()).limit(50)
    )).scalars().all())
    return SuccessResponse(success=True, data=[{
        "id": str(r.id), "doc_url": r.doc_url, "title": r.title,
        "endpoint_count": r.endpoint_count, "status": r.status, "error": r.error,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows])


@router.get("/docs/{import_id}", response_model=SuccessResponse, summary="文档解析详情")
async def get_doc(import_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(ApiDocImport).where(ApiDocImport.id == UUID(import_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="导入记录不存在")
    return SuccessResponse(success=True, data={
        "id": str(row.id), "doc_url": row.doc_url, "title": row.title,
        "status": row.status, "error": row.error,
        "endpoints": json.loads(row.endpoints) if row.endpoints else [],
    })


# --- Scripts -----------------------------------------------------------------

@router.post("/scripts/generate", response_model=SuccessResponse,
             summary="AI 生成第一版接口自动化脚本")
async def generate_script(data: GenerateScriptRequest, user: CurrentUserDep):
    result = await api_auto_service.generate_script(
        data.import_id, data.name, base_url=data.base_url,
        module=data.module, project_id=data.project_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "脚本生成失败"))
    return SuccessResponse(success=True, data=result)


@router.get("/scripts", response_model=SuccessResponse, summary="脚本列表")
async def list_scripts(user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(ApiScript).order_by(ApiScript.updated_at.desc()).limit(100)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_script_dict(s) for s in rows])


@router.get("/scripts/{script_id}", response_model=SuccessResponse, summary="脚本详情(含内容)")
async def get_script(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(ApiScript).where(ApiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    return SuccessResponse(success=True, data=_script_dict(row, full=True))


@router.put("/scripts/{script_id}", response_model=SuccessResponse, summary="手动编辑脚本")
async def update_script(script_id: str, data: dict, user: CurrentUserDep, db: DbSessionDep):
    row = (await db.execute(
        select(ApiScript).where(ApiScript.id == UUID(script_id)))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="脚本不存在")
    if "content" in data:
        row.content = data["content"]
        row.version += 1
    if "name" in data:
        row.name = data["name"]
    if "status" in data:
        row.status = data["status"]
    await db.commit()
    return SuccessResponse(success=True, data=_script_dict(row))


@router.post("/scripts/{script_id}/run", response_model=SuccessResponse,
             summary="执行脚本(失败时 AI 自修复)")
async def run_script(script_id: str, data: RunScriptRequest, user: CurrentUserDep):
    result = await api_auto_service.run_script(
        script_id, base_url=data.base_url, auto_repair=data.auto_repair)
    return SuccessResponse(success=True, data=result)


@router.post("/scripts/{script_id}/run-async", response_model=SuccessResponse,
             summary="后台执行脚本")
async def run_script_async(script_id: str, data: RunScriptRequest,
                           user: CurrentUserDep, background: BackgroundTasks):
    background.add_task(api_auto_service.run_script, script_id,
                        base_url=data.base_url, auto_repair=data.auto_repair)
    return SuccessResponse(success=True, data={"started": True})


@router.get("/scripts/{script_id}/runs", response_model=SuccessResponse, summary="脚本执行历史")
async def list_runs(script_id: str, user: CurrentUserDep, db: DbSessionDep):
    rows = list((await db.execute(
        select(ApiScriptRun).where(ApiScriptRun.script_id == UUID(script_id))
        .order_by(ApiScriptRun.created_at.desc()).limit(30)
    )).scalars().all())
    return SuccessResponse(success=True, data=[_run_dict(r) for r in rows])
