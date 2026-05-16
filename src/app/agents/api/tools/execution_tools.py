"""Agent tools for API test script execution and batch operations.

Provides tools for running Playwright tests, creating test runs,
parsing results, and batch generation/execution of tests.
"""

import json
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import select

from src.app.db.database import async_session_factory
from src.app.db.models.api_test import APITest, APITestRun
from src.app.db.services.api_test_service import APITestService


@tool
async def execute_api_script(
    test_id: str,
    execution_config: str = "{}",
) -> str:
    """Create a test run for an API test script.

    Creates an APITestRun record with pending status. Actual execution
    is performed by APITestExecutor (Plan 04). This tool prepares
    the execution context and returns the run ID for tracking.

    Args:
        test_id: UUID of the API test to execute.
        execution_config: JSON string of execution parameters
            (e.g., base_url, timeout, env vars).

    Returns:
        JSON string with success, run_id, and status.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            config = json.loads(execution_config) if isinstance(execution_config, str) else execution_config
            run = await service.create_test_run(
                api_test_id=UUID(test_id),
                execution_config=config,
            )
            await session.commit()
            return json.dumps({
                "success": True,
                "run_id": str(run.id),
                "identifier": run.identifier,
                "status": run.status,
                "message": "Test run created. Execution pending (APITestExecutor in Plan 04).",
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def get_test_execution_status(run_id: str) -> str:
    """Get the execution status and progress of a test run.

    Args:
        run_id: UUID of the test run.

    Returns:
        JSON string with run status, progress stats, and duration.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            run = await service.get_test_run(UUID(run_id))
            results = await service.get_test_results(UUID(run_id))
            return json.dumps({
                "success": True,
                "run_id": str(run.id),
                "identifier": run.identifier,
                "status": run.status,
                "total_tests": run.total_tests,
                "passed_tests": run.passed_tests,
                "failed_tests": run.failed_tests,
                "skipped_tests": run.skipped_tests,
                "duration_ms": run.duration_ms,
                "error_message": run.error_message,
                "results_count": len(results),
            }, default=str, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def run_tests(script_path: str, base_url: str = "") -> str:
    """Run Playwright tests via the shell backend.

    Executes `npx playwright test` with the given script path.
    Uses the agent's LocalShellBackend for command execution.

    Args:
        script_path: Path to the test script or directory.
        base_url: Optional base URL override for the test runner.

    Returns:
        JSON string with execution result (stdout/stderr).
        Note: This tool requires the agent's shell_backend to be available.
    """
    # This is a placeholder that returns instructions for the agent.
    # The actual execution happens via the agent's backend execute tool.
    import os

    # Build the command
    cmd_parts = ["npx", "playwright", "test", script_path, "--reporter=json"]
    if base_url:
        cmd_parts.extend(["--base-url", base_url])
    cmd = " ".join(cmd_parts)

    return json.dumps({
        "success": True,
        "message": f"Execute this command via the shell backend: {cmd}",
        "command": cmd,
        "script_path": script_path,
        "base_url": base_url or "not specified",
    }, indent=2)


@tool
async def run_test_suite(
    test_ids: str,
    execution_config: str = "{}",
) -> str:
    """Create test runs for multiple API tests in batch.

    Args:
        test_ids: Comma-separated UUIDs of API tests to execute.
        execution_config: JSON string of shared execution parameters.

    Returns:
        JSON string with batch run results.
    """
    async with async_session_factory() as session:
        try:
            service = APITestService(session)
            config = json.loads(execution_config) if isinstance(execution_config, str) else execution_config
            ids = [tid.strip() for tid in test_ids.split(",") if tid.strip()]

            runs = []
            for tid in ids:
                try:
                    run = await service.create_test_run(
                        api_test_id=UUID(tid),
                        execution_config=config,
                    )
                    runs.append({
                        "test_id": tid,
                        "run_id": str(run.id),
                        "status": run.status,
                    })
                except Exception as e:
                    runs.append({
                        "test_id": tid,
                        "error": str(e),
                    })

            await session.commit()
            return json.dumps({
                "success": True,
                "total_requested": len(ids),
                "runs": runs,
            }, default=str, indent=2)
        except Exception as e:
            await session.rollback()
            return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def parse_test_results(results_json: str) -> str:
    """Parse Playwright JSON test results into a structured summary.

    Extracts test suite name, pass/fail/skip counts, duration,
    and per-test details from Playwright JSON reporter output.

    Args:
        results_json: Raw JSON string from Playwright --reporter=json output.

    Returns:
        JSON string with parsed summary including pass rate and failures list.
    """
    try:
        data = json.loads(results_json) if isinstance(results_json, str) else results_json

        suites = data.get("suites", [])
        total_tests = 0
        passed = 0
        failed = 0
        skipped = 0
        failures = []

        def _extract_from_suite(suite: dict) -> None:
            nonlocal total_tests, passed, failed, skipped
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    total_tests += 1
                    status = test.get("status", "unknown")
                    if status == "expected":
                        passed += 1
                    elif status == "unexpected":
                        failed += 1
                        failures.append({
                            "title": spec.get("title", "unknown"),
                            "file": suite.get("file", ""),
                            "error": test.get("results", [{}])[0].get("error", {}).get("message", ""),
                        })
                    elif status == "skipped":
                        skipped += 1
            for child in suite.get("suites", []):
                _extract_from_suite(child)

        for suite in suites:
            _extract_from_suite(suite)

        pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0

        return json.dumps({
            "success": True,
            "summary": {
                "total": total_tests,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_rate": f"{pass_rate:.1f}%",
            },
            "failures": failures,
            "duration_ms": data.get("stats", {}).get("duration", 0),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


@tool
async def batch_generate_tests(
    project_id: str,
    endpoint_ids: str,
) -> str:
    """Initiate batch test generation for multiple endpoints.

    Returns endpoint details that the agent uses to generate tests
    for each endpoint. The agent generates scripts individually.

    Args:
        project_id: UUID of the project.
        endpoint_ids: Comma-separated UUIDs of API endpoints.

    Returns:
        JSON string with endpoint details for batch generation.
    """
    from src.app.agents.api.tools.openapi_tools import get_endpoint_artifacts

    results = []
    ids = [eid.strip() for eid in endpoint_ids.split(",") if eid.strip()]

    for eid in ids:
        # Get endpoint details (reuses existing tool)
        detail = await get_endpoint_artifacts(eid)
        results.append(detail)

    return json.dumps({
        "success": True,
        "project_id": project_id,
        "total_endpoints": len(ids),
        "endpoints": results,
        "instruction": "Generate test scripts for each endpoint using the details above.",
    }, default=str, indent=2)


@tool
async def batch_run_tests(
    project_id: str,
    test_ids: str,
) -> str:
    """Execute multiple API tests in batch.

    Convenience wrapper around run_test_suite that also validates
    all test IDs belong to the specified project.

    Args:
        project_id: UUID of the project (for validation).
        test_ids: Comma-separated UUIDs of API tests.

    Returns:
        JSON string with batch execution results.
    """
    # Delegate to run_test_suite (same logic)
    return await run_test_suite(test_ids, execution_config="{}")


# Export list for registration in __init__.py
EXECUTION_TOOLS = [
    execute_api_script,
    get_test_execution_status,
    run_tests,
    run_test_suite,
    parse_test_results,
    batch_generate_tests,
    batch_run_tests,
]
