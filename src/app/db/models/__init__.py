"""Database models package.

Imports all models in dependency order to ensure proper SQLAlchemy
metadata registration. All models must be imported here before
calling Base.metadata.create_all().
"""

# Base and mixins (no table, but required for inheritance)
from src.app.db.models.base import UUIDMixin, TimestampMixin  # noqa: F401

# 项目表：2026-08 用例存储 MD 化之后，它不再是"项目资源库"，只剩一个身份锚点——
# api_scripts / unity_scripts / web_ui_scripts 各有一列 nullable 的 project_id
# 外键指过来（ondelete=SET NULL）。表要留着让 create_all 建出来，否则新库上这些
# 外键会悬空。它的 CRUD API / service / repo / schema 已随「项目模块无 UI」
# 一并删除（2026-09-18）。
from src.app.db.models.project import Project  # noqa: F401

# Thread Messages (for local message storage, independent of LangGraph state)
from src.app.db.models.thread_message import ThreadMessage  # noqa: F401

# Thread Info (for persisting thread metadata across LangGraph restarts)
from src.app.db.models.thread_info import ThreadInfo  # noqa: F401

# --- Transformation modules (2026-08) ---------------------------------------

# User module (用户模块)
from src.app.db.models.user import User, AuthToken  # noqa: F401

# Codebase-graph module (代码图谱模块)
from src.app.db.models.codebase import (  # noqa: F401
    CodebaseImpactReport,
    CodebaseIndexRun,
    CodebaseRepo,
)

# API automation module (接口自动化模块)
from src.app.db.models.api_script import ApiScript, ApiScriptRun  # noqa: F401
from src.app.db.models.api_doc import ApiDocImport  # noqa: F401

# Unity UI automation module (Unity 自动化模块)
from src.app.db.models.unity_script import UnityScript, UnityScriptRun  # noqa: F401

# Browser UI automation module (Web-UI 自动化模块, Playwright CLI)
from src.app.db.models.web_ui_script import WebUiScript, WebUiScriptRun  # noqa: F401

# Eval module (测评模块)
from src.app.db.models.eval_run import EvalBatch, EvalCaseResult  # noqa: F401

# Settings module (设置模块)
from src.app.db.models.setting import SettingKV  # noqa: F401

# Identifier counters: 只被 db/utils/identifier.py 的裸 SQL 读写，但必须有模型——
# init_db() 是按 Base.metadata 建表的，纯裸 SQL 的表永远不会被创建
from src.app.db.models.identifier import IdentifierSeq  # noqa: F401
