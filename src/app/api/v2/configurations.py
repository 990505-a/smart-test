"""Configuration management routes.

Provides 6 endpoints for configuration CRUD and system configuration retrieval.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from fastapi import APIRouter, HTTPException, status

from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import MessageResponse, SuccessResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo


router = APIRouter(prefix="/configurations")


# ---------------------------------------------------------------------------
# Service dependency (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

async def _get_configuration_service(db: DbSessionDep):
    from src.app.db.services.configuration_service import ConfigurationService
    return ConfigurationService(db)


# ---------------------------------------------------------------------------
# Configuration CRUD endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create configuration",
    description="Create a new OS/browser/device configuration",
)
async def create_configuration(
    data: dict,
    db: DbSessionDep,
):
    """Create a new configuration."""
    svc = await _get_configuration_service(db)
    result = await svc.create(data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List configurations",
    description="List all configurations with pagination",
)
async def list_configurations(
    db: DbSessionDep,
    pagination: PaginationDep,
):
    """List configurations with pagination."""
    svc = await _get_configuration_service(db)
    items, total = await svc.get_list(
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/configurations",
        ),
    )


@router.get(
    "/system",
    response_model=SuccessResponse,
    summary="Get system configurations",
    description="Get all system-provided configurations",
)
async def get_system_configurations(
    db: DbSessionDep,
):
    """Get system configurations."""
    svc = await _get_configuration_service(db)
    configs = await svc.get_system_configurations()
    return SuccessResponse(success=True, data=configs)


@router.get(
    "/{id}",
    response_model=SuccessResponse,
    summary="Get configuration",
    description="Get a single configuration by ID",
)
async def get_configuration(
    id: int,
    db: DbSessionDep,
):
    """Get a configuration by ID."""
    svc = await _get_configuration_service(db)
    result = await svc.get(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    return SuccessResponse(success=True, data=result)


@router.patch(
    "/{id}",
    response_model=SuccessResponse,
    summary="Update configuration",
    description="Update a configuration",
)
async def update_configuration(
    id: int,
    data: dict,
    db: DbSessionDep,
):
    """Update a configuration."""
    svc = await _get_configuration_service(db)
    result = await svc.update(id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Configuration not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    summary="Delete configuration",
    description="Delete a configuration",
)
async def delete_configuration(
    id: int,
    db: DbSessionDep,
):
    """Delete a configuration."""
    svc = await _get_configuration_service(db)
    deleted = await svc.delete(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Configuration not found")
    await db.commit()
    return MessageResponse(success=True, message="Configuration deleted")
