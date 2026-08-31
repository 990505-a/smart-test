"""Minimal stdio JSON-RPC client for codebase-memory-mcp (代码分析模块).

The codebase-memory exe speaks plain newline-delimited JSON-RPC over
stdio. The generic MCP python SDKs fail against its custom C runtime
(stdout interleaves logger lines, etc.), so this module drives the
protocol directly, robustly: spawn → initialize → tool call → exit.

The exe is spawned per call (handshake < 1s), matching how agents use it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.app.core.config import settings

logger = logging.getLogger(__name__)

_HANDSHAKE_TIMEOUT = 30.0
_TOOL_TIMEOUT = 900.0


class CbmClientError(Exception):
    pass


async def _spawn(exe: str | None = None) -> asyncio.subprocess.Process:
    cmd = exe or settings.codebase_memory_exe
    proc = await asyncio.create_subprocess_exec(
        cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    return proc


async def _write_json(proc: asyncio.subprocess.Process, payload: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    await proc.stdin.drain()


async def _read_json(proc: asyncio.subprocess.Process, req_id: int, timeout: float) -> dict:
    """Read until the response for req_id arrives (skip logger/non-JSON lines)."""
    assert proc.stdout is not None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    buffer = b""
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise CbmClientError(f"codebase-memory 响应超时（{timeout:.0f}s）")
        try:
            chunk = await asyncio.wait_for(proc.stdout.read(4096), timeout=remaining)
        except TimeoutError:
            raise CbmClientError(f"codebase-memory 响应超时（{timeout:.0f}s）")
        if not chunk:
            raise CbmClientError("codebase-memory 进程已退出")
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if not text or not text.startswith("{"):
                continue  # 跳过 exe 内部日志行
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise CbmClientError(str(msg["error"])[:500])
                return msg.get("result") or {}


async def list_tools(timeout: float = _HANDSHAKE_TIMEOUT) -> list[dict]:
    """Connect and list available tools: [{name, description, input_schema}]."""
    proc = await _spawn()
    try:
        await _write_json(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "smart-test-platform", "version": "1.0"}},
        })
        result = await _read_json(proc, 1, timeout)
        await _write_json(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        await _write_json(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = await _read_json(proc, 2, timeout)
        return [{"name": t.get("name"), "description": t.get("description", ""),
                 "input_schema": t.get("inputSchema", {})} for t in tools.get("tools", [])]
    except OSError as exc:
        raise CbmClientError(f"无法启动 codebase-memory（{settings.codebase_memory_exe}）: {exc}")
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass


async def call_tool(tool_name: str, args: dict, timeout: float = _TOOL_TIMEOUT,
                    exe: str | None = None) -> dict:
    """Spawn, handshake, call one tool, return its result (JSON-normalized)."""
    proc = await _spawn(exe)
    req_id = 3
    try:
        await _write_json(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "smart-test-platform", "version": "1.0"}},
        })
        await _read_json(proc, 1, _HANDSHAKE_TIMEOUT)
        await _write_json(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        await _write_json(proc, {
            "jsonrpc": "2.0", "id": req_id, "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        })
        result = await _read_json(proc, req_id, timeout)
        content = result.get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                try:
                    return {"success": True, "data": json.loads(text)}
                except json.JSONDecodeError:
                    return {"success": True, "data": text}
        if result.get("isError"):
            raise CbmClientError(str(result.get("content"))[:500])
        return {"success": True, "data": result}
    except CbmClientError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CbmClientError(f"codebase-memory 调用失败: {exc}")
    finally:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
