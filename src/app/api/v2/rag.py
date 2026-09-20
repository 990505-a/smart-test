"""RAG module routes: 知识库列表 / 展示快照 / 检索 / 服务控制 / 本体配置。

分工（2026-09 定案）：平台侧只做**看**——状态、文档、图谱规模、检索验证；
真正改数据的事（入库、删除、重新解析、实体/关系编辑、图谱可视化）都在
LightRAG 自带界面里做，本页给出直达地址。唯一例外是**服务控制**（启动/停止/重启
本机实例）与**配置**：前者本来就在平台这层（启动器托管进程），后者是 LightRAG
官方没有的能力（它的 LLM/embedding 是启动环境变量，WebUI 改不了），所以由
LightRAG 界面里的「RAG 设置」页（tools/lightrag-ui，启动器注入）调用这里的接口。

一个知识库 = 一个实例 + 一个 workspace，见 services/rag_kbs.py。
"""

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.core.config import settings
from src.app.db.schemas.common import SuccessResponse
from src.app.services import lightrag_service
from src.app.services.rag_kbs import (
    KB_PORT_BASE,
    KB_PORT_MAX,
    default_kb,
    describe_keys,
    get_kb,
    load_kbs,
    suggest_kb,
    to_rows,
)
from src.app.services.settings_service import PLATFORM_KEYS, SettingsService, mask_secrets

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/rag")

#: 「RAG 设置」页能改的键。都在 platform 命名空间里——与设置页同一份存储，
#: 只是入口搬到了 LightRAG 界面（见 tests/test_wiring.py 的 ui_elsewhere）。
RAG_CONFIG_KEYS: tuple[str, ...] = (
    "lightrag_llm_base_url", "lightrag_llm_model", "lightrag_llm_api_key",
    "lightrag_embedding_base_url", "lightrag_embedding_model",
    "lightrag_embedding_api_key", "lightrag_embedding_dim",
)


class QueryRequest(BaseModel):
    question: str
    mode: str = "hybrid"
    top_k: int = 6
    kb: str = ""


class KbRow(BaseModel):
    key: str
    label: str = ""
    port: int = 0
    description: str = ""


class KbsUpdate(BaseModel):
    kbs: list[KbRow]


class RagConfigUpdate(BaseModel):
    values: dict[str, str]


def _effective_llm(db_values: dict[str, str]) -> dict:
    """LLM 三件套的实际来源：留空的项在启动器里回退到平台主模型。

    必须把"实际用的是谁"讲清楚——LightRAG 的入库/检索会真的去调这个端点，
    配错了只会在入库时报 401 之类的错，而那时用户已经在等结果了。
    """
    key = db_values.get("lightrag_llm_api_key") or settings.llm_api_key
    base_url = db_values.get("lightrag_llm_base_url") or settings.llm_base_url
    model = db_values.get("lightrag_llm_model") or settings.llm_model
    return {"base_url": base_url, "model": model, "api_key_set": bool(key),
            "inherited": not (db_values.get("lightrag_llm_api_key")
                              and db_values.get("lightrag_llm_base_url")
                              and db_values.get("lightrag_llm_model"))}


# ---------------------------------------------------------------------------
# 展示
# ---------------------------------------------------------------------------

@router.get("/kbs", response_model=SuccessResponse, summary="知识库列表（含在线状态）")
async def rag_kbs(user: CurrentUserDep):
    """所有知识库 + 在线状态 + 文档数。页面顶部的"选库"用这个。"""
    return SuccessResponse(success=True, data=await lightrag_service.kbs_status())


@router.get("/status", response_model=SuccessResponse, summary="某个知识库的服务状态")
async def rag_status(user: CurrentUserDep, kb: str = ""):
    target = get_kb(kb)
    if target is None:
        raise HTTPException(status_code=404, detail=f"没有这个知识库: {kb}（现有：{describe_keys()}）")
    health = await lightrag_service.health(target.key)
    return SuccessResponse(success=True, data={
        "kb": target.to_dict(),
        "reachable": "error" not in health,
        "health": health,
        "base_url": target.base_url,
        "webui_url": target.webui_url,
    })


@router.get("/overview", response_model=SuccessResponse, summary="知识库展示快照")
async def rag_overview(user: CurrentUserDep, kb: str = ""):
    """状态 + 文档计数 + 管道 + 图谱规模，一个请求给页面渲染用。"""
    return SuccessResponse(success=True, data=await lightrag_service.overview(kb))


