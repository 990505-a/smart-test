---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/app/agents/testcase/agent.py
autonomous: true
requirements: [BUG-1, BUG-2]
must_haves:
  truths:
    - "Every ensure_project call is immediately followed by save_test_cases_batch in the same instruction block"
    - "Total project save reads actual test_cases_*.md files and uses their real step content"
    - "No placeholder text like 参见子项目 allowed in steps — prompt explicitly bans it"
  artifacts:
    - path: "src/app/agents/testcase/agent.py"
      provides: "Updated SYSTEM_PROMPT Phase 5 with atomic save pairs and anti-lazy-merge instructions"
      contains: "save_test_cases_batch"
  key_links:
    - from: "SYSTEM_PROMPT Phase 5"
      to: "ensure_project + save_test_cases_batch"
      via: "atomic paired instructions"
      pattern: "ensure_project.*save_test_cases_batch"
    - from: "SYSTEM_PROMPT Phase 5"
      to: "read_file test_cases_*.md"
      via: "explicit read-parse-save workflow for total project"
      pattern: "read_file.*test_cases"
---

<objective>
Fix two TestCase Agent bugs by modifying the SYSTEM_PROMPT in agent.py.

**Bug 1 — Empty projects:** The Phase 5 prompt tells the LLM to "call ensure_project then save_test_cases_batch for each module" as separate steps. The LLM sometimes calls `ensure_project` but skips `save_test_cases_batch` for certain modules (token limit, context loss). No validation enforces the pair.

**Bug 2 — Lazy merge:** The Phase 5 prompt tells the LLM to merge all sub-module cases into the total project, but provides no instructions to actually read the sub-module files. The LLM takes a shortcut: creates cases with titles only, fills steps with placeholder text like "参见子项目中的详细步骤".

Purpose: Ensure every project in the database has real test cases with actual step content.
Output: Modified SYSTEM_PROMPT with atomic save instructions and anti-lazy-merge guardrails.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/app/agents/testcase/agent.py (SYSTEM_PROMPT — focus on Phase 5 section, lines ~303-383)
@src/app/agents/testcase/tools/db_tools.py (ensure_project and save_test_cases_batch tool definitions)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix Phase 5 prompt — atomic ensure_project + save_test_cases_batch and anti-lazy-merge</name>
  <files>src/app/agents/testcase/agent.py</files>
  <action>
In `SYSTEM_PROMPT`, locate the section starting at `## 保存流程` (around line 319) and the surrounding Phase 5 auto-save content. Apply these two changes:

**Change A — Atomic save pairs (fixes Bug 1):**

Replace the current `### 保存流程` block which says:
```
1. 遍历每个子模块，调用 `ensure_project("{项目名}-{模块名}-{时间}")` + `save_test_cases_batch`
2. 最后调用 `ensure_project("{项目名}-总-{时间}")`，将所有子模块用例合并保存到这个总项目
```

With an explicit atomic workflow that binds `ensure_project` and `save_test_cases_batch` into mandatory paired calls:

```
### 保存流程（强制原子操作）

**核心规则：`ensure_project` 和 `save_test_cases_batch` 必须成对调用。禁止只调用 `ensure_project` 不调用 `save_test_cases_batch`。**

#### 步骤 1：逐模块保存（子模块项目）

对 Phase 1 识别出的每个子模块，**按以下固定顺序执行**（不可跳过任何一步）：

```
对每个模块：
  1. result = ensure_project("{项目名}-{模块名}-{时间}")
  2. 立即将该模块的测试用例传入 save_test_cases_batch(project_id=result.project_id, test_cases=[...全部用例])
  3. 确认 save_test_cases_batch 返回 success=true，记录 saved_count
  4. 如果返回 success=false，必须重试，不可跳过
