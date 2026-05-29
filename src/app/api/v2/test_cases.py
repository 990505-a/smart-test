"""Test case API routes.

Provides test case CRUD endpoints with step management.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

import json
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from src.app.api.deps import DbSessionDep, PaginationDep, TestCaseServiceDep
from src.app.core.llms import get_deepseek_model
from src.app.db.schemas.common import SuccessResponse, MessageResponse
from src.app.db.schemas.enums import Priority, TestCaseState
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo
from src.app.db.schemas.test_case import TestCaseCreate, TestCaseInfo, TestCaseUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test-cases")


@router.get(
    "",
    response_model=PaginatedResponse[TestCaseInfo],
    summary="List test cases",
    description="List test cases with filtering and pagination",
)
async def list_test_cases(
    service: TestCaseServiceDep,
    pagination: PaginationDep,
    project_id: Optional[UUID] = Query(default=None, description="Filter by project"),
    folder_id: Optional[UUID] = Query(default=None, description="Filter by folder"),
    priority: Optional[str] = Query(default=None, description="Filter by priority"),
    state: Optional[str] = Query(default=None, description="Filter by state"),
):
    """List test cases with filtering and pagination."""
    cases, total = await service.list_with_filters(
        project_id=project_id,
        folder_id=folder_id,
        priority=priority,
        state=state,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=cases,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/test-cases",
        ),
    )


@router.get(
    "/{test_case_id}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="Get test case",
    description="Get a test case with its steps",
)
async def get_test_case(
    test_case_id: UUID,
    service: TestCaseServiceDep,
):
    """Get a test case with eagerly loaded steps."""
    test_case = await service.get_with_steps(test_case_id)
    return SuccessResponse(success=True, data=test_case)


@router.post(
    "",
    response_model=SuccessResponse[TestCaseInfo],
    status_code=status.HTTP_201_CREATED,
    summary="Create test case",
    description="Create a test case with steps",
)
async def create_test_case(
    data: TestCaseCreate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Create a test case with steps in a single transaction."""
    test_case = await service.create_with_steps(data)
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.patch(
    "/{test_case_id}",
    response_model=SuccessResponse[TestCaseInfo],
    summary="Update test case",
    description="Update a test case's fields",
)
async def update_test_case(
    test_case_id: UUID,
    data: TestCaseUpdate,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Update a test case."""
    test_case = await service.update(test_case_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=test_case)


@router.delete(
    "/{test_case_id}",
    response_model=MessageResponse,
    summary="Delete test case",
    description="Delete a test case and its steps",
)
async def delete_test_case(
    test_case_id: UUID,
    service: TestCaseServiceDep,
    db: DbSessionDep,
):
    """Delete a test case."""
    message = await service.delete(test_case_id)
    await db.commit()
    return MessageResponse(success=True, message=message)


# ---------------------------------------------------------------------------
# AI-organized export endpoint
# ---------------------------------------------------------------------------

class OrganizeRequest(BaseModel):
    cases: list[dict]


class OrganizeResponse(BaseModel):
    organized: list[dict]
    raw_count: int


ORGANIZE_PROMPT = """你是一个测试用例分类专家。你会收到一批用例的编号和标题，需要将它们分成三级层级结构。

你的任务：
1. 根据用例标题内容，归纳出功能模块（一级，如"悬赏俸禄系统"、"深渊系统"、"系统解锁条件"）
2. 在每个模块下归纳出子模块（二级，如"长间隔挂机"、"短间隔挂机"、"排名奖励"）
3. 把每条用例归入对应的模块和子模块

输出格式（严格JSON，不加markdown标记）：
[
  {{
    "module": "模块名",
    "sub_modules": [
      {{
        "name": "子模块名",
        "indices": [1, 5, 12]
      }}
    ]
  }}
]

indices 是输入中用例的编号（从1开始）。每个用例只能出现一次。

要求：
- 模块 3-8 个
- 子模块每个模块 2-6 个
- 每条用例必须且只能归入一个子模块
- 严格返回JSON数组

用例列表：
{{cases}}"""


def _strip_tc_prefix(name: str) -> str:
    import re
    name = re.sub(r"^TC-[A-Z0-9]+-[A-Z0-9]+-\d+[：:]\s*", "", name)
    name = re.sub(r"^TC-[A-Z0-9]+-\d+[：:]\s*", "", name)
    return name


@router.post(
    "/organize",
    summary="AI-organize test cases into hierarchical structure",
    description="Uses AI to classify test cases into a 3-level hierarchy, then assembles with original data.",
)
async def organize_test_cases(request: OrganizeRequest) -> OrganizeResponse:
    if not request.cases:
        return OrganizeResponse(organized=[], raw_count=0)

    import re

    # Build index → original data map
    cases = request.cases
    priority_map = {"critical": "P0-严重", "high": "P1-高", "medium": "P2-中", "low": "P3-低"}

    # Build compact title-only list for AI (saves output tokens)
    title_lines = []
    for i, c in enumerate(cases, 1):
        name = _strip_tc_prefix(c.get("name", f"用例{i}"))
        title_lines.append(f"{i}. {name}")
    cases_text = "\n".join(title_lines)

    try:
        llm = get_deepseek_model()
        prompt = ORGANIZE_PROMPT.format(cases=cases_text)
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        classification = json.loads(content)

        # Build index → case data lookup
        def build_case(idx: int) -> dict:
            c = cases[idx - 1]
            return {
                "title": _strip_tc_prefix(c.get("name", "")),
                "steps": "；".join(
                    s.get("action", "") for s in (c.get("steps") or []) if s.get("action", "").strip()
                ),
                "expected": "；".join(
                    s.get("expected_result", "") for s in (c.get("steps") or []) if s.get("expected_result", "").strip()
                ),
                "data": c.get("preconditions", "") or "",
                "priority": priority_map.get(c.get("priority", ""), "P2-中"),
            }

        # Assemble organized structure from AI classification + original data
        organized = []
        used_indices: set[int] = set()
        for mod in classification:
            sub_modules = []
            for sub in mod.get("sub_modules", []):
                sub_cases = []
                for idx in sub.get("indices", []):
                    if 1 <= idx <= len(cases) and idx not in used_indices:
                        sub_cases.append(build_case(idx))
                        used_indices.add(idx)
                if sub_cases:
                    sub_modules.append({"name": sub.get("name", "未分类"), "cases": sub_cases})
            if sub_modules:
                organized.append({"module": mod.get("module", "未分类"), "sub_modules": sub_modules})

        # Append any cases the AI missed
        missed = []
        for i in range(1, len(cases) + 1):
            if i not in used_indices:
                missed.append(build_case(i))
        if missed:
            organized.append({"module": "其他", "sub_modules": [{"name": "未分类", "cases": missed}]})

        return OrganizeResponse(organized=organized, raw_count=len(cases))

    except json.JSONDecodeError as e:
        logger.error("AI classify returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("AI organize failed: %s", e)

    # Fallback: no AI, just return flat list
    return OrganizeResponse(
        organized=[{
            "module": "全部用例",
            "sub_modules": [{
                "name": "未分类",
                "cases": [
                    {
                        "title": _strip_tc_prefix(c.get("name", "")),
                        "steps": "；".join(s.get("action", "") for s in (c.get("steps") or []) if s.get("action", "").strip()),
                        "expected": "；".join(s.get("expected_result", "") for s in (c.get("steps") or []) if s.get("expected_result", "").strip()),
                        "data": c.get("preconditions", "") or "",
                        "priority": priority_map.get(c.get("priority", ""), "P2-中"),
                    }
                    for c in cases
                ],
            }],
        }],
        raw_count=len(cases),
    )
