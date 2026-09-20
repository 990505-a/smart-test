"""Knowledge-base Agent package（知识库能力）.

把 LightRAG 暴露成对话页可用的能力：检索、入库、查文档列表。与
``mcp_servers/rag_server.py``（给 dsh 这类外部宿主）共用同一套 ``lightrag_service``
方法，区别只在"以什么形式暴露"。
"""
