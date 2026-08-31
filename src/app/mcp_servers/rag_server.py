"""RAG MCP server (rag_mcp) — exposes LightRAG as MCP tools.

Run standalone::

    python -m src.app.mcp_servers.rag_server

Tools: rag_health, rag_query, rag_ingest_text, rag_ingest_file,
rag_list_documents.
"""

from __future__ import annotations

from fastmcp import FastMCP

from src.app.services import lightrag_service

mcp = FastMCP("rag-lightrag")


@mcp.tool
async def rag_health() -> dict:
    """检查 LightRAG 知识库服务是否可达。"""
    return await lightrag_service.health()


@mcp.tool
async def rag_query(
    question: str,
    mode: str = "hybrid",
    top_k: int = 6,
) -> dict:
    """在知识库中检索与问题相关的内容（需求文档 / 历史用例 / 项目知识）。

    mode: local=实体邻域, global=主题全局, hybrid=图谱混合, naive=纯向量, mix=图谱+向量。
    建议默认 hybrid；找具体规则/配置用 local，找方案/概览用 global。
    """
    return await lightrag_service.query(question, mode=mode, top_k=top_k)


@mcp.tool
async def rag_ingest_text(text: str, file_source: str | None = None) -> dict:
    """把一段文本写入知识库索引（需求文档、测试用例、经验沉淀等，Markdown 纯文本均可）。"""
    return await lightrag_service.ingest_text(text, file_source)


@mcp.tool
async def rag_ingest_file(file_path: str) -> dict:
    """把本地文件（txt/md/pdf/docx 等）上传到知识库并自动解析索引。"""
    return await lightrag_service.ingest_file(file_path)


@mcp.tool
async def rag_list_documents(page: int = 1, page_size: int = 50) -> dict:
    """列出知识库中已入库的文档（分页）。"""
    return await lightrag_service.list_documents(page, page_size)


if __name__ == "__main__":
    mcp.run()
