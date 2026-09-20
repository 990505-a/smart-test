"""Langfuse transport (测评模块).

Hand-rolled HTTP client over Langfuse's public API rather than the official
SDK, for the same reason dsh-eval-automation's runner talks to the REST API:
the eval runner lives **outside** the agent process, so it only needs
fire-and-forget ingestion plus a couple of read/write endpoints — pulling the
SDK in would add an OTEL stack and a batching lifecycle for nothing.

Endpoints used (verified against the repo's own Langfuse 4.36):

    POST /api/public/ingestion          trace/span/generation events (batched)
    POST /api/public/scores             one score against a trace
    POST /api/public/datasets           upsert a dataset by name
    POST /api/public/dataset-items      upsert a dataset item by deterministic id
    POST /api/public/dataset-run-items  link a trace into a named dataset run
    GET  /api/public/dataset-items      read back item ids after mirroring
    GET  /api/public/traces/{id}        verification helper

Wire contract notes learned from that same Langfuse version:
* a trace's id is settable — pass ``id`` in the ``trace-create`` body — which
  is what lets the runner score a trace it never observed live;
* ``value`` is a **number** for both NUMERIC and BOOLEAN (``true`` is rejected
  with HTTP 400), and a string only for CATEGORICAL;
* reads are eventually consistent (~10s) because ingestion lands in ClickHouse
  asynchronously, so verification must poll rather than assert immediately.
"""

from __future__ import annotations

import base64
import os
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from src.app.core.config import settings

logger = logging.getLogger(__name__)


def container_reachable_host(url: str) -> str:
    """把人填的回环地址翻译成容器里能走通的地址。

    配置记的是**宿主视角**的地址（`http://127.0.0.1:3000`——自建 Langfuse 跑在
    宿主上，宿主机上的 CLI 也用它）。但容器里的 127.0.0.1 指向容器自己，所以
    容器进程要用 host.docker.internal。放在构造函数里是因为它是所有调用方的
    唯一入口：漏掉任何一处（比如设置页的「测试连通」）就会出现「显示能用的
    地址、却报连不上」这种自相矛盾的现象。
    """
    if not os.path.exists("/.dockerenv"):
        return url
    for loopback in ("://127.0.0.1", "://localhost"):
        if loopback in url:
            return url.replace(loopback, "://host.docker.internal", 1)
    return url


def iso(timestamp: float | None = None) -> str:
    """UTC ISO-8601, which is what every Langfuse timestamp field expects."""
    moment = datetime.fromtimestamp(timestamp, tz=timezone.utc) if timestamp is not None \
        else datetime.now(timezone.utc)
    return moment.isoformat()


