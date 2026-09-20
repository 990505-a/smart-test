"""装配中间件 —— 让"用户自己搭智能体"在**下一轮对话**生效。

为什么只能这么做：graph 是 LangGraph 进程启动时编译一次的（``start_server.py``，
``reload=False``），工具面在编译时就烘进 ``ToolNode`` 与模型的 bind 里了。改不了
编译产物，就只能改**每次模型调用**的那份请求 —— 而 ``ModelRequest.override()``
支持换 ``tools`` 与 ``system_message``，这正是官方 ``_ToolExclusionMiddleware``
用的同一招。

于是：**一个 graph 服务任意多个用户定义的智能体**。构建期把代码里所有工具都挂上，
每轮按 ``configurable.agent_id`` 现算"这个智能体此刻有哪些能力"，然后：

1. ``AssemblyToolsMiddleware``——过滤 ``request.tools``（不属于任何启用能力的工具
   不进模型视野），并把 system prompt 里 ``<!--@capabilities-->…<!--@capabilities-->``
   那段换成**当前智能体**的能力清单（分诊表 + 领域规则 + 依赖）。改名/改说明/改
   领域提示词/增删能力，全都体现在这一段里，不用重启。
2. ``LiveSkillsMiddleware``——技能清单按"当前智能体各能力声明的技能之并集"过滤，
   手法与 ``MemoryInjectionMiddleware`` 一致：只覆写"取清单"的那一步，官方钩子原封
   不动（自己写 ``before_agent`` 会因为注解派发炸掉，见 memory_injection.py 的警告）。

审批（``gated``）不在这里：它走 ``interrupt_on`` 的 when 谓词，每轮现查目录
（见 ``services/assembly_service.py: is_tool_gated``）。
"""

from __future__ import annotations

import functools
import logging
from pathlib import PurePosixPath
from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

from deepagents.middleware.skills import SkillsMiddleware

from src.app.agents.capabilities import (
    CAPABILITY_SECTION_CLOSE,
    CAPABILITY_SECTION_OPEN,
    build_capability_prompt,
)
from src.app.services.assembly_service import (
    active_agent_id,
    agent_capabilities,
    load_catalog,
    repo_bound_tool_names,
    resolve_agent,
    tool_names,
)

logger = logging.getLogger(__name__)

__all__ = ["AssemblyToolsMiddleware", "LiveSkillsMiddleware", "SKILLS_SOURCE"]


#: 技能库在 backend 里的挂载点（与 harness 传给 create_deep_agent 的一致）
SKILLS_SOURCE = "/skills/"


