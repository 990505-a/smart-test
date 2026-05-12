# Phase 3: RAG Knowledge System - Validation Architecture

**Phase:** 03-rag-knowledge-system
**Created:** 2026-05-12

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | None (uses defaults) |
| Quick run command | `pytest tests/test_wiki_integration.py -x -v` |
| Full suite command | `pytest tests/ -x -v` |

## Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File |
|--------|----------|-----------|-------------------|------|
| D-04 | wiki-mcp stdio tools load correctly | unit | `pytest tests/test_wiki_integration.py::TestWikiMCPClient -x` | test_wiki_integration.py |
| D-05 | wiki-mcp 6 tools registered in agent | integration | `pytest tests/test_wiki_integration.py::TestWikiSkill::test_wiki_skill_has_all_tools -x` | test_wiki_integration.py |
| D-06 | wiki-query SKILL.md loads with valid frontmatter | unit | `pytest tests/test_wiki_integration.py::TestWikiSkill::test_wiki_skill_frontmatter_valid -x` | test_wiki_integration.py |
| D-06 | SKILL.md name matches directory name | unit | `pytest tests/test_wiki_integration.py::TestWikiSkill::test_wiki_skill_frontmatter_valid -x` | test_wiki_integration.py |
| D-07 | SKILL.md references requirement-analysis and test-strategy | unit | `pytest tests/test_wiki_integration.py::TestWikiSkill::test_wiki_skill_has_workflow_integration -x` | test_wiki_integration.py |
| D-08 | config.py reads wiki-mcp settings from env | unit | `pytest tests/test_wiki_integration.py::TestWikiConfig -x` | test_wiki_integration.py |
| D-16 | No middleware changes (2-layer preserved) | manual | Verify agent.py does not import new middleware | visual |

## Sampling Rate

- **Per task commit:** `pytest tests/test_wiki_integration.py -x -v`
- **Per wave merge:** `pytest tests/ -x -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

## Wave 0 Gaps

- [ ] `tests/test_wiki_integration.py` -- covers D-04, D-05, D-06, D-07, D-08 (created in Plan 02 Task 2)
- [ ] `D:/llm-wiki/wiki-mcp/wiki-mcp-config.json` -- minimal config file for testing (created in Plan 01 Task 1)
- [ ] Test wiki project directory with sample .md files (created in Plan 01 Task 1 if missing)

## Structural Verification

| Check | How | Expected |
|-------|-----|----------|
| config.py has wiki_mcp_* fields | `python -c "from app.core.config import settings; assert hasattr(settings, 'wiki_mcp_command')"` | Pass |
| mcp_client.py has wiki-mcp stdio | `python -c "content = open('src/app/mcp/mcp_client.py').read(); assert 'wiki-mcp' in content and 'stdio' in content"` | Pass |
| wiki-query SKILL.md exists | `python -c "from pathlib import Path; assert Path('src/app/skills/wiki-query/SKILL.md').is_file()"` | Pass |
| wiki-mcp-config.json exists | `python -c "import json; cfg = json.loads(open('D:/llm-wiki/wiki-mcp/wiki-mcp-config.json').read()); assert 'wikis' in cfg"` | Pass |
| Agent has wiki tools | `python -c "from app.agents.testcase.agent import wiki_tools; assert isinstance(wiki_tools, list)"` | Pass |
| All 6 skills discoverable | `pytest tests/test_wiki_integration.py::TestAllSkills -x -v` | Pass |

## Graceful Degradation Tests

| Scenario | Expected Behavior |
|----------|-------------------|
| wiki-mcp not installed (npx fails) | `_load_wiki_tools()` returns empty list, agent works with `[export_test_cases_to_excel]` only |
| wiki-mcp-config.json missing | `_load_wiki_tools()` returns empty list, no crash |
| DEEPSEEK_API_KEY not set | Agent import may fail (existing behavior), but config/client tests should still pass |
| No wiki project directory | wiki-mcp starts but returns empty results; agent still functional |
