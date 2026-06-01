---
status: awaiting_human_verify
trigger: "LangGraph 线程状态反复膨胀导致 /state 返回 500。之前做了 upload-to-workspace 改造（PDF文本不再嵌入消息），但线程仍然膨胀到 488KB，84 次工具调用后 /state 返回 500。需要彻底分析根因并找到不影响用例质量的根治方案。"
created: 2026-05-28T09:00:00Z
updated: 2026-05-28T09:30:00Z
---

## Current Focus

hypothesis: CONFIRMED - Thread bloat has 4 compounding root causes: (1) ChatDeepSeek has NO model profile, so SummarizationMiddleware trigger is 170k tokens (too high for 128k context), (2) custom tools bypass eviction entirely, (3) read_file excluded from eviction accumulates PDF text, (4) agent system prompt tells LLM to read files without limit. Fix requires: explicit SummarizationMiddleware config + custom tool result size limits + prompt change for paginated reads.
test: Implement fix in agent.py with explicit summarization config + custom tool wrapper
expecting: Thread stays under 128k tokens, summarization triggers properly, /state returns 200
next_action: Implement fix

## Symptoms

expected: 智能体完成 Phase 1/2 需求分析后，线程状态保持在合理范围内（<200KB），/state 正常返回 200
actual: 即使消息中不再嵌入 PDF 全文（改为文件路径引用），线程状态仍膨胀到 488KB（2 human + 42 ai + 84 tool messages），/state 返回 500
errors: openai.BadRequestError: 3853778 tokens requested (sub-agent); LangGraph /state 500 Internal Server Error
reproduction: 上传 4 个 PDF -> 选仓库 -> 生成测试用例 -> Phase 1/2 完成后线程已经很大 -> Phase 3 子智能体 token 爆炸
started: 一直是潜在问题，upload-to-workspace 改造后仍然发生

## Eliminated

## Evidence

- timestamp: 2026-05-28T09:00:00Z
  checked: FilesystemMiddleware TOOLS_EXCLUDED_FROM_EVICTION (filesystem.py line 523-530)
  found: read_file, edit_file, write_file, ls, glob, grep are all excluded from eviction. read_file returns up to 100 lines by default but agent prompt says "不设 limit，确保阅读完整内容"
  implication: read_file ToolMessages with full file content are never evicted. Each read of a PDF extracted text (up to 50,000 chars) stays in thread state permanently.

- timestamp: 2026-05-28T09:01:00Z
  checked: Custom tools registration in agent.py (line 449-456)
  found: 6 git tools + wiki-mcp tools registered via tools= parameter, NOT through FilesystemMiddleware. These include git_diff_content (returns up to 300 lines), grep_code_context (up to 50 results), read_code_file (up to 200 lines)
  implication: Custom tools bypass FilesystemMiddleware entirely - their ToolMessage results are NEVER checked for eviction because wrap_tool_call only intercepts FilesystemMiddleware's own tools

- timestamp: 2026-05-28T09:02:00Z
  checked: wrap_tool_call in filesystem.py (lines 2045-2085)
  found: wrap_tool_call checks `request.tool_call["name"] in TOOLS_EXCLUDED_FROM_EVICTION` and skips eviction for excluded tools. For non-excluded tools, it calls _intercept_large_tool_result. But this middleware only wraps its OWN tools (ls, read_file, write_file, edit_file, glob, grep, execute).
  implication: Custom tools (git_log, git_diff_stat, grep_code, read_code_file, git_diff_content, grep_code_context, export_test_cases, save_test_cases_batch, wiki-mcp tools) are handled by the base agent tool node, NOT by FilesystemMiddleware. Their results are never size-checked or evicted.

- timestamp: 2026-05-28T09:03:00Z
  checked: SummarizationMiddleware configuration via create_summarization_middleware in graph.py (line 699)
  found: create_summarization_middleware(model, backend) is called with the resolved model. compute_summarization_defaults checks model.profile for max_input_tokens. If deepseek model has no profile, defaults to trigger=("tokens", 170000), keep=("messages", 6).
  implication: Summarization SHOULD trigger at 170k tokens, but the model's context window may be smaller (deepseek-chat has 128k). Need to verify whether deepseek model exposes a profile with max_input_tokens.

- timestamp: 2026-05-28T09:04:00Z
  checked: LangGraph persistence file size (.langgraph_ops.pckl)
  found: 18MB persistence file. Thread state includes ALL messages including ToolMessages.
  implication: 18MB for a single thread is extremely large. Confirms that state is not being effectively compacted.

- timestamp: 2026-05-28T09:05:00Z
  checked: ChatDeepSeek model profile (runtime verification)
  found: ChatDeepSeek extends BaseChatOpenAI but has NO _resolve_model_profile override. model.profile returns None. This means compute_summarization_defaults falls into the "no profile" branch with trigger=("tokens", 170000).
  implication: CRITICAL - deepseek-chat has a 128k token context window, but summarization triggers at 170k tokens. This means summarization NEVER triggers before the context window overflows. The model will hit context overflow before summarization activates.

