"""System enum definitions.

2026-08 用例 MD 重构后仅保留仍被引用的枚举（附件、通用排序等）；
用例相关枚举（Priority / TestCaseState / 模板等）随 test_cases 表一并移除，
用例优先级改以 MD 标题里的 [P0]-[P3] 标记表达。
"""

from enum import Enum


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


class AttachmentEntityType(str, Enum):
    """Entity type that an attachment is associated with.

    附件实体类型沿用历史取值（SQLite 枚举按值存储，删值不影响旧行）。
    """

    TEST_CASE = "test_case"
    TEST_CASE_STEP = "test_case_step"
    TEST_RESULT = "test_result"
    TEST_STEP_RESULT = "test_step_result"
    API_ENDPOINT = "api_endpoint"
    API_TEST_PLAN = "api_test_plan"
    API_TEST_CASE = "api_test_case"
    API_TEST_SCRIPT = "api_test_script"
    API_TEST_REPORT = "api_test_report"
