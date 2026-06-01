"""Workspace report file viewer API.

Read-only endpoints to list and serve markdown test reports
from the workspace filesystem.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports")


def _get_reports_base() -> Path:
    """Get base path for testcase workspace reports."""
    return settings.workspace_dir / "default" / "testcase" / "workspace"


@router.get("/sessions")
async def list_sessions() -> dict:
    """List all session directories with their .md files."""
    base = _get_reports_base()
    if not base.exists():
        return {"success": True, "data": []}

    sessions = []
    for item in sorted(base.iterdir(), reverse=True):
        if not item.is_dir():
            continue
        md_files = sorted(
            [f.name for f in item.iterdir() if f.suffix == ".md" and f.is_file()],
            key=lambda n: (0 if n.startswith("phase") else 1, n),
        )
        if md_files:
            sessions.append({
                "name": item.name,
                "files": md_files,
                "file_count": len(md_files),
            })

    return {"success": True, "data": sessions}


@router.get("/sessions/{session_name}/files/{file_name:path}")
async def get_report_content(session_name: str, file_name: str) -> dict:
    """Read and return markdown file content."""
    base = _get_reports_base().resolve()
    file_path = (base / session_name / file_name).resolve()

    if not file_path.is_relative_to(base):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.suffix != ".md":
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    content = file_path.read_text(encoding="utf-8")
    return {
        "success": True,
        "data": {
            "name": file_name,
            "session": session_name,
            "content": content,
        },
    }
