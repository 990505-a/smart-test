"""Web test artifact management tools.

Provides 6 tools for saving and querying web test artifacts:
  - save_web_test_plan
  - save_web_test_cases
  - save_web_test_script
  - get_web_sub_function_artifacts
  - save_web_test_report
  - get_artifact_content

Phase 15 uses local filesystem storage under workspace/{space_id}/web/artifacts/.
Phase 16: add DB attachment records when WebFunction/WebSubFunction models exist.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from langchain_core.tools import tool

from src.app.core.config import settings
from src.app.core.workspace import get_space_id, get_workspace_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_workspace_path(file_path: str) -> Path:
    """Resolve file path, supporting relative paths within the web workspace.

    On Windows, leading-slash paths are treated as relative (no drive letter).
    """
    path = Path(file_path)
    workspace_root = settings.web_mcp_root_resolved.resolve()

    if os.name == "nt":
        if file_path.startswith("/") or file_path.startswith("\\"):
            file_path = file_path.lstrip("/\\")
            path = Path(file_path)

    if path.is_absolute():
        return path

    if path.exists():
        return path.resolve()

    workspace_path = workspace_root / path
    if workspace_path.exists():
        return workspace_path

    # Fall back to workspace-relative path
    return workspace_root / path


def _artifacts_dir(space_id: str, sub_function_id: str) -> Path:
    """Return the artifacts directory for a sub-function."""
    d = get_workspace_dir(space_id, "web") / "artifacts" / sub_function_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _reports_dir(space_id: str) -> Path:
    """Return the reports directory."""
    d = get_workspace_dir(space_id, "web") / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Tool 1: Save test plan
# ---------------------------------------------------------------------------


@tool
async def save_web_test_plan(
    sub_function_id: str,
    plan_content: Optional[str] = None,
    plan_path: Optional[str] = None,
    test_plan: Optional[dict] = None,
    plan_format: str = "markdown",
    project_identifier: str = "",
) -> dict:
    """Save a test plan for a web sub-function.

    Supports three input modes:
      1. plan_path: read from a generated file
      2. test_plan: dict serialized as JSON
      3. plan_content: raw string content

    Args:
        sub_function_id: Sub-function UUID.
        plan_content: Plan text content (Markdown or string).
        plan_path: Path to a generated test plan file.
        test_plan: Plan as a dict (serialized to JSON).
        plan_format: Output format (markdown or json).
        project_identifier: Project identifier for path namespacing.

    Returns:
        Dict with file_path and format information.
    """
    space_id = get_space_id()
    artifacts = _artifacts_dir(space_id, sub_function_id)

    content: str | None = None
    ext = "md"
    content_type = "text/markdown"

    if plan_path:
        resolved = _resolve_workspace_path(plan_path)
        if not resolved.exists():
            return {
                "error": f"Test plan file not found: {plan_path}",
                "hint": f"Resolved path: {resolved}",
            }
        content = resolved.read_text(encoding="utf-8")
        if resolved.suffix == ".json":
            ext, content_type, plan_format = "json", "application/json", "json"
    elif test_plan:
        content = json.dumps(test_plan, ensure_ascii=False, indent=2)
        ext, content_type, plan_format = "json", "application/json", "json"
    elif plan_content:
        content = plan_content
        if plan_format == "json":
            ext, content_type = "json", "application/json"
    else:
        return {"error": "Either plan_path, test_plan, or plan_content must be provided"}

    file_name = f"test-plan.{ext}"
    file_path = artifacts / file_name
    file_path.write_text(content, encoding="utf-8")

    # Phase 16: add DB attachment record when WebFunction/WebSubFunction models exist

    return {
        "success": True,
        "file_path": str(file_path),
        "format": plan_format,
        "file_extension": ext,
        "message": f"Test plan saved ({plan_format})",
    }


# ---------------------------------------------------------------------------
# Tool 2: Save test cases
# ---------------------------------------------------------------------------


@tool
async def save_web_test_cases(
    sub_function_id: str,
    test_cases: list[dict],
    project_identifier: str,
) -> dict:
    """Save test cases for a web sub-function.

    Args:
        sub_function_id: Sub-function UUID.
        test_cases: List of test case dicts.
        project_identifier: Project identifier.

    Returns:
        Dict with file_path and count information.
    """
    space_id = get_space_id()
    artifacts = _artifacts_dir(space_id, sub_function_id)

    cases_json = json.dumps(test_cases, ensure_ascii=False, indent=2)
    file_path = artifacts / "test-cases.json"
    file_path.write_text(cases_json, encoding="utf-8")

    # Phase 16: add DB attachment record when WebFunction/WebSubFunction models exist

    return {
        "success": True,
        "file_path": str(file_path),
        "test_cases_count": len(test_cases),
        "message": f"Saved {len(test_cases)} test cases",
    }


# ---------------------------------------------------------------------------
# Tool 3: Save test script
# ---------------------------------------------------------------------------


@tool
async def save_web_test_script(
    sub_function_id: str,
    script_content: Optional[str] = None,
    script_path: Optional[str] = None,
    script_language: str = "typescript",
    script_format: str = "playwright",
    project_identifier: str = "",
) -> dict:
    """Save a test script for a web sub-function.

    Args:
        sub_function_id: Sub-function UUID.
        script_content: Script source code text.
        script_path: Path to a generated script file.
        script_language: Language (typescript, javascript, python).
        script_format: Test framework (playwright, cypress, selenium).
        project_identifier: Project identifier.

    Returns:
        Dict with file_path and language info.
    """
    space_id = get_space_id()
    artifacts = _artifacts_dir(space_id, sub_function_id)

    content: str | None = None

    if script_path:
        resolved = _resolve_workspace_path(script_path)
        if not resolved.exists():
            return {
                "error": f"Script file not found: {script_path}",
                "hint": f"Resolved path: {resolved}",
            }
        content = resolved.read_text(encoding="utf-8")
    elif script_content:
        content = script_content
    else:
        return {"error": "Either script_path or script_content must be provided"}

    ext_map = {"typescript": "spec.ts", "javascript": "spec.js", "python": ".py"}
    ext = ext_map.get(script_language, "spec.ts")
    file_name = f"test-script.{ext}"
    file_path = artifacts / file_name
    file_path.write_text(content, encoding="utf-8")

    # Phase 16: add DB attachment record when WebFunction/WebSubFunction models exist

    return {
        "success": True,
        "file_path": str(file_path),
        "language": script_language,
        "format": script_format,
        "message": "Test script saved",
    }


# ---------------------------------------------------------------------------
# Tool 4: Get sub-function artifacts
# ---------------------------------------------------------------------------


@tool
async def get_web_sub_function_artifacts(
    sub_function_id: str,
    artifact_type: Optional[str] = None,
) -> dict:
    """List artifacts for a web sub-function.

    Scans the artifacts directory for saved files and categorizes them.

    Args:
        sub_function_id: Sub-function UUID.
        artifact_type: Optional filter: test_plan, test_cases, test_script, test_report.

    Returns:
        Dict with artifacts list and total count.
    """
    space_id = get_space_id()
    artifacts_dir = _artifacts_dir(space_id, sub_function_id)

    type_map = {
        "test-plan": "test_plan",
        "test-plan.md": "test_plan",
        "test-plan.json": "test_plan",
        "test-cases.json": "test_cases",
        "test-script.spec.ts": "test_script",
        "test-script.spec.js": "test_script",
        "test-script.py": "test_script",
    }

    results = []
    if artifacts_dir.exists():
        for fp in artifacts_dir.iterdir():
            if fp.is_file():
                artifact = {
                    "id": str(fp),  # Phase 15: file path serves as artifact ID
                    "file_name": fp.name,
                    "type": type_map.get(fp.name, "unknown"),
                    "file_size": fp.stat().st_size,
                    "created_at": datetime.fromtimestamp(
                        fp.stat().st_ctime, tz=timezone.utc
                    ).isoformat(),
                }
                if artifact_type is None or artifact.get("type") == artifact_type:
                    results.append(artifact)

    return {
        "success": True,
        "sub_function_id": sub_function_id,
        "artifacts": results,
        "total": len(results),
    }


# ---------------------------------------------------------------------------
# Tool 5: Save test report
# ---------------------------------------------------------------------------


@tool
async def save_web_test_report(
    test_run_id: str,
    report_content: Optional[str] = None,
    report_path: Optional[str] = None,
    project_identifier: str = "",
) -> dict:
    """Save a test execution report.

    Args:
        test_run_id: Test run identifier.
        report_content: Report HTML/JSON content.
        report_path: Path to report file.
        project_identifier: Project identifier.

    Returns:
        Dict with file_path and message.
    """
    space_id = get_space_id()

    content: str | None = None
    if report_path:
        resolved = _resolve_workspace_path(report_path)
        if not resolved.exists():
            return {"error": f"Report file not found: {report_path}"}
        content = resolved.read_text(encoding="utf-8")
    elif report_content:
        content = report_content
    else:
        return {"error": "Either report_path or report_content must be provided"}

    reports = _reports_dir(space_id)
    run_dir = reports / test_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    file_path = run_dir / "report.html"
    file_path.write_text(content, encoding="utf-8")

    # Phase 16: add DB attachment record when WebFunction/WebSubFunction models exist

    return {
        "success": True,
        "file_path": str(file_path),
        "message": "Test report saved",
    }


# ---------------------------------------------------------------------------
# Tool 6: Get artifact content
# ---------------------------------------------------------------------------


@tool
async def get_artifact_content(artifact_id: str) -> dict:
    """Read file content from local filesystem path.

    Phase 15: artifact_id is the local file path.
    Phase 16: artifact_id will be a UUID mapped to an Attachment record.

    Args:
        artifact_id: File path (Phase 15) or attachment UUID (Phase 16).

    Returns:
        Dict with file content and metadata.
    """
    file_path = Path(artifact_id)

    if not file_path.exists():
        return {"error": f"File not found: {artifact_id}"}

    # Path safety check: ensure within workspace
    workspace_root = settings.web_mcp_root_resolved.resolve()
    try:
        file_path.resolve().relative_to(workspace_root)
    except ValueError:
        return {"error": "File path must be within workspace directory"}

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "success": True,
            "file_name": file_path.name,
            "content": content,
            "file_size": file_path.stat().st_size,
            "created_at": datetime.fromtimestamp(
                file_path.stat().st_ctime, tz=timezone.utc
            ).isoformat(),
        }
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}


# Tool list for package export
ARTIFACT_TOOLS: list = [
    save_web_test_plan,
    save_web_test_cases,
    save_web_test_script,
    get_web_sub_function_artifacts,
    save_web_test_report,
    get_artifact_content,
]
