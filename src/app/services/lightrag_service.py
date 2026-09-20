"""LightRAG HTTP client (RAG 模块).

每个**知识库**是一个独立的 lightrag-server 进程（端口 / workspace 各不相同，
见 ``services/rag_kbs.py``），所以这里每个函数都收一个 ``kb`` 参数——空串表示
默认库。所有调用都返回普通 dict 且**从不抛异常**：服务没起时 error 字段会说明
是哪个库、地址在哪、怎么启动。

隔离模型提醒：LightRAG 官方没有"按请求切库"的能力（``/query``、``/documents/*``
的请求体里没有 workspace 字段），一个进程就是一个库。所以"选库"在这里等于
"选地址"，不是给同一个进程传参数。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

from src.app.core import breaker
from src.app.core.http import local_client
from src.app.services.rag_kbs import KB, get_kb

_INGEST_TIMEOUT = 120.0  # 首次入库含实体抽取，LLM 调用较慢
_READ_TIMEOUT = 30.0     # 状态/列表这类读接口

QUERY_MODES = ("local", "global", "hybrid", "naive", "mix", "bypass")

#: LightRAG 文档状态机的取值（用于前端筛选与计数展示）
DOC_STATUSES = ("pending", "parsing", "analyzing", "processing",
                "preprocessed", "processed", "failed")

#: 图谱规模最多取多少个节点（超过则显示 "≥N"）。全量读一张大图又慢又占内存，
#: 展示页只需要量级。
GRAPH_SAMPLE_NODES = 3000

# 服务没起的时候，每次调用都要等满超时。快速失败把它压成一次——**按库分别计数**：
# 一个库没起不该把其它库也判成不可用。
_guards: dict[str, breaker.Guard] = {}


def _guard(kb: KB) -> breaker.Guard:
    return _guards.setdefault(kb.key, breaker.Guard(f"LightRAG[{kb.label}]"))


def resolve(kb_key: str | None) -> KB | None:
    """按 key 找库；空 = 默认库。找不到返回 None（调用方给可读错误）。"""
    return get_kb(kb_key)


def unknown_kb_error(kb_key: str) -> dict:
    from src.app.services.rag_kbs import describe_keys

    return {"success": False,
            "error": f"没有这个知识库: {kb_key!r}；现有知识库：{describe_keys()}"}


def _client(kb: KB, timeout: float) -> httpx.AsyncClient:
    return local_client(base_url=kb.base_url.rstrip("/"), timeout=timeout)


async def _call(kb: KB, method: str, path: str, *,
                timeout: float = _INGEST_TIMEOUT, **kwargs) -> dict:
    """Perform one request; map any failure to a degraded dict."""
    if (reason := _guard(kb).blocked()) is not None:
        return {"success": False, "error": reason, "kb": kb.key}
    try:
        async with _client(kb, timeout) as client:
            resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        _guard(kb).ok()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        # 有响应 = 服务活着，只是这个请求不行（参数/权限/内部错）。打不通才算不可用，
        # 所以这里不动熔断计数。
        detail = exc.response.text[:300]
        return {"success": False, "error": f"HTTP {exc.response.status_code}: {detail}",
                "kb": kb.key}
    except httpx.HTTPError as exc:
        _guard(kb).fail()
        return {"success": False,
                "error": f"知识库「{kb.label}」服务不可达（{kb.base_url}），"
                         f"请在启动器(:5010)或平台知识库页启动它: {exc}",
                "kb": kb.key}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"LightRAG 响应不是有效 JSON: {exc}",
                "kb": kb.key}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LightRAG 请求处理失败: {exc}",
                "kb": kb.key}


# ---------------------------------------------------------------------------
# 状态 / 展示
# ---------------------------------------------------------------------------

async def health(kb_key: str = "") -> dict:
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    return await _call(kb, "GET", "/health", timeout=_READ_TIMEOUT)


async def status_counts(kb_key: str = "") -> dict:
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    return await _call(kb, "GET", "/documents/status_counts", timeout=_READ_TIMEOUT)


async def pipeline_status(kb_key: str = "") -> dict:
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    return await _call(kb, "GET", "/documents/pipeline_status", timeout=_READ_TIMEOUT)


async def graph_size(kb_key: str = "") -> dict:
    """图谱规模（实体/关系数）。

    LightRAG 没有"给我计数"的接口，只有取全图（``GET /graphs``）。所以这里只取
    一个上限内的样本并如实标注是否截断——展示页要的是量级，不是精确普查。
    """
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    data = await _call(kb, "GET", "/graphs", timeout=_READ_TIMEOUT,
                       params={"label": "*", "max_nodes": GRAPH_SAMPLE_NODES})
    if "error" in data:
        return data
    nodes = data.get("nodes") or []
    edges = data.get("edges") or []
    truncated = bool(data.get("is_truncated"))
    return {"success": True, "entities": len(nodes), "relations": len(edges),
            "truncated": truncated, "sample_nodes": GRAPH_SAMPLE_NODES}


def _health_view(health: dict) -> dict:
    """从 /health 里挑出展示要用的字段（前端不必懂 LightRAG 的整棵配置树）。"""
    from src.app.core.config import settings

    cfg = health.get("configuration") or {}
    llm_host = cfg.get("llm_binding_host") or ""
    # 本机模式下，上游网关要额外请求头时 LightRAG 的绑定会指向控制台的代转端点
    # （见 launcher.py 的 llm_proxy）。真上游一并给出来，否则用户看到
    # "LLM: 127.0.0.1:5010" 会以为配错了。
    relay_prefix = settings.launcher_url.rstrip("/") + "/"
    llm_upstream = ""
    if llm_host.startswith(relay_prefix):
        llm_upstream = settings.lightrag_llm_base_url or settings.llm_base_url
    return {
        "core_version": health.get("core_version"),
        "api_version": health.get("api_version"),
        "working_directory": health.get("working_directory"),
        "input_directory": health.get("input_directory"),
        "workspace": cfg.get("workspace"),
        "storage_workspaces": cfg.get("storage_workspaces"),
        "llm_model": cfg.get("llm_model"),
        "llm_binding_host": llm_host,
        "llm_upstream": llm_upstream,
        "embedding_model": cfg.get("embedding_model"),
        "embedding_binding_host": cfg.get("embedding_binding_host"),
        "kv_storage": cfg.get("kv_storage"),
        "graph_storage": cfg.get("graph_storage"),
        "vector_storage": cfg.get("vector_storage"),
        "pipeline_busy": health.get("pipeline_busy"),
        "auth_mode": health.get("auth_mode"),
    }


async def overview(kb_key: str = "") -> dict:
    """一个知识库的展示快照：服务状态 + 文档计数 + 管道 + 图谱规模。

    四路并发、各自尽力而为：图谱那一路在超大库上会慢，不该拖住整个页面；
    某一路失败时对应字段带 error，页面照常显示其它部分。
    """
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    # 局部变量别叫 health/status_counts 这些名字：会遮住同名的模块函数，
    # 于是 "先调用、再赋值" 的那一行抛 UnboundLocalError（真踩过）。
    health_data, counts, pipeline_data, graph_data = await asyncio.gather(
        health(kb.key), status_counts(kb.key), pipeline_status(kb.key),
        graph_size(kb.key),
    )
    reachable = "error" not in health_data
    return {
        "success": True,
        "kb": kb.to_dict(),
        "reachable": reachable,
        "error": health_data.get("error"),
        "health": _health_view(health_data) if reachable else None,
        "status_counts": counts.get("status_counts") if "error" not in counts else None,
        "counts_error": counts.get("error"),
        "pipeline": (
            {k: pipeline_data.get(k) for k in
             ("busy", "job_name", "job_start", "docs", "batchs", "cur_batch",
              "latest_message", "recovery_required", "scanning")}
            if "error" not in pipeline_data else None
        ),
        "pipeline_error": pipeline_data.get("error"),
        "graph": ({"entities": graph_data.get("entities"),
                   "relations": graph_data.get("relations"),
                   "truncated": graph_data.get("truncated")}
                  if "error" not in graph_data else None),
        "graph_error": graph_data.get("error"),
    }


async def kbs_status() -> list[dict]:
    """所有知识库的状态（库里挑库用）：元信息 + 是否在线 + 文档总数。"""
    from src.app.services.rag_kbs import load_kbs

    kbs = load_kbs()

    async def one(kb: KB) -> dict:
        health_data = await health(kb.key)
        reachable = "error" not in health_data
        row = {**kb.to_dict(), "reachable": reachable,
               "error": health_data.get("error") if not reachable else None,
               "documents": None}
        if reachable:
            counts = await status_counts(kb.key)
            if "error" not in counts:
                row["documents"] = (counts.get("status_counts") or {}).get("all")
        return row

    return list(await asyncio.gather(*(one(kb) for kb in kbs)))


# ---------------------------------------------------------------------------
# 文档
# ---------------------------------------------------------------------------

async def list_documents(page: int = 1, page_size: int = 20,
                         status: str = "", kb_key: str = "") -> dict:
    """分页列文档。status 非空时只列该状态（LightRAG 的 status_filter）。"""
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    payload: dict = {"page": max(1, int(page)),
                     "page_size": min(200, max(10, int(page_size)))}
    if status:
        if status not in DOC_STATUSES:
            return {"success": False,
                    "error": f"无效状态 {status!r}，可选 {DOC_STATUSES}"}
        payload["status_filter"] = status
    return await _call(kb, "POST", "/documents/paginated", json=payload,
                       timeout=_READ_TIMEOUT)


async def query(question: str, mode: str = "hybrid", top_k: int = 6,
                only_need_context: bool = False, kb_key: str = "") -> dict:
    """检索知识库。mode: local(邻域) / global(主题) / hybrid(混合) / naive(纯向量) / mix(混合+naive) / bypass(不检索，直接问模型)。"""
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    if mode not in QUERY_MODES:
        return {"success": False, "error": f"无效 mode: {mode}，可选 {QUERY_MODES}"}
    payload = {
        "query": question,
        "mode": mode,
        "top_k": top_k,
        "only_need_context": only_need_context,
    }
    return await _call(kb, "POST", "/query", json=payload)


# ---------------------------------------------------------------------------
# 入库（平台页面不再提供入口，由智能体的 rag 工具与 LightRAG 界面使用）
# ---------------------------------------------------------------------------

async def ingest_text(text: str, file_source: str | None = None,
                      kb_key: str = "") -> dict:
    """把一段文本（需求文档/历史用例 markdown 等）写入知识库索引。"""
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    payload: dict = {"text": text}
    if file_source:
        payload["file_source"] = file_source
    result = await _call(kb, "POST", "/documents/text", json=payload)
    if isinstance(result, dict) and "success" not in result:
        result["success"] = True
        result["kb"] = kb.key
    return result


async def ingest_file(file_path: str | Path, kb_key: str = "") -> dict:
    """上传本地文件（txt/md/pdf/docx…）到知识库并自动解析。"""
    kb = resolve(kb_key)
    if kb is None:
        return unknown_kb_error(kb_key)
    path = Path(file_path)
    if not path.is_file():
        return {"success": False, "error": f"文件不存在: {path}"}
    if (reason := _guard(kb).blocked()) is not None:
        return {"success": False, "error": reason, "kb": kb.key}
    try:
        async with _client(kb, _INGEST_TIMEOUT) as client:
            resp = await client.post(
                "/documents/upload",
                files={"file": (path.name, path.read_bytes())},
            )
        resp.raise_for_status()
        result = resp.json()
        _guard(kb).ok()
    except httpx.HTTPStatusError as exc:
        return {"success": False,
                "error": f"HTTP {exc.response.status_code}: {exc.response.text[:300]}"}
    except httpx.HTTPError as exc:
        _guard(kb).fail()
        return {"success": False, "error": f"知识库「{kb.label}」服务不可达: {exc}"}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"LightRAG 响应不是有效 JSON: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LightRAG 请求处理失败: {exc}"}
    if isinstance(result, dict) and "success" not in result:
        result["success"] = True
        result["kb"] = kb.key
    return result
