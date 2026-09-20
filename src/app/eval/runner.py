"""Eval runner core (测评模块).

Drives dataset items through the platform's agents, scores each run, and hangs
the scores on a Langfuse trace whose id was derived deterministically from the
run's session id — the property that lets this process, which never observed
the agent live, still score the right trace.

Both the agent transport and the score sink sit behind seams
({@link AgentDriver}, {@link ScoreReporter}) so the whole loop runs offline in
tests, exactly like dsh-eval-automation's runner.

Isolation model: one thread per item. The agent runs in the LangGraph server
process, so items cannot leak state through this one; each gets a fresh
thread_id and its own trace.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from src.app.core.config import settings
from src.app.eval.dataset import EvalDataset, EvalItem, item_id_for
from src.app.eval.langfuse_client import LangfuseClient
from src.app.eval.scorers import RunRecord, ScoreResult, score_run
from src.app.eval.tracing import TraceCollector, iter_sse_lines

logger = logging.getLogger(__name__)


@dataclass
class ItemRow:
    """One row of the outcome table."""

    item: EvalItem
    trace_id: str
    scores: list[ScoreResult]
    duration_ms: int
    thread_id: str | None = None
    error: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)


@dataclass
class DatasetRunOutcome:
    dataset: str
    run_name: str
    rows: list[ItemRow]
    agent: str

    @property
    def all_rows_scored(self) -> bool:
        return all(row.error is None for row in self.rows)


class AgentDriver(Protocol):
    """Executes one item; the production driver talks to the LangGraph API."""

    async def run(self, item: EvalItem, agent: str, *, thread_id: str) -> RunRecord: ...


class ScoreReporter(Protocol):
    def report_trace(self, trace: RunTrace) -> None: ...

    def report(self, trace_id: str, score: ScoreResult, item_id: str) -> None: ...

    async def link(self, trace_id: str, dataset_item_id: str, run_name: str) -> None: ...

    def flush(self) -> None: ...


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run_dataset(*, dataset: EvalDataset, scorers: list, driver: AgentDriver,
                      reporter: ScoreReporter | None = None, concurrency: int = 1,
                      run_name: str | None = None, on_item: Any = None,
                      on_start: Any = None) -> DatasetRunOutcome:
    """Run a whole dataset; never raises on item failure — failures become rows.

    ``on_start`` / ``on_item`` are observation hooks (CLI prints, platform UI
    persists each row as it lands). They may be sync **or** async: the platform
    API needs to write to the database, the CLI just prints.
    """
    label = run_name or f"{dataset.name}@{time.strftime('%Y%m%d-%H%M%S')}"
    rows: list[ItemRow] = []
    lock = asyncio.Lock()

    async def notify(callback: Any, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if inspect.isawaitable(result):
            await result

    async def work(item: EvalItem) -> None:
        started = time.monotonic()
        # LangGraph rejects non-UUID thread ids, so the readable label lives in
        # metadata and the id itself is opaque. The trace id is derived from
        # this thread id, which is what keeps runner-side scoring aligned with
        # anything tracing the same session in-process.
        thread_id = str(uuid.uuid4())
        # 开始事件在锁外发：它只写进度文件，不碰数据库；并发时几条用例同时在跑，
        # 界面正是要看到"这几条正在跑"。
        await notify(on_start, item)
        try:
            record = await driver.run(item, dataset.agent, thread_id=thread_id)
            scores = await score_run(scorers, record)
            row = ItemRow(
                item=item, trace_id=record.trace.trace_id, scores=scores,
                duration_ms=record.duration_ms, thread_id=thread_id,
                evidence=record.evidence, tool_names=record.tool_names,
            )
            # Trace first, then the scores that hang on it: the score endpoints
            # do not require the trace to exist yet, but uploading in this order
            # keeps a partially-failed upload diagnosable (missing scores vs.
            # missing trace are different bug reports).
            if reporter is not None:
                reporter.report_trace(record.trace)
                for score in scores:
                    reporter.report(record.trace.trace_id, score, item.id)
                if item.langfuse_item_id is not None:
                    await reporter.link(record.trace.trace_id, item.langfuse_item_id, label)
        except Exception as exc:  # noqa: BLE001
            logger.exception("eval item %s failed", item.id)
            row = ItemRow(item=item, trace_id="", scores=[],
                          duration_ms=int((time.monotonic() - started) * 1000),
                          thread_id=thread_id, error=str(exc)[:1_000])
        # 落库的钩子在锁里跑：同一个 AsyncSession 不能被两条用例同时使用
        async with lock:
            rows.append(row)
            await notify(on_item, item, row)

    await _pool(dataset.items, concurrency, work)
    if reporter is not None:
        reporter.flush()
    # 按数据集顺序输出，便于人读（并发下完成顺序是乱的）
    order = {item.id: index for index, item in enumerate(dataset.items)}
    rows.sort(key=lambda row: order.get(row.item.id, 0))
    return DatasetRunOutcome(dataset=dataset.name, run_name=label, rows=rows, agent=dataset.agent)


async def _pool(items: list[EvalItem], size: int, work: Any) -> None:
    """Minimal semaphore pool; the LLM endpoints rate-limit long before this."""
    limit = max(1, size)
    index = 0
    guard = asyncio.Lock()

    async def worker() -> None:
        nonlocal index
        while True:
            async with guard:
                if index >= len(items):
                    return
                item = items[index]
                index += 1
            await work(item)

    await asyncio.gather(*[worker() for _ in range(min(limit, len(items)))])


# ---------------------------------------------------------------------------
# Production driver: LangGraph API
# ---------------------------------------------------------------------------

class LangGraphDriver:
    """Drive one graph run per item over the LangGraph server's HTTP API.

    Subscribes to ``messages`` + ``updates`` so the trace gets per-step model
    identity, token usage, tool calls and tool results — the same shape
    dsh-eval-automation gets from its in-process telemetry plugin, except here
    it is reconstructed from the stream, because the agent runs elsewhere.
    """

    def __init__(self, *, base_url: str | None = None, timeout_s: float = 1_800.0,
                 recursion_limit: int = 300, space_id: str = "default",
                 release: str | None = None, environment: str | None = None,
                 note: Any = None) -> None:
        self.base_url = (base_url or settings.langgraph_api_url).rstrip("/")
        self.timeout_s = timeout_s
        self.recursion_limit = recursion_limit
        self.space_id = space_id
        self.release = release
        self.environment = environment or settings.langfuse_environment
        #: ``note(item, text)``：执行过程中的一步步（工具调用/模型生成），
        #: 给实时进度用。必须是同步回调——它在 SSE 读取循环里被调用。
        self.note = note

    async def run(self, item: EvalItem, agent: str, *, thread_id: str) -> RunRecord:
        started = time.monotonic()
        collector = TraceCollector(
            thread_id, instruction=item.input,
            name=f"smart-test-eval:{item.id}",
            environment=self.environment, release=self.release,
            tags=["eval", f"item:{item.id}"],
            metadata={"item_id": item.id, "agent": agent, "dataset::item": item.id},
            note=(lambda text: self.note(item, text)) if self.note else None,
        )
        timeout = httpx.Timeout(connect=20.0, read=self.timeout_s, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            created = await client.post(f"{self.base_url}/threads", json={
                "thread_id": thread_id,
                "metadata": {"source": "eval", "agent": agent, "item_id": item.id},
                "if_exists": "do_nothing",
            })
            created.raise_for_status()

            payload = {
                "assistant_id": agent,
                "input": {"messages": [{"type": "human", "content": item.input}]},
                "config": {
                    "recursion_limit": self.recursion_limit,
                    "configurable": {"space_id": self.space_id},
                },
                "stream_mode": ["updates", "messages"],
                "stream_subgraphs": True,
            }
            error: str | None = None
            async with client.stream(
                "POST", f"{self.base_url}/threads/{thread_id}/runs/stream", json=payload,
            ) as response:
                if response.status_code >= 300:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(f"LangGraph run 启动失败 HTTP {response.status_code}: {body[:400]}")
                # 事件**边到边处理**（而不是先攒成一个列表）：整个 item 的摘要、
                # 每一步工具调用都要立刻出现在实时进度里。
                async for mode, data in iter_sse_lines(response.aiter_lines()):
                    if mode in ("error", "metadata", "end"):
                        if mode == "error":
                            error = json.dumps(data, ensure_ascii=False)[:1_000]
                        continue
                    # Every other channel is forwarded verbatim: the server splits
                    # `messages` into `messages/metadata` + `messages/partial`, so
                    # matching on exact mode names here would silently drop the
                    # generation channel.
                    collector.handle(mode, data)

        duration_ms = int((time.monotonic() - started) * 1000)
        trace = collector.finish(error=error)
        trace.metadata["duration_ms"] = duration_ms
        if error:
            trace.metadata["error"] = error
        evidence = _collect_evidence(trace)
        record = RunRecord(item=item, trace=trace, duration_ms=duration_ms,
                           error=error, evidence=evidence)
        if not trace.output and not trace.steps:
            record.error = record.error or "agent 未产生任何 LLM 步骤或输出（图未注册？）"
        return record


def _collect_evidence(trace: Any) -> list[dict[str, Any]]:
    """Harvest Playwright artifacts referenced by the run's tool outputs.

    Evidence is what `expected.evidence` scores against, so it has to come from
    what actually ran, not from a directory scan that a stale run could satisfy.
    """
    seen: dict[str, dict[str, Any]] = {}
    for span in trace.tools:
        if span.name != "webui_run_spec" or not isinstance(span.output, str):
            continue
        text = span.output.strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        run_id = payload.get("runner_run_id")
        for artifact in payload.get("artifacts") or []:
            if not isinstance(artifact, dict):
                continue
            name = str(artifact.get("name") or "")
            if name:
                seen[name] = {**artifact, "runner_run_id": run_id}
    return list(seen.values())


# ---------------------------------------------------------------------------
# Langfuse reporting
# ---------------------------------------------------------------------------

class LangfuseReporter:
    """Report scores against deterministic trace ids; mirror + link datasets.

    Mirrors dsh-eval-automation's `LangfuseReporter`: the dataset is upserted
    into Langfuse so the UI shows a DatasetRun per evaluation batch, and each
    item's trace is linked into that run by name.
    """

    def __init__(self, client: LangfuseClient, dataset_name: str | None = None) -> None:
        self.client = client
        self.dataset_name = dataset_name
        self.reported: list[tuple[str, ScoreResult, str]] = []
        self.traces_uploaded = 0
        self.trace_failures = 0
        self.link_failures = 0

    def report_trace(self, trace: RunTrace) -> None:
        """Upload the run's whole trace tree as one ingestion batch."""
        if not self.client.enabled:
            return
        if trace.upload(self.client):
            self.traces_uploaded += 1
        else:
            self.trace_failures += 1

    async def mirror_dataset(self, dataset: EvalDataset) -> None:
        if not self.client.enabled:
            return
        self.client.upsert_dataset(dataset.name, dataset.description)
        for item in dataset.items:
            remote_id = item_id_for(dataset.name, item.id)
            self.client.upsert_dataset_item(
                item_id=remote_id, dataset_name=dataset.name,
                input_={"task": item.input, "agent": dataset.agent},
                expected=(_expectations_payload(item) or None),
                metadata={"evalItemId": item.id, **item.metadata},
            )
        # Re-read to confirm the ids the API actually holds — the endpoint
        # upserts, but a failed write must not silently detach every run link.
        remote = {entry.get("id") for entry in self.client.list_dataset_items(dataset.name)}
        for item in dataset.items:
            candidate = item_id_for(dataset.name, item.id)
            if candidate in remote:
                item.langfuse_item_id = candidate

    def report(self, trace_id: str, score: ScoreResult, item_id: str) -> None:
        if not self.client.enabled:
            return
        ok = self.client.score(
            trace_id=trace_id, name=score.name, value=score.value,
            data_type=score.data_type, comment=score.comment,
            metadata={"itemId": item_id})
        if ok:
            self.reported.append((trace_id, score, item_id))

    async def link(self, trace_id: str, dataset_item_id: str, run_name: str) -> None:
        if not self.client.enabled:
            return
        if not self.client.link_run(run_name=run_name, dataset_item_id=dataset_item_id,
                                    trace_id=trace_id):
            self.link_failures += 1

    def flush(self) -> None:
        return None


def _expectations_payload(item: EvalItem) -> dict[str, Any]:
    """The item's expectations as plain data, for the Langfuse dataset item."""
    expected = item.expected
    if expected is None:
        return {}
    payload: dict[str, Any] = {}
    if expected.contains:
        payload["contains"] = expected.contains
    if expected.not_contains:
        payload["not_contains"] = expected.not_contains
    if expected.tools is not None:
        payload["tools"] = {"sequence": expected.tools.sequence, "mode": expected.tools.mode}
    if expected.evidence:
        payload["evidence"] = expected.evidence
    if item.judge is not None:
        payload["judge"] = {"criteria": item.judge.criteria, "pass": item.judge.pass_threshold}
    return payload


def build_reporters_items(dataset: EvalDataset) -> list[EvalItem]:
    """Items that have anything to score at all."""
    return [item for item in dataset.items
            if item.expected is not None or item.judge is not None]
