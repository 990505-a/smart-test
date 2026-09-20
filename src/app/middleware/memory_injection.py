"""工作区记忆注入 = 官方 ``MemoryMiddleware`` + 一段"读哪些文件"的策略。

平台过去自己写了整套注入：读文件 → 拼 ``### 标题`` 段 → 追加到 system prompt，
而且每次模型调用都重算一遍。这是在重造官方的轮子——``deepagents.MemoryMiddleware``
做的是同一件事，并且多出几样我们那版没做的：

* **官方模板带 ``<memory_guidelines>``**：明确教模型在学到东西时用 ``edit_file``
  把知识写回记忆（自我进化闭环）。我们那版只贴内容、不说怎么更新，模型没有"改记忆"
  这个动作的意识。
* 读进 ``state["memory_contents"]``，**一次 run 只读一次**（我们是每个模型调用重读）。
* 剥掉 HTML 注释（``<!-- -->``）再注入，作者注释不会进 prompt。
* ``TracePolicy(process_inputs=omit_payload)``：记忆正文不进 trace。
* ``add_cache_control``：需要时给 Anthropic 打 prompt-cache 断点。

这里只保留平台确实需要**那一条**策略——"读哪些文件按会话定"：启用哪几个模块看
manifest.json，目录看 ``memory_root(space)``。所以继承官方类，只在每次 run 开始时
刷新 ``sources``，加载 / 模板 / 注入全部走官方实现。

**sources 必须是绝对路径**：官方 backend 在 ``virtual_mode=False`` 下把绝对路径原样
使用（相对路径会落到 agent 的工作区，而记忆目录是 ``workspace/<space>/memory``，
跟 agent 工作区不是同一个地方）。

行为变化（有意接受，属于官方语义）：记忆现在是**每个会话加载一次**，不再每次模型
调用重读；而且不再按字符预算裁剪。代价是"在 /memories 页改完记忆，当前会话不会
立刻变"——新会话生效。换来的是模型知道自己可以、也应该去更新记忆。
"""

from __future__ import annotations

import logging

from deepagents import MemoryMiddleware
from deepagents.backends import FilesystemBackend
from deepagents.middleware.memory import MEMORY_SYSTEM_PROMPT

from src.app.core.config import settings
from src.app.core.workspace import get_space_id
from src.app.services.memory_service import list_modules, memory_root

logger = logging.getLogger(__name__)

__all__ = ["MemoryInjectionMiddleware"]

# 记忆走绝对路径读取（见模块 docstring），这个 backend 只是个"读文件的口子"，
# 用根目录即可——绝对路径不受 root_dir 影响。
_reader = FilesystemBackend(root_dir="/", virtual_mode=False)


def enabled_memory_sources(space_id: str | None = None) -> list[str]:
    """当前 space 下**启用中**模块的绝对路径，按 manifest 里的顺序。

    这就是官方 ``MemoryMiddleware.sources`` 的取值来源：官方的 sources 是构造期
    静态清单，平台必须是"按当前会话的 manifest 现算"（见下方类的 docstring）。

    总开关 ``settings.memory_enabled`` 关掉时返回空清单——它决定"agent 是否看得见
    记忆"。这个开关曾经是**假的**：它只被一个生产代码没有调用方的函数读（那套手写的
    记忆块拼装已随 2026-09-18 清理删除），于是设置页关掉它之后中间件照旧注入记忆。
    """
    if not settings.memory_enabled:
        return []
    space = space_id or get_space_id()
    root = memory_root(space)
    return [str(root / module.file) for module in list_modules(space) if module.enabled]


class MemoryInjectionMiddleware(MemoryMiddleware):
    """把启用中的记忆模块注入 system prompt（官方 MemoryMiddleware 的薄封装）。

    只覆写 ``sources`` 这一件事：官方把它当构造参数存成静态清单，平台需要"按**当前
    会话**的 manifest 决定读哪些文件"。做成属性就够了——官方在 ``before_agent`` /
    ``_format_agent_memory`` 里都是**用的时候才读** ``self.sources``。

    ⚠️ **不要在子类里覆写 ``before_agent`` / ``abefore_agent``**。官方的钩子签名带
    ``config`` 形参，而框架是**按注解**判断要不要注入它的；自己再写一遍（哪怕参数名
    一样、只把注解写成 ``Any``）就会被当成"这个钩子不需要 config"来调用，直接：

        TypeError: MemoryInjectionMiddleware.abefore_agent()
                   missing 1 required positional argument: 'config'

    构建期（import / compile）完全查不出来，只有真跑一轮才炸——实测踩过。用属性就没
    这个问题：钩子仍是官方那一个，签名和注解都是原装的。
    """

    def __init__(self) -> None:
        # 官方 __init__ 会执行 self.sources = sources，落进下面的 setter 被忽略；
        # 真正的清单每次用到时现算（只读 manifest.json，开销可忽略）。
        #
        # add_cache_control=True：记忆块边界打一个 prompt-cache 断点，避免记忆更新后
        # 整段 prefix 缓存失效。**当前模型（GLM/DeepSeek 等 OpenAI 兼容端点）是
        # no-op**——官方只在 Anthropic 系模型上生效（_prompt_caching.py 只装
        # Anthropic/Bedrock/Fireworks）。开着是为了将来换到 Claude 时不用回头改，
        # 代价为零（官方注释原话：safe to enable unconditionally）。
        super().__init__(backend=_reader, sources=[], add_cache_control=True)

    @property
    def sources(self) -> list[str]:
        """当前 space 下启用中的记忆模块（绝对路径）。读不到就返回空，不拦对话。"""
        try:
            return enabled_memory_sources()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MemoryInjectionMiddleware] 记忆模块清单读取失败: %s", exc)
            return []

    @sources.setter
    def sources(self, _value: list[str]) -> None:
        # 官方 __init__ 的赋值落点。静态清单在"按会话决定"的语义下没有意义，忽略。
        return

    @property
    def system_prompt(self) -> str | None:
        """总开关关掉时返回 ``None``——官方在 ``system_prompt is None`` 时**完全不贴**。

        为什么做成 property 而不是在 ``__init__`` 里算一次：这个中间件在 agent 模块
        里是**模块级单例**（构造一次、随 graph 编译固定），而设置页改完应当"下一轮
        生效"。官方在 ``wrap_model_call`` 里每次调用都现读 ``self.system_prompt``，
        所以这里现算就是对的。同时 ``sources`` 也返回空，``before_agent`` 便不会去
        读文件（它不看 ``system_prompt``，只看 ``sources``）。
        """
        return MEMORY_SYSTEM_PROMPT if settings.memory_enabled else None

    @system_prompt.setter
    def system_prompt(self, _value: str | None) -> None:
        # 同 sources：官方 __init__ 的赋值落点，实际取值由上面的 property 现算。
        return
