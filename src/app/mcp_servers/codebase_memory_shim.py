"""codebase-memory stdio shim (Windows asyncio 兼容层).

codebase-memory-mcp.exe 是 C 构建，其 stdio 实现在 asyncio Proactor 事件循环
创建的 overlapped 管道下收不到数据（进程存活但永不响应 MCP initialize）；
而 Node/Rust 宿主的同步管道一切正常。Python MCP 客户端（fastmcp /
langchain-mcp-adapters / mcp SDK）在 Windows 上全部走 asyncio → 全部挂起。

本垫片用普通 subprocess.Popen（同步管道）拉起 exe 并做字节级透传，
SDK 连接本垫片（python.exe 的 stdio 对 overlapped 管道无兼容问题）。
代价是每条连接多一个轻量 python 进程。

Run as the MCP command::

    python -m src.app.mcp_servers.codebase_memory_shim
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

DEFAULT_EXE = "C:/codebase/codebase-memory-mcp/build/c/codebase-memory-mcp.exe"
EXE = os.environ.get("CODEBASE_MEMORY_EXE", DEFAULT_EXE)


def main() -> None:
    exe = subprocess.Popen(
        [EXE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def pump_stdin() -> None:
        try:
            while True:
                chunk = sys.stdin.buffer.read1(65536)
                if not chunk:
                    break
                exe.stdin.write(chunk)
                exe.stdin.flush()
        except OSError:
            pass
        finally:
            try:
                exe.stdin.close()
            except OSError:
                pass

    def pump_stderr() -> None:
        try:
            while True:
                chunk = exe.stderr.read1(65536)
                if not chunk:
                    break
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
        except OSError:
            pass

    threading.Thread(target=pump_stdin, daemon=True).start()
    threading.Thread(target=pump_stderr, daemon=True).start()

    # 主线程转发 exe stdout；EOF 时进程结束
    while True:
        chunk = exe.stdout.read1(65536)
        if not chunk:
            break
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()

    exe.wait()
    sys.exit(exe.returncode or 0)


if __name__ == "__main__":
    main()
