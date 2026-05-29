"""Agent tools for direct database writes.

Per D-05: Agent tools write directly to database via SQLAlchemy session.
Per D-06: Agent tools bypass FastAPI and use shared session factory.
These tools allow the TestCase Agent to persist generated test cases
directly to PostgreSQL without going through the API layer.

Phase 10 additions:
- ensure_project: Auto-create project for workspace before saving test cases.
"""

from datetime import datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from langchain_core.tools import tool
from sqlalchemy import select

from src.app.db.database import async_session_factory
from src.app.db.models.project import Project
from src.app.db.models.test_case import TestCase, TestStep
from src.app.db.schemas.enums import (
    Priority,
    TestCaseState,
    TestCaseTemplate,
    TestCaseType,
)
from src.app.db.utils.identifier import generate_identifier_simple

DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@tool
def get_beijing_timestamp() -> str:
    """Get the current Beijing time (UTC+8) formatted as YYYY.MM.DD.HH.MM.

    Call this once at the start of Phase 1 to get a reliable timestamp.
    Use the returned value in workspace directory names and ensure_project calls
    to ensure consistency (e.g., "七日_2026.05.29.14.30").

    Returns:
        Beijing time string in YYYY.MM.DD.HH.MM format.
    """
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%Y.%m.%d.%H.%M")


@tool
async def save_test_case_to_db(
    project_id: str,
    name: str,
    steps: list[dict],
    priority: str = "medium",
    folder_id: str | None = None,
    description: str | None = None,
    preconditions: str | None = None,
    test_case_type: str = "functional",
    template: str = "test_case",
    custom_fields: dict | None = None,
) -> dict:
    """Save a generated test case to the database.

    Args:
        project_id: UUID of the project to save under.
        name: Test case title (max 500 chars).
        steps: List of step dicts, each with 'action' (required) and 'expected_result' (optional).
        priority: Priority level - low, medium, high, critical.
        folder_id: UUID of the folder (optional).
        description: Test case description.
        preconditions: Prerequisites for the test.
        test_case_type: Type - functional, regression, smoke_sanity, etc.
        template: Template - test_case or test_case_bdd.
        custom_fields: Additional custom fields as JSON.

    Returns:
        Dict with success, test_case_id, identifier, and steps_count.
    """
    async with async_session_factory() as session:
        try:
            identifier = generate_identifier_simple("TC")
            test_case = TestCase(
                project_id=UUID(project_id),
                folder_id=UUID(folder_id) if folder_id else None,
                identifier=identifier,
                name=name,
                description=description,
                preconditions=preconditions,
                priority=Priority(priority),
                test_case_type=TestCaseType(test_case_type),
                template=TestCaseTemplate(template),
                custom_fields=custom_fields,
                created_by=DEFAULT_USER_ID,
            )
            session.add(test_case)
            await session.flush()

            for i, step in enumerate(steps, 1):
                test_step = TestStep(
                    test_case_id=test_case.id,
                    step_number=i,
                    action=step["action"],
                    expected_result=step.get("expected_result"),
                )
                session.add(test_step)

            await session.commit()
            return {
                "success": True,
                "test_case_id": str(test_case.id),
                "identifier": identifier,
                "steps_count": len(steps),
            }
        except Exception as e:
            await session.rollback()
            return {"success": False, "error": str(e)}


