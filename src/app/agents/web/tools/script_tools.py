"""Web test script management tools.

Provides 3 tools for managing test scripts in the workspace:
  - get_web_script_info: query script file metadata
  - download_web_script: copy script from artifacts to tests directory
  - delete_web_script: remove a script from the tests directory

Phase 15 uses local filesystem only (no MinIO, no Attachment DB lookups).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from src.app.core.config import settings
from src.app.core.workspace import get_space_id, get_workspace_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tests_dir(space_id: str) -> Path:
    """Return the tests directory, creating it if needed."""
    d = get_workspace_dir(space_id, "web") / "tests"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Tool 1: Get script info
# ---------------------------------------------------------------------------


@tool
async def get_web_script_info(script_id: str) -> dict:
    """Get metadata for a web test script file.

    Phase 15: script_id is the file path on local filesystem.
    Phase 16: script_id will be an Attachment UUID resolved from DB.

    Args:
        script_id: File path or attachment UUID.

    Returns:
        Dict with script metadata (file_name, size, timestamps, local_path).
    """
    script_path = Path(script_id)

    if not script_path.exists():
        return {"success": False, "error": f"Script file not found: {script_id}"}

    stat = script_path.stat()
    return {
        "success": True,
        "script": {
            "id": script_id,
            "file_name": script_path.name,
            "file_size": stat.st_size,
            "local_path": str(script_path),
            "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Tool 2: Download (copy) script to tests directory
# ---------------------------------------------------------------------------


@tool
async def download_web_script(
    script_id: str,
    filename: Optional[str] = None,
) -> dict:
    """Copy a test script from artifacts to the tests directory.

    Generates a timestamped filename to avoid conflicts. The file is then
    ready for execution via ``execute_web_script``.

    Args:
        script_id: Source file path (e.g., an artifact file path).
        filename: Optional base name for the destination file (without extension).

    Returns:
        Dict with local_path of the copied script.
    """
    source = Path(script_id)

    if not source.exists():
        return {"success": False, "error": f"Script file not found: {script_id}"}

    space_id = get_space_id()
    tests = _tests_dir(space_id)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = filename or source.stem

    # Ensure Playwright test file naming (.spec.ts or .test.ts)
    if source.suffix == ".ts" and ".spec" not in source.name and ".test" not in source.name:
        local_filename = f"{stem}_{timestamp}.spec.ts"
    else:
        suffix = source.suffix or ".spec.ts"
        local_filename = f"{stem}_{timestamp}{suffix}"

    dest = tests / local_filename
    dest.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "success": True,
        "script_id": script_id,
        "original_filename": source.name,
        "local_filename": local_filename,
        "local_path": str(dest),
        "file_size": dest.stat().st_size,
        "download_time": datetime.now(timezone.utc).isoformat(),
        "message": "Script copied to tests directory",
    }


# ---------------------------------------------------------------------------
# Tool 3: Delete script from tests directory
# ---------------------------------------------------------------------------


@tool
async def delete_web_script(local_path: str) -> dict:
    """Delete a test script from the tests directory.

    Only allows deletion of files within the workspace tests directory
    for safety.

    Args:
        local_path: Absolute path to the script file to delete.

    Returns:
        Dict confirming deletion or error.
    """
    script_path = Path(local_path)

    if not script_path.exists():
        return {"success": False, "error": f"File not found: {local_path}"}

    # Safety: ensure path is within tests directory
    space_id = get_space_id()
    tests = _tests_dir(space_id)
    try:
        script_path.resolve().relative_to(tests.resolve())
    except ValueError:
        return {"success": False, "error": "Can only delete files in the tests directory"}

    script_path.unlink()

    return {
        "success": True,
        "local_path": local_path,
        "message": "Script deleted",
    }


# Tool list for package export
SCRIPT_TOOLS: list = [
    get_web_script_info,
    download_web_script,
    delete_web_script,
]
