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


def _code_resplit_steps(steps: list[dict]) -> list[dict]:
    """Fallback: code-based splitting when AI resplit is unavailable.

    Detects mismatched action/expected_result counts and redistributes
    expected_result sentences across steps proportionally.
    """
    if not steps:
        return steps

    actions = [s["action"].strip() for s in steps]
    expecteds = [(s["expected_result"] or "").strip() for s in steps]

    # Count non-empty expected results
    non_empty_er = [e for e in expecteds if e]
    if len(non_empty_er) == 0 or len(non_empty_er) == len(actions):
        # Already balanced or no expected results — nothing to fix
        return steps

    # Collect all expected_result sentences, split by Chinese/English period
    all_er_parts: list[str] = []
    for e in expecteds:
        if e:
            # Split by Chinese period (。) or English period followed by space/end
            import re
            sentences = re.split(r"(?<=[。；])|(?<=\.\s)", e)
            all_er_parts.extend(s.strip() for s in sentences if s.strip())

    if not all_er_parts:
        return steps

    # Redistribute sentences across steps proportionally
    n_steps = len(actions)
    per_step = max(1, len(all_er_parts) // n_steps)
    result = []
    er_idx = 0
    for i, action in enumerate(actions):
        if i < n_steps - 1:
            chunk = all_er_parts[er_idx:er_idx + per_step]
            er_idx += per_step
        else:
            # Last step gets remaining
            chunk = all_er_parts[er_idx:]
        result.append({"action": action, "expected_result": "。".join(chunk)})
    return result


RESPLIT_PROMPT = """你是一个测试用例格式化专家。你会收到若干条测试用例的操作步骤和预期结果数据。

每条用例的 steps 数组中，每个元素有 action 和 expected_result 两个字段。
问题：有些用例的 action 有多条但 expected_result 只有一条（或反过来），导致操作步骤和预期结果无法一一对应。

你的任务：对每条用例，将操作步骤和预期结果重新拆分为 **1:1 配对** 的列表。每条操作步骤对应一条预期结果。

输出格式（严格JSON，不加markdown标记）：
{{
  "cases": [
    {{
      "index": 0,
      "steps": [
        {{"action": "操作1", "expected_result": "预期结果1"}},
        {{"action": "操作2", "expected_result": "预期结果2"}}
      ]
    }}
  ]
}}

index 是输入中的用例编号（从0开始）。
规则：
- action 和 expected_result 必须 1:1 配对
- 如果原始 expected_result 包含多个验证点，按逻辑拆分到对应 action
- 如果某个 action 没有明确的预期结果，用该 action 应产生的直接结果补充
- 保持原始语言和内容，不要增删信息
- 只输出需要处理的用例（steps 已正确配对的跳过）

输入数据：
{data}"""


async def _ai_resplit_steps(organized: list[dict], llm) -> list[dict]:
    """Use AI to re-split steps into 1:1 action/expected_result pairs."""
    # Collect all cases that need resplitting
    needs_resplit: list[tuple[int, int, int]] = []  # (flat_index, module_idx, sub_idx, case_idx)
    flat_cases: list[dict] = []
    flat_positions: list[tuple[int, int, int]] = []  # (mi, si, ci)

    for mi, mod in enumerate(organized):
        for si, sub in enumerate(mod.get("sub_modules", [])):
            for ci, case in enumerate(sub.get("cases", [])):
                steps = case.get("steps", [])
                if not steps or not isinstance(steps, list):
                    continue
                actions = [(s.get("action") or "") for s in steps]
                expecteds = [(s.get("expected_result") or "") for s in steps]
                # Check if steps are mismatched (some expected_result empty while others are long)
                non_empty_er = [e for e in expecteds if e and e.strip()]
                if len(non_empty_er) != len(actions) and len(non_empty_er) > 0:
                    flat_cases.append({"index": len(flat_cases), "title": case["title"], "steps": steps})
                    flat_positions.append((mi, si, ci))

    if not flat_cases:
        return organized

    try:
        import json as _json
        data_str = _json.dumps(flat_cases, ensure_ascii=False, indent=2)
        # Limit to first 20 cases to avoid token overflow
        if len(data_str) > 8000:
            flat_cases_limited = flat_cases[:20]
            data_str = _json.dumps(flat_cases_limited, ensure_ascii=False, indent=2)
        else:
            flat_cases_limited = flat_cases

        prompt = RESPLIT_PROMPT.format(data=data_str)
        response = await llm.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:])
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        result = _json.loads(content)
        resplit_map = {c["index"]: c["steps"] for c in result.get("cases", [])}

        # Apply resplit results
        for i, (mi, si, ci) in enumerate(flat_positions):
            if i < len(flat_cases_limited) and i in resplit_map:
                organized[mi]["sub_modules"][si]["cases"][ci]["steps"] = resplit_map[i]

        return organized

    except Exception as e:
        logger.warning("AI resplit failed, falling back to code resplit: %s", e)
        # Fallback: code-based splitting
        for mi, si, ci in flat_positions:
            steps = organized[mi]["sub_modules"][si]["cases"][ci]["steps"]
            organized[mi]["sub_modules"][si]["cases"][ci]["steps"] = _code_resplit_steps(steps)
        return organized


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
            # Keep structured steps so frontend can render numbered list
            raw_steps = c.get("steps") or []
            structured_steps = [
                {"action": (s.get("action") or ""), "expected_result": (s.get("expected_result") or "")}
                for s in raw_steps
                if (s.get("action") or "").strip()
            ]
            # Resplit: redistribute expected_result sentences to match action count
            structured_steps = _code_resplit_steps(structured_steps)
            return {
                "title": _strip_tc_prefix(c.get("name", "")),
                "steps": structured_steps,
                "expected": "",
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

        # ---- Phase 2: AI re-split steps/expected_results into 1:1 pairs ----
        organized = await _ai_resplit_steps(organized, llm)

        return OrganizeResponse(organized=organized, raw_count=len(cases))

    except json.JSONDecodeError as e:
        logger.error("AI classify returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("AI organize failed: %s", e)

    # Fallback: no AI, just return flat list with code-based resplit
    def build_fallback_case(c: dict) -> dict:
        raw_steps = c.get("steps") or []
        structured_steps = [
            {"action": (s.get("action") or ""), "expected_result": (s.get("expected_result") or "")}
            for s in raw_steps
            if (s.get("action") or "").strip()
        ]
        structured_steps = _code_resplit_steps(structured_steps)
        return {
            "title": _strip_tc_prefix(c.get("name", "")),
            "steps": structured_steps,
            "expected": "",
            "data": c.get("preconditions", "") or "",
            "priority": priority_map.get(c.get("priority", ""), "P2-中"),
        }

    return OrganizeResponse(
        organized=[{
            "module": "全部用例",
            "sub_modules": [{
                "name": "未分类",
                "cases": [build_fallback_case(c) for c in cases],
            }],
        }],
        raw_count=len(cases),
    )
