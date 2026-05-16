"""Agent tools for API test database CRUD operations.

Per D-05/D-06: Agent tools write directly to database via SQLAlchemy session,
bypassing FastAPI and using the shared async_session_factory.

These tools allow the API Agent to manage test definitions, scripts,
and execution records without going through the REST API layer.
"""

import json
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select

from src.app.db.database import async_session_factory
from src.app.db.models.api_test import APITest, APITestRun
from src.app.db.schemas.api_test import APITestCreate, APITestUpdate
from src.app.db.services.api_test_service import APITestService
from src.app.db.utils.identifier import generate_identifier_simple


@tool
async def save_api_test(
    project_id: str,
    name: str,
    description: str = "",
    schema_url: str = "",
    script_format: str = "playwright",
    test_config: str = "{}",
) -> str:
    """Create a new API test in the database.

    Args:
        project_id: UUID of the project to create the test under.
        name: Test name (required).
        description: Test description.
        schema_url: URL of the OpenAPI/Swagger specification.
        script_format: Script format (default "playwright").
        test_config: JSON string of test configuration.

    Returns:
        JSON string with success, test_id, identifier, and name.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            config = json.loads(test_config) if isinstance(test_config, str) else test_config
            data = APITestCreate(
                project_id=UUID(project_id),
                name=name,
                description=description or None,
                schema_url=schema_url or None,
                script_format=script_format,
                test_config=config,
            )
            result = await service.create_api_test(UUID(project_id), data)
            await session.commit()
            return json.dumps({
                "success": True,
                "test_id": str(result.id),
                "identifier": result.identifier,
                "name": result.name,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def list_api_tests_db(
    project_id: str,
    search: str = "",
    page: int = 1,
) -> str:
    """List API tests for a project from the database.

    Args:
        project_id: UUID of the project.
        search: Optional search filter for test name.
        page: Page number (default 1).

    Returns:
        JSON string with success, tests list, total count.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            tests, total = await service.list_api_tests(
                project_id=UUID(project_id),
                search=search or None,
                page=page,
            )
            return json.dumps({
                "success": True,
                "tests": [t.model_dump() for t in tests],
                "total": total,
                "page": page,
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_api_test_detail(test_id: str) -> str:
    """Get detailed information about an API test including run history.

    Args:
        test_id: UUID of the API test.

    Returns:
        JSON string with test details and run history.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            test = await service.get_api_test(UUID(test_id))
            runs, _ = await service.list_test_runs(UUID(test_id))
            return json.dumps({
                "success": True,
                "test": test.model_dump(),
                "recent_runs": [r.model_dump() for r in runs[:10]],
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def update_api_test_db(
    test_id: str,
    name: str = "",
    description: str = "",
    test_config: str = "{}",
) -> str:
    """Update an existing API test in the database.

    Args:
        test_id: UUID of the API test to update.
        name: New name (empty string = no change).
        description: New description (empty string = no change).
        test_config: JSON string of updated test config.

    Returns:
        JSON string with success and updated test details.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            config = json.loads(test_config) if isinstance(test_config, str) else test_config
            update_data = APITestUpdate(test_config=config)
            if name:
                update_data.name = name
            if description:
                update_data.description = description
            result = await service.update_api_test(UUID(test_id), update_data)
            await session.commit()
            return json.dumps({
                "success": True,
                "test_id": str(result.id),
                "name": result.name,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def delete_api_test_db(test_id: str) -> str:
    """Delete an API test from the database.

    Args:
        test_id: UUID of the API test to delete.

    Returns:
        JSON string with success status.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            msg = await service.delete_api_test(UUID(test_id))
            await session.commit()
            return json.dumps({"success": True, "message": msg}, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def save_api_script(
    test_id: str,
    content: str,
    script_format: str = "playwright",
) -> str:
    """Save a test script file for an API test.

    Writes script content to the filesystem and updates the DB record.
    Must be called with the project_id inferred from the test record.

    Args:
        test_id: UUID of the API test to associate the script with.
        content: Script content (TypeScript/Python).
        script_format: Script format (default "playwright").

    Returns:
        JSON string with success and script_path.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            # First get the test to find its project_id
            test = await service.get_api_test(UUID(test_id))
            script_path = await service.save_script(
                project_id=UUID(test.project_id),
                test_id=UUID(test_id),
                content=content,
                script_format=script_format,
            )
            await session.commit()
            return json.dumps({
                "success": True,
                "script_path": script_path,
                "test_id": test_id,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_api_script_info(test_id: str) -> str:
    """Get script metadata for an API test.

    Args:
        test_id: UUID of the API test.

    Returns:
        JSON string with script metadata (path, format, language).
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            test = await service.get_api_test(UUID(test_id))
            return json.dumps({
                "success": True,
                "test_id": test_id,
                "script_path": test.script_path,
                "script_format": test.script_format,
                "script_language": test.script_language,
                "has_script": test.script_path is not None,
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def download_api_script(test_id: str) -> str:
    """Read and return the script content for an API test.

    Args:
        test_id: UUID of the API test.

    Returns:
        JSON string with success and script content.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            content = await service.get_script(UUID(test_id))
            return json.dumps({
                "success": True,
                "test_id": test_id,
                "content": content,
                "content_length": len(content),
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def delete_api_script(test_id: str) -> str:
    """Delete the script file associated with an API test.

    Args:
        test_id: UUID of the API test.

    Returns:
        JSON string with success status.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            test = await service.get_api_test(UUID(test_id))
            if not test.script_path:
                return json.dumps({
                    "success": False,
                    "error": "No script associated with this test",
                }, indent=2)

            import os
            if os.path.exists(test.script_path):
                os.remove(test.script_path)

            # Clear script_path in DB
            update = APITestUpdate(script_path=None)
            await service.update_api_test(UUID(test_id), update)
            await session.commit()
            return json.dumps({
                "success": True,
                "message": "Script deleted",
            }, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


# Export list for registration in __init__.py
DB_TOOLS = [
    save_api_test,
    list_api_tests_db,
    get_api_test_detail,
    update_api_test_db,
    delete_api_test_db,
    save_api_script,
    get_api_script_info,
    download_api_script,
    delete_api_script,
]
