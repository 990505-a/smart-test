"""Web test script execution tools.

Provides 2 tools for executing Playwright test scripts:
  - execute_web_script: run a script via npx playwright test
  - get_test_execution_status: placeholder for async status queries

Phase 15 uses asyncio.create_subprocess_exec for subprocess execution,
matching the API agent's APITestExecutor pattern.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from src.app.core.config import settings
from src.app.core.workspace import get_space_id, get_workspace_dir


# ---------------------------------------------------------------------------
# Tool 1: Execute web script
# ---------------------------------------------------------------------------


@tool
async def execute_web_script(
    local_script_path: str,
    framework: str = "playwright",
    reporter: str = "html",
    project_identifier: str = "",
    sub_function_id: Optional[str] = None,
) -> dict:
    """Execute a web test script using Playwright.

    Runs ``npx playwright test`` in the web MCP root directory.
    The script must be within the workspace tests directory.

    Args:
        local_script_path: Path to the .spec.ts test script.
        framework: Test framework (only 'playwright' supported).
        reporter: Reporter format (html, json, list).
        project_identifier: Project identifier for report namespacing.
        sub_function_id: Optional sub-function ID for tracking.

    Returns:
        Dict with execution results (stdout, stderr, duration, return_code).
    """
    if framework != "playwright":
        return {
            "success": False,
            "error": f"Unsupported framework: {framework}. Only 'playwright' is supported.",
        }

    script_path = Path(local_script_path)
    if not script_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}

    project_root = settings.web_mcp_root_resolved

    # Determine the script filename relative to the project root
    try:
        relative_path = script_path.relative_to(project_root)
    except ValueError:
        # Script is outside project root (e.g., in a different workspace)
        # Use just the filename
        relative_path = script_path.name

    script_filename = str(relative_path)

    start_time = datetime.now(timezone.utc)

    try:
        # Build command
        cmd = [
            "npx", "playwright", "test",
            script_filename,
            f"--reporter={reporter}",
        ]

        # Prepare environment (CI=1 prevents browser auto-open)
        env = os.environ.copy()
        if reporter == "html":
            env["CI"] = "1"

        # Execute via subprocess
        is_windows = sys.platform == "win32"
        if is_windows:
            # Windows: use shell for npx resolution
            proc = await asyncio.create_subprocess_shell(
                " ".join(cmd),
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        else:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=300
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        # Check for HTML report
        report_path = None
        if reporter == "html":
            report_dir = project_root / "playwright-report"
            if report_dir.exists():
                report_path = str(report_dir)

        result = {
            "success": proc.returncode == 0,
            "script_path": local_script_path,
            "script_filename": script_filename,
            "execution_result": {
                "return_code": proc.returncode,
                "duration": round(duration, 2),
                "stdout": stdout,
                "stderr": stderr,
                "report_path": report_path,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
            },
        }

        if sub_function_id:
            result["sub_function_id"] = sub_function_id

        return result

    except asyncio.TimeoutError:
        return {"success": False, "error": "Script execution timed out (300s limit)"}
    except Exception as e:
        return {"success": False, "error": f"Execution error: {str(e)}"}


# ---------------------------------------------------------------------------
# Tool 2: Get execution status (placeholder)
# ---------------------------------------------------------------------------


@tool
async def get_test_execution_status(execution_id: str) -> dict:
    """Get the status of a test execution.

    Phase 15 only supports synchronous execution, so this always returns
    'completed'. Future phases may add async execution with polling.

    Args:
        execution_id: Execution identifier.

    Returns:
        Dict with status information.
    """
    return {
        "success": True,
        "execution_id": execution_id,
        "status": "completed",
        "message": "Synchronous execution only -- status is always completed",
    }


# Tool list for package export
EXECUTION_TOOLS: list = [
    execute_web_script,
    get_test_execution_status,
]