def clip(value: Any, limit: int = 4_000) -> str:
    """Render a value for a trace field, bounded — traces are not a log sink."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if text is None:
        return ""
    return text if len(text) <= limit else f"{text[:limit]}…(截断, 共 {len(text)} 字符)"


class LangfuseClient:
    """Minimal authenticated client. Constructed per run, closed at the end."""

    def __init__(self, *, host: str | None = None, public_key: str | None = None,
                 secret_key: str | None = None, enabled: bool | None = None,
                 timeout: float = 30.0) -> None:
        """`enabled=None` 时用 .env 的开关；设置页保存的值由调用方显式传入。"""
        self.host = container_reachable_host((host or settings.langfuse_base_url).rstrip("/"))
        self.public_key = public_key or settings.langfuse_public_key
        self.secret_key = secret_key or settings.langfuse_secret_key
        self.enabled = bool(
            (settings.langfuse_enabled if enabled is None else enabled)
            and self.host and self.public_key and self.secret_key)
        self._token = base64.b64encode(
            f"{self.public_key}:{self.secret_key}".encode()).decode() if self.enabled else ""
        # 项目 id 只查一次就缓存：它决定了界面链接的路由前缀
        self._project_id: str | None = None
        # trust_env=False: the deployment's outbound proxy must not intercept
        # calls to a Langfuse that may well be another container on localhost.
        self._client = httpx.Client(timeout=timeout, trust_env=False)

    # -- plumbing ----------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Basic {self._token}", "Content-Type": "application/json"}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LangfuseClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _post(self, path: str, payload: dict) -> dict | None:
        if not self.enabled:
            return None
        try:
            response = self._client.post(f"{self.host}{path}", headers=self._headers, json=payload)
        except Exception as exc:  # noqa: BLE001 — telemetry must never break a run
            logger.warning("langfuse POST %s failed: %s", path, exc)
            return None
        if response.status_code >= 300:
            logger.warning("langfuse POST %s -> HTTP %s: %s",
                           path, response.status_code, response.text[:300])
            return None
        try:
            return response.json()
        except json.JSONDecodeError:
            return {}

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        if not self.enabled:
            return None
        try:
            response = self._client.get(f"{self.host}{path}", headers=self._headers, params=params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse GET %s failed: %s", path, exc)
            return None
        if response.status_code >= 300:
            return None
        try:
            return response.json()
        except json.JSONDecodeError:
            return None

    # -- ingestion ---------------------------------------------------------

    def ingest(self, events: list[dict]) -> bool:
        """Send one ingestion batch; returns True when every event was accepted."""
        if not self.enabled or not events:
            return False
        body = self._post("/api/public/ingestion", {"batch": events})
        if body is None:
            return False
        errors = body.get("errors") or []
        if errors:
            logger.warning("langfuse ingestion reported %d error(s): %s",
                           len(errors), json.dumps(errors)[:400])
        return not errors

    # -- scores ------------------------------------------------------------

    def score(self, *, trace_id: str, name: str, value: float | str | bool,
              data_type: str, comment: str | None = None,
              metadata: dict | None = None, observation_id: str | None = None) -> bool:
        """Attach one score. Boolean scores MUST go over the wire as 0/1."""
        if isinstance(value, bool):
            value = 1 if value else 0
        payload: dict[str, Any] = {
            "traceId": trace_id, "name": name, "value": value, "dataType": data_type,
        }
        if comment:
            payload["comment"] = comment[:1_000]
        if metadata:
            payload["metadata"] = metadata
        if observation_id:
            payload["observationId"] = observation_id
        return self._post("/api/public/scores", payload) is not None

    # -- datasets ----------------------------------------------------------

    def upsert_dataset(self, name: str, description: str | None = None) -> bool:
        return self._post("/api/public/datasets", {
            "name": name, **({"description": description} if description else {}),
        }) is not None

    def upsert_dataset_item(self, *, item_id: str, dataset_name: str, input_: Any,
                            expected: Any = None, metadata: dict | None = None) -> bool:
        """Upsert on ``item_id`` — re-running a dataset updates in place."""
        payload: dict[str, Any] = {
            "id": item_id, "datasetName": dataset_name, "input": input_,
        }
        if expected is not None:
            payload["expectedOutput"] = expected
        if metadata:
            payload["metadata"] = metadata
        return self._post("/api/public/dataset-items", payload) is not None

    def link_run(self, *, run_name: str, dataset_item_id: str, trace_id: str) -> bool:
        return self._post("/api/public/dataset-run-items", {
            "runName": run_name, "datasetItemId": dataset_item_id, "traceId": trace_id,
        }) is not None

    def project_id(self) -> str | None:
        """自建实例的项目 id。Langfuse 的界面路由是
        `/project/<projectId>/traces/<traceId>`，少了这一段就是 404——
        所以拼链接前必须先拿到它，而不是猜。"""
        if self._project_id is not None:
            return self._project_id
        payload = self._get("/api/public/projects")
        projects = (payload or {}).get("data") or []
        self._project_id = (projects[0].get("id") if projects else None) or None
        return self._project_id

    def list_dataset_items(self, dataset_name: str, limit: int = 100) -> list[dict]:
        body = self._get("/api/public/dataset-items",
                         {"datasetName": dataset_name, "limit": limit})
        return (body or {}).get("data") or []

    # -- verification ------------------------------------------------------

    def wait_for_trace(self, trace_id: str, *, timeout_s: float = 40.0,
                       interval_s: float = 2.0, until: Any = None) -> dict | None:
        """Poll a trace until it is readable and ``until(trace)`` holds.

        Ingestion is asynchronous and the trace row becomes readable *before*
        its observations and scores are indexed — so "it returned 200" is not
        the same as "the data is there". Without ``until`` this returns the
        first readable snapshot; with it, the last snapshot seen before the
        deadline, so callers can report what they actually observed.
        """
        deadline = time.monotonic() + timeout_s
        latest: dict | None = None
        while time.monotonic() < deadline:
            body = self._get(f"/api/public/traces/{trace_id}")
            if body is not None:
                latest = body
                if until is None or until(body):
                    return body
            time.sleep(interval_s)
        return latest


def langfuse_client_for(values: dict[str, str]) -> "LangfuseClient":
    """按生效配置构造客户端（设置页优先，其次 .env）。

    唯一入口：测评 API 与就绪中心都走这条，免得不配 Langfuse 时两边判断不一致。
    """
    enabled = str(values.get("langfuse_enabled", "")).strip().lower() not in (
        "", "0", "false", "no")
    # 地址翻译在构造函数里做（container_reachable_host）
    return LangfuseClient(
        host=values.get("langfuse_base_url") or None,
        public_key=values.get("langfuse_public_key") or None,
        secret_key=values.get("langfuse_secret_key") or None,
        enabled=enabled,
    )
