# Phase 1: Core Infrastructure + Frontend Shell - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-11
**Phase:** 1-Core Infrastructure + Frontend Shell
**Areas discussed:** 服务端架构, 数据流与集成, 前端界面设计, 项目工程结构

---

## 服务端架构

| Option | Description | Selected |
|--------|-------------|----------|
| 单 graph.json 多路由 | 所有 Agent 注册在一个 graph.json 中，前端通过 Agent 名称路由 | ✓ |
| 多服务独立部署 | 每个 Agent 单独的 graph.json 和服务端口 | |

**User's choice:** 单 graph.json 多路由（推荐）
**Notes:** 与课堂代码方式一致，简化部署和管理

### 通信方式

| Option | Description | Selected |
|--------|-------------|----------|
| SSE 流式 | @langchain/langgraph-sdk 的 SSE 流式传输 | ✓ |
| WebSocket | 双向实时通信 | |

**User's choice:** SSE 流式（推荐）
**Notes:** 课堂代码使用的标准方式

---

## 数据流与集成

### 文件上传

| Option | Description | Selected |
|--------|-------------|----------|
| base64 嵌入消息 | 前端转 base64 放入 additional_kwargs.attachments | ✓ |
| 上传到磁盘 | 前端上传文件到服务器磁盘，后端通过文件路径读取 | |

**User's choice:** base64 嵌入消息（推荐）
**Notes:** 课堂代码验证的成熟模式

### MCP 集成

| Option | Description | Selected |
|--------|-------------|----------|
| MCP 标准协议 | MultiServerMCPClient 连接 Docling/Graphify/Playwright | ✓ |
| 直接 API 调用 | 直接调用各工具的 Python API | |

**User's choice:** MCP 标准协议（推荐）
**Notes:** 标准化工具接口，支持热插拔

---

## 前端界面设计

### Agent 切换

| Option | Description | Selected |
|--------|-------------|----------|
| Tab 标签切换 | 顶部 Tab 栏：用例生成 / Web自动化 / API自动化 | ✓ |
| 下拉菜单选择 | 侧边栏下拉菜单选择当前 Agent | |
| 对话级选择 | 每次创建新对话时选择 Agent 类型 | |

**User's choice:** Tab 标签切换（推荐）

### 界面布局

| Option | Description | Selected |
|--------|-------------|----------|
| 左右分栏 | 左侧线程列表 + 右侧聊天区域，可调整大小 | ✓ |
| 主区域 + 抽屉 | 主聊天区域 + 抽屉式侧边栏 | |

**User's choice:** 左右分栏（推荐）

### 主题风格

| Option | Description | Selected |
|--------|-------------|----------|
| 亮色为主 + 暗色切换 | 默认亮色，支持暗色，Shadcn/ui + Tailwind CSS | ✓ |
| 暗色为主 | 科技感暗色主题 | |

**User's choice:** 亮色为主 + 暗色切换（推荐）

---

## 项目工程结构

### 代码组织

| Option | Description | Selected |
|--------|-------------|----------|
| 前后端同仓库 | src/ 后端 + webui/ 前端在同一仓库 | ✓ |
| 前后端分离仓库 | 后端和前端分开两个仓库 | |

**User's choice:** 前后端同仓库（推荐）

### 启动方式

| Option | Description | Selected |
|--------|-------------|----------|
| 分别启动 | 后端 start_server.py + 前端 npm run dev | ✓ |
| 一键启动 | 一个命令同时启动前后端 | |

**User's choice:** 分别启动（推荐）

---

## Claude's Discretion

- 具体目录结构细节（如 src/ 下子目录命名）
- Shadcn/ui 组件选择
- 线程管理 UI 具体实现方式
- 前端状态管理库选择

## Deferred Ideas

None — discussion stayed within phase scope
