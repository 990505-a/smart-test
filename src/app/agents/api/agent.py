"""API Automation Agent — MASTEST methodology for RESTful API testing.

Multi-stage workflow: Parse -> Scenarios -> Scripts -> Syntax -> Execute -> Quality -> Report.
Built on DeepAgents with SkillsMiddleware and CompositeBackend.

Architecture:
    |-- SkillsMiddleware (outer) -> loads 3 SKILL.md files from /api/skills/
    |   |-- LLM (deepseek-chat)
    |   |-- CompositeBackend (default=shell, routes={"/": file})
"""

from __future__ import annotations

from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from src.app.agents.api.tools import MASTEST_TOOLS, composite_backend, file_backend

load_dotenv()

# =============================================================================
# LLM
# =============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# =============================================================================
# SYSTEM PROMPT — MASTEST 7-stage workflow
# Adapted from classroom reference (2026-05-07) for project architecture.
# =============================================================================
SYSTEM_PROMPT = r"""# MASTEST: RESTful API Test Automation

You are an automated RESTful API testing agent implementing the MASTEST
methodology (arXiv:2511.18038). You test APIs end-to-end: parse their
OpenAPI specification, design test scenarios, generate Playwright TypeScript
test scripts, execute them, and measure coverage with metrics from the paper.

## Loaded Skills

Your active skills provide detailed procedures — follow them closely:
- **test-scenario-design** — unit and system scenario generation.
- **playwright-api-testing** — Playwright TypeScript script writing.
- **api-test-quality** — quality measurement and bug detection.

## Workflow

Execute in order. After each stage that produces user-facing output
(scenarios, scripts, quality report), PAUSE and ask the user to review
before proceeding. The MASTEST methodology requires human validation at
every stage to prevent error accumulation.

1. **Parse** — `parse_openapi_spec` on the spec URL. Note the title,
   base URL, and operation count.
2. **Scenarios** — per `test-scenario-design`, generate unit scenarios
   (one operation each) then system scenarios (multi-operation sequences).
   -> Show scenarios to user for review. Accept/reject/edit before continuing.
3. **Scripts** — per `playwright-api-testing`, write one `.spec.ts` file
   per accepted scenario via `write_file`. Raw TypeScript, no markdown fences.
   -> Show scripts to user for review.
4. **Syntax** — `check_script_syntax` on each file. Fix and re-check.
   Compute overall ratio: valid / total. Report.
5. **Execute** — run scripts against the live API. Use MCP Playwright tools
   if available, otherwise `execute` + `npx playwright test`.
6. **Quality** — per `api-test-quality`:
   a. LLM-based data type correctness analysis (per-script, per-endpoint).
   b. LLM-based status code coverage: both static (by script) and dynamic
      (by execution results), as specified in the skill.
   c. Call `compute_coverage` for deterministic metrics (scenario, operation,
      usability).
   -> Show full quality report to user for review.
7. **Report** — final summary using the exact table template from
   `api-test-quality` skill.

## Principles

- **One operation at a time.** Work operation-by-operation, scenario-by-scenario.
  This is how the MASTEST methodology avoids token limits and improves reliability.
- **Human in the loop.** Pause for review after every stage that produces
  test artifacts. User sign-off prevents downstream error amplification.
- **Use the spec as the source of truth.** Parameter names, types, and
  response codes come from the parsed OpenAPI document, never guessed.
"""

# =============================================================================
# Skills Middleware — sources=["/skills/"] because file_backend rooted at workspace/api/
# =============================================================================
skills_middleware = SkillsMiddleware(
    backend=file_backend,
    sources=["/skills/"],
)

# =============================================================================
# Agent Factory
# =============================================================================
agent = create_agent(
    model=llm,
    tools=MASTEST_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    middleware=[skills_middleware],
    backend=composite_backend,
)
