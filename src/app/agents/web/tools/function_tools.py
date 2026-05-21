"""Web function management tools.

Provides 7 tools for managing Web functions and sub-functions:
  - list_web_functions
  - get_function_details
  - list_web_sub_functions
  - get_sub_function_details
  - get_folder_structure
  - create_web_function
  - create_web_sub_function

Phase 15 uses local JSON file storage (no WebFunction/WebSubFunction DB models).
Phase 16 will add DB models and migrate to DB-backed storage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from langchain_core.tools import tool

from src.app.core.workspace import get_space_id, get_workspace_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _functions_path(space_id: str) -> Path:
    """Return path to functions.json for the given workspace."""
    d = get_workspace_dir(space_id, "web")
    d.mkdir(parents=True, exist_ok=True)
    return d / "functions.json"


def _sub_functions_path(space_id: str) -> Path:
    """Return path to sub_functions.json for the given workspace."""
    d = get_workspace_dir(space_id, "web")
    d.mkdir(parents=True, exist_ok=True)
    return d / "sub_functions.json"


def _read_json(path: Path) -> list[dict]:
    """Read a JSON file, returning empty list if missing or corrupt."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_json(path: Path, data: list[dict]) -> None:
    """Write a JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool 1-2: Function listing and details
# ---------------------------------------------------------------------------


@tool
async def list_web_functions(
    project_identifier: str,
    folder_id: Optional[str] = None,
) -> dict:
    """List web functions for a project.

    Args:
        project_identifier: Project identifier string.
        folder_id: Optional folder ID to filter results.

    Returns:
        Dict with success flag, list of functions, and total count.
    """
    space_id = get_space_id()
    functions = _read_json(_functions_path(space_id))

    # Filter by project_identifier
    results = [f for f in functions if f.get("project_identifier") == project_identifier]

    if folder_id:
        results = [f for f in results if f.get("folder_id") == folder_id]

    # Sort by sort_order then created_at
    results.sort(key=lambda f: (f.get("sort_order", 0), f.get("created_at", "")))

    return {"success": True, "functions": results, "total": len(results)}


@tool
async def get_function_details(function_id: str) -> dict:
    """Get details for a specific web function.

    Args:
        function_id: The function UUID.

    Returns:
        Dict with function details or error message.
    """
    space_id = get_space_id()
    functions = _read_json(_functions_path(space_id))

    for func in functions:
        if func.get("id") == function_id:
            return {"success": True, **func}

    return {"error": f"Function {function_id} not found"}


# ---------------------------------------------------------------------------
# Tool 3-4: Sub-function listing and details
# ---------------------------------------------------------------------------


@tool
async def list_web_sub_functions(
    project_identifier: str,
    function_id: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> dict:
    """List web sub-functions for a project.

    Args:
        project_identifier: Project identifier string.
        function_id: Optional function ID to filter by parent function.
        folder_id: Optional folder ID to filter results.

    Returns:
        Dict with success flag, list of sub-functions, and total count.
    """
    space_id = get_space_id()
    sub_functions = _read_json(_sub_functions_path(space_id))

    results = [
        sf
        for sf in sub_functions
        if sf.get("project_identifier") == project_identifier
    ]

    if function_id:
        results = [sf for sf in results if sf.get("function_id") == function_id]
    if folder_id:
        results = [sf for sf in results if sf.get("folder_id") == folder_id]

    results.sort(key=lambda sf: (sf.get("sort_order", 0), sf.get("created_at", "")))

    return {"success": True, "sub_functions": results, "total": len(results)}


@tool
async def get_sub_function_details(sub_function_id: str) -> dict:
    """Get details for a specific web sub-function.

    Args:
        sub_function_id: The sub-function UUID.

    Returns:
        Dict with sub-function details or error message.
    """
    space_id = get_space_id()
    sub_functions = _read_json(_sub_functions_path(space_id))

    for sf in sub_functions:
        if sf.get("id") == sub_function_id:
            return {"success": True, **sf}

    return {"error": f"Sub-function {sub_function_id} not found"}


# ---------------------------------------------------------------------------
# Tool 5: Folder structure
# ---------------------------------------------------------------------------


@tool
async def get_folder_structure(project_identifier: str) -> dict:
    """Get folder tree for web test type folders.

    Phase 15 returns an empty structure since Folder model is not yet
    configured for web_test type. Phase 16 will add DB-backed folder queries.

    Args:
        project_identifier: Project identifier string.

    Returns:
        Dict with success flag and folder tree.
    """
    # Phase 16: Query Folder model with folder_type=WEB_TEST
    return {"success": True, "folders": [], "total": 0}


# ---------------------------------------------------------------------------
# Tool 6-7: Create function and sub-function
# ---------------------------------------------------------------------------


@tool
async def create_web_function(
    project_identifier: str,
    display_name: str,
    name: str,
    folder_id: Optional[str] = None,
    description: Optional[str] = None,
    base_url: Optional[str] = None,
    business_module: Optional[str] = None,
    navigation: Optional[dict] = None,
    pages: Optional[list] = None,
    tags: Optional[list] = None,
    custom_config: Optional[dict] = None,
) -> dict:
    """Create a new web function.

    Args:
        project_identifier: Project identifier string.
        display_name: Human-readable function name.
        name: English identifier for the function.
        folder_id: Optional parent folder ID.
        description: Optional function description.
        base_url: Optional base URL for the function.
        business_module: Optional business module tag.
        navigation: Optional navigation config dict.
        pages: Optional page list.
        tags: Optional tag list.
        custom_config: Optional custom config dict.

    Returns:
        Dict with created function info.
    """
    space_id = get_space_id()
    path = _functions_path(space_id)
    functions = _read_json(path)

    func_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Auto-generate identifier
    identifier = f"WF-{len(functions) + 1:03d}"

    new_func = {
        "id": func_id,
        "identifier": identifier,
        "project_identifier": project_identifier,
        "display_name": display_name,
        "name": name,
        "folder_id": folder_id,
        "description": description,
        "base_url": base_url,
        "business_module": business_module,
        "navigation": navigation or {},
        "pages": pages or [],
        "tags": tags or [],
        "custom_config": custom_config or {},
        "total_sub_functions": 0,
        "total_test_cases": 0,
        "total_test_runs": 0,
        "last_run_status": None,
        "sort_order": 0,
        "created_at": now,
        "updated_at": now,
    }

    functions.append(new_func)
    _write_json(path, functions)

    return {
        "success": True,
        "id": func_id,
        "identifier": identifier,
        "display_name": display_name,
        "name": name,
        "message": f"Web function '{display_name}' created successfully",
    }


@tool
async def create_web_sub_function(
    project_identifier: str,
    function_id: str,
    display_name: str,
    name: str,
    folder_id: Optional[str] = None,
    description: Optional[str] = None,
    test_type: str = "functional",
    target_pages: Optional[list] = None,
    test_scenario: Optional[str] = None,
    test_data: Optional[dict] = None,
    expected_results: Optional[list] = None,
    priority: str = "medium",
    tags: Optional[list] = None,
    custom_config: Optional[dict] = None,
) -> dict:
    """Create a new web sub-function under a parent function.

    Args:
        project_identifier: Project identifier string.
        function_id: Parent function UUID.
        display_name: Human-readable sub-function name.
        name: English identifier for the sub-function.
        folder_id: Optional parent folder ID.
        description: Optional sub-function description.
        test_type: Test type (default: functional).
        target_pages: Optional target page list.
        test_scenario: Optional test scenario description.
        test_data: Optional test data dict.
        expected_results: Optional expected results list.
        priority: Priority level (default: medium).
        tags: Optional tag list.
        custom_config: Optional custom config dict.

    Returns:
        Dict with created sub-function info.
    """
    space_id = get_space_id()

    # Verify parent function exists
    functions = _read_json(_functions_path(space_id))
    parent = None
    for f in functions:
        if f.get("id") == function_id:
            parent = f
            break
    if not parent:
        return {"error": f"Parent function {function_id} not found"}

    sf_path = _sub_functions_path(space_id)
    sub_functions = _read_json(sf_path)

    sf_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Auto-generate identifier
    identifier = f"WSF-{len(sub_functions) + 1:03d}"

    new_sf = {
        "id": sf_id,
        "identifier": identifier,
        "project_identifier": project_identifier,
        "function_id": function_id,
        "display_name": display_name,
        "name": name,
        "folder_id": folder_id,
        "description": description,
        "test_type": test_type,
        "target_pages": target_pages or [],
        "test_scenario": test_scenario,
        "test_data": test_data or {},
        "expected_results": expected_results or [],
        "priority": priority,
        "tags": tags or [],
        "custom_config": custom_config or {},
        "total_test_cases": 0,
        "total_test_runs": 0,
        "last_run_status": None,
        "sort_order": 0,
        "created_at": now,
        "updated_at": now,
    }

    sub_functions.append(new_sf)
    _write_json(sf_path, sub_functions)

    # Update parent's sub-function count
    parent["total_sub_functions"] = parent.get("total_sub_functions", 0) + 1
    parent["updated_at"] = now
    _write_json(_functions_path(space_id), functions)

    return {
        "success": True,
        "id": sf_id,
        "identifier": identifier,
        "display_name": display_name,
        "name": name,
        "message": f"Web sub-function '{display_name}' created successfully",
    }


# Tool list for package export
FUNCTION_TOOLS: list = [
    list_web_functions,
    get_function_details,
    list_web_sub_functions,
    get_sub_function_details,
    get_folder_structure,
    create_web_function,
    create_web_sub_function,
]
