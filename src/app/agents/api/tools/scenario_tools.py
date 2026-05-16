"""Agent tools for test scenario CRUD and step management.

Provides tools for creating, updating, and executing test scenarios
that compose multiple API calls into business flow tests with
data mapping, extractors, and assertions.
"""

import json
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select

from src.app.db.database import async_session_factory
from src.app.db.models.test_scenario import ScenarioStep, TestScenario
from src.app.db.services.scenario_service import ScenarioService


@tool
async def create_test_scenario(
    project_id: str,
    name: str,
    description: str = "",
) -> str:
    """Create a new test scenario for multi-API business flow testing.

    Args:
        project_id: UUID of the project.
        name: Scenario name (required).
        description: Scenario description.

    Returns:
        JSON string with success and scenario details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            scenario = await service.create_scenario(
                project_id=UUID(project_id),
                data={"name": name, "description": description or None},
            )
            await session.commit()
            return json.dumps({
                "success": True,
                "scenario_id": str(scenario.id),
                "identifier": scenario.identifier,
                "name": scenario.name,
                "status": scenario.status,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def update_test_scenario(
    scenario_id: str,
    name: str = "",
    description: str = "",
) -> str:
    """Update a test scenario's name or description.

    Args:
        scenario_id: UUID of the scenario to update.
        name: New name (empty = no change).
        description: New description (empty = no change).

    Returns:
        JSON string with success and updated details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            data = {}
            if name:
                data["name"] = name
            if description:
                data["description"] = description
            scenario = await service.update_scenario(UUID(scenario_id), data)
            await session.commit()
            return json.dumps({
                "success": True,
                "scenario_id": str(scenario.id),
                "name": scenario.name,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def add_scenario_step(
    scenario_id: str,
    name: str,
    endpoint_id: str = "",
    step_order: int = 0,
    request_override: str = "{}",
    assertions: str = "[]",
    extractors: str = "[]",
) -> str:
    """Add a step to a test scenario.

    Each step represents a single API call within the business flow.
    Steps are executed in order by step_order.

    Args:
        scenario_id: UUID of the scenario to add the step to.
        name: Step name (e.g., "User Login").
        endpoint_id: UUID of the API endpoint this step calls (optional).
        step_order: Execution order (0 = auto-assign at end).
        request_override: JSON string with request overrides (headers, body, params).
        assertions: JSON array of assertion objects.
        extractors: JSON array of data extractor objects.

    Returns:
        JSON string with success and step details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            req_override = json.loads(request_override) if isinstance(request_override, str) else request_override
            step_assertions = json.loads(assertions) if isinstance(assertions, str) else assertions
            step_extractors = json.loads(extractors) if isinstance(extractors, str) else extractors

            step_data = {
                "name": name,
                "request_override": req_override,
                "assertions": step_assertions,
                "extractors": step_extractors,
            }
            if endpoint_id:
                step_data["endpoint_id"] = UUID(endpoint_id)
            if step_order > 0:
                step_data["step_order"] = step_order

            step = await service.add_step(UUID(scenario_id), step_data)
            await session.commit()
            return json.dumps({
                "success": True,
                "step_id": str(step.id),
                "name": step.name,
                "step_order": step.step_order,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def update_scenario_step(
    step_id: str,
    name: str = "",
    request_override: str = "{}",
) -> str:
    """Update a scenario step's fields.

    Args:
        step_id: UUID of the step to update.
        name: New step name (empty = no change).
        request_override: JSON string with updated request overrides.

    Returns:
        JSON string with success and updated step details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            data = {}
            if name:
                data["name"] = name
            if request_override:
                data["request_override"] = json.loads(request_override)
            step = await service.update_step(UUID(step_id), data)
            await session.commit()
            return json.dumps({
                "success": True,
                "step_id": str(step.id),
                "name": step.name,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def add_data_mapping(
    step_id: str,
    source_type: str,
    source_step_id: str = "",
    source_path: str = "",
    target_path: str = "",
    transform_expression: str = "",
) -> str:
    """Add a data mapping to transfer data between scenario steps.

    Data mappings enable passing data (like tokens, IDs) from one
    step's response to a subsequent step's request.

    Args:
        step_id: UUID of the target step to receive the data.
        source_type: Source type (e.g., "step_response", "variable", "static").
        source_step_id: UUID of the source step (for step_response type).
        source_path: JSONPath to extract from source (e.g., "$.data.token").
        target_path: Where to inject the data (e.g., "headers.Authorization").
        transform_expression: Optional transform (e.g., "'Bearer ' + value").

    Returns:
        JSON string with success and mapping details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            mapping_data = {
                "source_type": source_type,
                "target_path": target_path,
            }
            if source_step_id:
                mapping_data["source_step_id"] = UUID(source_step_id)
            if source_path:
                mapping_data["source_path"] = source_path
            if transform_expression:
                mapping_data["transform_expression"] = transform_expression

            mapping = await service.add_data_mapping(UUID(step_id), mapping_data)
            await session.commit()
            return json.dumps({
                "success": True,
                "mapping_id": str(mapping.id),
                "source_type": source_type,
                "target_path": target_path,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def add_step_extractor(step_id: str, extractor_json: str) -> str:
    """Add a data extractor to a scenario step.

    Extractors pull data from API responses (using JSONPath) for use
    in subsequent steps via data mappings.

    Args:
        step_id: UUID of the step to add the extractor to.
        extractor_json: JSON object with extractor definition.
            Example: {"name": "token", "path": "$.data.token", "type": "jsonpath"}

    Returns:
        JSON string with success and updated extractors list.
    """
    async with async_session_factory() as session:
        try:
            new_extractor = json.loads(extractor_json) if isinstance(extractor_json, str) else extractor_json

            # Get current step to read existing extractors
            result = await session.execute(
                select(ScenarioStep).where(ScenarioStep.id == UUID(step_id))
            )
            step = result.scalar_one_or_none()
            if not step:
                return json.dumps({
                    "success": False,
                    "error": f"Step {step_id} not found",
                }, indent=2)

            # Append to existing extractors
            current_extractors = step.extractors or []
            current_extractors.append(new_extractor)

            # Update via service
            service = ScenarioService(session)
            await service.update_step(UUID(step_id), {"extractors": current_extractors})
            await session.commit()

            return json.dumps({
                "success": True,
                "step_id": step_id,
                "extractors": current_extractors,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def add_step_assertion(step_id: str, assertion_json: str) -> str:
    """Add an assertion to a scenario step.

    Assertions validate API response data against expected values.

    Args:
        step_id: UUID of the step to add the assertion to.
        assertion_json: JSON object with assertion definition.
            Example: {"type": "status_code", "expected": 200}
            Example: {"type": "jsonpath", "path": "$.status", "expected": "success"}

    Returns:
        JSON string with success and updated assertions list.
    """
    async with async_session_factory() as session:
        try:
            new_assertion = json.loads(assertion_json) if isinstance(assertion_json, str) else assertion_json

            # Get current step
            result = await session.execute(
                select(ScenarioStep).where(ScenarioStep.id == UUID(step_id))
            )
            step = result.scalar_one_or_none()
            if not step:
                return json.dumps({
                    "success": False,
                    "error": f"Step {step_id} not found",
                }, indent=2)

            # Append to existing assertions
            current_assertions = step.assertions or []
            current_assertions.append(new_assertion)

            # Update via service
            service = ScenarioService(session)
            await service.update_step(UUID(step_id), {"assertions": current_assertions})
            await session.commit()

            return json.dumps({
                "success": True,
                "step_id": step_id,
                "assertions": current_assertions,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_scenario_details(scenario_id: str) -> str:
    """Get full scenario details including all steps, mappings, and variables.

    Args:
        scenario_id: UUID of the scenario.

    Returns:
        JSON string with complete scenario structure.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            scenario = await service.get_scenario(UUID(scenario_id))

            steps_data = []
            for step in scenario.steps:
                mappings = [
                    {
                        "id": str(m.id),
                        "source_type": m.source_type,
                        "source_path": m.source_path,
                        "target_path": m.target_path,
                        "transform_expression": m.transform_expression,
                    }
                    for m in step.data_mappings
                ]
                steps_data.append({
                    "id": str(step.id),
                    "step_order": step.step_order,
                    "name": step.name,
                    "description": step.description,
                    "endpoint_id": str(step.endpoint_id) if step.endpoint_id else None,
                    "request_override": step.request_override,
                    "extractors": step.extractors,
                    "assertions": step.assertions,
                    "data_mappings": mappings,
                })

            return json.dumps({
                "success": True,
                "scenario": {
                    "id": str(scenario.id),
                    "identifier": scenario.identifier,
                    "name": scenario.name,
                    "description": scenario.description,
                    "status": scenario.status,
                    "total_steps": scenario.total_steps,
                    "global_variables": scenario.global_variables,
                    "setup_config": scenario.setup_config,
                    "teardown_config": scenario.teardown_config,
                },
                "steps": steps_data,
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def list_test_scenarios(
    project_id: str,
    status: str = "",
    page: int = 1,
) -> str:
    """List test scenarios for a project with optional status filtering.

    Args:
        project_id: UUID of the project.
        status: Filter by status (draft, ready, running, passed, failed, etc.).
        page: Page number (default 1).

    Returns:
        JSON string with scenarios list and pagination info.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            scenarios, total = await service.list_scenarios(
                project_id=UUID(project_id),
                status=status or None,
                page=page,
            )
            return json.dumps({
                "success": True,
                "scenarios": [
                    {
                        "id": str(s.id),
                        "identifier": s.identifier,
                        "name": s.name,
                        "status": s.status,
                        "total_steps": s.total_steps,
                        "last_run_status": s.last_run_status,
                    }
                    for s in scenarios
                ],
                "total": total,
                "page": page,
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def execute_scenario(
    scenario_id: str,
    mode: str = "async",
    execution_config: str = "{}",
) -> str:
    """Create a scenario execution run.

    Creates a ScenarioRun record. Actual execution is performed by
    the ScenarioExecutor (Plan 04). This prepares the run context.

    Args:
        scenario_id: UUID of the scenario to execute.
        mode: Execution mode ("async" or "sync", default "async").
        execution_config: JSON string of execution parameters.

    Returns:
        JSON string with success and run details.
    """
    async with async_session_factory() as session:
        try:
            service = ScenarioService(session)
            config = json.loads(execution_config) if isinstance(execution_config, str) else execution_config
            run = await service.create_scenario_run(
                scenario_id=UUID(scenario_id),
                execution_config=config,
            )
            await session.commit()
            return json.dumps({
                "success": True,
                "run_id": str(run.id),
                "identifier": run.identifier,
                "status": run.status,
                "mode": mode,
                "total_steps": run.total_steps,
                "message": "Scenario run created. Execution pending (ScenarioExecutor in Plan 04).",
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


# Export list for registration in __init__.py
SCENARIO_TOOLS = [
    create_test_scenario,
    update_test_scenario,
    add_scenario_step,
    update_scenario_step,
    add_data_mapping,
    add_step_extractor,
    add_step_assertion,
    get_scenario_details,
    list_test_scenarios,
    execute_scenario,
]
