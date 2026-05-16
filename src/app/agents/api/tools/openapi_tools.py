"""Agent tools for OpenAPI specification parsing and endpoint management.

Parses OpenAPI specs, creates tag-based folder structure, and manages
API endpoint records in the database.
"""

import json
from uuid import UUID, uuid4

from langchain_core.tools import tool
from sqlalchemy import select

from src.app.db.database import async_session_factory
from src.app.db.models.api_endpoint import APIEndpoint
from src.app.db.models.folder import Folder
from src.app.db.schemas.enums import FolderType
from src.app.agents.api.tools.api_parser import parse_api_spec


@tool
async def parse_openapi_to_db(project_id: str, spec_url: str) -> str:
    """Parse an OpenAPI specification and save endpoints to the database.

    Fetches and parses the spec, creates tag-based FolderType.API_TEST folders,
    and creates APIEndpoint records for each endpoint organized by tag.

    Args:
        project_id: UUID of the project to save endpoints under.
        spec_url: URL or file path to the OpenAPI specification.

    Returns:
        JSON string with summary of created folders and endpoints.
    """
    async with async_session_factory() as session:
        try:
            # Parse the spec
            parsed = await parse_api_spec(spec_url)
            operations = parsed.get("operations", [])

            if not operations:
                return json.dumps({
                    "success": False,
                    "error": "No operations found in specification",
                }, indent=2)

            # Group operations by tag
            tag_operations: dict[str, list] = {}
            for op in operations:
                tags = op.get("tags", ["Default"])
                tag = tags[0] if tags else "Default"
                if tag not in tag_operations:
                    tag_operations[tag] = []
                tag_operations[tag].append(op)

            # Create folders and endpoints
            created_folders = []
            created_endpoints = []

            # Get or create root API_TEST folder for project
            root_folder = Folder(
                id=uuid4(),
                project_id=UUID(project_id),
                name=parsed.get("title", "API Endpoints"),
                folder_type=FolderType.API_TEST,
            )
            session.add(root_folder)
            await session.flush()
            created_folders.append({
                "id": str(root_folder.id),
                "name": root_folder.name,
            })

            for tag, ops in tag_operations.items():
                # Create tag-based subfolder
                tag_folder = Folder(
                    id=uuid4(),
                    project_id=UUID(project_id),
                    parent_id=root_folder.id,
                    name=tag,
                    folder_type=FolderType.API_TEST,
                )
                session.add(tag_folder)
                await session.flush()
                created_folders.append({
                    "id": str(tag_folder.id),
                    "name": tag,
                    "parent": str(root_folder.id),
                })

                for op in ops:
                    method = op.get("method", "GET")
                    path = op.get("path", "/")
                    endpoint = APIEndpoint(
                        id=uuid4(),
                        project_id=UUID(project_id),
                        folder_id=tag_folder.id,
                        display_name=f"{method} {path}",
                        path=path,
                        method=method,
                        summary=op.get("summary", ""),
                        description=op.get("description", ""),
                        parameters=op.get("parameters", []),
                        request_body=op.get("requestBody"),
                        responses=op.get("responses", {}),
                        tags=[tag],
                        tag_group=tag,
                    )
                    session.add(endpoint)
                    created_endpoints.append({
                        "id": str(endpoint.id),
                        "method": method,
                        "path": path,
                        "tag": tag,
                        "folder_id": str(tag_folder.id),
                    })

            await session.flush()
            await session.commit()

            return json.dumps({
                "success": True,
                "api_title": parsed.get("title", "Unknown"),
                "api_version": parsed.get("version", "unknown"),
                "base_url": parsed.get("base_url", ""),
                "total_operations": len(operations),
                "folders_created": len(created_folders),
                "endpoints_created": len(created_endpoints),
                "tags": list(tag_operations.keys()),
                "created_folders": created_folders,
                "created_endpoints": created_endpoints[:50],  # Limit output
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def save_api_endpoint(
    project_id: str,
    folder_id: str,
    path: str,
    method: str,
    summary: str = "",
    parameters: str = "[]",
    responses: str = "{}",
) -> str:
    """Save a single API endpoint to the database.

    Args:
        project_id: UUID of the project.
        folder_id: UUID of the folder to save the endpoint under.
        path: API endpoint path (e.g., /api/v1/users).
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        summary: Short description of the endpoint.
        parameters: JSON string of parameter definitions.
        responses: JSON string of response definitions.

    Returns:
        JSON string with success and endpoint details.
    """
    async with async_session_factory() as session:
        try:
            params = json.loads(parameters) if isinstance(parameters, str) else parameters
            resp = json.loads(responses) if isinstance(responses, str) else responses

            endpoint = APIEndpoint(
                id=uuid4(),
                project_id=UUID(project_id),
                folder_id=UUID(folder_id),
                display_name=f"{method.upper()} {path}",
                path=path,
                method=method.upper(),
                summary=summary,
                parameters=params,
                responses=resp,
            )
            session.add(endpoint)
            await session.flush()
            await session.commit()

            return json.dumps({
                "success": True,
                "endpoint_id": str(endpoint.id),
                "display_name": endpoint.display_name,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_endpoint_artifacts(endpoint_id: str) -> str:
    """Get an API endpoint's details along with associated test artifacts.

    Args:
        endpoint_id: UUID of the API endpoint.

    Returns:
        JSON string with endpoint details and associated test/script IDs.
    """
    async with async_session_factory() as session:
        try:
            result = await session.execute(
                select(APIEndpoint).where(
                    APIEndpoint.id == UUID(endpoint_id)
                )
            )
            endpoint = result.scalar_one_or_none()
            if not endpoint:
                return json.dumps({
                    "success": False,
                    "error": f"Endpoint {endpoint_id} not found",
                }, indent=2)

            return json.dumps({
                "success": True,
                "endpoint": {
                    "id": str(endpoint.id),
                    "display_name": endpoint.display_name,
                    "path": endpoint.path,
                    "method": endpoint.method,
                    "summary": endpoint.summary,
                    "description": endpoint.description,
                    "parameters": endpoint.parameters,
                    "request_body": endpoint.request_body,
                    "responses": endpoint.responses,
                    "tags": endpoint.tags,
                    "tag_group": endpoint.tag_group,
                    "test_case_ids": endpoint.test_case_ids,
                    "api_test_ids": endpoint.api_test_ids,
                    "total_test_cases": endpoint.total_test_cases,
                    "total_test_runs": endpoint.total_test_runs,
                },
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def list_api_endpoints(
    project_id: str,
    tag: str = "",
    folder_id: str = "",
    limit: int = 100,
) -> str:
    """List API endpoints for a project with optional filtering.

    Args:
        project_id: UUID of the project.
        tag: Filter by tag group (empty = all).
        folder_id: Filter by folder UUID (empty = all).
        limit: Maximum number of endpoints to return.

    Returns:
        JSON string with success and endpoints list.
    """
    async with async_session_factory() as session:
        try:
            query = select(APIEndpoint).where(
                APIEndpoint.project_id == UUID(project_id)
            )
            if tag:
                query = query.where(APIEndpoint.tag_group == tag)
            if folder_id:
                query = query.where(APIEndpoint.folder_id == UUID(folder_id))
            query = query.order_by(APIEndpoint.tag_group, APIEndpoint.path).limit(limit)

            result = await session.execute(query)
            endpoints = result.scalars().all()

            return json.dumps({
                "success": True,
                "endpoints": [
                    {
                        "id": str(e.id),
                        "display_name": e.display_name,
                        "method": e.method,
                        "path": e.path,
                        "summary": e.summary,
                        "tag_group": e.tag_group,
                    }
                    for e in endpoints
                ],
                "count": len(endpoints),
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_multiple_endpoints_details(endpoint_ids: str) -> str:
    """Get details for multiple API endpoints by their IDs.

    Args:
        endpoint_ids: Comma-separated UUIDs of endpoints.

    Returns:
        JSON string with success and list of endpoint details.
    """
    async with async_session_factory() as session:
        try:
            ids = [UUID(eid.strip()) for eid in endpoint_ids.split(",") if eid.strip()]
            result = await session.execute(
                select(APIEndpoint).where(APIEndpoint.id.in_(ids))
            )
            endpoints = result.scalars().all()

            return json.dumps({
                "success": True,
                "endpoints": [
                    {
                        "id": str(e.id),
                        "display_name": e.display_name,
                        "path": e.path,
                        "method": e.method,
                        "summary": e.summary,
                        "description": e.description,
                        "parameters": e.parameters,
                        "request_body": e.request_body,
                        "responses": e.responses,
                        "tags": e.tags,
                    }
                    for e in endpoints
                ],
                "count": len(endpoints),
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


# Export list for registration in __init__.py
OPENAPI_TOOLS = [
    parse_openapi_to_db,
    save_api_endpoint,
    get_endpoint_artifacts,
    list_api_endpoints,
    get_multiple_endpoints_details,
]
