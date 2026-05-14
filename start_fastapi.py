"""FastAPI server startup script.

Runs the FastAPI server on port 8000 alongside the LangGraph server on port 2026.

Usage:
    python start_fastapi.py
"""

import uvicorn

from src.app.fastapi_app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
