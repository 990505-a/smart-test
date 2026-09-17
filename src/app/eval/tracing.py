"""Agent run → Langfuse trace tree (测评模块).

Port of dsh-eval-automation's `TraceMapper` idea onto smart-test's agent runs.
The load-bearing property is **deterministic trace identity**:
``trace_id_for(session_id)`` hashes a session id into the 32-hex id Langfuse
wants, so the runner — which sits outside the agent process — can hang scores
on the right trace without ever querying the API. Change the algorithm and
every historical score detaches, so it is deliberately duplicated verbatim
from the dsh plugin (FNV-1a over char codes, hi/lo pair, zero-padded tail).

Mapping rules (one agent run = one trace):

    agent run start        → trace (deterministic id)
    user instruction       → trace input
    LLM step               → generation `step-N` (model + usage when reported)
    tool call … result     → span `tool:<name>` (ERROR level on failure)
    agent run end          → trace output + end

The mapper is synchronous and side-effect free; {@link TraceRecorder} owns the
buffering and the single ingestion call, so a run produces exactly one batch.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from src.app.eval.langfuse_client import LangfuseClient, clip, iso

logger = logging.getLogger(__name__)


def _brief(value: Any, limit: int = 120) -> str:
    """One-line preview of a tool call's arguments, for the live log."""
    if value in (None, "", {}, []):
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]}…"


def trace_id_for(session_id: str) -> str:
    """Deterministic 32-hex Langfuse trace id for a session id.

    MUST stay byte-identical to dsh-eval-automation's ``traceIdFor`` so a
    session traced by either system scores against the same trace. Note the
    rotate is *not* masked to 16 bits — JS ``code >> 8 | code << 8`` keeps the
    shifted-out high bits, and masking would diverge for non-ASCII ids.
    """
    hi = 0x811C9DC5
    lo = 0x811C9DC5 ^ 0x9E3779B9
    for char in session_id:
        code = ord(char)
        hi = ((hi ^ (code & 0xFF)) * 0x01000193) & 0xFFFFFFFF
        lo = ((lo ^ ((code >> 8) | (code << 8))) * 0x01000193) & 0xFFFFFFFF
    return f"{hi:08x}{lo:08x}{'0' * 16}"[:32]


@dataclass
class ToolSpan:
    """One tool invocation, opened on call and closed on result."""

    call_id: str
    name: str
    arguments: Any
    started_at: float
    ended_at: float | None = None
    output: Any = None
    is_error: bool = False
    error: str | None = None

    def to_event(self, *, trace_id: str, observation_id: str) -> dict:
        end = self.ended_at or self.started_at
        body: dict[str, Any] = {
            "id": observation_id,
            "traceId": trace_id,
            "name": f"tool:{self.name}",
            "startTime": iso(self.started_at),
            "endTime": iso(end),
            "input": clip(self.arguments, 2_000),
            "output": clip(self.output, 4_000) if self.output is not None else None,
            "metadata": {"call_id": self.call_id, "duration_ms": int((end - self.started_at) * 1000)},
        }
        if self.is_error:
            body["level"] = "ERROR"
            body["statusMessage"] = clip(self.error or "tool error", 500)
        return {"id": str(uuid.uuid4()), "type": "span-create",
                "timestamp": iso(end), "body": {k: v for k, v in body.items() if v is not None}}


@dataclass
class StepGeneration:
    """One LLM call inside the run."""

    index: int
    node: str | None = None
    model: str | None = None
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    output: Any = None
    input_messages: Any = None
    usage: dict[str, Any] | None = None

    def to_event(self, *, trace_id: str, observation_id: str) -> dict:
        end = self.ended_at or self.started_at
        body: dict[str, Any] = {
            "id": observation_id,
            "traceId": trace_id,
            "name": f"step-{self.index}",
            "startTime": iso(self.started_at),
            "endTime": iso(end),
            "output": clip(self.output, 4_000) if self.output is not None else None,
            "metadata": {"node": self.node, "duration_ms": int((end - self.started_at) * 1000)},
        }
        if self.model:
            body["model"] = self.model
        if self.input_messages is not None:
            body["input"] = self.input_messages
        if self.usage:
            body["usageDetails"] = self.usage
        return {"id": str(uuid.uuid4()), "type": "generation-create",
                "timestamp": iso(end), "body": {k: v for k, v in body.items() if v is not None}}