- timestamp: 2026-05-28T09:06:00Z
  checked: SummarizationMiddleware truncate_args_settings defaults
  found: truncate_args_settings trigger=("messages", 20), keep=("messages", 20). This means tool-call arg truncation starts at 20 messages but also KEEPS the last 20 messages untruncated. With 128 messages total, the first 108 messages would get args truncated. However, this only truncates write_file/edit_file args in AIMessage.tool_calls, NOT ToolMessage content.
  implication: Arg truncation is working but only addresses AIMessage tool_calls (write_file content), not the much larger ToolMessage results.

- timestamp: 2026-05-28T09:07:00Z
  checked: Subagent state inheritance (subagents.py _validate_and_prepare_state)
  found: Line 531-532: subagent_state copies ALL parent state keys EXCEPT messages/todos/structured_response/skills_metadata/skills_load_errors/memory_contents. Subagent starts with only messages=[HumanMessage(content=description)]. However, the _files_ state IS inherited (not excluded).
  implication: The sub-agent token explosion (3853778 tokens) is NOT from inherited state but from the sub-agent's OWN tool calls within its fresh context. The sub-agent reads the same large files and accumulates its own ToolMessages.

- timestamp: 2026-05-28T09:08:00Z
  checked: Agent system prompt read_file instructions (agent.py lines 372-397)
  found: Line 382: "完整阅读：读取文件时不要限制行数（不设 limit），确保阅读完整内容". This explicitly tells the agent to read files WITHOUT limits.
  implication: Agent reads full PDF extracted text (up to 50,000 chars) in a single read_file call. Since read_file is excluded from eviction, the full content stays in thread state as a ToolMessage.

- timestamp: 2026-05-28T09:09:00Z
  checked: FilesystemMiddleware _truncate in read_file tool (filesystem.py line 847-858)
  found: read_file DOES have its own truncation: if content exceeds token_limit chars (20000 tokens * 4 = 80000 chars), it truncates. But the truncated content is still stored as a ToolMessage in state and is excluded from eviction.
  implication: Each read_file call can produce up to 80KB of content that stays permanently in thread state. With 4 PDFs + requirement docs + code files, this easily accumulates to 200KB+ of ToolMessage content.

## Resolution

root_cause: Thread state bloat is caused by 4 compounding factors:

1. **SummarizationMiddleware misconfigured for deepseek**: ChatDeepSeek has NO model profile (model.profile is None), so compute_summarization_defaults falls back to trigger=("tokens", 170000). But deepseek-chat only has 128k context. Summarization NEVER triggers because the model hits context overflow at ~128k tokens, well before the 170k threshold. The middleware catches ContextOverflowError and retries with summarization, but by then the state is already bloated and the /state endpoint fails.

2. **Custom tools bypass eviction entirely**: The 6 git tools + 6 wiki-mcp tools + export_test_cases + save_test_cases_batch are registered via tools= parameter, not through FilesystemMiddleware. FilesystemMiddleware's wrap_tool_call only intercepts its OWN tools. Custom tool results (git_diff_content returns 300 lines, read_code_file returns 200 lines, wiki search/get_page can return large content) are never size-checked or evicted.

3. **read_file excluded from eviction but reads large files**: TOOLS_EXCLUDED_FROM_EVICTION includes read_file. Agent system prompt explicitly says "读取文件时不要限制行数". Each read_file of a PDF extracted text (up to 50,000 chars / 80KB after internal truncation at 80,000 chars) produces a ToolMessage that stays permanently in thread state.

4. **Sub-agent inherits same broken summarization config**: General-purpose sub-agent gets the same create_summarization_middleware(model, backend) with the same misconfigured 170k trigger. Sub-agent reads the same large files, accumulates ToolMessages, and with a 128k context window, hits the 3853778 token error when trying to send the bloated context to the model.

fix: Three-layer fix addressing all 4 root causes:

1. **Set model profile for deepseek** (agent.py): Added `llm.profile = {"max_input_tokens": 131072}` after model creation. This makes compute_summarization_defaults compute fraction-based triggers: trigger=("fraction", 0.85) = 111k tokens, keep=("fraction", 0.10) = 13k tokens. Summarization now triggers at 111k tokens (well within 128k context), preventing context overflow. The general-purpose sub-agent inherits the same model with profile, so it also gets correct summarization thresholds.

2. **Add ToolResultLimiterMiddleware** (new file tool_result_limiter.py + agent.py): Created a middleware that wraps ALL tool calls and truncates results from custom tools (git tools, wiki-mcp, export tools) exceeding 20,000 chars (~5,000 tokens). Filesystem tools are excluded since FilesystemMiddleware handles those. This prevents custom tool results from bloating thread state.

3. **Update system prompt** (agent.py): Changed read_file instructions from "不设 limit，确保阅读完整内容" to "分页读取大文件...建议先 read_file(file_path, limit=100)...避免单次读取超过 200 行". This reduces the size of individual read_file ToolMessages. Combined with the corrected summarization trigger, even if read_file results are large, summarization will compact them at 111k tokens.

verification: Python compilation passed. Runtime verification confirmed: model.profile set correctly, summarization trigger changed from ("tokens", 170000) to ("fraction", 0.85) = 111k tokens, ToolResultLimiterMiddleware created and added to middleware chain. Full agent module imports without errors.
files_changed: [src/app/agents/testcase/agent.py, src/app/middleware/tool_result_limiter.py]
