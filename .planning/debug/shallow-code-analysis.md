---
status: investigating
trigger: "测试用例生成时代码分析太浅。当前只有 git_log、git_diff_stat、grep_code 三个工具，智能体只能看到文件名和搜索匹配行，无法读取实际代码内容。"
created: 2026-05-28T00:00:00
updated: 2026-05-28T00:00:00
---

## Current Focus

hypothesis: The agent has no file-reading capability for code repositories. The three git tools (git_log, git_diff_stat, grep_code) provide only metadata (commit messages, file names, matching lines), and the system prompt explicitly forbids reading full diffs. The deepagents framework already ships read_file/ls/grep/glob as built-in FilesystemMiddleware tools, but TestCase agent uses a CompositeBackend rooted at workspace (not the repo), so these tools can never reach repo source files.
test: Verify that FilesystemMiddleware's read_file is present but scoped to workspace, not to the configured repo_path. Confirm no other tool can read arbitrary repo files.
expecting: FilesystemMiddleware is active but its backend points to workspace/{space_id}/testcase/, while repo_path comes from configurable — two separate paths with no bridge.
next_action: design tool enhancements

## Symptoms

expected: 智能体在设计测试用例时能深入阅读实际代码实现（接口定义、参数校验、业务逻辑、数据库操作、异常处理），基于代码生成精准的测试数据和预期结果
actual: 智能体只能看到 git commit 消息、文件名+行数统计、grep 关键词匹配行。设计用例时只能靠需求和猜测，无法参考实际代码实现
errors: 无报错，但生成的测试用例质量受限于代码可见性
reproduction: 上传需求文档 + 选择仓库路径 + 生成测试用例，观察智能体是否参考了代码实现
started: 一直是这样的，从未支持深入代码分析

## Eliminated

## Evidence

- timestamp: 2026-05-28T00:01
  checked: agent.py tool list (line 333-337)
  found: _all_tools = [export_test_cases, save_test_cases_batch, save_test_case_to_db, list_project_test_cases, ensure_project, git_log, git_diff_stat, grep_code] + wiki_tools. No file-reading tools for repo code.
  implication: The agent physically cannot read source code files from the configured repository.

- timestamp: 2026-05-28T00:02
  checked: git_tools.py (full file, 118 lines)
  found: Three tools exist: git_log (commit search, oneline format), git_diff_stat (--stat only, no diff content), grep_code (git grep -n, max 50 results, matching lines only). All three operate on repo_path from get_config()["configurable"]["repo_path"].
  implication: Even grep_code only returns matching lines, not surrounding context or full functions.

- timestamp: 2026-05-28T00:03
  checked: SYSTEM_PROMPT lines 257-282 (code analysis section)
  found: Explicit rule: "禁止读取完整 diff 内容". Lightweight analysis prescribed: git_log -> git_diff_stat -> grep_code. Trigger condition: [代码分析上下文] marker required.
  implication: The system prompt deliberately limits code visibility. This was a design choice to keep analysis "lightweight", but it prevents the agent from seeing actual code logic.

- timestamp: 2026-05-28T00:04
  checked: CompositeBackend configuration (lines 57-70)
  found: file_backend = FilesystemBackend(root_dir=workspace/{space_id}/testcase/), skills_backend = FilesystemBackend(root_dir=src/app/skills/). The FilesystemMiddleware injected by deepagents reads from these backends, NOT from the git repo at configurable.repo_path.
  implication: The built-in read_file tool exists (deepagents provides it) but it reads workspace files, not repo source code. The agent has no way to read files from the configured git repository.

- timestamp: 2026-05-28T00:05
  checked: deepagents graph.py — FilesystemMiddleware tool suite
  found: create_deep_agent always injects FilesystemMiddleware which provides: read_file, write_file, edit_file, ls, glob, grep. These operate on the configured backend (CompositeBackend in this case).
  implication: The agent already HAS a read_file tool, but it is scoped to the workspace directory, not the code repository. We need SEPARATE tools that target the repo_path.

- timestamp: 2026-05-28T00:06
  checked: API agent (api/agent.py) for comparison
  found: API agent uses GitNexus MCP (codegraph) for source-code-level analysis. It loads MCP tools via MultiServerMCPClient with stdio transport. System prompt mentions: "Extract API endpoint definitions from source code", "Analyze request/response schemas from code".
  implication: The API agent already has deep code analysis via MCP. The TestCase agent needs similar capability but the GitNexus MCP is API-specific. A simpler approach (direct file reading) may be more appropriate for TestCase agent's use case.

- timestamp: 2026-05-28T00:07
  checked: All 5 Skill files (requirement-analysis, test-strategy, test-case-design, test-data-generator, output-formatter)
  found: test-case-design SKILL.md extensively references field types, parameter boundaries, API contracts, business rules, and data constraints — but has no guidance on extracting these from code. The requirement-analysis SKILL mentions PPDCS Product dimension: "接口清单：列出所有API端点及参数" but only from requirements, never from code.
  implication: Skills are designed around requirements-only input. They don't reference code reading at all, which means even if tools are added, Skills need updates to tell the agent WHEN and HOW to use code reading.

## Resolution

root_cause: Three converging limitations:
1. **Tool gap**: The agent has only 3 git tools (log/diff_stat/grep) that return metadata, not file content. No tool can read actual source files from the configured repository.
2. **System prompt prohibition**: The prompt explicitly says "禁止读取完整 diff 内容" and prescribes a "lightweight analysis" workflow that deliberately avoids reading code.
3. **Skill design**: None of the 5 Skill files reference code-reading as an information source. They assume requirements-only input.

The deepagents framework provides built-in read_file via FilesystemMiddleware, but it is scoped to the workspace directory (workspace/{space_id}/testcase/), not the code repository (configurable.repo_path). The agent needs NEW tools that bridge this gap — file-reading tools that operate on the repo_path, similar to how the existing git_tools use _get_repo_path().

fix: Add 3 new code-reading tools to git_tools.py:
1. `read_code_file(path, start_line, end_line)` — Read a specific file (or line range) from the repository
2. `git_diff_content(commit, file_path)` — Read the actual diff content for a specific file in a commit
3. `grep_code_context(pattern, file_glob, context_lines)` — Enhanced grep with surrounding context lines (before/after)

Plus update:
4. SYSTEM_PROMPT — Replace "禁止读取完整 diff 内容" with guided deep-analysis rules
5. Skill files — Add code-reading guidance to requirement-analysis, test-strategy, and test-case-design

verification: pending
files_changed: []
