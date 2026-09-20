"""Headless agent invocation (平台自用).

给"平台自己"跑智能体用：没有用户在浏览器里看流，只要最后那段文本——定时
任务触发的增量影响分析走这里（services/codebase_analysis_service.py）。

传输层与测评模块的 ``LangGraphDriver`` 是同一条路（同一台 LangGraph 服务、
同一套线程 + SSE 协议），所以这里不重新实现解析：SSE 交给
``eval.tracing.iter_sse_lines`` + ``TraceCollector``，它已经在处理
``stream_mode=["updates","messages"]`` 的所有事件通道，其
``finish().output`` 就是最后一条 AI 消息的正文。

与 LangGraphDriver 的差异只有两点：只要结论不要 trace 指标；**从不抛异常**，
失败降级成 ``{"success": False, "error": ...}``——调用方是定时任务，不能因为
一次 LLM 故障把整轮索引带崩。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import httpx

from src.app.core.config import settings
from src.app.eval.tracing import TraceCollector, iter_sse_lines

logger = logging.getLogger(__name__)


async def run_agent_once(
    prompt: str,
    *,
    assistant_id: str,
    configurable: dict[str, Any] | None = None,
    thread_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    recursion_limit: int = 200,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """跑一次智能体，返回 ``{"success", "output", "thread_id", "error"}``。

    ``output`` 是最后一条 AI 消息的正文；空输出（例如图未注册、或 run 停在
    无人应答的 interrupt 上）按失败处理并说明原因。

    ``thread_id`` 必须是**合法 UUID**——LangGraph 服务端会校验并回 422
    ``Invalid thread ID: must be a UUID``。要可读的身份信息就放 ``metadata``。
    """
    tid = thread_id or str(uuid.uuid4())
    model_name = getattr(settings, "llm_model", "") or ""
    collector = TraceCollector(
        tid, instruction=prompt, name=f"smart-test-headless:{assistant_id}",
        environment=settings.langfuse_environment,
        tags=["headless", f"agent:{assistant_id}"],
        metadata={"source": "headless", "agent": assistant_id, **(metadata or {})},
    )
    timeout = httpx.Timeout(connect=20.0, read=timeout_s or 1_800.0,
                            write=30.0, pool=30.0)
    run_error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            created = await client.post(f"{settings.langgraph_api_url}/threads", json={
                "thread_id": tid,
                "metadata": {"source": "headless", "agent": assistant_id,
                             **(metadata or {})},
                "if_exists": "do_nothing",
            })
            created.raise_for_status()

            payload = {
                "assistant_id": assistant_id,
                "input": {"messages": [{"type": "human", "content": prompt}]},
                "config": {
                    "recursion_limit": recursion_limit,
                    "configurable": dict(configurable or {}),
                },
                "stream_mode": ["updates", "messages"],
                "stream_subgraphs": True,
            }
            async with client.stream(
                "POST",
                f"{settings.langgraph_api_url}/threads/{tid}/runs/stream",
                json=payload,
            ) as response:
                if response.status_code >= 300:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    return {"success": False, "output": "", "thread_id": tid,
                            "model": model_name,
                            "error": f"LangGraph run 启动失败 HTTP "
                                     f"{response.status_code}: {body[:400]}"}
                async for mode, data in iter_sse_lines(response.aiter_lines()):
                    if mode in ("error", "metadata", "end"):
                        if mode == "error":
                            run_error = json.dumps(data, ensure_ascii=False)[:1_000]
                        continue
                    # 其余通道原样转发：服务端把 messages 拆成 messages/metadata
                    # + messages/partial，按精确名字匹配会漏掉生成通道。
                    collector.handle(mode, data)
    except Exception as exc:  # noqa: BLE001 — 定时任务不能因 LLM 故障中断
        logger.warning("headless agent run failed (%s): %s", assistant_id, exc)
        return {"success": False, "output": "", "thread_id": tid,
                "model": model_name, "error": f"{type(exc).__name__}: {exc}"}

    trace = collector.finish(error=run_error)
    output = (trace.output or "").strip()
    # 模型名只有 SSE 的 messages/metadata 事件里才有，settings.llm_model 常为空
    # （留空=跟随 deepseek_model），所以优先取实际跑出来的那个。
    model_name = next((s.model for s in reversed(trace.steps) if s.model),
                      model_name)
    if not output:
        reason = run_error or ("智能体未产生输出：图未注册，或 run 停在人工审批上"
                               "（无头调用应传 permission_mode=full_access）")
        return {"success": False, "output": "", "thread_id": tid,
                "model": model_name, "error": reason}
    return {"success": True, "output": output, "thread_id": tid,
            "model": model_name, "error": None}
