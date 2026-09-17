"""Eval CLI (测评模块).

    python -m src.app.eval.cli --dataset datasets/douban-webui.yaml \
        --concurrency 2 --release v1 \
        --gate "avg(task_output_match)>=0.8 && all(tool_sequence)"

Keys come from the environment (or the project ``.env``, which `settings`
already loads): the agent under test needs ``DEEPSEEK_*``/``LLM_*``, the judge
needs ``JUDGE_*`` (falling back to the main LLM), and score upload needs
``LANGFUSE_*``. Without Langfuse keys the run is a local dry run — scores are
printed but not uploaded, which is the right default for iterating on a
dataset before it is trusted.

Exit code 0 = all items ran and the gate passed; 1 = gate failed; 2 = the run
itself could not start.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from src.app.core.config import settings
from src.app.eval.dataset import DEFAULT_DATASET_DIR, load_dataset
from src.app.eval.gate import evaluate_gate
from src.app.eval.langfuse_client import LangfuseClient
from src.app.eval.runner import DatasetRunOutcome, ItemRow, LangGraphDriver, LangfuseReporter, run_dataset
from src.app.eval.scorers import LlmJudge, deterministic_scorers, judge_endpoint_from_settings
from src.app.eval.tracing import trace_id_for


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smart-test-eval", description="跑数据集、打分、上门禁（Langfuse 闭环）")
    parser.add_argument("--dataset", required=True,
                        help=f"数据集 YAML 路径（可只给文件名，默认在 {DEFAULT_DATASET_DIR}）")
    parser.add_argument("--agent", default=None, help="覆盖数据集里的 agent（LangGraph 图名）")
    parser.add_argument("--concurrency", type=int, default=1, help="并发用例数（默认 1）")
    parser.add_argument("--release", default=None, help="批次标签，写进 trace 便于跨批次对比")
    parser.add_argument("--run-name", default=None, help="Langfuse DatasetRun 名称")
    parser.add_argument("--gate", default=None,
                        help='门禁表达式，例："avg(task_output_match)>=0.8 && all(tool_sequence)"')
    parser.add_argument("--no-langfuse", action="store_true", help="本地上报关闭（dry-run）")
    parser.add_argument("--no-judge", action="store_true", help="不跑 LLM-as-judge")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="把结果写成 JSON 到指定路径")
    parser.add_argument("--verify-trace", action="store_true",
                        help="跑完后轮询 Langfuse 确认 trace 与分数确实落库")
    return parser


async def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    dataset = load_dataset(options.dataset)
    if options.agent:
        dataset.agent = options.agent
    if options.concurrency < 1:
        print("cli: --concurrency 必须是正整数", file=sys.stderr)
        return 2

    scorers = deterministic_scorers()
    wants_judge = any(item.judge is not None for item in dataset.items)
    if wants_judge and not options.no_judge:
        endpoint = judge_endpoint_from_settings()
        scorers.append(LlmJudge(endpoint))
        print(f"judge: {endpoint.model} @ {endpoint.base_url}")
    elif wants_judge:
        print("judge: 已禁用（--no-judge），llm_judge 分数将缺失")

    client = LangfuseClient()
    reporter: LangfuseReporter | None = None
    if options.no_langfuse:
        print("langfuse: 已禁用（--no-langfuse），本地 dry-run")
    elif not client.enabled:
        print("langfuse: 未配置 LANGFUSE_* 或已关闭 —— 本地 dry-run，分数只打印不上报")
    else:
        reporter = LangfuseReporter(client, dataset.name)
        await reporter.mirror_dataset(dataset)
        linked = sum(1 for item in dataset.items if item.langfuse_item_id)
        print(f"langfuse: 数据集 '{dataset.name}' 已镜像（{linked}/{len(dataset.items)} 项可挂载），"
              f"分数将上报到 {client.host}")
    if not settings.langfuse_enabled and not options.no_langfuse:
        print("langfuse: LANGFUSE_ENABLED=false —— 视为 dry-run")

    driver = LangGraphDriver(release=options.release)
    run_name = options.run_name or (f"{dataset.name}@{options.release}"
                                    if options.release else None)

    print(f"\n=== 开始执行 {dataset.name} · agent={dataset.agent} · "
          f"{len(dataset.items)} 条用例 · 并发 {options.concurrency} ===\n")

    def on_item(item, row: ItemRow) -> None:
        if row.error:
            print(f"  ✗ {item.id}: ERROR {row.error[:100]}")
        else:
            rendered = "  ".join(_render_score(score) for score in row.scores) or "(无分数)"
            print(f"  ✓ {item.id}: {row.duration_ms / 1000:.1f}s  {rendered}")

    started = time.monotonic()
    outcome = await run_dataset(
        dataset=dataset, scorers=scorers, driver=driver, reporter=reporter,
        concurrency=options.concurrency, run_name=run_name, on_item=on_item)
    elapsed = time.monotonic() - started

    print(f"\n=== {outcome.dataset} · run {outcome.run_name} · {elapsed:.1f}s ===")
    print(format_rows(outcome.rows))
    print(format_totals(outcome.rows))

    ok = outcome.all_rows_scored
    if options.gate:
        gate = evaluate_gate(options.gate, [row.scores for row in outcome.rows])
        print("\n=== 门禁 ===")
        print("\n".join(gate.lines))
        ok = ok and gate.ok

    if reporter is not None:
        print(f"\nlangfuse: trace 上报 {reporter.traces_uploaded} 条"
              + (f"（失败 {reporter.trace_failures}）" if reporter.trace_failures else "")
              + f"，分数 {len(reporter.reported)} 枚"
              + (f"，{reporter.link_failures} 次 DatasetRun 挂载失败"
                 if reporter.link_failures else ""))
        print(f"langfuse: 打开 {client.host} 查看 trace（按 release="
              f"{options.release or '-'} 过滤）")

    if options.verify_trace and reporter is not None:
        ok = await _verify(outcome, client) and ok

    if options.json_out:
        Path(options.json_out).write_text(serialize_outcome(outcome), encoding="utf-8")
        print(f"\n结果已写入 {options.json_out}")

    client.close()
    return 0 if ok else 1


def _render_score(score) -> str:
    if isinstance(score.value, bool):
        return f"{score.name}={'✓' if score.value else '✗'}"
    if isinstance(score.value, (int, float)):
        return f"{score.name}={round(float(score.value), 3)}"
    return f"{score.name}={score.value}"


def format_rows(rows: list[ItemRow]) -> str:
    lines = []
    for row in rows:
        if row.error:
            lines.append(f"✗ {row.item.id:<24} ERROR {row.error[:80]}")
            continue
        scores = "  ".join(_render_score(score) for score in row.scores) or "(无分数)"
        tools = f"tools={len(row.tool_names)}"
        lines.append(f"✓ {row.item.id:<24} {row.duration_ms / 1000:6.1f}s  {tools:<12} {scores}")
    return "\n".join(lines)


def format_totals(rows: list[ItemRow]) -> str:
    """Averages per score name — the same numbers the gate aggregates."""
    totals: dict[str, list[float]] = {}
    for row in rows:
        for score in row.scores:
            if isinstance(score.value, bool):
                totals.setdefault(score.name, []).append(1.0 if score.value else 0.0)
            elif isinstance(score.value, (int, float)):
                totals.setdefault(score.name, []).append(float(score.value))
    if not totals:
        return "\n（本次没有任何分数产出）"
    lines = ["", "=== 汇总 ==="]
    for name, values in sorted(totals.items()):
        lines.append(f"  {name:<26} avg={sum(values) / len(values):.3f}  "
                     f"min={min(values):.3f}  max={max(values):.3f}  n={len(values)}")
    errors = sum(1 for row in rows if row.error)
    lines.append(f"  用例 {len(rows)} 条，执行异常 {errors} 条")
    return "\n".join(lines)


def serialize_outcome(outcome: DatasetRunOutcome) -> str:
    import json

    return json.dumps({
        "dataset": outcome.dataset,
        "run_name": outcome.run_name,
        "agent": outcome.agent,
        "rows": [{
            "item_id": row.item.id,
            "input": row.item.input,
            "trace_id": row.trace_id,
            "thread_id": row.thread_id,
            "duration_ms": row.duration_ms,
            "error": row.error,
            "tool_names": row.tool_names,
            "evidence": row.evidence,
            "scores": [{"name": s.name, "value": s.value, "data_type": s.data_type,
                        "comment": s.comment} for s in row.scores],
        } for row in outcome.rows],
    }, ensure_ascii=False, indent=2)


async def _verify(outcome: DatasetRunOutcome, client: LangfuseClient) -> bool:
    """Poll Langfuse for each trace; ingestion is async so this must wait.

    Waits for the *scores* to appear rather than for the trace row, because the
    row is readable seconds before its observations and scores are indexed.
    """
    print("\n=== 落库核验（Langfuse 读取约 10-20s 延迟）===")
    ok = True
    for row in outcome.rows:
        expected: list[str] = []
        for score in row.scores:
            if isinstance(score.value, (bool, int, float)):
                expected.append(score.name)
        if not expected:
            continue
        trace = await asyncio.to_thread(
            client.wait_for_trace, row.trace_id,
            until=lambda t, n=len(expected): len(t.get("scores") or []) >= n)
        if trace is None:
            print(f"  ✗ {row.item.id}: trace {row.trace_id} 在超时内不可读")
            ok = False
            continue
        remote = {score.get("name"): score.get("value") for score in (trace.get("scores") or [])}
        missing = [name for name, _, _ in expected_as_triples(row) if name not in remote]
        observations = len(trace.get("observations") or [])
        if missing:
            ok = False
        print(f"  {'✓' if not missing else '✗'} {row.item.id}: trace 命中，"
              f"observations={observations}，scores={len(remote)}/{len(expected)}"
              + (f"，缺失 {missing}" if missing else ""))
    return ok


def expected_as_triples(row: ItemRow) -> list[tuple[str, float, str]]:
    """The numeric/boolean scores a row produced, in (name, value, data_type) form."""
    out: list[tuple[str, float, str]] = []
    for score in row.scores:
        if isinstance(score.value, bool):
            out.append((score.name, 1.0 if score.value else 0.0, "BOOLEAN"))
        elif isinstance(score.value, (int, float)):
            out.append((score.name, float(score.value), "NUMERIC"))
    return out


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
