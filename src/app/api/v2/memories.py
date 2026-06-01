"""Memory CRUD API endpoints.

Provides REST endpoints for managing agent persistent memories:
list, get, create, update, and delete.
"""

from uuid import UUID

from fastapi import APIRouter, Query

from src.app.api.deps import MemoryServiceDep
from src.app.db.schemas.memory import MemoryCreate, MemoryInfo, MemoryUpdate
from src.app.db.schemas.pagination import PaginatedResponse

router = APIRouter(prefix="/memories")


@router.get("", response_model=PaginatedResponse[MemoryInfo])
async def list_memories(
    service: MemoryServiceDep,
    p: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(30, ge=1, le=300, description="Items per page"),
    space_id: str = Query("default", description="Workspace scope"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search in key and content"),
) -> PaginatedResponse[MemoryInfo]:
    """List memories with pagination, category filter, and text search."""
    items, pagination = await service.list_memories(
        space_id=space_id,
        page=p,
        page_size=page_size,
        category=category,
        search=search,
    )
    return PaginatedResponse(info=pagination, data=items)


@router.get("/{memory_id}", response_model=dict)
async def get_memory(
    memory_id: UUID,
    service: MemoryServiceDep,
) -> dict:
    """Get a single memory by ID."""
    memory = await service.get_memory(memory_id)
    return {"success": True, "data": memory}


@router.post("", response_model=dict)
async def create_memory(
    data: MemoryCreate,
    service: MemoryServiceDep,
    space_id: str = Query("default", description="Workspace scope"),
) -> dict:
    """Create a new memory."""
    memory = await service.create_memory(data, space_id=space_id)
    return {"success": True, "data": memory}


@router.patch("/{memory_id}", response_model=dict)
async def update_memory(
    memory_id: UUID,
    data: MemoryUpdate,
    service: MemoryServiceDep,
) -> dict:
    """Update an existing memory."""
    memory = await service.update_memory(memory_id, data)
    return {"success": True, "data": memory}


@router.delete("/{memory_id}", response_model=dict)
async def delete_memory(
    memory_id: UUID,
    service: MemoryServiceDep,
) -> dict:
    """Delete a memory."""
    message = await service.delete_memory(memory_id)
    return {"success": True, "message": message}
