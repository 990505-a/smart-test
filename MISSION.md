# Mission: 用 Python 理解 Pi 智能体

## Why
从零读懂 `D:\pi` 这个 TypeScript 智能体项目，建立一套能迁移到 Python 项目中的心智模型，并最终能够自己写出一个带工具调用、上下文和持久化的最小智能体。

## Success looks like
- 能画出并解释 Pi 从用户输入到模型调用、工具执行、再到下一轮模型调用的主链。
- 能用 Python 写出等价的最小 `model → tool → model` agent loop。
- 能区分构建智能体的必需部分与 Pi 的流式 UI、会话树、扩展、上下文压缩等增强部分。
- 能在 Pi 源码中定位 `pi-ai`、`pi-agent-core`、`pi-coding-agent` 各自的职责。

## Constraints
- 用户熟悉 Python，但对 TypeScript 不熟悉；讲解优先使用 Python 类比，再解释 TypeScript 语法。
- 学习必须以 `D:\pi` 当前源码为主，结论注明文件和符号。
- 课程采用短课、源码阅读和小练习，不一次覆盖整个 monorepo。

## Out of scope
- 暂不深入所有 provider 的 HTTP 协议细节。
- 暂不把 TUI、发布流程、供应链脚本当作智能体核心来学习。
- 暂不假设 Pi 内置 sub-agent、plan mode 或权限弹窗；这些在当前项目哲学中是可选扩展。
