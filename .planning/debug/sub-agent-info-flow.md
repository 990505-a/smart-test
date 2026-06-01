---
status: awaiting_human_verify
trigger: "子智能体信息传递链路断裂。改回直接嵌入文本后，子智能体无法获取原始需求文档内容"
created: 2026-05-28T00:00:00Z
updated: 2026-05-28T00:15:00Z
---

## Current Focus

hypothesis: CONFIRMED - Fix applied and self-verified
test: All workspace/uploads/ references removed; phase0 file mechanism added throughout system prompt
expecting: User verifies the fix works end-to-end in a real flow
next_action: Await human verification

## Symptoms

expected: 子智能体在 Phase 3 用例设计时，应该能获取到完整的原始需求内容 + Phase 1 分析结果 + Phase 2 测试策略，以设计高质量测试用例
actual: 最近将 PDF 处理从 upload-to-workspace（保存文件到workspace，agent用read_file读）改回直接嵌入消息文本。这导致：1. 子智能体任务描述模板中引用的 workspace/uploads/ 下的文件路径不再存在；2. 子智能体不继承父智能体的消息历史，只收到任务描述（一个 HumanMessage）；3. 原始需求文档文本现在只存在于父智能体的消息中，子智能体看不到
errors: 无报错，但子智能体生成的用例质量会下降（缺少原始需求上下文）
reproduction: 启动完整流程，Phase 3 派子智能体时观察
started: 2026-05-28，将 multimodal.ts 从调 upload-to-workspace 改为调 extract-pdf-text，useChat.ts 去掉路径引用改为直接嵌入文本

## Eliminated

## Evidence

- timestamp: 2026-05-28T00:01:00Z
  checked: deepagents subagents.py _validate_and_prepare_state() (line 531)
  found: Sub-agents receive ONLY `subagent_state["messages"] = [HumanMessage(content=description)]`. They do NOT inherit any parent message history. The description string is whatever the parent LLM passes as the task tool's description argument.
  implication: Sub-agents can ONLY access information that is explicitly included in the task description or that they can read from workspace files via read_file.

- timestamp: 2026-05-28T00:02:00Z
  checked: useChat.ts sendMessage() (lines 91-105)
  found: PDF text is now extracted client-side and embedded directly in the user's HumanMessage as `### File: filename\n\n{text}`. No file is saved to workspace. No upload-to-workspace call exists.
  implication: The original requirement document text lives only in the parent agent's first HumanMessage. Sub-agents cannot see this message.

- timestamp: 2026-05-28T00:03:00Z
  checked: agent.py SYSTEM_PROMPT task description template (lines 177-186)
  found: Template instructs: `原始需求文件：[列出该模块对应的 workspace/uploads/ 下的文件路径]`. But workspace/uploads/ files no longer exist because multimodal.ts no longer saves them.
  implication: The template is stale -- it references a mechanism (file saved to workspace/uploads/) that no longer works. Sub-agents following this template will try to read non-existent files.

- timestamp: 2026-05-28T00:04:00Z
  checked: agent.py SYSTEM_PROMPT "上传文件说明" section (lines 379-383)
  found: System prompt correctly states: "用户上传的 PDF/Markdown 文件的文本内容已直接嵌入在用户消息中（以 ### File: 标记）。无需再使用 read_file 读取上传文件，直接分析消息中的文本即可。" This is correct for the MAIN agent but creates a contradiction for sub-agents.
  implication: Main agent knows PDF text is in messages, but sub-agents never see messages. The system prompt does not address how sub-agents should access original requirement text.

- timestamp: 2026-05-28T00:05:00Z
  checked: agent.py Phase output save rules (lines 160-170)
  found: Phase 1 saves to /workspace/phase1_requirement_analysis.md, Phase 2 saves to /workspace/phase2_test_strategy.md. These ARE saved via write_file and sub-agents CAN read them via read_file.
  implication: Sub-agents already have reliable access to Phase 1 and Phase 2 analysis. The only missing piece is the original raw requirement document text.

- timestamp: 2026-05-28T00:06:00Z
  checked: Sub-agent state inheritance in subagents.py _EXCLUDED_STATE_KEYS (lines 233-257)
  found: "messages" is in _EXCLUDED_STATE_KEYS. Sub-agent state is built as `{k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}` then `subagent_state["messages"] = [HumanMessage(content=description)]`. Only the "files" state key (from FilesystemBackend) and other non-excluded keys pass through.
  implication: Confirmed: sub-agents get a fresh message list with only the task description. They inherit the filesystem backend state (so workspace files are readable) but zero message history.

## Resolution

root_cause: Two-part root cause: (1) The system prompt's task description template (line 183) still references `workspace/uploads/` paths which no longer exist after the PDF extraction change. (2) More fundamentally, the original requirement text (now embedded in the parent's HumanMessage) is completely inaccessible to sub-agents because deepagents creates sub-agents with only a single HumanMessage containing the task description -- no parent message history is inherited.

fix: Three changes to agent.py SYSTEM_PROMPT: (1) Added `/workspace/phase0_original_requirements.md` to the Phase output save rules table, instructing the main agent to save original requirement text to a workspace file during Phase 1. (2) Added a "Phase 0 原始需求保存（强制）" paragraph explaining WHY this is necessary (sub-agents can't see parent messages). (3) Updated the task description template to replace the stale `workspace/uploads/` reference with `read_file("/workspace/phase0_original_requirements.md")`. (4) Updated the "上传文件说明" section to remind the main agent to save original text for sub-agents.

verification: System prompt review confirms all references to workspace/uploads/ are removed. New information flow: PDF text in parent HumanMessage -> main agent saves to phase0 file during Phase 1 -> sub-agent reads phase0 file via read_file in task description template.
files_changed: [src/app/agents/testcase/agent.py]