@tool
async def save_test_cases_batch(
    project_id: str,
    test_cases: list[dict],
    folder_id: str | None = None,
) -> dict:
    """Save multiple test cases to the database in a single transaction.

    Args:
        project_id: UUID of the project.
        test_cases: List of test case dicts, each with 'name', 'steps' (list of dicts
            with 'action' and optional 'expected_result'), and optional 'priority',
            'description', 'preconditions', 'test_case_type', 'custom_fields'.
        folder_id: Optional folder UUID to assign all cases to.

    Returns:
        Dict with success, total_count, saved_ids (list of identifiers), and errors (if any).
    """
    async with async_session_factory() as session:
        try:
            saved_ids = []
            errors = []

            # Batch insert: create all objects in-memory first, flush once at end.
            # UUIDMixin generates UUIDs in Python, so no flush needed for IDs.
            all_test_cases = []
            all_steps = []

            for case_data in test_cases:
                try:
                    identifier = generate_identifier_simple("TC")
                    test_case = TestCase(
                        project_id=UUID(project_id),
                        folder_id=UUID(folder_id) if folder_id else None,
                        identifier=identifier,
                        name=case_data["name"],
                        description=case_data.get("description"),
                        preconditions=case_data.get("preconditions"),
                        priority=Priority(case_data.get("priority", "medium")),
                        test_case_type=TestCaseType(
                            case_data.get("test_case_type", "functional")
                        ),
                        template=TestCaseTemplate(case_data.get("template", "test_case")),
                        custom_fields=case_data.get("custom_fields"),
                        created_by=DEFAULT_USER_ID,
                    )
                    all_test_cases.append(test_case)
                    session.add(test_case)

                    for i, step in enumerate(case_data.get("steps", []), 1):
                        test_step = TestStep(
                            test_case_id=test_case.id,
                            step_number=i,
                            action=step["action"],
                            expected_result=step.get("expected_result"),
                        )
                        all_steps.append(test_step)
                        session.add(test_step)
                    saved_ids.append(identifier)
                except Exception as e:
                    errors.append({"name": case_data.get("name", "unknown"), "error": str(e)})

            # Single flush + commit for all cases
            await session.flush()
            await session.commit()
            return {
                "success": True,
                "total_count": len(test_cases),
                "saved_ids": saved_ids,
                "saved_count": len(saved_ids),
                "errors": errors if errors else None,
            }
        except Exception as e:
            await session.rollback()
            return {"success": False, "error": str(e)}


@tool
async def list_project_test_cases(
    project_id: str,
    limit: int = 50,
) -> dict:
    """List test cases in a project from the database.

    Args:
        project_id: UUID of the project.
        limit: Maximum number of test cases to return (default 50).

    Returns:
        Dict with success and test_cases list (id, identifier, name, priority, state, steps_count).
    """
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(TestCase)
                .where(TestCase.project_id == UUID(project_id))
                .order_by(TestCase.created_at.desc())
                .limit(limit)
            )
            cases = result.scalars().all()
            return {
                "success": True,
                "test_cases": [
                    {
                        "id": str(c.id),
                        "identifier": c.identifier,
                        "name": c.name,
                        "priority": c.priority.value,
                        "state": c.state.value,
                    }
                    for c in cases
                ],
                "count": len(cases),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


@tool
async def ensure_project(project_name: str = "AI Generated Project") -> dict:
    """Ensure a project exists for the current workspace. If no project exists, create one automatically.

    Call this before save_test_cases_batch if you don't have a project_id.
    The project_name should already include any desired timestamp/suffix for uniqueness.

    Args:
        project_name: Full project name (should include timestamp for uniqueness).

    Returns:
        Dict with success, project_id, identifier, project_name, and is_new (True if just created).
    """
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(Project).where(Project.name == project_name).limit(1)
            )
            project = result.scalar_one_or_none()

            if project:
                return {
                    "success": True,
                    "project_id": str(project.id),
                    "project_name": project.name,
                    "identifier": project.identifier,
                    "is_new": False,
                }

            identifier = generate_identifier_simple("PR")
            project = Project(
                identifier=identifier,
                name=project_name,
                created_by=DEFAULT_USER_ID,
            )
            session.add(project)
            await session.commit()

            return {
                "success": True,
                "project_id": str(project.id),
                "project_name": project.name,
                "identifier": identifier,
                "is_new": True,
            }
        except Exception as e:
            await session.rollback()
            return {"success": False, "error": str(e)}
