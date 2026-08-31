"""Feishu export tools for the testcase agent (飞书思维导图保存).

After test cases are generated and persisted as a Markdown case document,
the agent calls ``export_project_mindmap`` with the project name; the tool
loads the MD file (sole source of truth — annotations stripped on parse)
and mirrors it into a Feishu mindnote via lark-cli.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.app.services import feishu_service


@tool
async def export_project_mindmap(
    project_name: str,
    root_text: str | None = None,
    mindnote_id: str | None = None,
) -> dict:
    """把已保存的用例 MD 文档导出为飞书思维导图（lark-cli）。

    数据直接读平台的用例 MD 文件（分组树 + 用例 + 嵌套步骤），人工标注
    （✅❌ 与批注）自动剥离，导出干净版本；与会话上下文无关。

    平台配置了飞书目录（FEISHU_FOLDER_TOKEN）时，每次调用会在该目录下
    自动新建一张思维导图（文档名 = root_text）；返回值中的 url 是新导图
    链接，必须把该链接展示给用户。显式传 mindnote_id 时改为向该导图
    追加节点。

    Args:
        project_name: 项目名（save_case_document 用的同一个名字）。
        root_text: 根节点/文档标题，默认用项目名；建议格式
                   "{项目名}_用例集_{日期}"。
        mindnote_id: 可选，向指定导图追加节点（覆盖目录模式）。

    Returns:
        成功时 {"success": True, "url": <导图链接>, "mindnote_id": ...,
        "case_count": N}——请把 url 告知用户；
        未配置或未安装 lark-cli 时 {"success": False, "skipped": True, ...}，
        此时只需告知用户未配置即可，不影响已保存的用例文档。
    """
    loaded = await feishu_service.load_doc_tree(project_name)
    if not loaded.get("success"):
        return {"success": False,
                "error": loaded.get("error") or "用例文档载入失败"}
    if not loaded.get("case_count"):
        return {"success": False, "error": "文档里没有用例，先保存用例再导出"}
    root = (root_text or "").strip() or loaded["root_text"]
    result = await feishu_service.save_tree_to_mindnote(
        root, loaded["tree"], mindnote_id=mindnote_id)
    if result.get("success"):
        result["case_count"] = loaded["case_count"]
    return result


@tool
async def check_feishu_status() -> dict:
    """检查飞书 lark-cli 是否可用及登录状态。"""
    return await feishu_service.auth_status()
