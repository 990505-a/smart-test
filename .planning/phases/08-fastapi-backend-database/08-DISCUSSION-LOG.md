# Phase 8: FastAPI Backend & Database - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-14
**Phase:** 08-fastapi-backend-database
**Areas discussed:** 数据库策略, ORM选择, 数据模型范围, 用户认证, Agent↔DB流程, 文件存储

---

## 数据库策略

| Option | Description | Selected |
|--------|-------------|----------|
| PostgreSQL + MongoDB（课堂方案） | 和课堂完全一致，双数据库部署 | |
| 仅 PostgreSQL + JSONB（推荐） | 部署简单，JSONB 提供灵活数据支持 | ✓ |
| SQLite → PostgreSQL（渐进式） | 先 SQLite 后迁移 | |

**User's choice:** 仅 PostgreSQL + JSONB
**Notes:** 用户问"仅 PostgreSQL + JSONB 会不会有功能缺失"。分析后确认 JSONB 完全覆盖我们的场景需求：结构化查询、灵活数据、嵌套文档都支持。Neo4j 已有图数据库，不需要 MongoDB。

## ORM 选择

| Option | Description | Selected |
|--------|-------------|----------|
| SQLAlchemy async（推荐） | 2.0 风格异步 ORM，和课堂一致，FastAPI 集成好 | ✓ |
| Tortoise ORM | 更 Pythonic 但生态较小 | |
| Claude 自行决定 | | |

**User's choice:** SQLAlchemy async

## 数据模型范围

| Option | Description | Selected |
|--------|-------------|----------|
| 完整课堂模型（9张表） | Users, Projects, Folders, TestCases, TestSteps, TestRuns, TestResults, APIEndpoints, TestScenarios | ✓ |
| 核心表先行（4张表） | Projects, TestCases, TestSteps, Folders 先跑通 | |
| Claude 自行决定 | | |

**User's choice:** 完整课堂模型（9张表）

## 用户认证

| Option | Description | Selected |
|--------|-------------|----------|
| 不需要认证（推荐） | 单一默认用户，专注业务逻辑 | ✓ |
| JWT 认证 | Users + JWT 登录流程 | |

**User's choice:** 不需要认证

## Agent→数据库流程

| Option | Description | Selected |
|--------|-------------|----------|
| Agent 工具直接写 DB（推荐） | 工具内 SQLAlchemy session 直接操作 | ✓ |
| Agent 工具调 FastAPI API | 解耦但增加网络开销 | |
| Claude 自行决定 | | |

**User's choice:** Agent 工具直接写 DB

## 文件存储

| Option | Description | Selected |
|--------|-------------|----------|
| 本地文件系统（推荐） | workspace/ 目录，零配置 | ✓ |
| MinIO 对象存储 | 课堂方案，需 Docker | |
| Claude 自行决定 | | |

**User's choice:** 本地文件系统

## Claude's Discretion

- FastAPI 代码在 src/app/ 下的具体目录结构
- 数据库迁移策略（Alembic vs 手动）
- 连接池配置
- CRUD 端点的错误处理模式
- Repository/Service 层分离深度
- Pydantic schema 设计细节

## Deferred Ideas

- MinIO 对象存储 — 可通过抽象存储接口在未来阶段添加
- 用户认证 (JWT) — 推迟到未来阶段
- Redis 缓存层 — 当前规模不需要
- Alembic 迁移 — 模式稳定后再添加
- API 限流 — FastAPI 中间件，后续按需添加