@dataclass
class RunTrace:
    """Accumulates one agent run, then emits a single Langfuse batch."""

    session_id: str
    name: str = "smart-test-eval"
    input: str | None = None
    output: str | None = None
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    environment: str | None = None
    release: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: list[ToolSpan] = field(default_factory=list)
    steps: list[StepGeneration] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def trace_id(self) -> str:
        return trace_id_for(self.session_id)

    def add_event(self, name: str, *, level: str = "DEFAULT", message: str = "",
                  metadata: dict | None = None) -> None:
        """Point-in-time marker (errors, retries, guardrails)."""
        self.events.append({
            "name": name, "level": level, "message": message,
            "metadata": metadata or {}, "at": time.time(),
        })

    def to_ingestion_batch(self) -> list[dict]:
        """Fold everything into trace-create + child observations."""
        end = self.ended_at or time.time()
        trace_body: dict[str, Any] = {
            "id": self.trace_id,
            "name": self.name,
            "timestamp": iso(self.started_at),
            "input": clip(self.input, 8_000) if self.input is not None else None,
            "output": clip(self.output, 8_000) if self.output is not None else None,
            "metadata": {**self.metadata, "session_id": self.session_id},
            "latency": round(end - self.started_at, 3),
        }
        if self.environment:
            trace_body["environment"] = self.environment
        if self.release:
            trace_body["release"] = self.release
        if self.tags:
            trace_body["tags"] = self.tags

        batch = [{
            "id": str(uuid.uuid4()), "type": "trace-create",
            "timestamp": iso(self.started_at),
            "body": {k: v for k, v in trace_body.items() if v is not None},
        }]
        for step in self.steps:
            batch.append(step.to_event(trace_id=self.trace_id, observation_id=uuid.uuid4().hex))
        for span in self.tools:
            batch.append(span.to_event(trace_id=self.trace_id, observation_id=uuid.uuid4().hex))
        for event in self.events:
            batch.append({
                "id": str(uuid.uuid4()), "type": "event-create", "timestamp": iso(event["at"]),
                "body": {
                    "id": uuid.uuid4().hex, "traceId": self.trace_id, "name": event["name"],
                    "level": event["level"],
                    "statusMessage": clip(event["message"], 1_000) or None,
                    "metadata": event["metadata"],
                    "startTime": iso(event["at"]),
                },
            })
        return [{**event, "body": {k: v for k, v in event["body"].items() if v is not None}}
                for event in batch]

    def upload(self, client: LangfuseClient) -> bool:
        """Emit the whole run as one ingestion batch."""
        return client.ingest(self.to_ingestion_batch())


# ---------------------------------------------------------------------------
# Building a RunTrace from a LangGraph event stream
# ---------------------------------------------------------------------------

def _message_text(message: Any) -> str:
    """Flatten a LangChain message's content (str, or a list of content blocks)."""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part)


def _normalize_usage(usage: Any) -> dict[str, Any] | None:
    """Map LangChain ``usage_metadata`` onto Langfuse ``usageDetails`` keys."""
    if not isinstance(usage, dict):
        return None
    details: dict[str, Any] = {}
    for source, target in (
        ("input_tokens", "input"), ("output_tokens", "output"), ("total_tokens", "total"),
    ):
        if isinstance(usage.get(source), int):
            details[target] = usage[source]
    cache = usage.get("input_token_details")
    if isinstance(cache, dict):
        if isinstance(cache.get("cache_read"), int):
            details["cache_read"] = cache["cache_read"]
        if isinstance(cache.get("cache_creation"), int):
            details["cache_write"] = cache["cache_creation"]
    reasoning = usage.get("output_token_details")
    if isinstance(reasoning, dict) and isinstance(reasoning.get("reasoning"), int):
        details["reasoning"] = reasoning["reasoning"]
    return details or None


def _node_of(meta: dict) -> str | None:
    """The graph node a generation belongs to.

    ``checkpoint_ns`` disambiguates subgraph instances (``model:<uuid>``) but
    changes every run, so the stable ``langgraph_node`` is preferred and the
    namespace is kept only as a fallback.
    """
    node = meta.get("langgraph_node")
    if isinstance(node, str) and node:
        return node
    namespace = meta.get("checkpoint_ns")
    if isinstance(namespace, str) and namespace:
        return namespace.split(":")[0]
    return None


