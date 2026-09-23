#!/usr/bin/env python3
"""
LangGraph API Server for Smart Test Platform - Port 5011

Starts the LangGraph API server with multi-agent routing configured
via graph.json. Three agent stubs (testcase/web/api) are registered
and accessible via the LangGraph API.
"""

import os
import sys
import json
import pickle
from pathlib import Path


#: langgraph_runtime_inmem 的落盘文件。`store*.pckl` 是**小文件**，但进程被硬杀/断电时
#: 会留下"6 个 \x00"的半截文件；下一次启动 `DiskBackedInMemStore.__init__` 直接抛
#: `RuntimeError: invalid load key, '\x00'`，整个服务起不来。
#:
#: 2026-09-23 一天里踩了三次（01:55 断电、10:29 死机、15:10 重启后）——每次都得人工
#: 把文件搬走才能启动。这里在 uvicorn 之前自检一次：坏的搬进 `_corrupt_<时间戳>/`
#: 留证，好的原样不动。只碰这两个小 store 文件：会话 checkpoint（几 MB 一个）交给运行时
#: 自己的兼容兜底，启动脚本不去搬。
_LANGGRAPH_STORE_FILES = ("store.pckl", "store.vectors.pckl")


def quarantine_corrupt_langgraph_store() -> list[str]:
    """启动前自检 langgraph 的 store 落盘文件，坏的隔离掉。返回被隔离的文件名。"""
    state_dir = Path(__file__).parent / ".langgraph_api"
    if not state_dir.is_dir():
        return []
    quarantined: list[str] = []
    for name in _LANGGRAPH_STORE_FILES:
        path = state_dir / name
        if not path.is_file():
            continue
        try:
            blob = path.read_bytes()
            # 空文件 / 全 0（断电写了一半）先短路，省得把异常当正常路径走
            if not blob or not blob.strip(b"\x00"):
                raise ValueError("文件是空的或全是 0x00")
            pickle.loads(blob)
        except Exception as exc:  # noqa: BLE001 —— 读不了就是坏的，原因只写进日志
            stamp = __import__("time").strftime("%Y%m%d_%H%M%S")
            target_dir = state_dir / f"_corrupt_{stamp}"
            target_dir.mkdir(exist_ok=True)
            try:
                path.replace(target_dir / name)
            except OSError:
                continue
            quarantined.append(name)
            print(f"[启动自检] {name} 已损坏（{exc}）→ 隔离到 {target_dir.name}/，"
                  "本次启动会重建（旧会话的长期记忆会缺这一段）")
    return quarantined


def setup_environment():
    """Setup required environment variables for LangGraph API server."""
    # Add src/ to Python path at position 0
    src_path = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_path))

    # Load graphs from graph.json
    config_path = Path(__file__).parent / "graph.json"
    graphs = {}

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            graphs = config.get("graphs", {})

    # .env must load BEFORE the defaults below so an explicit
    # N_JOBS_PER_WORKER in .env can override the built-in default
    # (load_dotenv never clobbers already-set process env vars).
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print("Loaded environment from .env")
        except ImportError:
            print("python-dotenv not installed, skipping .env file")

    # N_JOBS_PER_WORKER = server-wide concurrent run slots (inmem queue).
    # 1 serializes ALL conversations (window B waits for window A's reply);
    # default 4 lets several chats/subagent batches run in parallel.
    os.environ.update({
        "DATABASE_URI": ":memory:",
        "REDIS_URI": "fake",
        "MIGRATIONS_PATH": "__inmem",
        "ALLOW_PRIVATE_NETWORK": "true",
        "LANGGRAPH_UI_BUNDLER": "true",
        "LANGGRAPH_RUNTIME_EDITION": "inmem",
        "LANGSMITH_LANGGRAPH_API_VARIANT": "local_dev",
        # 会话 checkpoint 落盘（.langgraph_api/*.pckl，启动时自动恢复）。
        # 关掉的话每次重启服务所有会话的模型上下文清零——用户回到旧会话发
        # "继续"会因 LangGraph 里线程不存在而被前端静默新建一个会话，表现为
        # "输入继续却开了个新窗口"，且新会话不记得之前的对话（2026-09-21 踩过）。
        # 兼容性兜底由 langgraph_runtime_inmem 自己做：pickle 与代码不兼容时
        # 自动删缓存并记日志，代价是那次重启后旧会话状态丢失。
        # 注意：这个开关只是"允许落盘"，**不代表真的落盘** —— 运行时自带的刷盘
        # 线程在本机只覆盖 ops 存储，会话 checkpoint 分片得靠
        # src/app/agents/checkpoint_persistence.py 的保活线程写（2026-09-22 定位）。
        "LANGGRAPH_DISABLE_FILE_PERSISTENCE": os.environ.get(
            "LANGGRAPH_DISABLE_FILE_PERSISTENCE", "false"),
        "LANGGRAPH_ALLOW_BLOCKING": "true",
        "LANGGRAPH_API_URL": "http://localhost:5011",
        "LANGSERVE_GRAPHS": json.dumps(graphs) if graphs else "{}",
        "N_JOBS_PER_WORKER": os.environ.get("N_JOBS_PER_WORKER", "4"),
    })


def main():
    """Start the LangGraph API server on port 5011."""
    print("Starting Smart Test Platform API Server...")

    # 自检要在 import langgraph_runtime 之前跑（store 是 import 时加载的）。
    quarantine_corrupt_langgraph_store()

    # Setup environment
    setup_environment()

    # Print server information
    print("\n" + "=" * 60)
    print("Server URL: http://localhost:5011")
    print("API Documentation: http://localhost:5011/docs")
    print("Studio UI: http://localhost:5011/ui")
    print("Health Check: http://localhost:5011/ok")
    print("=" * 60)

    try:
        import uvicorn

        log_file_path = str(Path(__file__).parent / "langgraph_server.log")

        uvicorn.run(
            "langgraph_api.server:app",
            host="0.0.0.0",
            port=5011,
            reload=False,
            access_log=False,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    }
                },
                "handlers": {
                    "default": {
                        "formatter": "default",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout",
                    },
                    "file": {
                        "formatter": "default",
                        "class": "logging.FileHandler",
                        "filename": log_file_path,
                        "encoding": "utf-8",
                    }
                },
                "root": {
                    "level": "INFO",
                    "handlers": ["default", "file"],
                },
                "loggers": {
                    "uvicorn": {"level": "INFO"},
                    "uvicorn.error": {"level": "INFO"},
                    "uvicorn.access": {"level": "WARNING"},
                },
            },
        )
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server failed to start: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
