# Pi 智能体学习资源

## Knowledge

- [Pi monorepo README](file:///D:/pi/README.md)
  项目总览：`pi-ai` 是统一多供应商 LLM API，`pi-agent-core` 是带工具调用和状态管理的运行时，`pi-coding-agent` 是交互式编码代理。适合先建立全局地图。
- [Pi agent-core README](file:///D:/pi/packages/agent/README.md)
  最小 SDK 示例、AgentMessage 与 LLM Message 的边界、事件流和工具调用事件序列。适合学习核心闭环。
- [Pi ai README](file:///D:/pi/packages/ai/README.md)
  `Context`、工具 schema、`streamSimple`、provider/model 抽象。适合学习模型调用边界。
- [Agent loop source](file:///D:/pi/packages/agent/src/agent-loop.ts)
  `runLoop`、`streamAssistantResponse` 和工具执行逻辑的权威实现。适合逐行跟踪 `model → tool → model`。
- [Agent state source](file:///D:/pi/packages/agent/src/agent.ts)
  `Agent` 类、消息状态、队列、取消和事件订阅。
- [Coding-agent SDK](file:///D:/pi/packages/coding-agent/src/core/sdk.ts)
  说明完整编码代理如何在 core agent 上组装默认模型、工具、resource loader 和 session manager。
- [Coding-agent README: programmatic usage](file:///D:/pi/packages/coding-agent/README.md)
  展示完整 Pi SDK 的 `createAgentSession()` 用法，以及 Pi 有意不内置的功能边界。
- [OpenAI Function Calling guide](https://platform.openai.com/docs/guides/function-calling)
  供应商无关地解释模型如何请求工具、应用执行工具并回传结果。用于和 Pi 的 `ToolCall` / `toolResult` 对照。
- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview)
  解释工具 schema、工具调用和工具结果消息。用于理解 provider 适配层。

## Wisdom (Communities)

- [Pi Discord](https://discord.com/invite/3cU7Bz4UPx)
  Pi 项目交流社区；遇到扩展、provider 或工作流问题时查找真实实践。

## Gaps

- 当前课程暂未深入各 provider 的重试、缓存、OAuth 和 WebSocket 差异；先掌握统一抽象，再按需要补充。
