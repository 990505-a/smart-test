"""LightRAG HTTP client (RAG 模块).

Wraps the lightrag-server REST API (:5014, 由启动器管理). LightRAG is a single
workspace — no datasets — so the surface here is: health / ingest text / upload
file / list documents / query. All calls return plain dicts and never raise;
when the server is down the error field says so.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from src.app.core.config import settings

_TIMEOUT = 120.0  # 首次入库含实体抽取，LLM 调用较慢

QUERY_MODES = ("local", "global", "hybrid", "naive", "mix")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.lightrag_base_url.rstrip("/"),
        timeout=_TIMEOUT,
    )


async def _call(method: str, path: str, **kwargs) -> dict:
    """Perform one request; map any failure to a degraded dict."""
    try:
        async with _client() as client:
            resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        return {"success": False, "error": f"HTTP {exc.response.status_code}: {detail}"}
    except httpx.HTTPError as exc:
        return {"success": False,
                "error": f"LightRAG 服务不可达 ({settings.lightrag_base_url})，"
                         f"请在启动器(:5010)启动 lightrag 服务: {exc}"}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"LightRAG 响应不是有效 JSON: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LightRAG 请求处理失败: {exc}"}


async def health() -> dict:
    return await _call("GET", "/health")


async def ingest_text(text: str, file_source: str | None = None) -> dict:
    """把一段文本（需求文档/历史用例 markdown 等）写入 LightRAG 索引。"""
    payload: dict = {"text": text}
    if file_source:
        payload["file_source"] = file_source
    result = await _call("POST", "/documents/text", json=payload)
    if isinstance(result, dict) and "success" not in result:
        result["success"] = True
    return result


async def ingest_file(file_path: str | Path) -> dict:
    """上传本地文件（txt/md/pdf/docx…）到 LightRAG 并自动解析。"""
    path = Path(file_path)
    if not path.is_file():
        return {"success": False, "error": f"文件不存在: {path}"}
    try:
        async with _client() as client:
            resp = await client.post(
                "/documents/upload",
                files={"file": (path.name, path.read_bytes())},
            )
        resp.raise_for_status()
        result = resp.json()
    except httpx.HTTPError as exc:
        return {"success": False, "error": str(exc)}
    except json.JSONDecodeError as exc:
        return {"success": False, "error": f"LightRAG 响应不是有效 JSON: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LightRAG 请求处理失败: {exc}"}
    if isinstance(result, dict) and "success" not in result:
        result["success"] = True
    return result


async def list_documents(page: int = 1, page_size: int = 50) -> dict:
    return await _call("POST", "/documents/paginated",
                       json={"page": page, "page_size": page_size})


async def query(
    question: str,
    mode: str = "hybrid",
    top_k: int = 6,
    only_need_context: bool = False,
) -> dict:
    """检索知识库。mode: local(邻域) / global(主题) / hybrid(混合) / naive(纯向量) / mix(混合+naive)。"""
    if mode not in QUERY_MODES:
        return {"success": False,
                "error": f"无效 mode: {mode}，可选 {QUERY_MODES}"}
    payload = {
        "query": question,
        "mode": mode,
        "top_k": top_k,
        "only_need_context": only_need_context,
    }
    return await _call("POST", "/query", json=payload)
