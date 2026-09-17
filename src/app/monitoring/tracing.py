"""监控（日常智能体使用链路 → Langfuse）。

与测评（``src/app/eval``）是**两条线**：

* 测评：跑评测集时把每条用例的 run 上报到 **测评组织** 的 Langfuse，服务于回归门禁；
* 监控：日常对话（用例生成 / Unity / Web-UI / 代码分析）把每个 run 上报到 **监控组织**
  的 Langfuse，服务于"这次为什么答歪了"的排查。

两者用不同的 key（设置页「Langfuse 监控配置」vs「Langfuse（测评）」），互不干扰。
trace 的 ``sessionId`` 指向会话（thread），所以在 Langfuse 里能按会话把多轮串起来看。

实现要点：
* 复用 ``eval/tracing.py`` 的 RunTrace / StepGeneration / ToolSpan 与
  ``eval/langfuse_client.py`` 的客户端（同一套 Langfuse 4.x wire 契约已验证过）；
* 采集靠中间件 hooks（``before_agent`` / ``wrap_model_call`` / ``wrap_tool_call`` /
  ``after_agent``），所以 agent 侧不需要任何改动就能看到"模型调用 + 工具调用"的完整时间线；
* 上报是**尽力而为**：任何异常只写日志，绝不影响对话本身（监控挂了不能把聊天弄挂）。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import anyio
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.app.core.config import settings
from src.app.eval.langfuse_client import LangfuseClient, clip, iso
from src.app.eval.tracing import RunTrace, StepGeneration, ToolSpan

logger = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
_ENV_CACHE_TTL = 15.0
_env_cache: dict[str, Any] = {"at": 0.0, "values": {}}

#: 监控配置的 .env 键 → 字段名（设置页保存的落点）
_ENV_KEYS = {
    "LANGFUSE_MONITOR_ENABLED": "enabled",
    "LANGFUSE_MONITOR_BASE_URL": "base_url",
    "LANGFUSE_MONITOR_PUBLIC_KEY": "public_key",
    "LANGFUSE_MONITOR_SECRET_KEY": "secret_key",
    "LANGFUSE_MONITOR_ENVIRONMENT": "environment",
}

#: 单条 generation 只留最近一轮的输入（trace 不是日志仓库）
_INPUT_CLIP = 3_000
_OUTPUT_CLIP = 3_000
_MAX_TRACES = 64  # 进程内同时追踪的会话上限（防御性）


@dataclass
class MonitorConfig:
    enabled: bool
    base_url: str
    public_key: str
    secret_key: str
    environment: str

    @property
    def usable(self) -> bool:
        return bool(self.enabled and self.base_url and self.public_key and self.secret_key)


def _read_env_file() -> dict[str, str]:
    """直读 .env（设置页保存的目标），15 秒缓存——改完不用重启容器。"""
    now = time.monotonic()
    if now - _env_cache["at"] < _ENV_CACHE_TTL and _env_cache["values"]:
        return _env_cache["values"]
    values: dict[str, str] = {}
    try:
        if _ENV_PATH.exists():
            for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                name, _, value = stripped.partition("=")
                if name.strip() in _ENV_KEYS:
                    values[name.strip()] = value.strip()
    except OSError as exc:  # noqa: BLE001
        logger.debug("读取 .env 失败（监控配置回退进程环境）: %s", exc)
    _env_cache.update({"at": now, "values": values})
    return values


def monitor_config() -> MonitorConfig:
    """生效中的监控配置：.env（设置页写的）优先，其次进程环境。"""
    from_file = _read_env_file()
    raw: dict[str, str] = {}
    for env_name, field in _ENV_KEYS.items():
        raw[field] = from_file.get(env_name) or str(getattr(settings, f"langfuse_monitor_{field}", "") or "")
    enabled = raw.get("enabled", "").strip().lower() not in ("", "0", "false", "no", "off")
    return MonitorConfig(
        enabled=enabled,
        base_url=raw.get("base_url", "").strip(),
        public_key=raw.get("public_key", "").strip(),
        secret_key=raw.get("secret_key", "").strip(),
        environment=raw.get("environment", "").strip() or "monitor",
    )


def monitor_client() -> LangfuseClient | None:
    config = monitor_config()
    if not config.usable:
        return None
    # LangfuseClient 自己会把容器内的回环地址翻译成 host.docker.internal
    return LangfuseClient(host=config.base_url, public_key=config.public_key,
                          secret_key=config.secret_key, enabled=True)


def invalidate_monitor_env_cache() -> None:
    _env_cache.update({"at": 0.0, "values": {}})


class MonitorTrace(RunTrace):
    """一次 run 一条 trace；``sessionId`` 指回会话，Langfuse 里可按会话聚合。

    RunTrace 的 ``trace_id`` 由 session_id 确定性派生——监控这里 session_id 带
    run 序号，所以每轮对话是独立 trace（测评那边才需要"同一会话同一条 trace"，
    因为分数要挂回正确的地方）。
    """

    def to_ingestion_batch(self) -> list[dict]:
        batch = super().to_ingestion_batch()
        thread_id = self.metadata.get("thread_id")
        agent = self.metadata.get("agent")
        for event in batch:
            if event.get("type") == "trace-create":
                if thread_id:
                    event["body"]["sessionId"] = thread_id
                if agent:
                    event["body"].setdefault("tags", [])
                    event["body"]["tags"] = [agent]
        return batch


def _text_of_message(message: Any, limit: int = _INPUT_CLIP) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, list):
        parts = [str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = "\n".join(p for p in parts if p)
    return clip(content, limit)


def _usage_of(message: Any) -> dict[str, Any] | None:
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None
    details: dict[str, Any] = {}
    for source, target in (("input_tokens", "input"), ("output_tokens", "output"),
                           ("total_tokens", "total")):
        if isinstance(usage.get(source), int):
            details[target] = usage[source]
    cache = usage.get("input_token_details")
    if isinstance(cache, dict) and isinstance(cache.get("cache_read"), int):
        details["cache_read"] = cache["cache_read"]
    return details or None


class MonitorMiddleware(AgentMiddleware):
    """把一个 run 的模型/工具调用上报到监控 Langfuse（尽力而为）。"""

    def __init__(self, agent_name: str, *, enabled: bool | None = None) -> None:
        self.agent_name = agent_name
        self._force_disabled = enabled is False
        self._traces: dict[str, MonitorTrace] = {}
        self._run_seq: dict[str, int] = {}

    # -- 进程内状态 ---------------------------------------------------------

    def _thread_id(self) -> str:
        try:
            from langgraph.config import get_config

            return str((get_config().get("configurable") or {}).get("thread_id") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _start(self, thread_id: str) -> MonitorTrace | None:
        if self._force_disabled:
            return None
        if len(self._traces) >= _MAX_TRACES:
            self._traces.clear()  # 防御：异常退出留下的残迹不该无限增长
        seq = self._run_seq.get(thread_id, 0) + 1
        self._run_seq[thread_id] = seq
        trace = MonitorTrace(
            session_id=f"{thread_id or 'no-thread'}#{seq}",
            name=f"{self.agent_name}",
            environment=monitor_config().environment,
            metadata={"agent": self.agent_name, "thread_id": thread_id, "turn": seq},
        )
        self._traces[thread_id] = trace
        return trace

    def _current(self) -> MonitorTrace | None:
        thread_id = self._thread_id()
        trace = self._traces.get(thread_id)
        if trace is None:
            trace = self._start(thread_id)
        return trace

    # -- hooks --------------------------------------------------------------

    def before_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        try:
            if not monitor_config().enabled:
                return None
            thread_id = self._thread_id()
            stale = self._traces.pop(thread_id, None)
            if stale is not None:  # 上一轮没走到 after_agent（中断/异常）→ 先送出去
                self._upload(stale)
            trace = self._start(thread_id)
            if trace is not None and isinstance(state, dict):
                messages = state.get("messages") or []
                for message in messages:
                    if getattr(message, "type", "") == "human" or message.__class__.__name__ == "HumanMessage":
                        trace.input = _text_of_message(message, 4_000)
                        break
        except Exception as exc:  # noqa: BLE001
            logger.debug("monitor before_agent failed: %s", exc)
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        return self.before_agent(state, runtime)

    def after_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        try:
            thread_id = self._thread_id()
            trace = self._traces.pop(thread_id, None)
            if trace is None:
                return None
            if isinstance(state, dict):
                messages = state.get("messages") or []
                for message in reversed(messages):
                    if getattr(message, "type", "") == "ai" or message.__class__.__name__ == "AIMessage":
                        trace.output = _text_of_message(message, 4_000)
                        break
            trace.ended_at = time.time()
            self._upload(trace)
        except Exception as exc:  # noqa: BLE001
            logger.debug("monitor after_agent failed: %s", exc)
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> None:  # noqa: ANN001
        """异步路径把上传丢到线程里——上报是网络 IO，不能卡住事件循环。"""
        try:
            thread_id = self._thread_id()
            trace = self._traces.pop(thread_id, None)
            if trace is None:
                return None
            if isinstance(state, dict):
                messages = state.get("messages") or []
                for message in reversed(messages):
                    if getattr(message, "type", "") == "ai" or message.__class__.__name__ == "AIMessage":
                        trace.output = _text_of_message(message, 4_000)
                        break
            trace.ended_at = time.time()
            await anyio.to_thread.run_sync(self._upload, trace)
        except Exception as exc:  # noqa: BLE001
            logger.debug("monitor aafter_agent failed: %s", exc)
        return None

    def wrap_model_call(self, request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> Any:
        return self._instrument(request, lambda: handler(request), request, is_async=False)

    async def awrap_model_call(self, request: ModelRequest,
                               handler: Callable[[ModelRequest], Any]) -> Any:
        return await self._instrument_async(request, handler)

    def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return self._instrument_tool(request, lambda: handler(request), is_async=False)

    async def awrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return await self._instrument_tool_async(request, handler)

    # -- 采集 ---------------------------------------------------------------

    def _record_generation(self, request: ModelRequest, started: float, ended: float,
                           response: Any = None, error: Exception | None = None) -> None:
        trace = self._current()
        if trace is None:
            return
        model_name = getattr(request.model, "model_name", None) or getattr(request.model, "model", None)
        step = StepGeneration(
            index=len(trace.steps) + 1,
            node=self.agent_name,
            model=str(model_name) if model_name else None,
            started_at=started,
            ended_at=ended,
        )
        messages = getattr(request, "messages", None) or []
        for message in reversed(list(messages)):
            if getattr(message, "type", "") == "human" or message.__class__.__name__ == "HumanMessage":
                step.input_messages = _text_of_message(message)
                break
        if error is not None:
            step.output = f"[error] {error}"
            trace.add_event("model-error", level="ERROR", message=str(error)[:500],
                            metadata={"agent": self.agent_name})
        elif response is not None:
            result = getattr(response, "result", None) or []
            for message in result:
                text = _text_of_message(message, _OUTPUT_CLIP)
                tool_calls = getattr(message, "tool_calls", None) or []
                if tool_calls:
                    names = ", ".join(str(tc.get("name")) for tc in tool_calls if isinstance(tc, dict))
                    text = (text + f"\n[tool_calls: {names}]").strip()
                step.output = text
                usage = _usage_of(message)
                if usage:
                    step.usage = usage
            if not result:
                step.output = None
        trace.steps.append(step)

    def _record_tool(self, tool_call: dict, started: float, ended: float,
                     output: Any = None, error: Exception | None = None) -> None:
        trace = self._current()
        if trace is None:
            return
        span = ToolSpan(
            call_id=str(tool_call.get("id") or uuid.uuid4().hex[:8]),
            name=str(tool_call.get("name") or "tool"),
            arguments=tool_call.get("args"),
            started_at=started,
            ended_at=ended,
            is_error=error is not None,
            error=str(error)[:500] if error is not None else None,
        )
        if output is not None:
            span.output = clip(output, 4_000)
        trace.tools.append(span)

    def _instrument(self, request: ModelRequest, call: Callable[[], Any], *args, **kwargs) -> Any:
        started = time.time()
        try:
            response = call()
        except Exception as exc:
            self._record_generation(request, started, time.time(), error=exc)
            raise
        self._record_generation(request, started, time.time(), response=response)
        return response

    async def _instrument_async(self, request: ModelRequest, handler: Callable[[Any], Any]) -> Any:
        started = time.time()
        try:
            response = await handler(request)
        except Exception as exc:
            self._record_generation(request, started, time.time(), error=exc)
            raise
        self._record_generation(request, started, time.time(), response=response)
        return response

    def _instrument_tool(self, request: Any, call: Callable[[], Any], is_async: bool) -> Any:
        started = time.time()
        tool_call = getattr(request, "tool_call", None) or {}
        try:
            result = call()
        except Exception as exc:
            self._record_tool(tool_call, started, time.time(), error=exc)
            raise
        self._record_tool(tool_call, started, time.time(), output=getattr(result, "content", None))
        return result

    async def _instrument_tool_async(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        started = time.time()
        tool_call = getattr(request, "tool_call", None) or {}
        try:
            result = await handler(request)
        except Exception as exc:
            self._record_tool(tool_call, started, time.time(), error=exc)
            raise
        self._record_tool(tool_call, started, time.time(), output=getattr(result, "content", None))
        return result

    # -- 上报 ---------------------------------------------------------------

    def _upload(self, trace: MonitorTrace) -> None:
        """一个 run 一个 ingestion 批次；失败只记日志。"""
        try:
            if not trace.steps and not trace.tools:
                return  # 什么都没采集到就不产生空 trace
            client = monitor_client()
            if client is None:
                return
            try:
                if trace.ended_at is None:
                    trace.ended_at = time.time()
                ok = trace.upload(client)
                if not ok:
                    logger.warning("监控 trace 上报未完全成功（agent=%s）", self.agent_name)
            finally:
                client.close()
        except Exception as exc:  # noqa: BLE001 — 监控挂了不能影响对话
            logger.warning("监控 trace 上报失败（agent=%s）: %s", self.agent_name, exc)


def monitor_enabled() -> bool:
    return monitor_config().usable
