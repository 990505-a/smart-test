"""System enum definitions.

Based on BrowserStack Test Management API enum definitions and
classroom reference implementation.
"""

from enum import Enum


class Priority(str, Enum):
    """Test case priority level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestCaseState(str, Enum):
    """Test case lifecycle state.

    Design phase: new, review_pending, reviewed
    Execution phase: not_run, passed, failed, blocked, skipped
    """

    NEW = "new"
    REVIEW_PENDING = "review_pending"
    REVIEWED = "reviewed"
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TestCaseType(str, Enum):
    """Test case type classification."""

    ACCEPTANCE = "acceptance"
    ACCESSIBILITY = "accessibility"
    COMPATIBILITY = "compatibility"
    DESTRUCTIVE = "destructive"
    FUNCTIONAL = "functional"
    OTHER = "other"
    PERFORMANCE = "performance"
    REGRESSION = "regression"
    SECURITY = "security"
    SMOKE_SANITY = "smoke_sanity"
    USABILITY = "usability"


class HTTPStatusCode(int, Enum):
    """Standard HTTP status codes."""

    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500


class SortOrder(str, Enum):
    """Sort order direction."""

    ASC = "asc"
    DESC = "desc"


class IssueType(str, Enum):
    """External issue tracking system type."""

    JIRA = "jira"
    GITHUB = "github"
    GITLAB = "gitlab"
    AZURE = "azure"
    OTHER = "other"


class TestCaseTemplate(str, Enum):
    """Test case template type (standard vs BDD)."""

    TEST_CASE = "test_case"
    TEST_CASE_BDD = "test_case_bdd"


class AutomationStatus(str, Enum):
    """Test case automation status."""

    NOT_AUTOMATED = "not_automated"
    AUTOMATED = "automated"
    IN_PROGRESS = "in_progress"
    OBSOLETE = "obsolete"


class BulkEditOperation(str, Enum):
    """Bulk edit operation type."""

    IGNORE = "ignore"
    REPLACE = "replace"
    ADD = "add"
    REMOVE = "remove"


class ExportStatus(str, Enum):
    """Export task status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TestRunState(str, Enum):
    """Test run execution state."""

    NEW_RUN = "new_run"
    IN_PROGRESS = "in_progress"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"
    DONE = "done"
    CLOSED = "closed"


class TestRunActiveState(str, Enum):
    """Test run active/closed state."""

    ACTIVE = "active"
    CLOSED = "closed"


class TestResultStatus(str, Enum):
    """Test result execution status for a single test case in a run."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    NOT_EXECUTED = "not_executed"


class TestPlanStatus(str, Enum):
    """Test plan status."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TestPlanActiveState(str, Enum):
    """Test plan active/closed state."""

    ACTIVE = "active"
    CLOSED = "closed"


class FolderType(str, Enum):
    """Folder type for organizing test assets."""

    TEST_CASE = "test_case"
    API_TEST = "api_test"


class AttachmentEntityType(str, Enum):
    """Entity type that an attachment is associated with."""

    TEST_CASE = "test_case"
    TEST_CASE_STEP = "test_case_step"
    TEST_RESULT = "test_result"
    TEST_STEP_RESULT = "test_step_result"
    API_ENDPOINT = "api_endpoint"
    API_TEST_PLAN = "api_test_plan"
    API_TEST_CASE = "api_test_case"
    API_TEST_SCRIPT = "api_test_script"
    API_TEST_REPORT = "api_test_report"


class APITestRunStatus(str, Enum):
    """API test run execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
