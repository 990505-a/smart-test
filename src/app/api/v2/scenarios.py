"""Scenario management routes.

Provides 18 endpoints for test scenario CRUD, step management,
data mapping, and execution tracking.
Per D-04: no auth, uses DEFAULT_USER_ID.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from src.app.api.deps import DbSessionDep, PaginationDep
from src.app.db.schemas.common import MessageResponse, SuccessResponse
from src.app.db.schemas.pagination import PaginatedResponse, PaginationInfo


router = APIRouter(prefix="/scenarios")


# ---------------------------------------------------------------------------
# Service dependency (lazy import to avoid circular deps with Plan 01)
# ---------------------------------------------------------------------------

async def _get_scenario_service(db: DbSessionDep):
    from src.app.db.services.scenario_service import ScenarioService
    return ScenarioService(db)


# ---------------------------------------------------------------------------
# Scenario CRUD
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedResponse,
    summary="List scenarios",
    description="List test scenarios with optional filtering",
)
async def list_scenarios(
    db: DbSessionDep,
    pagination: PaginationDep,
    project_id: Optional[UUID] = Query(default=None, description="Filter by project"),
    status_filter: Optional[str] = Query(
        default=None, alias="status", description="Filter by status"
    ),
):
    """List scenarios with pagination and filtering."""
    svc = await _get_scenario_service(db)
    items, total = await svc.list_scenarios(
        project_id=project_id,
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        success=True,
        data=items,
        info=PaginationInfo.create(
            page=pagination.page,
            page_size=pagination.page_size,
            total=total,
            base_url="/api/v2/scenarios",
        ),
    )


@router.post(
    "",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create scenario",
    description="Create a new test scenario",
)
async def create_scenario(
    data: dict,
    db: DbSessionDep,
):
    """Create a new scenario."""
    svc = await _get_scenario_service(db)
    project_id = data.get("project_id")
    result = await svc.create_scenario(project_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.get(
    "/{id}",
    response_model=SuccessResponse,
    summary="Get scenario",
    description="Get a scenario with its steps and variables",
)
async def get_scenario(
    id: UUID,
    db: DbSessionDep,
):
    """Get a scenario with steps and variables."""
    svc = await _get_scenario_service(db)
    result = await svc.get_scenario(id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return SuccessResponse(success=True, data=result)


@router.put(
    "/{id}",
    response_model=SuccessResponse,
    summary="Update scenario",
    description="Full update of a scenario",
)
async def update_scenario(
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update a scenario."""
    svc = await _get_scenario_service(db)
    result = await svc.update_scenario(id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}",
    response_model=MessageResponse,
    summary="Delete scenario",
    description="Delete a scenario and all associated data (cascade)",
)
async def delete_scenario(
    id: UUID,
    db: DbSessionDep,
):
    """Delete a scenario with cascade."""
    svc = await _get_scenario_service(db)
    deleted = await svc.delete_scenario(id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scenario not found")
    await db.commit()
    return MessageResponse(success=True, message="Scenario deleted")


# ---------------------------------------------------------------------------
# Step management
# ---------------------------------------------------------------------------

@router.get(
    "/steps/{step_id}",
    response_model=SuccessResponse,
    summary="Get step",
    description="Get a single scenario step",
)
async def get_step(
    step_id: UUID,
    db: DbSessionDep,
):
    """Get a step by ID.

    Loads the parent scenario to get its steps, then finds the matching step.
    """
    svc = await _get_scenario_service(db)
    step = await svc.get_step_by_id(step_id)
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    return SuccessResponse(success=True, data=step)


@router.get(
    "/{id}/steps",
    response_model=SuccessResponse,
    summary="List steps",
    description="List steps for a scenario ordered by step_order",
)
async def list_steps(
    id: UUID,
    db: DbSessionDep,
):
    """List steps for a scenario."""
    svc = await _get_scenario_service(db)
    scenario = await svc.get_scenario(id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    steps = getattr(scenario, "steps", []) if hasattr(scenario, "steps") else []
    return SuccessResponse(success=True, data=steps)


@router.post(
    "/{id}/steps",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add step",
    description="Add a step to a scenario",
)
async def add_step(
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Add a step to a scenario."""
    svc = await _get_scenario_service(db)
    result = await svc.add_step(id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.put(
    "/{id}/steps/{step_id}",
    response_model=SuccessResponse,
    summary="Update step",
    description="Update a scenario step",
)
async def update_step(
    id: UUID,
    step_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Update a step."""
    svc = await _get_scenario_service(db)
    result = await svc.update_step(step_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="Step not found")
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}/steps/{step_id}",
    response_model=MessageResponse,
    summary="Delete step",
    description="Delete a step (auto-reorder remaining)",
)
async def delete_step(
    id: UUID,
    step_id: UUID,
    db: DbSessionDep,
):
    """Delete a step and auto-reorder."""
    svc = await _get_scenario_service(db)
    deleted = await svc.delete_step(step_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Step not found")
    await db.commit()
    return MessageResponse(success=True, message="Step deleted")


@router.post(
    "/{id}/steps/reorder",
    response_model=SuccessResponse,
    summary="Reorder steps",
    description="Reorder scenario steps",
)
async def reorder_steps(
    id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Reorder steps by providing an ordered list of step IDs."""
    svc = await _get_scenario_service(db)
    step_ids = data.get("step_ids", [])
    steps = await svc.reorder_steps(id, step_ids)
    await db.commit()
    return SuccessResponse(success=True, data=steps)


# ---------------------------------------------------------------------------
# Data mappings
# ---------------------------------------------------------------------------

@router.post(
    "/{id}/steps/{step_id}/mappings",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add data mapping",
    description="Add a data mapping between steps",
)
async def add_data_mapping(
    id: UUID,
    step_id: UUID,
    data: dict,
    db: DbSessionDep,
):
    """Add a data mapping to a step."""
    svc = await _get_scenario_service(db)
    result = await svc.add_data_mapping(step_id, data)
    await db.commit()
    return SuccessResponse(success=True, data=result)


@router.delete(
    "/{id}/steps/{step_id}/mappings/{mapping_id}",
    response_model=MessageResponse,
    summary="Delete data mapping",
    description="Delete a data mapping",
)
async def delete_data_mapping(
    id: UUID,
    step_id: UUID,
    mapping_id: UUID,
    db: DbSessionDep,
):
    """Delete a data mapping."""
    svc = await _get_scenario_service(db)
    deleted = await svc.delete_data_mapping(mapping_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Data mapping not found")
    await db.commit()
    return MessageResponse(success=True, message="Data mapping deleted")


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------

@router.post(
    "/{id}/execute",
    response_model=SuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute scenario",
    description="Trigger scenario execution (placeholder)",
)
async def execute_scenario(
    id: UUID,
    data: Optional[dict] = None,
    db: DbSessionDep = None,
):
    """Execute a scenario.

    Creates a ScenarioRun record with status=pending.
    Actual execution is handled by the ScenarioExecutionEngine in Plan 03.
    """
    svc = await _get_scenario_service(db)
    execution_config = data.get("execution_config", {}) if data else {}
    run = await svc.create_scenario_run(id, execution_config)
    await db.commit()
    return SuccessResponse(success=True, data=run)


@router.get(
    "/{id}/runs",
    response_model=SuccessResponse,
    summary="List scenario runs",
    description="List execution records for a scenario",
)
async def list_scenario_runs(
    id: UUID,
    db: DbSessionDep,
    limit: int = Query(default=20, ge=1, le=100, description="Max runs to return"),
):
    """List execution records for a scenario."""
    svc = await _get_scenario_service(db)
    runs = await svc.list_scenario_runs(id, limit)
    return SuccessResponse(success=True, data=runs)


@router.get(
    "/{id}/runs/{run_id}",
    response_model=SuccessResponse,
    summary="Get scenario run",
    description="Get a scenario run detail with step results",
)
async def get_scenario_run(
    id: UUID,
    run_id: UUID,
    db: DbSessionDep,
):
    """Get a scenario run detail."""
    svc = await _get_scenario_service(db)
    run = await svc.get_scenario_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Scenario run not found")
    return SuccessResponse(success=True, data=run)


@router.get(
    "/{id}/runs/{run_id}/results",
    response_model=SuccessResponse,
    summary="Get step results",
    description="Get step results for a scenario run",
)
async def get_step_results(
    id: UUID,
    run_id: UUID,
    db: DbSessionDep,
):
    """Get step results for a run."""
    svc = await _get_scenario_service(db)
    results = await svc.get_step_results(run_id)
    return SuccessResponse(success=True, data=results)
