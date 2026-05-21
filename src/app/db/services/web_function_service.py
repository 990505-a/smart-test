"""Web function service.

Business logic layer for web function and sub-function CRUD operations.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.web_function import WebFunction, WebSubFunction
from src.app.db.repositories.web_function_repo import (
    WebFunctionRepository,
    WebSubFunctionRepository,
)
from src.app.db.schemas.web_function import (
    WebFunctionInfo,
    WebSubFunctionInfo,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class WebFunctionService:
    """Service for web function and sub-function business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WebFunctionRepository(db)
        self.sub_repo = WebSubFunctionRepository(db)

    # --- Web Function CRUD ---

    async def create_web_function(
        self,
        project_id: UUID,
        data: dict,
    ) -> WebFunctionInfo:
        """Create a new web function."""
        identifier = generate_identifier_simple("WF")
        web_function = WebFunction(
            project_id=project_id,
            folder_id=data.get("folder_id"),
            identifier=identifier,
            display_name=data.get("display_name", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            base_url=data.get("base_url"),
            business_module=data.get("business_module"),
            navigation=data.get("navigation"),
            pages=data.get("pages", []),
            tags=data.get("tags", []),
            custom_config=data.get("custom_config"),
        )
        self.db.add(web_function)
        await self.db.flush()
        await self.db.refresh(web_function)
        return WebFunctionInfo.model_validate(web_function)

    async def get_web_function(self, function_id: UUID) -> WebFunctionInfo:
        """Get a web function by ID with sub-functions loaded."""
        result = await self.db.execute(
            select(WebFunction)
            .options(selectinload(WebFunction.sub_functions))
            .where(WebFunction.id == function_id)
        )
        web_function = result.scalar_one_or_none()
        if not web_function:
            raise NotFoundException("Web function", str(function_id))
        return WebFunctionInfo.model_validate(web_function)

    async def update_web_function(
        self,
        function_id: UUID,
        data: dict,
    ) -> WebFunctionInfo:
        """Update a web function."""
        web_function = await self.repo.get_by_id(function_id)
        if not web_function:
            raise NotFoundException("Web function", str(function_id))

        for key, value in data.items():
            if hasattr(web_function, key) and value is not None:
                setattr(web_function, key, value)

        await self.db.flush()
        await self.db.refresh(web_function)
        return WebFunctionInfo.model_validate(web_function)

    async def delete_web_function(self, function_id: UUID) -> str:
        """Delete a web function."""
        web_function = await self.repo.get_by_id(function_id)
        if not web_function:
            raise NotFoundException("Web function", str(function_id))
        identifier = web_function.identifier
        await self.repo.delete(web_function)
        return f"Web function {identifier} deleted successfully"

    async def list_web_functions(
        self,
        project_id: UUID,
        folder_id: Optional[UUID] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[WebFunctionInfo], int]:
        """List web functions with filtering and pagination."""
        offset = (page - 1) * page_size

        functions = await self.repo.list_by_project(
            project_id, folder_id=folder_id, search=search,
            offset=offset, limit=page_size,
        )
        total = await self.repo.count_by_project(
            project_id, folder_id=folder_id, search=search,
        )
        return ([WebFunctionInfo.model_validate(f) for f in functions], total)

    # --- Sub-Function CRUD ---

    async def create_sub_function(
        self,
        function_id: UUID,
        data: dict,
    ) -> WebSubFunctionInfo:
        """Create a new sub-function within a web function."""
        # Verify parent function exists
        web_function = await self.repo.get_by_id(function_id)
        if not web_function:
            raise NotFoundException("Web function", str(function_id))

        identifier = generate_identifier_simple("WSF")
        sub_function = WebSubFunction(
            project_id=web_function.project_id,
            function_id=function_id,
            folder_id=data.get("folder_id"),
            identifier=identifier,
            display_name=data.get("display_name", ""),
            name=data.get("name", ""),
            description=data.get("description"),
            test_type=data.get("test_type", "functional"),
            target_pages=data.get("target_pages", []),
            test_scenario=data.get("test_scenario"),
            test_data=data.get("test_data"),
            expected_results=data.get("expected_results", []),
            priority=data.get("priority", "medium"),
            tags=data.get("tags", []),
            custom_config=data.get("custom_config"),
        )
        self.db.add(sub_function)

        # Update parent function's sub-function count
        web_function.total_sub_functions = (web_function.total_sub_functions or 0) + 1

        await self.db.flush()
        await self.db.refresh(sub_function)
        return WebSubFunctionInfo.model_validate(sub_function)

    async def get_sub_function(self, sub_id: UUID) -> WebSubFunctionInfo:
        """Get a sub-function by ID."""
        sub_function = await self.sub_repo.get_by_id(sub_id)
        if not sub_function:
            raise NotFoundException("Web sub-function", str(sub_id))
        return WebSubFunctionInfo.model_validate(sub_function)

    async def update_sub_function(
        self,
        sub_id: UUID,
        data: dict,
    ) -> WebSubFunctionInfo:
        """Update a sub-function."""
        sub_function = await self.sub_repo.get_by_id(sub_id)
        if not sub_function:
            raise NotFoundException("Web sub-function", str(sub_id))

        for key, value in data.items():
            if hasattr(sub_function, key) and value is not None:
                setattr(sub_function, key, value)

        await self.db.flush()
        await self.db.refresh(sub_function)
        return WebSubFunctionInfo.model_validate(sub_function)

    async def delete_sub_function(self, sub_id: UUID) -> str:
        """Delete a sub-function."""
        sub_function = await self.sub_repo.get_by_id(sub_id)
        if not sub_function:
            raise NotFoundException("Web sub-function", str(sub_id))

        # Update parent function's sub-function count
        parent = await self.repo.get_by_id(sub_function.function_id)
        if parent and parent.total_sub_functions:
            parent.total_sub_functions -= 1

        identifier = sub_function.identifier
        await self.sub_repo.delete(sub_function)
        return f"Web sub-function {identifier} deleted successfully"

    async def list_sub_functions(
        self,
        function_id: UUID,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[WebSubFunctionInfo], int]:
        """List sub-functions for a web function with pagination."""
        offset = (page - 1) * page_size

        sub_functions = await self.sub_repo.list_by_function(
            function_id, offset=offset, limit=page_size,
        )
        total = await self.sub_repo.count_by_function(function_id)
        return ([WebSubFunctionInfo.model_validate(sf) for sf in sub_functions], total)
