# Resources（测评课）

> 教材优先级：**本仓库的文件** > 上游官方文档 > 二手文章。
> 这套测评模块是为本平台写的，任何外部教程的字段名、分数名都可能对不上。

## 一手材料（仓库内，权威）

| 材料 | 路径 | 用途 |
| --- | --- | --- |
| 流程与设计说明 | `EVAL.md`（含流程图、Langfuse 接线的坑、已知限制） | 每节课的第一读物 |
| 执行主循环 | `src/app/eval/runner.py` | 「一条用例怎么跑、分数怎么挂回 trace」 |
| 打分器实现 | `src/app/eval/scorers.py` | 每个分数名的**真实算法**（含注释里的设计理由） |
| 门禁语法 | `src/app/eval/gate.py` | `avg/min/max/all` 的语义与 fail-closed 行为 |
| 事件流 → trace | `src/app/eval/tracing.py` | 确定性 traceId、工具 span、generation |
| Langfuse 客户端 | `src/app/eval/langfuse_client.py` | 上报了哪些东西（ingestion / scores / datasets） |
| 实时进度 | `src/app/eval/live.py` + `src/app/api/v2/eval.py` | 执行中的活动流与心跳 |
| 评测集样例 | `datasets/smoke-testcase.yaml`（纯文本，1 分钟）<br>`datasets/smoke-webui.yaml`（Web-UI 智能体）<br>`datasets/douban-webui.yaml`（6 条真业务集） | 从最简单的抄起 |
| 平台内说明 | 页面 `/eval` 顶部 + 「命令行等价用法」卡片 | 界面上就能找到 CLI 对应命令 |

## 上游文档（Langfuse 官方，用于理解"分数/数据集/实验"的通用概念）

| 主题 | 链接 |
| --- | --- |
| 评测总览 | https://langfuse.com/docs/evaluation/overview |
| Datasets（数据集与条目） | https://langfuse.com/docs/evaluation/experiments/datasets |
| Scores（分数与类型） | https://langfuse.com/docs/evaluation/scores/overview |
| Tracing 基础 | https://langfuse.com/docs/tracing |

注意：本机是自建 **4.36.1-zh**（汉化分支）。官方文档是 v4 主线，概念一致；但界面上
文字是中文，URL 路由形如 `/project/<projectId>/traces/<traceId>`（少了项目段就是 404）。

## 社区（拿到"智慧"的地方）

- Langfuse 官方 GitHub Discussions：https://github.com/langfuse/langfuse/discussions ——
  "怎么设计评测集"、"LLM-as-judge 怎么防偏差"这类问题在这里能拿到真实工程经验。
- Playwright 社区（测 Web-UI 智能体时）：https://github.com/microsoft/playwright/discussions
