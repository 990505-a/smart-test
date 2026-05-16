"""Scenario service.

Business logic layer for test scenario CRUD with step management,
data mapping, and execution history.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.test_scenario import (
    ScenarioRun,
    ScenarioStep,
    ScenarioStepResult,
    ScenarioVariable,
    StepDataMapping,
    TestScenario,
)
from src.app.db.utils.exceptions import NotFoundException
from src.app.db.utils.identifier import generate_identifier_simple


class ScenarioService:
    """Service for test scenario business logic with step, variable,
    data mapping, and execution run management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Scenario CRUD ---

    async def create_scenario(
        self,
        project_id: UUID,
        data: dict,
    ) -> TestScenario:
        """Create a new test scenario."""
        identifier = generate_identifier_simple("SC")
        scenario = TestScenario(
            project_id=project_id,
            folder_id=data.get("folder_id"),
            identifier=identifier,
            name=data["name"],
            description=data.get("description"),
            global_variables=data.get("global_variables", {}),
            setup_config=data.get("setup_config", {}),
            teardown_config=data.get("teardown_config", {}),
            retry_count=data.get("retry_count", 0),
            timeout_seconds=data.get("timeout_seconds", 300),
            parallel_execution=data.get("parallel_execution", False),
            status=data.get("status", "draft"),
        )
        self.db.add(scenario)
        await self.db.flush()
        await self.db.refresh(scenario)
        return scenario

    async def get_scenario(self, scenario_id: UUID) -> TestScenario:
        """Get a scenario with eagerly loaded steps and variables."""
        result = await self.db.execute(
            select(TestScenario)
            .options(
                selectinload(TestScenario.steps).selectinload(
                    ScenarioStep.data_mappings
                ),
                selectinload(TestScenario.variables),
            )
            .where(TestScenario.id == scenario_id)
        )
        scenario = result.scalar_one_or_none()
        if not scenario:
            raise NotFoundException("Scenario", str(scenario_id))
        return scenario

    async def list_scenarios(
        self,
        project_id: UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[TestScenario], int]:
        """List scenarios with filtering and pagination."""
        offset = (page - 1) * page_size

        query = select(TestScenario).where(
            TestScenario.project_id == project_id
        )
        count_query = select(func.count()).select_from(TestScenario).where(
            TestScenario.project_id == project_id
        )

        if status:
            query = query.where(TestScenario.status == status)
            count_query = count_query.where(TestScenario.status == status)

        # Get total count
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        # Get paginated results with relationships
        query = (
            query.options(selectinload(TestScenario.steps))
            .order_by(TestScenario.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        scenarios = list(result.scalars().all())

        return (scenarios, total)

    async def update_scenario(
        self,
        scenario_id: UUID,
        data: dict,
    ) -> TestScenario:
        """Update a scenario's fields."""
        scenario = await self.get_scenario(scenario_id)

        for key, value in data.items():
            if hasattr(scenario, key) and value is not None:
                setattr(scenario, key, value)

        await self.db.flush()
        await self.db.refresh(scenario)
        return scenario

    async def delete_scenario(self, scenario_id: UUID) -> str:
        """Delete a scenario and all related data (cascade)."""
        scenario = await self.get_scenario(scenario_id)
        identifier = scenario.identifier
        await self.db.delete(scenario)
        await self.db.flush()
        return f"Scenario {identifier} deleted successfully"

    # --- Step Management ---

    async def add_step(
        self,
        scenario_id: UUID,
        step_data: dict,
    ) -> ScenarioStep:
        """Add a step to a scenario."""
        # Verify scenario exists
        await self.get_scenario(scenario_id)

        # Auto-assign step_order if not provided
        if "step_order" not in step_data:
            result = await self.db.execute(
                select(func.count()).select_from(ScenarioStep).where(
                    ScenarioStep.scenario_id == scenario_id
                )
            )
            step_data["step_order"] = result.scalar_one() + 1

        step = ScenarioStep(
            scenario_id=scenario_id,
            **step_data,
        )
        self.db.add(step)
        await self.db.flush()
        await self.db.refresh(step)

        # Update scenario total_steps count
        await self._update_scenario_step_count(scenario_id)

        return step

    async def update_step(
        self,
        step_id: UUID,
        step_data: dict,
    ) -> ScenarioStep:
        """Update a step's fields."""
        result = await self.db.execute(
            select(ScenarioStep).where(ScenarioStep.id == step_id)
        )
        step = result.scalar_one_or_none()
        if not step:
            raise NotFoundException("Scenario step", str(step_id))

        for key, value in step_data.items():
            if hasattr(step, key):
                setattr(step, key, value)

        await self.db.flush()
        await self.db.refresh(step)
        return step

    async def delete_step(self, step_id: UUID) -> bool:
        """Delete a step and auto-reorder remaining steps."""
        result = await self.db.execute(
            select(ScenarioStep).where(ScenarioStep.id == step_id)
        )
        step = result.scalar_one_or_none()
        if not step:
            raise NotFoundException("Scenario step", str(step_id))

        scenario_id = step.scenario_id
        deleted_order = step.step_order

        await self.db.delete(step)
        await self.db.flush()

        # Auto-reorder remaining steps to fill the gap
        await self.db.execute(
            ScenarioStep.__table__.update()
            .where(ScenarioStep.scenario_id == scenario_id)
            .where(ScenarioStep.step_order > deleted_order)
            .values(step_order=ScenarioStep.step_order - 1)
        )
        await self.db.flush()

        # Update scenario total_steps count
        await self._update_scenario_step_count(scenario_id)

        return True

    async def reorder_steps(
        self,
        scenario_id: UUID,
        step_ids: list[UUID],
    ) -> list[ScenarioStep]:
        """Reorder steps by providing an ordered list of step IDs."""
        # Verify scenario exists
        await self.get_scenario(scenario_id)

        for new_order, step_id in enumerate(step_ids, 1):
            result = await self.db.execute(
                select(ScenarioStep).where(ScenarioStep.id == step_id)
            )
            step = result.scalar_one_or_none()
            if step and step.scenario_id == scenario_id:
                step.step_order = new_order

        await self.db.flush()

        # Reload steps in new order
        result = await self.db.execute(
            select(ScenarioStep)
            .where(ScenarioStep.scenario_id == scenario_id)
            .order_by(ScenarioStep.step_order)
        )
        return list(result.scalars().all())

    # --- Data Mapping Management ---

    async def add_data_mapping(
        self,
        step_id: UUID,
        mapping_data: dict,
    ) -> StepDataMapping:
        """Add a data mapping to a step."""
        # Verify step exists
        result = await self.db.execute(
            select(ScenarioStep).where(ScenarioStep.id == step_id)
        )
        step = result.scalar_one_or_none()
        if not step:
            raise NotFoundException("Scenario step", str(step_id))

        mapping = StepDataMapping(
            step_id=step_id,
            **mapping_data,
        )
        self.db.add(mapping)
        await self.db.flush()
        await self.db.refresh(mapping)
        return mapping

    async def delete_data_mapping(self, mapping_id: UUID) -> bool:
        """Delete a data mapping."""
        result = await self.db.execute(
            select(StepDataMapping).where(StepDataMapping.id == mapping_id)
        )
        mapping = result.scalar_one_or_none()
        if not mapping:
            raise NotFoundException("Data mapping", str(mapping_id))

        await self.db.delete(mapping)
        await self.db.flush()
        return True

    # --- Scenario Run Management ---

    async def create_scenario_run(
        self,
        scenario_id: UUID,
        execution_config: Optional[dict] = None,
    ) -> ScenarioRun:
        """Create a new scenario execution run."""
        scenario = await self.get_scenario(scenario_id)

        identifier = generate_identifier_simple("SCR")
        run = ScenarioRun(
            scenario_id=scenario_id,
            project_id=scenario.project_id,
            identifier=identifier,
            status="pending",
            execution_config=execution_config or {},
            total_steps=scenario.total_steps,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def list_scenario_runs(
        self,
        scenario_id: UUID,
        limit: int = 30,
    ) -> list[ScenarioRun]:
        """List runs for a scenario."""
        result = await self.db.execute(
            select(ScenarioRun)
            .where(ScenarioRun.scenario_id == scenario_id)
            .order_by(ScenarioRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_scenario_run(self, run_id: UUID) -> ScenarioRun:
        """Get a scenario run with step results."""
        result = await self.db.execute(
            select(ScenarioRun)
            .options(selectinload(ScenarioRun.step_results))
            .where(ScenarioRun.id == run_id)
        )
        run = result.scalar_one_or_none()
        if not run:
            raise NotFoundException("Scenario run", str(run_id))
        return run

    async def save_step_results(
        self,
        run_id: UUID,
        results: list[dict],
    ) -> list[ScenarioStepResult]:
        """Save batch of step results for a scenario run."""
        # Verify run exists
        run = await self.get_scenario_run(run_id)

        instances = []
        for data in results:
            data["run_id"] = run_id
            instance = ScenarioStepResult(**data)
            self.db.add(instance)
            instances.append(instance)

        await self.db.flush()
        for instance in instances:
            await self.db.refresh(instance)

        return instances

    # --- Helpers ---

    async def _update_scenario_step_count(self, scenario_id: UUID) -> None:
        """Update total_steps count on a scenario."""
        result = await self.db.execute(
            select(func.count()).select_from(ScenarioStep).where(
                ScenarioStep.scenario_id == scenario_id
            )
        )
        count = result.scalar_one()

        scenario_result = await self.db.execute(
            select(TestScenario).where(TestScenario.id == scenario_id)
        )
        scenario = scenario_result.scalar_one_or_none()
        if scenario:
            scenario.total_steps = count
            await self.db.flush()
