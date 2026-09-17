"""API router registration.

Aggregates all v2 API routers under /api/v2 prefix.
"""

from fastapi import APIRouter

from src.app.api.v2 import (
    api_auto,
    attachments,
    auth,
    case_docs,
    codebase,
    configurations,
    eval as eval_api,
    extract_pdf,
    feishu,
    mcp,
    memories,
    messages,
    projects,
    rag,
    settings,
    skills,
    unity_auto,
    web_ui_auto,
    workspaces,
)

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(projects.router, tags=["Projects"])
api_router.include_router(case_docs.router, tags=["Case Docs (用例 MD 文档)"])
api_router.include_router(attachments.router, tags=["Attachments"])
api_router.include_router(workspaces.router, tags=["Workspaces"])
api_router.include_router(configurations.router, tags=["Configurations"])
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
