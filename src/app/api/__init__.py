"""API router registration.

Aggregates all v2 API routers under /api/v2 prefix.
"""

from fastapi import APIRouter

from src.app.api.v2 import (
    agents,
    api_auto,
    auth,
    case_docs,
    codebase,
    eval as eval_api,
    extract_pdf,
    feishu,
    integrations,
    mcp,
    memories,
    messages,
    rag,
    settings,
    skills,
    unity_auto,
    web_ui_auto,
)

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(case_docs.router, tags=["Case Docs (用例 MD 文档)"])
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(extract_pdf.router, tags=["PDF Extraction"])
api_router.include_router(memories.router, tags=["Memories"])

# --- Transformation modules (2026-08) ---
api_router.include_router(auth.router, tags=["Auth (用户模块)"])
api_router.include_router(settings.router, tags=["Settings (设置模块)"])
api_router.include_router(feishu.router, tags=["Feishu (飞书模块)"])
api_router.include_router(skills.router, tags=["Skills (Skill 蒸馏模块)"])
api_router.include_router(api_auto.router, tags=["API Automation (接口自动化模块)"])
api_router.include_router(unity_auto.router, tags=["Unity Automation (Unity 自动化模块)"])
api_router.include_router(web_ui_auto.router, tags=["Web-UI Automation (Web-UI 自动化模块)"])
api_router.include_router(eval_api.router, tags=["Eval (测评模块)"])
api_router.include_router(mcp.router, tags=["MCP (MCP 模块)"])
api_router.include_router(rag.router, tags=["RAG (知识库本体)"])
api_router.include_router(codebase.router, tags=["Codebase (代码图谱本体)"])
api_router.include_router(agents.router, tags=["Agents (智能体装配)"])
api_router.include_router(integrations.router, tags=["Integrations (外部依赖就绪)"])
