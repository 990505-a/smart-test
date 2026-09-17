# Mission: 把「智能体测评」跑成一条自己复现得出的闭环

## Why

smart-test 平台里的测评模块（`/eval`）已经能跑：评测集 → 驱动智能体 → 打分 → 上报
Langfuse → 门禁判定。但你现在的用法是「点一下、看个数字」——数字从哪来、为什么这条
用例没过、这次改动到底能不能上线，都还答不上来。

这一课的目标是把这条链路变成**你自己的工具**：能自己设计评测用例，看懂每个分数的
来源，在 Langfuse 里回放某次运行，最后用一条门禁表达式替你对「能不能发」下结论。

这与 `langfuse-course`（用 Langfuse 给测评平台装上"眼睛"）是同一条线的后半段：
那边解决**看得见**，这边解决**敢不敢发**。

## Success looks like

- 能独立写出评测集 YAML，并说清每条用例的三块（`input` / `expected` / `judge`）为什么这么写。
- 能跑完一个批次，逐个解释 `task_output_match`、`tool_sequence`、`webui_case_pass_rate`、
  `llm_judge` 这些分数分别是谁算的、怎么算的。
- 能在 Langfuse 里按 traceId 找到某条用例的完整调用链，指出哪一步慢、哪一步失败。
- 能写出门禁表达式，并解释「批次 passed」与「分数达标」为什么是两件事。
- 能在换提示词 / 改模型 / 加用例之后，用同一套评测集与门禁做出可比较的回归结论。

## Constraints

- **环境随时可以回到空场**：`bash tools/reset-data.sh`（备份后清空平台业务数据、
  运行时产物与 Langfuse 内容；账号、设置、Langfuse 项目与密钥保留）。每节课从一个
  已知状态开始，结论才可复现。
- **讲练结合**：每节课都必须落到一次真实运行上（批次、分数、trace、门禁至少各见一次）。
- **结论要落到文件与符号**：`EVAL.md`、`src/app/eval/*.py`、`datasets/*.yaml`、页面 `/eval`。

## Out of scope（暂不）

- 不深入自建 Langfuse 栈的部署与升级（`langfuse-course` 的主题）。
- 暂不做多引擎横向对比（ragas / DeepEval / promptfoo）与并发压测。
- 暂不碰 Unity / 接口自动化的测评扩展，先把 Web-UI 与纯文本这条主线走通。
