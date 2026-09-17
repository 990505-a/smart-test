"""Agent 记忆工具（harness 风格 Markdown 记忆）。

记忆 = 工作区 ``memory/`` 目录下的一组 Markdown 模块（AGENTS.md / MEMORY.md /
USER.md / failures.md / PROJECT.md / DECISIONS.md，外加用户自建），文件是唯一事实源。
工具面刻意保持小：

* ``save_memory``         追加一条长期记忆（默认写 MEMORY.md）
* ``record_failure``      追加一条失败教训（failures.md）
* ``search_memories``     关键词检索所有启用模块
* ``read_memory_module``  读某个模块全文
* ``list_memory_modules`` 列出模块与启用状态
* ``update_memory_module``整体重写某个模块（AGENTS.md 除外——规则由用户维护）

旧版 ``save_memory(key, content, category)`` 走 EverOS；现在没有外部服务，写的就是
工作区里的文件，用户在平台「Agent 记忆」页能立刻看到并修改。
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from src.app.core.workspace import get_space_id
from src.app.services import memory_service

logger = logging.getLogger(__name__)


def _space() -> str:
    return get_space_id()


@tool
def save_memory(content: str, module: str = "memory", category: str = "") -> dict:
    """把一条值得跨会话记住的结论写进长期记忆（默认 MEMORY.md）。

    Args:
        content: 要记住的内容。写"结论 + 依据"，不要写过程流水账。
        module: 目标模块 id 或文件名（memory / user / project / decisions / MEMORY.md …）。
        category: 可选分类标签，例如「领域知识」「项目约定」「用户偏好」。

    Returns:
        dict: {success, module, file, chars} 或 {success: False, error}
    """
    try:
        saved = memory_service.append_entry(
            module or "memory", content, category=category, space_id=_space(), source="agent")
        return {"success": True, "module": saved.id, "file": saved.file, "chars": saved.chars}
    except Exception as exc:  # noqa: BLE001 — 工具错误要能被 agent 读到并自我修正
        logger.warning("save_memory failed: %s", exc)
        return {"success": False, "error": str(exc)}


@tool
def record_failure(summary: str, detail: str = "") -> dict:
    """把一次失败/返工记进 failures.md，避免同样的错误再犯。

    Args:
        summary: 一句话说清"做了什么、为什么不行"。
        detail: 可选补充：正确做法、涉及的文件或工具。

    Returns:
        dict: {success, module, file} 或 {success: False, error}
    """
    body = summary.strip()
    if detail.strip():
        body += f"\n\n  **下次怎么做**：{detail.strip()}"
    try:
        saved = memory_service.append_entry("failures", body, space_id=_space(), source="agent")
        return {"success": True, "module": saved.id, "file": saved.file}
    except Exception as exc:  # noqa: BLE001
        logger.warning("record_failure failed: %s", exc)
        return {"success": False, "error": str(exc)}


@tool
def search_memories(query: str, limit: int = 8) -> dict:
    """在启用中的记忆模块里按关键词检索（返回文件、行号与原文片段）。

    Args:
        query: 关键词，空格分隔多个词即可（中文整句也能匹配子串）。
        limit: 最多返回多少条命中。

    Returns:
        dict: {success, count, memories: [{file, label, line, text}]}
    """
    try:
        hits = memory_service.search(query, limit=max(1, min(int(limit or 8), 30)), space_id=_space())
        return {
            "success": True,
            "count": len(hits),
            "memories": [
                {"file": h.file, "label": h.label, "line": h.line, "text": h.text} for h in hits
            ],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("search_memories failed: %s", exc)
        return {"success": False, "error": str(exc)}


@tool
def read_memory_module(module: str) -> dict:
    """读某个记忆模块的全文（注入到提示词里的可能是被裁断的版本）。

    Args:
        module: 模块 id 或文件名，如 agents / MEMORY.md / failures.md。
    """
    try:
        content = memory_service.read_module(module, space_id=_space())
        return {"success": True, "module": module, "content": content, "chars": len(content)}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


@tool
def list_memory_modules() -> dict:
    """列出所有记忆模块（含未启用的）与各自字符数。"""
    try:
        modules = memory_service.list_modules(space_id=_space())
        return {
            "success": True,
            "modules": [
                {"id": m.id, "file": m.file, "label": m.label, "enabled": m.enabled,
                 "chars": m.chars, "builtin": m.builtin, "description": m.description}
                for m in modules
            ],
        }
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


@tool
def update_memory_module(module: str, content: str) -> dict:
    """整体重写某个记忆模块（用于整理去重）。AGENTS.md 只能由用户修改。

    Args:
        module: 模块 id 或文件名。
        content: 新的完整正文（覆盖写入，请先 read_memory_module 拿到旧内容）。
    """
    try:
        target = memory_service.get_module(module, space_id=_space())
        if target is None:
            return {"success": False, "error": f"记忆模块不存在: {module}"}
        if target.id == "agents":
            return {"success": False,
                    "error": "AGENTS.md 是用户维护的工作区规则，智能体不能整体覆盖；"
                             "需要新增规则请让用户在平台「Agent 记忆」页修改。"}
        saved = memory_service.write_module(target.id, content, space_id=_space())
        return {"success": True, "module": saved.id, "file": saved.file, "chars": saved.chars}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


MEMORY_TOOLS = [
    save_memory,
    record_failure,
    search_memories,
    read_memory_module,
    list_memory_modules,
    update_memory_module,
]
