"""Database models package.

Imports all models in dependency order to ensure proper SQLAlchemy
metadata registration. All models must be imported here before
calling Base.metadata.create_all().
"""

# Base and mixins (no table, but required for inheritance)
from src.app.db.models.base import UUIDMixin, TimestampMixin  # noqa: F401

# Workspace (independent top-level entity)
from src.app.db.models.workspace import Workspace  # noqa: F401

# Core table: Project (referenced by attachments)
from src.app.db.models.project import Project  # noqa: F401

# Attachment (depends on Project)
from src.app.db.models.attachment import Attachment  # noqa: F401

# Configuration (independent)
from src.app.db.models.configuration import Configuration  # noqa: F401

# Memory (independent, scoped by space_id)
from src.app.db.models.memory import Memory  # noqa: F401

# Thread Messages (for local message storage, independent of LangGraph state)
from src.app.db.models.thread_message import ThreadMessage  # noqa: F401

# Thread Info (for persisting thread metadata across LangGraph restarts)
from src.app.db.models.thread_info import ThreadInfo  # noqa: F401

# --- Transformation modules (2026-08) ---------------------------------------

# User module (用户模块)
from src.app.db.models.user import User, AuthToken  # noqa: F401

# Self-evolution module (自进化模块)
from src.app.db.models.evolution import EvolutionRun  # noqa: F401

# Codebase-graph module (代码图谱模块)
from src.app.db.models.codebase import CodebaseIndexRun, CodebaseRepo  # noqa: F401

# API automation module (接口自动化模块)
from src.app.db.models.api_script import ApiScript, ApiScriptRun  # noqa: F401
from src.app.db.models.api_doc import ApiDocImport  # noqa: F401

# Unity UI automation module (UI 自动化模块)
from src.app.db.models.ui_script import UiScript, UiScriptRun  # noqa: F401

# Settings module (设置模块)
from src.app.db.models.setting import SettingKV  # noqa: F401
