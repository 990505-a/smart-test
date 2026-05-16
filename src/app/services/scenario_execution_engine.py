"""Scenario execution engine.

Multi-step scenario execution engine that:
1. Resolves data dependencies (JSONPath extraction from prior steps)
2. Builds HTTP request (method, url, headers, body)
3. Sends request via httpx.AsyncClient
4. Extracts data from response using JSONPath
5. Runs assertions (eq, ne, gt, lt, contains, matches)
6. Records result

Includes ExecutionContext and DataDependencyResolver helper classes.

Adapted from classroom reference with our project's service/repository pattern
and async_session_factory for background task execution.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.database import async_session_factory
from src.app.db.models.test_scenario import (
    ScenarioRun,
    ScenarioStep,
    ScenarioStepResult,
    StepDataMapping,
    TestScenario,
)
from src.app.db.services.scenario_service import ScenarioService

logger = logging.getLogger(__name__)


class ExecutionContext:
    """Stores variables and step data for scenario execution.

    Provides JSONPath-like extraction via dot notation for response data
    and template variable substitution.
    """

    def __init__(self) -> None:
        self.variables: dict[str, Any] = {}
        self.step_data: dict[str, dict[str, Any]] = {}

    def initialize(self, global_vars: dict, runtime_vars: dict) -> None:
        """Initialize context with global and runtime variables."""
        self.variables = {**global_vars, **runtime_vars}

    def set_variable(self, name: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[name] = value

    def get_variable(self, name: str) -> Any:
        """Get a context variable by name."""
        return self.variables.get(name)

    def set_step_data(self, step_id: str, data: dict[str, Any]) -> None:
        """Store response data for a completed step."""
        self.step_data[step_id] = data

    def get_step_data(
        self, step_id: str, path: str | None = None
    ) -> Any:
        """Get step data, optionally extracting via dot-notation path."""
        data = self.step_data.get(step_id, {})
        if path:
            return self._extract_by_path(data, path)
        return data

    def _extract_by_path(self, data: Any, path: str) -> Any:
        """Extract value using simple dot-notation JSONPath.

        Supports: body.data.name, items.0.name, status_code

        Args:
            data: The data structure to extract from.
            path: Dot-separated path string.

        Returns:
            The extracted value, or None if not found.
        """
        keys = path.split(".")
        current = data
        for key in keys:
            if current is None:
                return None
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                current = current[idx] if idx < len(current) else None
            else:
                return None
        return current


class DataDependencyResolver:
    """Resolves data dependencies between scenario steps.

    Handles:
    - previous_response: Extract data from prior step responses
    - variable: Read from execution context variables
    - static: Use literal value
    - Template variable substitution: {{variable}} in strings
    """

    def __init__(self, context: ExecutionContext) -> None:
        self.context = context

    async def resolve_mapping(self, mapping: StepDataMapping) -> Any:
        """Resolve a single data mapping to its value.

        Args:
            mapping: StepDataMapping with source_type, source_path, etc.

        Returns:
            The resolved value.
        """
        if mapping.source_type == "previous_response":
            raw_value = self.context.get_step_data(
                str(mapping.source_step_id), mapping.source_path
            )
        elif mapping.source_type == "variable":
            raw_value = self.context.get_variable(
                mapping.source_path or ""
            )
        elif mapping.source_type == "static":
            raw_value = mapping.source_path
        else:
            logger.warning("Unknown source_type: %s", mapping.source_type)
            raw_value = None

        # Apply transform if configured
        if mapping.transform_expression and raw_value is not None:
            raw_value = self._apply_transform(
                raw_value, mapping.transform_expression
            )

        return raw_value

    def _apply_transform(self, value: Any, expression: str) -> Any:
        """Apply a simple transform expression to a value.

        Example: 'Bearer ' + value -> 'Bearer abc123'
        """
        try:
            return eval(expression, {"__builtins__": {}}, {"value": value})  # noqa: S307
        except Exception:
            return value

    def apply_to_request(
        self, request_override: dict, resolved_mappings: list[tuple[str, Any]]
    ) -> dict[str, Any]:
        """Apply resolved mappings to a request configuration.

        Args:
            request_override: Base request override from the step.
            resolved_mappings: List of (target_path, value) tuples.

        Returns:
            Final request configuration dictionary.
        """
        request = {
            "method": request_override.get("method", "GET"),
            "url": request_override.get("url", ""),
            "headers": dict(request_override.get("headers", {})),
            "params": dict(request_override.get("params", {})),
            "body": request_override.get("body"),
        }

        # Apply each resolved mapping to its target path
        for target_path, value in resolved_mappings:
            self._set_nested_value(request, target_path, value)

        # Substitute template variables {{variable}}
        request = self._substitute_variables(request)

        return request

    def _set_nested_value(
        self, obj: dict, path: str, value: Any
    ) -> None:
        """Set a nested value by dot-notation path.

        Example: "headers.Authorization" -> obj["headers"]["Authorization"] = value
        """
        parts = path.split(".")
        current = obj
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            if not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value

    def _substitute_variables(self, obj: Any) -> Any:
        """Recursively substitute {{variable}} placeholders in strings.

        Supports: {{variable}}, {{variable.nested}}
        """
        if isinstance(obj, str):
            pattern = r"\{\{(\w+(?:\.\w+)*)\}\}"

            def replacer(match: re.Match) -> str:
                var_name = match.group(1)
                value = self.context.get_variable(var_name)
                if value is not None:
                    return str(value)
                return match.group(0)  # Keep placeholder if not found

            return re.sub(pattern, replacer, obj)
        elif isinstance(obj, dict):
            return {
                k: self._substitute_variables(v) for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [self._substitute_variables(item) for item in obj]
        return obj


class ScenarioExecutionEngine:
    """Multi-step scenario execution engine.

    For each step in a scenario:
    1. Resolve data dependencies (JSONPath extraction from prior steps)
    2. Build HTTP request (method, url, headers, body)
    3. Send request via httpx.AsyncClient
    4. Extract data from response using JSONPath
    5. Run assertions (eq, ne, gt, lt, contains, matches)
    6. Record result
    """

    def __init__(self) -> None:
        self.http_client: httpx.AsyncClient | None = None

    async def execute_scenario(self, scenario_run_id: UUID) -> None:
        """Execute a scenario run. Called as background task.

        Args:
            scenario_run_id: The ScenarioRun ID to execute.
        """
        async with async_session_factory() as session:
            svc = ScenarioService(session)

            try:
                # Load run and scenario
                run = await svc.get_scenario_run(scenario_run_id)

                # Update status to running
                run.status = "running"
                run.started_at = datetime.now(timezone.utc)
                await session.flush()

                scenario = await svc.get_scenario(run.scenario_id)

                # Initialize execution context
                context = ExecutionContext()
                context.initialize(
                    scenario.global_variables or {},
                    run.runtime_variables or {},
                )

                # Set baseUrl from execution config if provided
                base_url = (run.execution_config or {}).get("base_url", "")
                if base_url:
                    context.set_variable("baseUrl", base_url)

                # Initialize HTTP client
                self.http_client = httpx.AsyncClient(timeout=30.0)

                results: list[dict[str, Any]] = []
                start_time = time.time()
                run_failed = False

                for step in scenario.steps:
                    if run_failed and not step.continue_on_failure:
                        # Skip remaining steps after a failure
                        results.append({
                            "step_id": step.id,
                            "step_order": step.step_order,
                            "status": "skipped",
                        })
                        continue

                    step_result = await self._execute_step(
                        step, context, session
                    )
                    results.append(step_result)

                    if step_result["status"] == "failed":
                        if not step.continue_on_failure:
                            run_failed = True

                # Calculate stats
                duration_ms = int((time.time() - start_time) * 1000)
                passed = sum(1 for r in results if r.get("status") == "passed")
                failed = sum(1 for r in results if r.get("status") == "failed")
                skipped = sum(
                    1 for r in results if r.get("status") == "skipped"
                )

                # Save step results
                await svc.save_step_results(scenario_run_id, results)

                # Update run stats
                final_status = "completed" if not run_failed else "failed"
                await session.execute(
                    update(ScenarioRun)
                    .where(ScenarioRun.id == scenario_run_id)
                    .values(
                        status=final_status,
                        passed_steps=passed,
                        failed_steps=failed,
                        skipped_steps=skipped,
                        duration_ms=duration_ms,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

                logger.info(
                    "Scenario run %s %s: %d passed, %d failed, %d skipped",
                    scenario_run_id,
                    final_status,
                    passed,
                    failed,
                    skipped,
                )

            except Exception as e:
                logger.error("Scenario run %s failed: %s", scenario_run_id, e)
                try:
                    await session.execute(
                        update(ScenarioRun)
                        .where(ScenarioRun.id == scenario_run_id)
                        .values(
                            status="failed",
                            error_message=str(e),
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()
                except Exception:
                    logger.exception(
                        "Failed to update run status for %s", scenario_run_id
                    )
            finally:
                if self.http_client:
                    await self.http_client.aclose()
                    self.http_client = None

    async def _execute_step(
        self,
        step: ScenarioStep,
        context: ExecutionContext,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Execute a single scenario step.

        Args:
            step: The ScenarioStep to execute.
            context: Execution context with variables and prior step data.
            session: Database session for loading mappings.

        Returns:
            Step result dictionary with status, request/response data,
            assertion results, etc.
        """
        step_start = time.time()

        try:
            # 1. Resolve data dependencies
            resolver = DataDependencyResolver(context)
            mappings_stmt = select(StepDataMapping).where(
                StepDataMapping.step_id == step.id
            )
            mappings_result = await session.execute(mappings_stmt)
            mappings = mappings_result.scalars().all()

            resolved: list[tuple[str, Any]] = []
            for mapping in mappings:
                value = await resolver.resolve_mapping(mapping)
                resolved.append((mapping.target_path, value))

            # 2. Build request from step config + resolved data
            request_override = step.request_override or {}
            request_config = resolver.apply_to_request(
                request_override, resolved
            )

            url = request_config.get("url", "")
            method = request_config.get("method", "GET").upper()
            headers = request_config.get("headers", {})
            body = request_config.get("body")
            params = request_config.get("params", {})

            # Prepend baseUrl if the URL is relative
            base_url = context.get_variable("baseUrl") or ""
            if base_url and url and not url.startswith(("http://", "https://")):
                url = base_url.rstrip("/") + "/" + url.lstrip("/")

            # 3. Apply delay if configured
            if step.delay_ms > 0:
                await asyncio.sleep(step.delay_ms / 1000)

            # 4. Send HTTP request with retry
            response = None
            last_error: Exception | None = None
            for attempt in range(step.retry_count + 1):
                try:
                    response = await self.http_client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=body,
                    )
                    break
                except Exception as e:
                    last_error = e
                    if attempt < step.retry_count:
                        await asyncio.sleep(1)

            if response is None:
                return {
                    "step_id": step.id,
                    "step_order": step.step_order,
                    "status": "failed",
                    "error_message": str(last_error),
                    "duration_ms": int((time.time() - step_start) * 1000),
                }

            # 5. Parse response
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text
            else:
                response_body = response.text

            response_data = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
            }

            # Store step data for dependency resolution by later steps
            context.set_step_data(str(step.id), response_data)

            # 6. Run extractors
            extractors = step.extractors or []
            extracted: dict[str, Any] = {}
            for extractor in extractors:
                ext_name = extractor.get("name", "")
                ext_path = extractor.get("path", "")
                if ext_name and ext_path:
                    value = context._extract_by_path(response_body, ext_path)
                    extracted[ext_name] = value
                    context.set_variable(ext_name, value)

            # 7. Run assertions
            assertions = step.assertions or []
            assertion_results = []
            for assertion in assertions:
                result = self._evaluate_assertion(
                    assertion, response_data, context
                )
                assertion_results.append(result)

            all_passed = all(r.get("passed", False) for r in assertion_results)
            step_status = "passed" if all_passed else "failed"

            # 8. Build result
            duration_ms = int((time.time() - step_start) * 1000)
            return {
                "step_id": step.id,
                "step_order": step.step_order,
                "status": step_status,
                "request_data": request_config,
                "response_data": response_data,
                "extracted_data": extracted,
                "assertion_results": assertion_results,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            logger.exception("Step %s execution error: %s", step.id, e)
            return {
                "step_id": step.id,
                "step_order": step.step_order,
                "status": "failed",
                "error_message": str(e),
                "duration_ms": int((time.time() - step_start) * 1000),
            }

    def _evaluate_assertion(
        self,
        assertion: dict,
        response: dict,
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Evaluate a single assertion against response data.

        Args:
            assertion: Assertion config with type, path, operator, expected.
            response: Response data dictionary.
            context: Execution context for variable access.

        Returns:
            Dictionary with passed, actual, expected, operator.
        """
        assertion_type = assertion.get("type", "jsonpath")
        path = assertion.get("path", "")
        operator = assertion.get("operator", "eq")
        expected = assertion.get("expected")

        # Extract actual value based on assertion type
        if assertion_type == "status":
            actual = response.get("status_code")
        elif assertion_type == "header":
            actual = response.get("headers", {}).get(path)
        elif assertion_type == "jsonpath":
            body = response.get("body", {})
            actual = context._extract_by_path(body, path)
        else:
            actual = None

        # Compare
        passed = self._compare(actual, expected, operator)

        return {
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "operator": operator,
            "type": assertion_type,
        }

    def _compare(
        self, actual: Any, expected: Any, operator: str
    ) -> bool:
        """Compare actual vs expected using the given operator.

        Operators: eq, ne, gt, lt, contains, matches
        """
        try:
            if operator == "eq":
                return actual == expected
            elif operator == "ne":
                return actual != expected
            elif operator == "gt":
                return actual > expected
            elif operator == "lt":
                return actual < expected
            elif operator == "contains":
                return expected in str(actual)
            elif operator == "matches":
                return bool(re.match(str(expected), str(actual)))
        except (TypeError, ValueError):
            return False
        return False