```

**禁止行为：**
- 禁止连续调用多个 ensure_project 后再统一 save（会导致遗漏）
- 禁止只调用 ensure_project 就进入下一个模块
- 禁止因为用例数量多就跳过某个模块的保存

#### 步骤 2：汇总保存（总项目）

所有子模块保存完成后，创建总项目并合并所有用例：
```
  1. total_result = ensure_project("{项目名}-总-{时间}")
  2. 对每个子模块，用 read_file 读取该模块的 test_cases_{模块名}.md 文件
  3. 解析文件中的每条用例，提取标题、步骤、预期结果等结构化数据
  4. 将所有子模块的完整用例合并为一个列表
  5. 调用 save_test_cases_batch(project_id=total_result.project_id, test_cases=[...全部合并用例])
```

**步骤 2 的关键要求：**
- 必须用 `read_file` 逐个读取子模块文件获取实际内容
- 步骤（steps）必须使用文件中的真实操作步骤和预期结果
- **绝对禁止**在 steps 中使用以下占位文本：
  - "参见子项目中的详细步骤"
  - "详见子模块用例"
  - "同子项目用例"
  - 任何暗示"去看别的文件"的文本
- 如果子模块文件不存在或为空，跳过该模块并在最终回复中说明

#### 步骤 3：输出保存结果

对每个项目（包括总项目），输出保存结果格式（见下方 [SAVE_RESULT] 格式）。
```

**Change B — Add quality verification after save (reinforces both bugs):**

After the `## 数据库保存规范（重要）` block (around line 343), add a verification checkpoint:

```
## 保存完成自检（强制）

保存流程结束后，必须执行以下自检：

1. **项目数验证**：子模块数 + 1个总项目 = 创建的项目总数。如果项目数不匹配，说明有遗漏。
2. **用例数验证**：总项目的用例数应等于所有子模块用例数之和。如果不等，说明合并不完整。
3. **步骤内容验证**：抽查总项目中的前3条用例，确认 steps 不包含任何占位文本（"参见"、"详见"、"同上"等）。如发现占位文本，必须重新执行步骤2的汇总保存。

自检结果随保存结果一起输出。
```

The exact line numbers may shift due to the changes — use the section headers (`## 保存流程`, `## 保存结果格式`, `## 数据库保存规范`) as anchors when editing.
  </action>
  <verify>
    <automated>cd D:/test_agent/smart-test-platform && python -c "from src.app.agents.testcase.agent import SYSTEM_PROMPT; assert '禁止只调用' in SYSTEM_PROMPT, 'Bug 1 fix missing: atomic pair enforcement'; assert 'read_file' in SYSTEM_PROMPT.split('步骤 2')[1].split('步骤 3')[0], 'Bug 2 fix missing: read_file instruction in total project'; assert '参见子项目' in SYSTEM_PROMPT.split('绝对禁止')[1].split('步骤 3')[0], 'Bug 2 fix missing: anti-placeholder text'; assert '保存完成自检' in SYSTEM_PROMPT, 'Verification checkpoint missing'; print('All checks passed')"</automated>
  </verify>
  <done>
    - SYSTEM_PROMPT Phase 5 enforces atomic ensure_project + save_test_cases_batch pairs
    - SYSTEM_PROMPT Phase 5 explicitly instructs LLM to read_file each sub-module's test_cases_*.md
    - SYSTEM_PROMPT Phase 5 bans placeholder text in steps
    - SYSTEM_PROMPT Phase 5 includes post-save self-verification checkpoint
    - Agent module still imports and initializes correctly
  </done>
</task>

</tasks>

<verification>
1. Python import check: `python -c "from src.app.agents.testcase.agent import agent"` succeeds
2. SYSTEM_PROMPT contains all four fix elements: atomic pairs, read_file instruction, anti-placeholder ban, self-check
3. No syntax errors in the Python file
</verification>

<success_criteria>
- SYSTEM_PROMPT modified with atomic save workflow for sub-modules (Bug 1 fix)
- SYSTEM_PROMPT modified with read-parse-save workflow for total project merge (Bug 2 fix)
- Placeholder text explicitly banned in steps
- Post-save self-verification checkpoint added
- Agent module imports without error
</success_criteria>

<output>
After completion, create `.planning/quick/260529-shr-fix-agent-empty-projects-and-lazy-merge/260529-shr-SUMMARY.md`
</output>
