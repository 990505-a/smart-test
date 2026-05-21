"""Web Agent tool registry and backend configuration.

Tool categories (4 categories, 16 tools total):
  1. Function management: list/get/create web functions and sub-functions (7 tools)
  2. Test artifacts: save plan/cases/script/report, get artifacts/content (6 tools)
  3. Script management: info/download/delete (3 tools)
  4. Execution: execute script, get status (2 tools)

Backends:
  - shell_backend: LocalShellBackend for executing Playwright commands
  - file_backend: FilesystemBackend for reading/writing workspace files
  - composite_backend: CompositeBackend routing to both backends
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import CompositeBackend, FilesystemBackend, LocalShellBackend

from src.app.agents.web.tools.function_tools import FUNCTION_TOOLS
from src.app.agents.web.tools.test_artifacts_tools import ARTIFACT_TOOLS
from src.app.agents.web.tools.script_tools import SCRIPT_TOOLS
from src.app.agents.web.tools.execution_tools import EXECUTION_TOOLS
from src.app.core.config import settings
from src.app.core.workspace import get_workspace_dir

# Combined tool list for the Web agent
WEB_AGENT_TOOLS: list = (
    FUNCTION_TOOLS +     # 7 function management tools
    ARTIFACT_TOOLS +     # 6 test artifact tools
    SCRIPT_TOOLS +       # 3 script management tools
    EXECUTION_TOOLS      # 2 execution tools
)

# Backends
_default_workspace_dir = get_workspace_dir("default", "web")
_default_workspace_dir.mkdir(parents=True, exist_ok=True)

shell_backend = LocalShellBackend(
    root_dir=_default_workspace_dir,
    virtual_mode=False,
    inherit_env=True,
    timeout=180,
)

file_backend = FilesystemBackend(
    root_dir=_default_workspace_dir,
    virtual_mode=True,
)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={"/": file_backend},
)
