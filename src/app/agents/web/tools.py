"""
Standalone tools and backend configuration for the Web Automation Testing Agent.

This module contains no LLM initialization, so it can be imported and tested
independently of model-provider dependencies.

Custom Tools:
    - detect_test_mode: classify user request as MODE_A_QA / MODE_B_COMPONENT / ASK_CLARIFICATION
    - check_environment: verify playwright-cli and agent-browser availability
    - ensure_output_dir: create timestamped artifact directories for testing sessions

Backends:
    - shell_backend: LocalShellBackend for executing Playwright commands
    - file_backend: FilesystemBackend for reading SKILL.md and writing artifacts
    - composite_backend: CompositeBackend routing file ops to file_backend,
      execute ops to shell_backend
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

from src.app.core.config import settings

# =============================================================================
# Workspace & Artifact Directories
# =============================================================================
workspace_dir = settings.workspace_dir / "web"
output_root = workspace_dir / "web-output"
output_root.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Custom Tools
# =============================================================================


def detect_test_mode(user_request: str) -> str:
    """
    Analyze the user's request and decide which testing mode to run.

    Args:
        user_request: The raw user message describing what they want.

    Returns:
        "MODE_A_QA" if the request contains a URL and no repo path.
        "MODE_B_COMPONENT" if the request contains a local directory/repo path.
        "ASK_CLARIFICATION" if ambiguous.
    """
    url_pattern = re.compile(r"https?://[^\s\"']+")
    has_url = bool(url_pattern.search(user_request))

    path_markers = [
        r"[a-zA-Z]:\\",
        r"/home/",
        r"/Users/",
        r"/workspace/",
        r"git@",
        r"github\.com",
        r"\.git",
        r"src/",
        r"repo",
        r"project path",
        r"source code",
        r"codebase",
    ]
    has_repo = any(re.search(marker, user_request) for marker in path_markers)

    if has_repo and not has_url:
        return "MODE_B_COMPONENT"
    if has_url and not has_repo:
        return "MODE_A_QA"
    if has_url and has_repo:
        return "MODE_B_COMPONENT"
    return "ASK_CLARIFICATION"


def check_environment() -> dict[str, Any]:
    """
    Verify that required CLI tools are available in the current environment.

    Returns:
        A status dictionary with availability flags and version strings.
    """
    results: dict[str, Any] = {"platform": os.name, "tools": {}}

    for tool in ["playwright-cli", "agent-browser"]:
        candidates = [tool]
        if os.name == "nt":
            candidates.append(f"{tool}.cmd")

        for cmd in candidates:
            try:
                proc = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    shell=False,
                )
                results["tools"][tool] = {
                    "available": proc.returncode == 0,
                    "version": proc.stdout.strip() if proc.returncode == 0 else None,
                    "error": proc.stderr.strip() if proc.returncode != 0 else None,
                }
                break
            except FileNotFoundError:
                continue
            except Exception as e:  # noqa: BLE001
                results["tools"][tool] = {"available": False, "version": None, "error": str(e)}
                break
        else:
            results["tools"][tool] = {"available": False, "version": None, "error": "not found on PATH"}

    return results


def ensure_output_dir(mode: str, label: str = "") -> str:
    """
    Create a timestamped artifact directory tree for the current testing session.

    Args:
        mode: Either "MODE_A_QA" or "MODE_B_COMPONENT".
        label: Optional project name or URL hostname for the directory name.

    Returns:
        The absolute path to the created root output directory.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = re.sub(r"[^\w\-]", "_", label)[:40] if label else "session"

    if mode == "MODE_A_QA":
        root = output_root / "qa" / f"{safe_label}_{ts}"
        for sub in ("screenshots", "traces", "videos", "storage"):
            (root / sub).mkdir(parents=True, exist_ok=True)
    elif mode == "MODE_B_COMPONENT":
        root = output_root / "tests" / f"{safe_label}_{ts}"
        for sub in ("poms", "tests", "references"):
            (root / sub).mkdir(parents=True, exist_ok=True)
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return str(root.resolve())


# =============================================================================
# Backends
# =============================================================================

shell_backend = LocalShellBackend(
    root_dir=workspace_dir,
    virtual_mode=False,
    inherit_env=True,
    timeout=180,
)

file_backend = FilesystemBackend(
    root_dir=workspace_dir,
    virtual_mode=True,
)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={"/": file_backend},
)
