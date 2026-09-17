"""Live progress for eval batches (测评模块).

为什么需要它：一个 6 条用例的评测集串行跑要几分钟——每条用例都要跑完整个 agent
run（含若干次浏览器工具调用），几十秒到几分钟不等。而批次结果原本是**整轮跑完才
落库**的，于是页面上长时间只有"用例 0/6"和一个转圈的图标：分不清是在跑、卡住了，
还是执行进程早就跟着服务重启一起没了。

这里把执行过程中的事实**边跑边写磁盘**（与 Web-UI 自动化的运行目录同一套思路）：

- ``live.ndjson`` —— 结构化事件：begin / item_start / note / item / heartbeat / end
- ``live.log``    —— 同样内容的人读版本，直接给界面当"实时日志尾"

心跳是这套东西的关键：进程被杀或容器重启时文件不会再有新行，于是"最后一条心跳是
多久以前"就成了"这个批次还活着吗"的唯一可靠证据（{@link is_stale}）。仅靠"最后
一条事件多久以前"会误判——一次工具调用可能安静地跑很久。

写失败一律吞掉：磁盘满不能把正在跑的测评弄挂，进度是观测手段，不是执行前提。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, TextIO

from src.app.core.config import settings

logger = logging.getLogger(__name__)

#: 本进程正在执行的批次 id。心跳文件能证明"刚才还活着"，但只有这个集合能区分
#: "正在跑只是暂时没输出"与"执行进程已经不在了"。单 worker 部署下它是权威答案。
LIVE: set[str] = set()


def runs_root() -> Path:
    root = (Path(settings.eval_run_dir) if settings.eval_run_dir
            else settings.workspace_dir / "default" / "eval-runs")
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_dir(batch_id: str) -> Path:
    path = runs_root() / batch_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fmt_duration(ms: int) -> str:
    seconds = max(0, int(ms / 1000))
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m{seconds % 60:02d}s"


def _render_score(score: dict[str, Any]) -> str:
    value = score.get("value")
    if isinstance(value, bool):
        return f"{score.get('name')}={'✓' if value else '✗'}"
    if isinstance(value, (int, float)):
        return f"{score.get('name')}={round(float(value), 3)}"
    return f"{score.get('name')}={value}"


class LiveLog:
    """一个批次的执行现场：结构化事件 + 人读日志 + 心跳。"""

    def __init__(self, batch_id: str, *, total: int, dataset: str, agent: str,
                 concurrency: int = 1) -> None:
        self.batch_id = batch_id
        self.total = total
        self.dataset = dataset
        self.agent = agent
        self.concurrency = concurrency
        directory = run_dir(batch_id)
        self.events_path = directory / "live.ndjson"
        self.log_path = directory / "live.log"
        # 行缓冲：崩了也要留下最后一行（这是排除故障时最值钱的东西）
        self._events = self._open(self.events_path)
        self._log = self._open(self.log_path)
        self.started_at = time.time()
        self._closed = False
        self.event("begin", total=total, dataset=dataset, agent=agent,
                   concurrency=concurrency)
        self.line(f"批次开始 · {dataset} · agent={agent} · {total} 条用例 · 并发 {concurrency}")

    def set_total(self, total: int) -> None:
        """数据集实际条数与批次行不一致时更正（进度条的分母）。"""
        if total == self.total:
            return
        self.total = total
        self.event("begin", total=total, dataset=self.dataset, agent=self.agent,
                   concurrency=self.concurrency, corrected=True)

    @staticmethod
    def _open(path: Path) -> TextIO | None:
        try:
            return path.open("a", encoding="utf-8", buffering=1)
        except OSError as exc:
            logger.warning("实时进度文件不可写 %s: %s", path, exc)
            return None

    def _write(self, handle: TextIO | None, text: str) -> None:
        if handle is None or self._closed:
            return
        try:
            handle.write(text)
            handle.flush()
        except (OSError, ValueError) as exc:  # ValueError: 已关闭
            logger.debug("实时进度写入失败: %s", exc)

    # -- 事件 ------------------------------------------------------------------

    def event(self, kind: str, **fields: Any) -> None:
        payload = {"event": kind, "ts": round(time.time(), 3), **fields}
        self._write(self._events, json.dumps(payload, ensure_ascii=False) + "\n")

    def line(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._write(self._log, f"[{stamp}] {text}\n")

    # -- 执行侧的调用点 --------------------------------------------------------

    def item_start(self, item_id: str) -> None:
        self.event("item_start", item_id=item_id)
        self.line(f"▶ {item_id} 开始")

    def note(self, item_id: str, text: str) -> None:
        """agent 执行过程中的一步（工具调用/模型生成），来自 TraceCollector。"""
        self.event("note", item_id=item_id, text=text)
        self.line(f"  · {item_id} {text}")

    def item_done(self, item_id: str, *, status: str, duration_ms: int,
                  scores: list[dict[str, Any]] | None = None,
                  tools: list[str] | None = None, error: str | None = None) -> None:
        scores = scores or []
        self.event("item", item_id=item_id, status=status, duration_ms=duration_ms,
                   scores=scores, tools=tools or [], error=error)
        if status == "error":
            self.line(f"✗ {item_id} ERROR {(error or '')[:200]}")
            return
        rendered = "  ".join(_render_score(score) for score in scores) or "(无分数)"
        self.line(f"✓ {item_id} {_fmt_duration(duration_ms)}  {rendered}")

    def finish(self, status: str, *, summary: str | None = None) -> None:
        elapsed_ms = int((time.time() - self.started_at) * 1000)
        self.event("end", status=status, elapsed_ms=elapsed_ms, summary=summary)
        self.line(f"批次结束 · {status} · 用时 {_fmt_duration(elapsed_ms)}")
        self.close()

    def close(self) -> None:
        self._closed = True
        for handle in (self._events, self._log):
            try:
                handle.close() if handle is not None else None
            except OSError:
                pass

    async def heartbeat_loop(self, interval_s: float | None = None) -> None:
        """周期性写心跳，直到被取消。只进 ndjson，不污染给人看的日志。"""
        interval = float(interval_s or settings.eval_heartbeat_s)
        try:
            while True:
                await asyncio.sleep(max(1.0, interval))
                self.event("heartbeat")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 心跳绝不能带崩批次
            logger.debug("心跳循环退出", exc_info=True)


# ---------------------------------------------------------------------------
# 读侧：给接口用
# ---------------------------------------------------------------------------

def _read_events(path: Path, limit: int) -> list[dict]:
    """只读最后若干行——一个批次最多几百条事件，不需要全读。"""
    if not path.is_file():
        return []
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []
    events: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 正在写入的半行
    return events


def _tail(path: Path, limit: int) -> str:
    if not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def read_live(batch_id: str, *, limit: int = 600) -> dict:
    """批次执行现场的快照。文件不存在时返回"还没开始"的空壳，不抛异常。"""
    directory = runs_root() / batch_id
    events = _read_events(directory / "live.ndjson", limit)
    now = time.time()

    begin_events = [e for e in events if e.get("event") == "begin"]
    begin = begin_events[0] if begin_events else None
    # 分母取最后一次 begin：executor 拿到数据集后可能更正条数（set_total）
    total = (begin_events[-1].get("total") if begin_events else None)
    items = [e for e in events if e.get("event") == "item"]
    done_ids = {e.get("item_id") for e in items}
    active = [
        {"item_id": e.get("item_id"), "elapsed_ms": int((now - float(e.get("ts") or now)) * 1000)}
        for e in events
        if e.get("event") == "item_start" and e.get("item_id") not in done_ids
    ]
    # 活动流：模型/工具的一步步 + 用例落地，按时间排序给界面逐条读
    activity = sorted(
        (e for e in events if e.get("event") in ("item_start", "note", "item")),
        key=lambda e: float(e.get("ts") or 0),
    )[-80:]
    heartbeats = [e for e in events if e.get("event") == "heartbeat"]
    end = next((e for e in events if e.get("event") in ("end", "error")), None)

    return {
        "batch_id": batch_id,
        "started": begin is not None,
        "dataset": (begin or {}).get("dataset"),
        "agent": (begin or {}).get("agent"),
        "total": total if total is not None else (begin or {}).get("total"),
        "started_at": begin.get("ts") if begin else None,
        "done": len(items),
        "passed": sum(1 for e in items if e.get("status") == "ok"),
        "failed": sum(1 for e in items if e.get("status") == "error"),
        "active": active[-8:],
        "activity": activity,
        "terminal": end.get("event") if end else None,
        "terminal_status": (end or {}).get("status"),
        "summary": (end or {}).get("summary"),
        "heartbeat_age_s": (round(now - float(heartbeats[-1]["ts"]), 1)
                            if heartbeats else None),
        "log_tail": _tail(directory / "live.log", 6000),
        # 没有开始事件时（进程还没写下第一行）耗时交给调用方按批次创建时间算
        "elapsed_ms": (int((now - float(begin["ts"])) * 1000) if begin else 0),
    }


def heartbeat_age(batch_id: str) -> float | None:
    """最后一次心跳距今多少秒；文件/心跳不存在时返回 None。"""
    return read_live(batch_id, limit=60)["heartbeat_age_s"]


#: 文件都还没出现时的宽限期：POST /run 返回后后台任务才启动，这段空窗不算中断
START_GRACE_S = 120


def is_stale(batch_id: str, *, created_age_s: float) -> bool:
    """批次记录说"运行中"，但执行进程是否已经没了？

    判据按可靠性从高到低：
    1. 批次就在本进程的 LIVE 集合里 —— 一定在跑（哪怕安静很久）；
    2. 心跳文件存在 —— 心跳静默超过阈值就判定进程已停；
    3. 连文件都没有 —— 启动宽限期内不算，超过就是启动都没起来。
    """
    if batch_id in LIVE:
        return False
    age = heartbeat_age(batch_id)
    if age is None:
        return created_age_s > START_GRACE_S
    return age > settings.eval_stale_after_s
