"""Re-run the last requirement through the refactored testcase_agent (async)."""
import asyncio
import json
import sqlite3
import time

from langgraph_sdk import get_client

DB = "smart_test_platform.db"
API = "http://localhost:2026"
REPO = "E:\\m72-publish\\m72"


def load_requirement() -> str:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "select content from thread_messages where msg_type='human' order by rowid desc limit 1"
    ).fetchone()
    con.close()
    if not row:
        raise SystemExit("no human message found")
    content = row["content"]
    try:
        blocks = json.loads(content)
        if isinstance(blocks, list):
            return "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
    except (json.JSONDecodeError, TypeError):
        pass
    return content


async def main() -> None:
    text = load_requirement()
    print(f"[runner] requirement loaded: {len(text)} chars", flush=True)
    client = get_client(url=API, timeout=600)
    thread = await client.threads.create()
    tid = thread["thread_id"]
    print(f"[runner] thread: {tid}", flush=True)

    t0 = time.time()
    final_state = None
    steps = 0
    async for chunk in client.runs.stream(
        tid,
        "testcase_agent",
        input={"messages": [{"type": "human", "content": text}]},
        config={
            "recursion_limit": 1000,
            "configurable": {"space_id": "default", "repo_path": REPO},
        },
        stream_mode="values",
    ):
        steps += 1
        if chunk.data and isinstance(chunk.data, dict) and "messages" in chunk.data:
            final_state = chunk.data
            last = final_state["messages"][-1]
            kind = last.get("type", "?")
            name = last.get("name") or ""
            preview = str(last.get("content") or "")[:80].replace("\n", " ")
            print(f"[{time.time()-t0:7.1f}s] step {steps} {kind} {name}: {preview}", flush=True)

    print(f"[runner] finished in {time.time()-t0:.1f}s, {steps} stream events", flush=True)
    if final_state:
        ai_msgs = [m for m in final_state["messages"] if m.get("type") == "ai" and m.get("content")]
        print("=" * 60, flush=True)
        print("FINAL AI OUTPUT (last message):", flush=True)
        print("=" * 60, flush=True)
        if ai_msgs:
            out = str(ai_msgs[-1]["content"])
            print(out[:6000], flush=True)
            if len(out) > 6000:
                print(f"... ({len(out) - 6000} more chars)", flush=True)
        calls = {}
        for m in final_state["messages"]:
            for tc in m.get("tool_calls") or []:
                calls[tc["name"]] = calls.get(tc["name"], 0) + 1
        print("-" * 60, flush=True)
        print("TOOL CALLS:", json.dumps(calls, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