class AssemblyToolsMiddleware(AgentMiddleware):
    """按"本次 run 的智能体"过滤工具面，并重排提示词里的能力段。"""

    def __init__(self) -> None:
        super().__init__()

    # ---------------------------------------------------------------- 钩子

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> Any:
        # 同步路径不 await 探针：用缓存里上次的结果（没探过 = 就绪，不误伤）
        return handler(self._apply(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> Any:
        await self._refresh_readiness()
        return await handler(self._apply(request))

    async def _refresh_readiness(self) -> None:
        """刷一次本次智能体各能力依赖的就绪状态（TTL 内不重探，见 core/integrations）。

        探活里出任何问题都吞掉：这条路在**每次模型调用**上，装配问题一律不该把对话
        卡死（与 _apply 的"判不出来就按原样放行"同一条原则）；快照里的未知状态按
        "就绪"处理，最坏情况是依赖不在线的工具多给一轮。
        """
        try:
            from src.app.core import integrations

            keys = self._required_keys()
            if keys:
                await integrations.ensure_fresh(keys)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[assembly] 依赖就绪探活失败，本轮按就绪处理: %s", exc)

    def _required_keys(self) -> tuple[str, ...]:
        """当前智能体所有能力声明依赖的集成 key（判不出来就空 = 全按就绪）。"""
        try:
            catalog = load_catalog()
            agent = resolve_agent(catalog, active_agent_id(catalog))
            from src.app.services.assembly_service import required_integrations

            return tuple({key for cap in agent_capabilities(catalog, agent)
                          for key in required_integrations(cap)})
        except Exception:  # noqa: BLE001
            return ()

    # ---------------------------------------------------------------- 实现

    def _apply(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        """注意：**不能**在"目录是空的/没改过"时直接返回。

        工具可见性 = 智能体的能力集合（用户数据）∩ 代码里挂上的工具，每一轮都要现算：
        换个智能体、加一项能力、改一个工具开关，都在这条路上。判不出来（读配置文件
        失败等）就按原样放行，绝不因为装配问题把对话卡死。
        """
        try:
            catalog = load_catalog()
            agent = resolve_agent(catalog, active_agent_id(catalog))
            caps = agent_capabilities(catalog, agent)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[assembly] 装配目录读取失败，本轮按构建期工具面继续: %s", exc)
            return request

        visible = {name for cap in caps for name in tool_names(cap)}
        repo_bound = repo_bound_tool_names(catalog, agent)
        offline = self._offline_tools(caps)
        request = self._filter_tools(request, visible, _pool_names(), repo_bound,
                                     repo_mounted=_repo_mounted(), offline=offline)
        return self._rewrite_capability_section(request, caps, agent)

    def _offline_tools(self, caps) -> frozenset[str]:
        """依赖不在线的能力 → 它们的工具名（这些工具此刻只可能返回降级提示）。

        与 ``requires_repo`` 同一条道理：给了模型它就会去试，试了必然失败、还会
        让它以为"平台坏了"。藏掉 + 在提示词里写明缺什么，才是诚实且省轮次的做法。
        """
        from src.app.core import integrations
        from src.app.services.assembly_service import required_integrations

        keys = {k for cap in caps for k in required_integrations(cap)}
        if not keys:
            return frozenset()
        snapshot = integrations.readiness_snapshot(keys)
        dead = [cap for cap in caps
                if any(snapshot.get(k) is False for k in required_integrations(cap))]
        if not dead:
            return frozenset()
        names = {name for cap in dead for name in tool_names(cap)}
        logger.debug("[assembly] 依赖不在线，隐藏能力工具: %s",
                     [(cap.key, list(required_integrations(cap))) for cap in dead])
        return frozenset(names)

    def _filter_tools(self, request: ModelRequest[ContextT], visible: set[str],
                      pool: frozenset[str], repo_bound: frozenset[str], *,
                      repo_mounted: bool,
                      offline: frozenset[str] = frozenset()) -> ModelRequest[ContextT]:
        tools = request.tools
        if not tools:
            return request
        kept = [tool for tool in tools
                if _keep(tool, visible, pool, repo_bound, repo_mounted=repo_mounted,
                         offline=offline)]
        if len(kept) == len(tools):
            return request
        dropped = [getattr(t, "name", "?") for t in tools if t not in kept]
        logger.debug("[assembly] 本轮隐藏 %d 个未装配工具: %s", len(dropped), dropped)
        return request.override(tools=kept)

    def _rewrite_capability_section(self, request: ModelRequest[ContextT], caps,
                                    agent) -> ModelRequest[ContextT]:
        message = request.system_message
        content = getattr(message, "content", None)
        text = _content_text(content)
        if not text:
            return request
        start = text.find(CAPABILITY_SECTION_OPEN)
        end = text.find(CAPABILITY_SECTION_CLOSE)
        if start < 0 or end < start:
            # 没有槽位（比如旧 graph 的提示词）：不改，保持构建期那版
            return request

        # general=True 恒定：这段本来就是"这个智能体有哪些能力"的清单，只装一项能力
        # 也该列出来（旧 graph 的"单能力不写分诊表"是 per-mode 时代的语义，那条路径
        # 不挂这个中间件）。
        from src.app.core import integrations
        from src.app.services.assembly_service import required_integrations

        keys = {key for c in caps for key in required_integrations(c)}
        section = build_capability_prompt(
            tuple(_as_capability(c) for c in caps),
            general=True,
            identity=(agent.label, agent.description),
            readiness=integrations.readiness_snapshot(keys) if keys else None,
        )
        if text[start + len(CAPABILITY_SECTION_OPEN):end].strip() == section.strip():
            return request  # 这一轮算出来和已经写进去的一样 → 不动（省一次字符串重建）

        replacement = f"{CAPABILITY_SECTION_OPEN}\n{section}\n"
        logger.debug("[assembly] 能力段重写: agent=%s caps=%s", agent.id,
                     [c.key for c in caps] or "（空）")
        return request.override(
            system_message=message.model_copy(
                update={"content": _replace_span(content, start, end, replacement)}
            )
        )


def _keep(tool: Any, visible: set[str], pool: frozenset[str], repo_bound: frozenset[str], *,
          repo_mounted: bool, offline: frozenset[str] = frozenset()) -> bool:
    """这个工具该不该出现在模型面前。

    - **不在候选池里的名字**（框架自带的文件 / shell / 技能 / 子智能体工具）→ 永远
      保留：装配只管代码清单里声明过的工具，别把框架的地基也筛掉；
    - 在池子里但不属于当前智能体的任何能力 → 不给（用户没给它装配）；
    - 属于声明了「依赖仓库」的能力、而这次 run 没挂仓库 → 不给
      （那些工具只会返回降级提示，给了等于让模型白试一轮）；
    - 属于声明了外部依赖、而该依赖此刻不在线的能力 → 不给（同上，改由提示词的
      依赖段告诉模型"缺什么、怎么补"）。
    """
    name = getattr(tool, "name", None)
    if not isinstance(name, str) or not name:
        return True  # provider 侧的内置工具是 dict，没有 name
    if name not in pool:
        return True
    if name not in visible:
        return False
    if name in offline:
        return False
    if name in repo_bound and not repo_mounted:
        return False
    return True


@functools.lru_cache(maxsize=1)
def _pool_names() -> frozenset[str]:
    """候选池里所有工具名（进程内不变：工具是代码里的）。"""
    from src.app.services.assembly_service import catalog_tool_names

    return frozenset(catalog_tool_names())


class LiveSkillsMiddleware(SkillsMiddleware):
    """技能清单按"当前智能体各能力声明的技能"过滤。

    ⚠️ **卸载是提示级**：``/skills/`` 仍以只读方式挂在整个技能库上，模型看不到清单
    里的条目，但如果它去 ``read_file`` 猜路径，文件依然读得到。要真做到"看不见"，
    得按能力拆成子智能体（见 ``capabilities.py`` 模块注释里的取舍）。
    """

    @property
    def name(self) -> str:
        """与官方同名 —— deepagents 的 ``_apply_custom_middleware`` 按 ``.name``
        原地替换，这样中间件栈里仍然只有一份技能中间件，位置也不变。"""
        return "SkillsMiddleware"

    def _format_skills_list(self, skills: list) -> str:
        """官方 ``modify_request`` 调的就是这个方法：过滤后再交给它排版。"""
        try:
            from src.app.services.assembly_service import enabled_skill_dirs

            allowed = set(enabled_skill_dirs())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[assembly] 装配目录读取失败，技能清单按全量展示: %s", exc)
            return super()._format_skills_list(skills)

        kept = [s for s in skills if _skill_dir(s) in allowed]
        return super()._format_skills_list(kept)


def _as_capability(defn):
    from src.app.services.assembly_service import to_capability

    return to_capability(defn)


def _repo_mounted() -> bool:
    """本次 run 有没有挂载一个**真实存在**的仓库目录。

    判"存在"是为了与 backend 对齐：``resolve_workspace_dir`` 遇到不存在的挂载路径会
    回退默认目录，那时 agent 的 cwd 根本不是这个仓库，图谱工具也就不该出现（它按挂载
    路径解析项目名，路径无效只会拿到一堆报错）。

    判不出来（非图执行上下文）返回 True：宁可多给几个工具，也不要因为读不到配置
    把能力藏掉。
    """
    try:
        from pathlib import Path

        from src.app.agents.workspace_backend import mounted_workspace_path

        mounted = mounted_workspace_path()
        return bool(mounted) and Path(mounted).expanduser().is_dir()
    except Exception:  # noqa: BLE001 —— 非图执行上下文（单测直接调时）
        return True


def _skill_dir(metadata: Any) -> str:
    """技能目录名 —— ``/skills/<dir>/SKILL.md`` 的父目录名。"""
    meta = metadata if isinstance(metadata, dict) else {}
    path = str(meta.get("path") or "")
    parent = PurePosixPath(path).parent.name
    return parent or str(meta.get("name") or "")


# ---------------------------------------------------------------------------
# system message 的正文可能是 str，也可能是**内容块列表**（langchain 组装提示词时
# 会这么放，Anthropic 系的 prompt-cache 断点也挂在块上）。两个形状都得支持，
# 并且**保留块上的其他字段**（cache_control 之类）。
# ---------------------------------------------------------------------------

def _content_text(content: Any) -> str:
    """把 content（str 或块列表）拼成纯文本；认不出来的形状返回空串。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _replace_span(content: Any, start: int, end: int, replacement: str) -> Any:
    """把 content 里 ``[start:end)`` 这段换成 ``replacement``（跨块也支持）。

    区间按**拼接后的文本**算，写回时保留原来的形状与块上的附加字段。
    """
    if isinstance(content, str):
        return content[:start] + replacement + content[end:]

    out: list[Any] = []
    offset = 0
    for block in content:
        if not (isinstance(block, dict) and block.get("type") == "text"):
            out.append(block)
            continue
        text = str(block.get("text") or "")
        b_start, b_end = offset, offset + len(text)
        offset = b_end

        if b_end <= start or b_start >= end:          # 与区间不相交
            out.append(block)
            continue
        if b_start <= start < b_end:                  # 起始块：前缀 + 新正文 + 尾巴
            tail = text[max(0, end - b_start):] if end < b_end else ""
            out.append({**block, "text": text[: start - b_start] + replacement + tail})
            continue
        if b_end <= end:                              # 整块落在区间里：正文已被替换
            continue
        out.append({**block, "text": text[max(0, end - b_start):]})   # 结束块：留尾巴
    return out
