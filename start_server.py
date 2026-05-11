#!/usr/bin/env python3
"""
LangGraph API Server for Smart Test Platform - Port 2026

Starts the LangGraph API server with multi-agent routing configured
via graph.json. Three agent stubs (testcase/web/api) are registered
and accessible via the LangGraph API.
"""

import os
import sys
import json
from pathlib import Path


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

    # Set environment variables
    os.environ.update({
        "DATABASE_URI": ":memory:",
        "REDIS_URI": "fake",
        "MIGRATIONS_PATH": "__inmem",
        "ALLOW_PRIVATE_NETWORK": "true",
        "LANGGRAPH_UI_BUNDLER": "true",
        "LANGGRAPH_RUNTIME_EDITION": "inmem",
        "LANGSMITH_LANGGRAPH_API_VARIANT": "local_dev",
        "LANGGRAPH_DISABLE_FILE_PERSISTENCE": "false",
        "LANGGRAPH_ALLOW_BLOCKING": "true",
        "LANGGRAPH_API_URL": "http://localhost:2026",
        "LANGSERVE_GRAPHS": json.dumps(graphs) if graphs else "{}",
        "N_JOBS_PER_WORKER": "1",
    })

    # Load .env file if exists
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            print("Loaded environment from .env")
        except ImportError:
            print("python-dotenv not installed, skipping .env file")


def main():
    """Start the LangGraph API server on port 2026."""
    print("Starting Smart Test Platform API Server...")

    # Setup environment
    setup_environment()

    # Print server information
    print("\n" + "=" * 60)
    print("Server URL: http://localhost:2026")
    print("API Documentation: http://localhost:2026/docs")
    print("Studio UI: http://localhost:2026/ui")
    print("Health Check: http://localhost:2026/ok")
    print("=" * 60)

    try:
        import uvicorn

        uvicorn.run(
            "langgraph_api.server:app",
            host="0.0.0.0",
            port=2026,
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
                    }
                },
                "root": {
                    "level": "INFO",
                    "handlers": ["default"],
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
