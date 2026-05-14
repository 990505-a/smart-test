"""
Web Automation Testing Agent — Enterprise Dual-Mode Architecture

Two mutually exclusive workflows, chosen automatically based on user input:
  - Mode A (Exploratory QA):     Target URL only  ->  pw-dogfood skill
  - Mode B (Component-Aware):    Source code repo  ->  7-Agent Pipeline skill

Built on deepagents. Built-in tools: ls, read_file, write_file, edit_file,
glob, grep, execute, task, write_todos. Additional custom tools:
  - detect_test_mode  -- Route user intent to Mode A or B
  - check_environment -- Verify CLI dependencies
  - ensure_output_dir -- Create timestamped artifact directories

Architecture:
    |-- SkillsMiddleware (outer) -> loads 5 SKILL.md files from /web/skills/
    |   |-- LLM (deepseek-chat)
    |   |-- CompositeBackend (default=shell, routes={"/": file})
"""

from __future__ import annotations

from deepagents import create_deep_agent as create_agent
from deepagents.middleware import SkillsMiddleware
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from app.agents.web.tools import (
    check_environment,
    composite_backend,
    detect_test_mode,
    ensure_output_dir,
    file_backend,
    output_root,
)

load_dotenv()

# =============================================================================
# LLM
# =============================================================================
llm = init_chat_model("deepseek:deepseek-chat")

# =============================================================================
# SYSTEM PROMPT -- Dual-Mode Orchestrator (~50 lines, no command hard-coding)
# Adapted from classroom reference (2026-05-07) for project architecture.
# =============================================================================
SYSTEM_PROMPT = f"""# Web Automation Testing Agent

You orchestrate two mutually exclusive testing workflows. **Never run both simultaneously.**

## Mode Selection
- **User provides a source-code repository path** -> Mode B: Component-Aware Test Generation
- **User provides only a target URL** -> Mode A: Exploratory QA Testing
- **Neither** -> Ask the user for clarification

## Mode A: Exploratory QA (Target URL)
Goal: Find bugs, capture evidence, produce structured reports.
1. Load `agent-browser-vs-playwright-cli` skill to choose the right browser framework.
2. Load `pw-dogfood` skill and follow its 6-phase workflow strictly.
3. Load `agent-browser` or `playwright-cli` skill only when you need command-level reference.
4. Save all evidence to `{output_root / "qa"}/{{timestamp}}/`. Use `ensure_output_dir` tool to create the directory tree.
5. Final deliverable: `report.md` using `pw-dogfood/templates/report-template.md`.

## Mode B: Component-Aware Test Generation (Source Repo)
Goal: Generate deterministic, maintainable Playwright test scripts from source code.
1. Load `component-aware-web-automation` skill and execute its 7-Agent Pipeline in strict order:
   Script Analyst -> Stage Manager -> Blocking Coach -> Set Designer -> Choreographer -> Assistant Director -> Continuity Lead.
2. Agent outputs are passed through the workspace filesystem; never keep them in conversation memory.
3. Save all artifacts to `{output_root / "tests"}/{{project_name}}/ `.
4. Final deliverables: `component-registry.json`, `locator-catalog.json`, `poms/*.ts`, `tests/*.spec.ts`.

## Universal Rules
- Do NOT repeat skill internals (commands, templates, thresholds) in your reasoning -- load the skill via `read_file` when needed.
- Before any browser command, verify dependencies with `check_environment`.
- One mode per session. If the user switches intent mid-session, acknowledge the switch and restart.
"""

# =============================================================================
# Skills Middleware
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
    tools=[detect_test_mode, check_environment, ensure_output_dir],
    backend=composite_backend,
    middleware=[skills_middleware],
    system_prompt=SYSTEM_PROMPT,
)
