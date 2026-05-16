"""OpenAPI spec parser service with auto-folder creation.

Parses OpenAPI/Swagger specifications and creates tag-based folder
hierarchies with APIEndpoint records in the database.

Reuses parse_api_spec from src.app.agents.api.tools.api_parser for
spec fetching and $ref resolution. This service adds the database
persistence layer on top.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.agents.api.tools.api_parser import parse_api_spec
from src.app.db.database import async_session_factory
from src.app.db.models.api_endpoint import APIEndpoint
from src.app.db.models.folder import Folder
from src.app.db.schemas.enums import FolderType

logger = logging.getLogger(__name__)

# HTTP method sort order for consistent endpoint ordering
_METHOD_ORDER: dict[str, int] = {
    "GET": 0,
    "POST": 1,
    "PUT": 2,
    "PATCH": 3,
    "DELETE": 4,
    "OPTIONS": 5,
    "HEAD": 6,
}


class OpenAPIParser:
    """Parses OpenAPI specs and auto-creates folder structures.

    For each tag in the spec:
    1. Creates a FolderType.API_TEST folder under the project root
    2. For each endpoint in the tag, creates an APIEndpoint record
    3. Returns summary of created resources
    """

    async def parse_and_create_structure(
        self,
        project_id: UUID,
        spec_url: str,
        parent_folder_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: fetch spec -> parse -> create folders + endpoints.

        Args:
            project_id: Project to create folders/endpoints in.
            spec_url: URL or file path to OpenAPI specification.
            parent_folder_id: Optional parent folder for the tag folders.

        Returns:
            Dictionary with title, version, base_url, tags_created,
            endpoints_created, and folder details.
        """
        # 1. Fetch and parse the spec using existing parser
        parsed = await parse_api_spec(spec_url)

        # 2. Group operations by tag
        tag_groups: dict[str, list[dict[str, Any]]] = {}
        for op in parsed.get("operations", []):
            tags = op.get("tags", ["Untagged"])
            primary_tag = tags[0] if tags else "Untagged"
            tag_groups.setdefault(primary_tag, []).append(op)

        # 3. Create folders and endpoints in a single transaction
        async with async_session_factory() as session:
            folders_created: list[dict[str, str]] = []
            endpoints_created = 0

            for tag, operations in sorted(tag_groups.items()):
                # Create tag-level folder
                folder = Folder(
                    project_id=project_id,
                    parent_id=parent_folder_id,
                    name=tag,
                    description=f"API endpoints for {tag}",
                    folder_type=FolderType.API_TEST,
                )
                session.add(folder)
                await session.flush()

                folders_created.append({
                    "id": str(folder.id),
                    "name": tag,
                    "tag": tag,
                })

                # Create APIEndpoint for each operation
                for op in operations:
                    display_name = f"{op.get('method', 'GET')} {op.get('path', '/')}"
                    endpoint = APIEndpoint(
                        project_id=project_id,
                        folder_id=folder.id,
                        display_name=display_name,
                        path=op.get("path", "/"),
                        method=op.get("method", "GET"),
                        summary=op.get("summary"),
                        description=op.get("description"),
                        parameters=op.get("parameters", []),
                        request_body=op.get("requestBody"),
                        responses=op.get("responses", {}),
                        tags=op.get("tags", []),
                        tag_group=tag,
                        sort_order=_METHOD_ORDER.get(
                            op.get("method", "GET").upper(), 99
                        ),
                    )
                    session.add(endpoint)
                    endpoints_created += 1

            await session.commit()

        result = {
            "title": parsed.get("title", ""),
            "version": parsed.get("version", ""),
            "base_url": parsed.get("base_url", ""),
            "tags_created": len(folders_created),
            "endpoints_created": endpoints_created,
            "folders": folders_created,
        }

        logger.info(
            "OpenAPI spec parsed: %s v%s — %d tags, %d endpoints",
            result["title"],
            result["version"],
            result["tags_created"],
            result["endpoints_created"],
        )

        return result
