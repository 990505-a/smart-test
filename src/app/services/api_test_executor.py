"""API test execution engine.

Async Playwright test executor that:
1. Gets script from storage (workspace/api/scripts/)
2. Writes to temp directory
3. Generates playwright.config.ts
4. Runs npx playwright test --reporter=json
5. Parses JSON results
6. Updates APITestRun with stats
7. Saves individual APITestResult records

Adapted from classroom reference with our project's service/repository pattern.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from src.app.db.database import async_session_factory
from src.app.db.services.api_test_service import APITestService

logger = logging.getLogger(__name__)


class APITestExecutor:
    """Async Playwright test execution engine.

    Pipeline:
    1. Get script from storage (workspace/api/scripts/)
    2. Write to temp directory
    3. Generate playwright.config.ts
    4. Run npx playwright test --reporter=json
    5. Parse JSON results
    6. Update APITestRun with stats
    7. Save individual APITestResult records
    """

    async def execute(self, run_id: UUID) -> None:
        """Execute a test run. Called as background task.

        Args:
            run_id: The APITestRun ID to execute.
        """
        async with async_session_factory() as session:
            svc = APITestService(session)
            exec_dir: Path | None = None

            try:
                # 1. Update status to running
                run_info = await svc.update_run_status(run_id, "running")
                api_test_id = run_info.api_test_id

                # 2. Get test and script content
                test_info = await svc.get_api_test(api_test_id)
                script_content = await svc.get_script(api_test_id)

                # 3. Create temp execution directory
                exec_dir = Path(tempfile.mkdtemp(prefix="api_test_"))

                # 4. Write script file
                identifier = test_info.identifier or "test"
                script_path = exec_dir / f"{identifier}.spec.ts"
                script_path.write_text(script_content, encoding="utf-8")

                # 5. Generate playwright.config.ts
                config_content = self._generate_config(exec_dir)
                (exec_dir / "playwright.config.ts").write_text(
                    config_content, encoding="utf-8"
                )

                # 6. Run npx playwright test
                start_time = time.time()
                proc = await asyncio.create_subprocess_exec(
                    "npx",
                    "playwright",
                    "test",
                    "--reporter=json",
                    str(script_path),
                    cwd=str(exec_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                duration_ms = int((time.time() - start_time) * 1000)

                # 7. Parse JSON results
                results = self._parse_results(stdout.decode("utf-8", errors="replace"))

                # 8. Update run and save results
                await svc.update_run_status(
                    run_id,
                    "completed" if proc.returncode == 0 else "failed",
                    total_tests=results.get("total", 0),
                    passed_tests=results.get("passed", 0),
                    failed_tests=results.get("failed", 0),
                    skipped_tests=results.get("skipped", 0),
                    duration_ms=duration_ms,
                )

                if results.get("suites"):
                    await svc.save_test_results(run_id, results["suites"])

                logger.info(
                    "Test run %s completed: %d passed, %d failed, %d skipped",
                    run_id,
                    results.get("passed", 0),
                    results.get("failed", 0),
                    results.get("skipped", 0),
                )

            except Exception as e:
                logger.error("Test run %s failed: %s", run_id, e)
                try:
                    await svc.update_run_status(
                        run_id, "failed", error_message=str(e)
                    )
                except Exception:
                    logger.exception(
                        "Failed to update run status for %s", run_id
                    )
            finally:
                # Cleanup temp dir
                if exec_dir:
                    shutil.rmtree(exec_dir, ignore_errors=True)

    def _generate_config(self, output_dir: Path) -> str:
        """Generate minimal playwright.config.ts.

        Args:
            output_dir: Directory where the config file lives.

        Returns:
            TypeScript config file content.
        """
        return f"""import {{ defineConfig }} from '@playwright/test';
export default defineConfig({{
  testDir: '.',
  reporter: [['json', {{ outputFile: '{output_dir / "results.json"} }}]],
  use: {{ baseURL: 'http://localhost:3000' }},
}});
"""

    def _parse_results(self, raw_output: str) -> dict[str, Any]:
        """Parse Playwright JSON reporter output.

        Args:
            raw_output: stdout from npx playwright test --reporter=json.

        Returns:
            Dictionary with total, passed, failed, skipped counts and
            a flat list of suite results for saving to database.
        """
        try:
            data = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError):
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "suites": [],
            }

        suites: list[dict[str, Any]] = []
        for suite in data.get("suites", []):
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    # Extract error message from last result attempt
                    results_list = test.get("results", [{}])
                    last_result = results_list[-1] if results_list else {}
                    error_msg = None
                    error_obj = last_result.get("error", {})
                    if isinstance(error_obj, dict):
                        error_msg = error_obj.get("message")
                    elif isinstance(error_msg, str):
                        error_msg = error_obj

                    suites.append({
                        "scenario_name": spec.get("title", ""),
                        "status": test.get("status", "skipped"),
                        "duration_ms": test.get("duration", 0),
                        "error_message": error_msg,
                    })

        passed = sum(1 for s in suites if s["status"] == "passed")
        failed = sum(1 for s in suites if s["status"] == "failed")

        return {
            "total": len(suites),
            "passed": passed,
            "failed": failed,
            "skipped": len(suites) - passed - failed,
            "suites": suites,
        }
