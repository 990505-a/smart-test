"""Database models package.

Imports all models in dependency order to ensure proper SQLAlchemy
metadata registration. All models must be imported here before
calling Base.metadata.create_all().
"""

# Base and mixins (no table, but required for inheritance)
from src.app.db.models.base import UUIDMixin, TimestampMixin  # noqa: F401

# Workspace (independent top-level entity)
from src.app.db.models.workspace import Workspace  # noqa: F401

# Core table: Project (referenced by most other models)
from src.app.db.models.project import Project  # noqa: F401

# Folder (depends on Project, self-referencing parent)
from src.app.db.models.folder import Folder  # noqa: F401

# TestCase domain (depends on Project, Folder)
from src.app.db.models.test_case import TestCase, TestStep, Tag, TestCaseTag  # noqa: F401

# TestRun domain (depends on Project, TestCase)
from src.app.db.models.test_run import TestRun, TestRunTestCase  # noqa: F401

# TestResult domain (depends on TestRun, TestCase, TestRunTestCase)
from src.app.db.models.test_result import TestResult, TestStepResult  # noqa: F401

# API Endpoint (depends on Project, Folder, Attachment)
from src.app.db.models.attachment import Attachment  # noqa: F401
from src.app.db.models.api_endpoint import APIEndpoint  # noqa: F401

# Test Scenario domain (depends on Project, Folder, APIEndpoint)
from src.app.db.models.test_scenario import (  # noqa: F401
    TestScenario,
    ScenarioStep,
    StepDataMapping,
    ScenarioVariable,
    ScenarioRun,
    ScenarioStepResult,
)

# API Test domain (depends on Project, Folder, TestCase)
from src.app.db.models.api_test import APITest, APITestRun, APITestResult  # noqa: F401

# Web Function domain (depends on Project, Folder)
from src.app.db.models.web_function import WebFunction, WebSubFunction  # noqa: F401

# Web Test domain (depends on Project, Folder, TestCase, WebFunction, WebSubFunction)
from src.app.db.models.web_test import WebTest, WebTestRun, WebTestResult  # noqa: F401

# Configuration (independent)
from src.app.db.models.configuration import Configuration  # noqa: F401

# Thread Messages (for local message storage, independent of LangGraph state)
from src.app.db.models.thread_message import ThreadMessage  # noqa: F401

# Thread Info (for persisting thread metadata across LangGraph restarts)
from src.app.db.models.thread_info import ThreadInfo  # noqa: F401
