---
status: investigating
trigger: "DeepAgents TestCase Agent's SkillsMiddleware uses progressive disclosure - agent can't read SKILL.md files"
created: 2026-05-15T14:30:00Z
updated: 2026-05-15T14:35:00Z
---

## Current Focus

hypothesis: Two separate FilesystemBackend instances (file_backend for agent tools, skills_backend for SkillsMiddleware) create an architectural mismatch. SkillsMiddleware injects skill paths from skills_backend (rooted at src/app/) into the system prompt, telling the agent to "Read {path} for full instructions". But the agent's file tools (read_file etc.) use file_backend (rooted at workspace/default/testcase/), which cannot resolve those skill paths. The classroom code uses a SINGLE backend for both.
test: Compare our agent.py two-backend architecture with classroom's single-backend architecture. Trace the path resolution flow.
expecting: Classroom code confirms single backend pattern where skills live INSIDE the workspace directory.
next_action: Implement fix by either (A) moving skills into workspace and using single backend, or (B) using CompositeBackend to route skill paths to skills_backend.

## Symptoms

expected: Agent loads 7 SKILL.md files via SkillsMiddleware and follows the 5-phase workflow (requirement analysis -> test strategy -> test case design -> quality review -> output formatting), calling tools like save_test_cases_batch, export_test_cases at Phase 5.
actual: Agent says "技能文件尚未就绪" (skill files not ready), generates text without proper skill guidance, doesn't follow the structured workflow.
errors: No error in logs - SkillsMiddleware loads metadata successfully. The problem is architectural: progressive disclosure expects agent to read files, but agent's file tools point to wrong directory.
reproduction: Upload any PDF to the chat, ask "看一下这个需求" (look at this requirement). Agent responds with "技能文件尚未就绪" instead of following the skill-based workflow.
started: Has been an issue since project inception. Never worked correctly.

## Eliminated

## Evidence

- timestamp: 2026-05-15T14:32:00Z
  checked: Our agent.py backend configuration (D:/test_agent/smart-test-platform/src/app/agents/testcase/agent.py)
  found: "Two SEPARATE backends. file_backend rooted at workspace/default/testcase/ (line 58). skills_backend rooted at src/app/ (line 66). SkillsMiddleware uses skills_backend. Agent uses file_backend. Progressive disclosure tells agent to read skill paths like /skills/requirement-analysis/SKILL.md, but agent's file tools resolve those paths against workspace/default/testcase/, not src/app/."
  implication: Agent physically cannot read SKILL.md files because its file tools point to the wrong root directory.

- timestamp: 2026-05-15T14:33:00Z
  checked: SkillsMiddleware source code (D:/PYTHON/Lib/site-packages/deepagents/middleware/skills.py)
  found: "SkillsMiddleware._format_skills_list() (line 950-951) injects: '-> Read `{skill["path"]}` for full instructions'. The SKILLS_SYSTEM_PROMPT template (line 783-823) explicitly tells agent to 'Use read_file on the path shown in the skill list above'. These paths come from skills_backend."
  implication: Progressive disclosure is BY DESIGN. The middleware only loads metadata (name, description, path), then tells the agent to use its file tools to read the full SKILL.md content. This REQUIRES agent's file tools to be able to resolve those paths.

- timestamp: 2026-05-15T14:34:00Z
  checked: Classroom reference code agent.py (D:/test_agent/2026-05-07-ai-test-agent-system/.../agents/testcase/agent.py)
  found: "Classroom uses ONE FilesystemBackend: file_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True) where workspace_dir points to src/workspace/. SkillsMiddleware uses SAME file_backend with sources=['/testcase/skills/', '/rag/skills/']. Skills live at src/workspace/testcase/skills/*/SKILL.md."
  implication: CONFIRMED: Classroom uses single-backend pattern. Skills are inside the workspace directory. Agent's file tools and SkillsMiddleware share the same backend, so progressive disclosure works.

- timestamp: 2026-05-15T14:35:00Z
  checked: Classroom skills directory structure (find command on extracted zip)
  found: "Skills at src/workspace/testcase/skills/requirement-analysis/SKILL.md etc. All 6 testcase skills are inside the workspace directory that file_backend is rooted at."
  implication: The correct architecture is: put skills inside the workspace directory, use single FilesystemBackend for both agent tools and SkillsMiddleware.

## Resolution

root_cause: Two separate FilesystemBackend instances create an architectural mismatch. SkillsMiddleware loads skill metadata from skills_backend (rooted at src/app/) and injects paths like /skills/requirement-analysis/SKILL.md into the system prompt. The agent is told to "Read {path} for full instructions". But the agent's file tools use file_backend (rooted at workspace/default/testcase/), which resolves /skills/requirement-analysis/SKILL.md as workspace/default/testcase/skills/requirement-analysis/SKILL.md - a path that does not exist. The classroom code uses a SINGLE FilesystemBackend with skills living inside the workspace directory, so progressive disclosure works correctly.
fix: Move skills into the workspace directory structure and use a single FilesystemBackend for both the agent and SkillsMiddleware. Specifically: (1) copy/link skills from src/app/skills/ into the workspace directory under testcase/skills/, (2) configure SkillsMiddleware to use the same file_backend as the agent, with sources=["/testcase/skills/"].
verification:
files_changed: []
