"""视觉门：主模型不支持图片时，把发给它的图片块换成占位说明。

为什么需要：Unity / Web-UI 自动化重度依赖截图——工具结果里带 base64 图片块，
下一轮模型调用就会把它们作为 ``image_url`` 发出去。主模型若不支持图像输入
（如 deepseek-v4-flash），网关直接 400 ``Model only supports text input``，
**整个 run 挂掉**，前端表现为"输出暂停"，且截图消息留在线程状态里——
这个会话之后每发一条消息都会再挂一次（卡死在图片上）。

开关是设置页的「模型支持读图」（``LLM_SUPPORTS_VISION``，默认关）。换了
多模态模型后打开它，图片照常发送。

关着的时候不是把图丢掉了事：占位文字告诉模型"截图没发、文件在哪"，
agent 还能靠 Unity MCP 的节点查询 / DOM 文本继续走盲操作路线，而不是当场 400。

自动降级（2026-09）：设置页开关说的是**用户以为的**模型能力，实际端点可能
并不收图（实测：glm-5.3 coding 端开着开关，发图即 400「Model only supports
text input」，且用户无从知道该关开关）。所以开着开关时也兜一层：调用抛
"不支持图片"类 400 → 当场剥图重试本次调用，并把该线程记进已知不支持名单，
**后续调用直接剥**（长会话每轮都白打一次全量上下文的失败请求，代价不可接受）。
名单按 thread_id 记忆：换模型预设的其他会话不受牵连，端点真换了多模态模型
也只是这个会话继续走占位路线——重开会话即恢复。

"""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langgraph.config import get_config

from src.app.core.config import settings

_PLACEHOLDER = (
    "[图片未发送：当前模型不支持图像输入（设置页可开「模型支持读图」，或换一个多模态模型）。"
    "若这是工具截图，**文件已经落盘、路径就在工具结果里**："
    "① 把那个路径原样贴给用户 —— 他在聊天里能直接看到图，让他替你看；"
    "② 你自己改用节点/文本方式拿界面信息：unity_hierarchy / unity_find_by_text / "
    "unity_object_text / unity_console，或者读游戏自己的数据（Lua/组件字段），不要靠猜；"
    "③ 需要「看一眼才知道」的结论时，明说「我看不了图，请用户确认这个界面/按钮」，"
    "不要硬推也不要假装看过。]"
)

_IMAGE_BLOCK_TYPES = ("image", "image_url")

# 「端点不支持图片」的网关报错特征。覆盖实测过的 bigmodel 文案与常见变体；
# 命中才降级，其余 400（key 错、参数错…）原样抛出。
_TEXT_ONLY_ERROR = re.compile(
    r"only supports text input"
    r"|unsupported content type\s*'?(?:image_url|image)"
    r"|image(?:_url)?\s+(?:input\s+)?(?:is\s+)?not supported"
    r"|not support (?:image|multimodal|vision)"
    r"|does not support image",
    re.IGNORECASE,
)

# thread_id → 已知"该端点不支持图片"的线程。有界，防长期运行无限增长。
_VISION_UNSUPPORTED_THREADS: OrderedDict[str, None] = OrderedDict()
_VISION_UNSUPPORTED_CAP = 512


def _has_image_block(content: Any) -> bool:
    return (
        isinstance(content, list)
        and any(
            isinstance(b, dict) and b.get("type") in _IMAGE_BLOCK_TYPES
            for b in content
        )
    )


def _strip_images(content: list) -> list:
    rebuilt: list = []
    for block in content:
        if isinstance(block, dict) and block.get("type") in _IMAGE_BLOCK_TYPES:
            rebuilt.append({"type": "text", "text": _PLACEHOLDER})
        else:
            rebuilt.append(block)
    return rebuilt


def _strip_request_images(request: ModelRequest) -> ModelRequest:
    """把请求里所有带图片块的消息换成剥图版本；没有图片时原样返回。"""
    rebuilt_messages = []
    for message in request.messages:
        content = getattr(message, "content", None)
        if _has_image_block(content):
            message = message.model_copy(update={"content": _strip_images(content)})
        rebuilt_messages.append(message)
    return request.override(messages=rebuilt_messages)


def _current_thread_id() -> str:
    try:
        cfg = get_config() or {}
        return str((cfg.get("configurable") or {}).get("thread_id", "") or "")
    except Exception:  # noqa: BLE001 — 非图执行上下文（如单测）
        return ""


def _remember_unsupported(thread_id: str) -> None:
    if not thread_id:
        return
    _VISION_UNSUPPORTED_THREADS[thread_id] = None
    while len(_VISION_UNSUPPORTED_THREADS) > _VISION_UNSUPPORTED_CAP:
        _VISION_UNSUPPORTED_THREADS.popitem(last=False)


def _is_text_only_error(err: BaseException) -> bool:
    return bool(_TEXT_ONLY_ERROR.search(str(err)))


class VisionGateMiddleware(AgentMiddleware):
    """``LLM_SUPPORTS_VISION=false``（或端点实测不支持）时剥掉模型输入里的全部图片块。"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if not settings.llm_supports_vision:
            return await handler(_strip_request_images(request))
        thread_id = _current_thread_id()
        if thread_id and thread_id in _VISION_UNSUPPORTED_THREADS:
            # 已知该线程的端点不收图：直接剥，不再付一次失败请求的代价
            return await handler(_strip_request_images(request))
        try:
            return await handler(request)
        except Exception as err:  # noqa: BLE001 — 只对"不支持图片"降级，其余原样抛
            request_has_images = any(
                _has_image_block(getattr(m, "content", None))
                for m in request.messages
            )
            if not (_is_text_only_error(err) and request_has_images):
                raise
            _remember_unsupported(thread_id)
            return await handler(_strip_request_images(request))
