"""FastAPI server startup script. Runs on port 8000 alongside LangGraph :2026."""
import uvicorn
from src.app.fastapi_app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
