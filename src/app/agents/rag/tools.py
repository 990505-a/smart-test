"""RAG / 知识库 agent 工具（知识库能力）。

对 ``lightrag_service`` 的薄封装 —— 与平台「知识库」页、以及给外部宿主（dsh）用的
``mcp_servers/rag_server.py`` 调的是**同一个 service 层**，业务逻辑不在这里重复，
这里只负责把能力声明成模型能调的工具。

**多知识库**：每个库是一个独立的 LightRAG 实例（不同项目的数据互不可见），
所以检索/入库类工具都有 ``kb`` 参数。不确定有哪些库时先 ``rag_list_kbs``，
不要凭空猜 key——猜错会得到一句"没有这个知识库"，而不是答案。

LightRAG 不在线时 service 一律返回 ``{"success": False, "error": …}`` 而不抛异常，
所以这些工具不需要 try/except：把结果如实转述给用户即可，不要反复重试。
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.app.services import lightrag_service


@tool
async def rag_list_kbs() -> dict:
    """列出全部知识库（key / 名称 / 端口 / 是否在线 / 已入库文档数）。

    多项目环境里第一步就该调它：拿到 key 之后再决定检索/入库进哪个库。
    """
    return {"success": True, "kbs": await lightrag_service.kbs_status()}


@tool
async def rag_health(kb: str = "") -> dict:
    """检查知识库（LightRAG）是否在线。

    检索或入库之前先调用一次；不在线时如实报告并建议用户在「知识库」页启动，
    不要反复重试。

    Args:
        kb: 知识库 key（留空 = 默认库）。多个库时用它指定要看哪个。
    """
    return await lightrag_service.health(kb)


@tool
async def rag_query(question: str, mode: str = "hybrid", top_k: int = 6,
                    kb: str = "") -> dict:
    """在知识库里检索并回答问题（图谱 + 向量的混合检索）。

    适用于"这个项目的需求文档里怎么规定的""历史用例里有没有类似场景"这类问题：
    答案来自已经入库的资料，而不是你的记忆。

    Args:
        question: 自然语言问题。
        mode: hybrid(推荐) / local(实体邻域) / global(主题全局) / naive(纯向量) /
            mix(图谱+向量) / bypass(不检索，直接问模型——只用来做对照)。
        top_k: 取多少条上下文，默认 6。
        kb: 知识库 key（留空 = 默认库）。**项目不同就换库**：不同项目的文档
            在不同的库里，问错库会拿到另一个项目的答案或空手而归。
    """
    return await lightrag_service.query(question=question, mode=mode, top_k=top_k,
                                       kb_key=kb)


@tool
async def rag_ingest_text(text: str, file_source: str = "", kb: str = "") -> dict:
    """把一段文本存进知识库（入库后即可被 ``rag_query`` 检索到）。

    适合用户直接把需求/约定贴给你、要求"记进知识库"的场景。
    file_source 是来源标注（文件名或 URL），便于之后在文档列表里认出来；
    直接把整段文本塞进去时也要填一个能认出来的名字。

    Args:
        kb: 知识库 key（留空 = 默认库）；写进哪个项目的库必须问清楚，写错库
            等于把资料放进了另一个项目。
    """
    return await lightrag_service.ingest_text(text=text, file_source=file_source or None,
                                              kb_key=kb)


@tool
async def rag_ingest_file(file_path: str, kb: str = "") -> dict:
    """把一个本地文件（txt/md/pdf/docx…）上传到知识库并自动解析入库。

    file_path 必须是**绝对路径**（用户上传的文件、工作区里的文档都按绝对路径给）。
    入库是异步解析：返回成功只代表已接收，解析完才检索得到。

    Args:
        kb: 知识库 key（留空 = 默认库）。
    """
    return await lightrag_service.ingest_file(file_path, kb_key=kb)


@tool
async def rag_list_documents(page: int = 1, page_size: int = 20, kb: str = "",
                            status: str = "") -> dict:
    """列出已入库的文档及其解析状态（pending/processing/processed/failed）。

    入库之后用它确认解析结果；用户问"知识库里有什么"时也用它。

    Args:
        kb: 知识库 key（留空 = 默认库）。
        status: 只看某个状态（failed 可用来找解析失败的文档）。
    """
    return await lightrag_service.list_documents(page=page, page_size=page_size,
                                                 status=status, kb_key=kb)