@router.get("/documents", response_model=SuccessResponse, summary="已入库文档列表（分页）")
async def rag_documents(user: CurrentUserDep, kb: str = "", page: int = 1,
                        page_size: int = 20, status: str = ""):
    return SuccessResponse(success=True, data=await lightrag_service.list_documents(
        page, page_size, status=status, kb_key=kb))


@router.post("/query", response_model=SuccessResponse, summary="检索测试")
async def rag_query(req: QueryRequest, user: CurrentUserDep):
    return SuccessResponse(success=True, data=await lightrag_service.query(
        req.question, mode=req.mode, top_k=req.top_k, kb_key=req.kb))


# ---------------------------------------------------------------------------
# 服务控制（启动/停止/重启本机实例）
# ---------------------------------------------------------------------------

@router.post("/service/{kb}/{action}", response_model=SuccessResponse,
             summary="启动/停止/重启知识库实例")
async def rag_service_action(kb: str, action: str, user: CurrentUserDep):
    """转调启动器（:5010）——与"重启 LangGraph"同一条路子。

    ``kb=all`` 表示所有库（例如改完 LLM/embedding 之后要让全部实例加载新配置）。
    """
    from src.app.core import integrations

    if action not in ("start", "stop", "restart"):
        raise HTTPException(status_code=422, detail=f"未知操作: {action}")
    if kb in ("all", "*"):
        targets = list(load_kbs())
    else:
        target = get_kb(kb)
        if target is None:
            raise HTTPException(status_code=404,
                                detail=f"没有这个知识库: {kb}（现有：{describe_keys()}）")
        targets = [target]

    results: dict[str, dict] = {}
    for target in targets:
        result = await integrations.launcher_action(target.service_name, action)
        results[target.key] = {
            "service": target.service_name,
            "ok": bool(result.get("success")),
            "port": target.port,
            "error": result.get("error"),
        }
    return SuccessResponse(success=any(r["ok"] for r in results.values()), data={
        "action": action,
        "results": results,
        "note": "启动后约 10-30 秒就绪（首次入库还要等 embedding 端点可用）。",
    })


# ---------------------------------------------------------------------------
# 配置（LightRAG 界面里的「RAG 设置」页用）
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=SuccessResponse, summary="RAG 本体配置（含知识库清单）")
async def rag_settings(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = await svc.get_namespace("platform", {k: PLATFORM_KEYS[k] for k in RAG_CONFIG_KEYS})
    kbs = load_kbs()
    return SuccessResponse(success=True, data={
        "values": mask_secrets(values),
        "effective": _effective_llm({
            k: str(values.get(k) or "") for k in RAG_CONFIG_KEYS}),
        "kbs": [kb.to_dict() for kb in kbs],
        "next_kb": suggest_kb(),
        "service": {
            "working_dir": settings.lightrag_working_dir,
            "default_base_url": default_kb().base_url,
            "port_range": f"{KB_PORT_BASE}-{KB_PORT_MAX}",
            "platform_managed": True,
        },
        "notes": [
            "LLM / Embedding 是所有知识库共用的：同一套模型读所有库的文档。",
            "每个知识库是一个独立的 lightrag-server 进程（独立端口 + 独立 workspace），"
            "数据互不可见；改端口/增删库之后要让实例重启才生效。",
            "平台侧的「知识库」页只做展示与检索验证，入库/删除/重新解析请在"
            "LightRAG 自带界面里做。",
        ],
    })


@router.put("/settings", response_model=SuccessResponse, summary="保存 RAG 本体配置")
async def update_rag_settings(data: RagConfigUpdate, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = {k: v for k, v in data.values.items() if k in RAG_CONFIG_KEYS}
    await svc.set_many("platform", values)
    written = svc.sync_env_file(values, {k: PLATFORM_KEYS[k] for k in RAG_CONFIG_KEYS})
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "env_written": written,
        "note": "已保存到 .env。运行中的知识库实例仍用旧配置——"
                "点「保存并重启」让所有实例带新配置重启（约 10-30 秒就绪）。",
    })


@router.put("/kbs", response_model=SuccessResponse, summary="保存知识库清单")
async def update_rag_kbs(data: KbsUpdate, user: CurrentUserDep):
    """写注册表。新库立刻能在「服务」里启动——启动器按注册表现算服务表
    （不必重启控制台）。删除一个库**不会**删数据：它的目录留在工作目录里。
    """
    from src.app.services import rag_kbs

    rows = [row.model_dump() for row in data.kbs]
    try:
        kbs = rag_kbs.save_kbs(rows)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SuccessResponse(success=True, data={
        "kbs": [kb.to_dict() for kb in kbs],
        "note": "已保存。新库要点「启动」才会跑起来；改过端口的库要重启才生效。",
    })