def _model_of(meta: dict) -> str | None:
    for key in ("ls_model_name", "ls_provider"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class TraceCollector:
    """Fold a LangGraph SSE stream into a {@link RunTrace}.

    Consumes the modes the runner subscribes to. The server expands
    ``messages`` into two channel names, so both must be handled:

    * ``messages/metadata`` — sent once, a ``{message_id: {metadata: …}}`` map.
      This is where ``ls_model_name`` / ``ls_provider`` / ``langgraph_node``
      live; the chunk stream itself carries no model identity.
    * ``messages/partial`` — token chunks, as a **list** of message dicts whose
      ``id`` keys back into the metadata map. Collapsed per message id so one
      LLM call becomes one generation regardless of chunk count.
    * ``updates`` — node-level state deltas. The complete message lands here,
      which is the only place ``usage_metadata`` and ``tool_calls`` are
      guaranteed to be populated, so tool spans and token usage are read from
      this channel rather than reassembled from chunks.

    Metadata in this deployment does not always carry ``usage_metadata``
    (the OpenAI-compatible endpoints behind the platform omit it on chunks),
    which is why usage is taken from the ``updates`` message when present and
    simply left off when not — a trace with no usage is honest; a fabricated
    one is not.
    """

    def __init__(self, session_id: str, *, instruction: str,
                 note: Callable[[str], None] | None = None, **trace_options: Any) -> None:
        self.trace = RunTrace(session_id=session_id, input=instruction, **trace_options)
        self._note = note
        self._open_calls: dict[str, ToolSpan] = {}
        self._call_order: list[str] = []
        self._steps: dict[str, StepGeneration] = {}
        self._step_order: list[str] = []
        self._message_meta: dict[str, dict] = {}
        self._last_assistant_text = ""

    def _notify(self, text: str) -> None:
        """One human line about what the agent is doing *right now*.

        Live progress must never be able to break the run it observes, so this
        swallows everything.
        """
        if self._note is None:
            return
        try:
            self._note(text)
        except Exception:  # noqa: BLE001
            logger.debug("live note 回调失败", exc_info=True)

    # -- stream handling ---------------------------------------------------

    def handle(self, mode: str, payload: Any, metadata: dict | None = None) -> None:
        if mode.startswith("messages/metadata"):
            self._on_message_metadata(payload)
        elif mode.startswith("messages"):
            self._on_message_chunk(payload, metadata or {})
        elif mode.startswith("updates"):
            self._on_update(payload)

    def _on_message_metadata(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for message_id, entry in payload.items():
            meta = (entry or {}).get("metadata") if isinstance(entry, dict) else None
            if isinstance(meta, dict):
                self._message_meta[str(message_id)] = meta

    def _on_message_chunk(self, payload: Any, metadata: dict) -> None:
        # `messages` arrives as a [chunk, metadata] tuple for the SSE form that
        # is not split into partial/metadata channels; `messages/partial`
        # arrives as a bare list of chunks.
        if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[0], dict) \
                and isinstance(payload[1], dict) and "id" not in payload[1]:
            chunks, meta = [payload[0]], {**payload[1], **metadata}
        elif isinstance(payload, list):
            chunks, meta = payload, metadata
        else:
            chunks, meta = [payload], metadata

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            message_id = str(chunk.get("id") or meta.get("message_id") or "step")
            chunk_meta = {**self._message_meta.get(message_id, {}), **meta}
            self._apply_chunk(message_id, chunk, chunk_meta)

    def _apply_chunk(self, message_id: str, chunk: dict, meta: dict) -> None:
        step = self._steps.get(message_id)
        if step is None:
            step = StepGeneration(
                index=len(self._steps) + 1,
                node=_node_of(meta),
                model=_model_of(meta),
                input_messages=None,
            )
            self._steps[message_id] = step
            self._step_order.append(message_id)
            self._notify(f"模型生成中 · {step.model or '未知模型'}"
                         + (f" · {step.node}" if step.node else ""))
        step.ended_at = time.time()
        text = _message_text(chunk)
        if text:
            step.output = (step.output or "") + text
        if step.model is None:
            step.model = _model_of(meta)

    def _on_update(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        for node, delta in payload.items():
            if not isinstance(delta, dict):
                continue
            for message in (delta.get("messages") or []):
                if not isinstance(message, dict):
                    continue
                self._consume_message(node, message)

    def _consume_message(self, node: str, message: dict) -> None:
        kind = message.get("type") or message.get("role")
        if kind in ("ai", "assistant"):
            tool_calls = [call for call in (message.get("tool_calls") or []) if isinstance(call, dict)]
            text = _message_text(message)
            if text:
                self._last_assistant_text = text

            # There is no message id linking this complete message back to a
            # chunk-built step, so attribute the payload to the newest step of
            # this node (the agent's last call) and otherwise to the newest
            # step overall — the common case is one LLM call per node.
            step = self._newest_step_for(node)
            if step is not None:
                usage = _normalize_usage(message.get("usage_metadata"))
                if usage:
                    step.usage = usage
                model_name = (message.get("response_metadata") or {}).get("model_name")
                if step.model is None and isinstance(model_name, str):
                    step.model = model_name
                if step.node is None:
                    step.node = node
                if text and not step.output:
                    step.output = text
                    step.ended_at = step.ended_at or time.time()

            for call in tool_calls:
                call_id = str(call.get("id") or f"anon-{len(self._open_calls)}")
                span = ToolSpan(
                    call_id=call_id,
                    name=str(call.get("name") or "unknown"),
                    arguments=call.get("args") or call.get("arguments"),
                    started_at=time.time(),
                )
                self._open_calls[call_id] = span
                self._call_order.append(call_id)
                self.trace.tools.append(span)
                self._notify(f"调用 {span.name}({_brief(span.arguments)})")
        elif kind in ("tool", "function"):
            call_id = str(message.get("tool_call_id") or message.get("id") or "")
            span = self._open_calls.pop(call_id, None)
            if span is None and self._call_order:
                # Result without a matched call (history replay): pair FIFO.
                fallback = next((cid for cid in self._call_order if cid in self._open_calls), None)
                if fallback is not None:
                    span = self._open_calls.pop(fallback)
                    self._call_order = [cid for cid in self._call_order if cid != fallback]
            text = _message_text(message) or clip(message.get("content"), 4_000)
            status = str(message.get("status") or "")
            is_error = status == "error" or bool(message.get("is_error"))
            if span is None:
                span = ToolSpan(call_id=call_id or "unpaired",
                                name=str(message.get("name") or "unknown"),
                                arguments=None, started_at=time.time())
                self.trace.tools.append(span)
            span.ended_at = time.time()
            span.output = text
            span.is_error = is_error
            if is_error:
                span.error = text
            took = (span.ended_at - span.started_at) if span.started_at else 0.0
            self._notify(f"{span.name} {took:.1f}s 返回 {len(text or '')} 字符"
                         + (" · 失败" if is_error else ""))
        elif kind in ("human", "user"):
            if self.trace.input is None:
                self.trace.input = _message_text(message)

    def _newest_step_for(self, node: str) -> StepGeneration | None:
        for step_id in reversed(self._step_order):
            step = self._steps[step_id]
            if step.node == node:
                return step
        for step_id in reversed(self._step_order):
            return self._steps[step_id]
        return None

    # -- lifecycle ---------------------------------------------------------

    def finish(self, *, output: str | None = None, error: str | None = None) -> RunTrace:
        now = time.time()
        for span in self.trace.tools:
            if span.ended_at is None:
                span.ended_at = now
                span.is_error = True
                span.error = span.error or "run ended before a tool result arrived"
        self.trace.steps = [self._steps[key] for key in self._step_order]
        self.trace.output = output if output is not None else self._last_assistant_text
        self.trace.ended_at = now
        if error:
            self.trace.add_event("agent-error", level="ERROR", message=error)
        return self.trace

    # -- convenience for the scorers --------------------------------------

    @property
    def tool_names(self) -> list[str]:
        return [span.name for span in self.trace.tools]

    @property
    def tool_errors(self) -> int:
        return sum(1 for span in self.trace.tools if span.is_error)


async def iter_sse_lines(lines: Any) -> AsyncIterator[tuple[str, Any]]:
    """Yield ``(event, data)`` pairs as they arrive.

    LangGraph emits ``event: <mode>`` followed by ``data: <json>``; heartbeat
    comments and blank separators are skipped.

    Streaming (rather than materialising the whole response first) is what lets
    the live-progress log show "agent 正在调用某个工具" while the run is still
    going — a single item can take minutes, and buffering made the UI silent
    until it ended.
    """
    current_event: str | None = None
    async for raw in lines:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        line = line.rstrip("\n").rstrip("\r")
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
            continue
        if line.startswith("data:"):
            data = line[len("data:"):].strip()
            if data == "":
                continue
            try:
                yield (current_event or "message", json.loads(data))
            except json.JSONDecodeError:
                continue
            continue
        if line == "":
            current_event = None


async def parse_sse_lines(lines: Any) -> list[tuple[str, Any]]:
    """Materialise {@link iter_sse_lines} into a list while the stream is open."""
    return [event async for event in iter_sse_lines(lines)]
