"""装配目录 —— 智能体 / 能力 / 工具 / 技能 全是**用户数据**。

事实源是 ``workspace/<space>/assembly.json`` 一个 JSON 文件（version 2）：

```json
{
  "agents": [{"id": "general", "label": "通用测试助手", "description": "...",
              "capabilities": ["testcase", "unity", "webui", "codebase"]}],
  "capabilities": [{"key": "webui", "label": "Web-UI 自动化", "description": "...",
                    "domain_prompt": "...", "tools": ["模块:符号", ...],
                    "skills": ["web-ui-test"], "requires_repo": false,
                    "gated": ["approve_case_document"]}]
}
```

层级是 **智能体 → 能力 → 工具/技能/权限**（页面上就按这个层级编辑）：

- 一个**智能体** = 名字 + 说明 + 它装配了哪些能力。对话页可以切换智能体。
- 一个**能力** = 名字 + 说明 + 领域提示词 + 工具集合 + 技能集合 + 是否依赖仓库 +
  哪些工具要人工审批。用户可建可删可改。
- **工具**只能从代码里已有的选（工具是 Python 函数，界面造不出来）：候选池 =
  ``capabilities.py`` 清单里声明过的全部符号，见 ``tool_catalog()``。
- **技能**从 ``src/app/skills/`` 下挑（每个目录一个 SKILL.md），见 ``skill_catalog()``。
  模型看得见的技能清单 = 当前智能体各能力声明的技能之并集 —— 所以技能不再是一个
  独立的库，而是能力的一部分。

代码里的 ``CAPABILITIES`` 退化为**种子**：文件不存在时用它播种；用户改过就以文件
为准（``DELETE`` 恢复默认 = 删文件重新播种）。

为什么读侧还在这里（而不是 DB）：装配中间件在 **LangGraph 进程**里每轮模型调用都要
读它，用户在 **FastAPI 进程**里改它。跨进程这一层，仓库里已有的桥都是"文件 + 用的时候
重读"（``.env`` 给模型热更、``memory/manifest.json`` 给记忆模块开关）。沿用同一套：
文件放 workspace 卷里，本机与容器两种部署都共享，读侧按 mtime 缓存，改完下一轮生效。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from src.app.core.workspace import get_space_id, get_workspace_dir

logger = logging.getLogger(__name__)

#: 装配文件的名字（放在 ``workspace/<space>/`` 下，与 agent 工作目录同级）
ASSEMBLY_FILENAME = "assembly.json"
ASSEMBLY_VERSION = 2

#: 技能库根目录（``src/app/skills``）——与 harness 挂到 ``/skills/`` 的是同一个
SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"


# ===========================================================================
# 数据模型
# ===========================================================================

@dataclass(frozen=True)
class CapabilityDef:
    """一项能力（用户可编辑）。``tools`` 存的是符号引用 ``"模块:符号"``。"""

    key: str
    label: str = ""
    description: str = ""
    domain_prompt: str = ""
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    requires_repo: bool = False
    gated: tuple[str, ...] = ()
    """需要人工审批的**工具名**（不是符号）。用户在能力编辑器里勾。"""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label or self.key,
            "description": self.description,
            "domain_prompt": self.domain_prompt,
            "tools": list(self.tools),
            "skills": list(self.skills),
            "requires_repo": self.requires_repo,
            "gated": list(self.gated),
        }

    @classmethod
    def from_raw(cls, raw: object) -> CapabilityDef | None:
        if not isinstance(raw, dict):
            return None
        key = str(raw.get("key") or "").strip()
        if not key:
            return None
        return cls(
            key=key,
            label=str(raw.get("label") or key),
            description=str(raw.get("description") or ""),
            domain_prompt=str(raw.get("domain_prompt") or ""),
            tools=_str_tuple(raw.get("tools")),
            skills=_str_tuple(raw.get("skills")),
            requires_repo=bool(raw.get("requires_repo")),
            gated=_str_tuple(raw.get("gated")),
        )


@dataclass(frozen=True)
class AgentDef:
    """一个智能体：名字 + 说明 + 它装配了哪些能力。"""

    id: str
    label: str = ""
    description: str = ""
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label or self.id,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_raw(cls, raw: object) -> AgentDef | None:
        if not isinstance(raw, dict):
            return None
        agent_id = str(raw.get("id") or "").strip()
        if not agent_id:
            return None
        return cls(
            id=agent_id,
            label=str(raw.get("label") or agent_id),
            description=str(raw.get("description") or ""),
            capabilities=_str_tuple(raw.get("capabilities")),
        )


@dataclass(frozen=True)
class Catalog:
    """一份装配目录。空 = 用代码清单播种。"""

    agents: tuple[AgentDef, ...] = ()
    capabilities: tuple[CapabilityDef, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.agents and not self.capabilities

    def agent(self, agent_id: str | None) -> AgentDef | None:
        for item in self.agents:
            if item.id == agent_id:
                return item
        return None

    def capability(self, key: str) -> CapabilityDef | None:
        for item in self.capabilities:
            if item.key == key:
                return item
        return None

    def default_agent(self) -> AgentDef | None:
        return self.agent(DEFAULT_AGENT_ID) or (self.agents[0] if self.agents else None)

    def to_dict(self) -> dict:
        return {
            "version": ASSEMBLY_VERSION,
            "agents": [a.to_dict() for a in self.agents],
            "capabilities": [c.to_dict() for c in self.capabilities],
        }

    @classmethod
    def from_raw(cls, raw: object) -> Catalog:
        if not isinstance(raw, dict):
            return cls()
        agents = tuple(
            a for a in (AgentDef.from_raw(x) for x in _list(raw.get("agents"))) if a
        )
        caps: list[CapabilityDef] = []
        seen: set[str] = set()
        for item in _list(raw.get("capabilities")):
            cap = CapabilityDef.from_raw(item)
            if cap and cap.key not in seen:
                seen.add(cap.key)
                caps.append(cap)
        return cls(agents=agents, capabilities=tuple(caps))


def _list(raw: object) -> list:
    return list(raw) if isinstance(raw, (list, tuple)) else []


def _str_tuple(raw: object) -> tuple[str, ...]:
    return tuple(s for s in _list(raw) if isinstance(s, str) and s)


# ===========================================================================
# 种子（代码清单 → 默认目录）
# ===========================================================================

#: 默认智能体的 id/名字 —— 新会话默认用它，也是"恢复默认"后唯一的智能体
DEFAULT_AGENT_ID = "general"
DEFAULT_AGENT_LABEL = "通用测试助手"
DEFAULT_AGENT_DESCRIPTION = "什么活都能接：用例生成、Unity / Web-UI 自动化、代码分析。按能力分诊，自己判断用哪一类。"


def default_catalog() -> Catalog:
    """用代码清单播种一份默认目录（文件不存在 / 恢复默认时用）。"""
    from src.app.agents.capabilities import CAPABILITIES

    capabilities = tuple(
        CapabilityDef(
            key=cap.key,
            label=cap.label,
            description=cap.description,
            domain_prompt=cap.domain_prompt,
            tools=cap.tool_specs(),
            skills=cap.skills,
            requires_repo=cap.requires_repo,
            gated=tuple(name for name, _ in cap.human_gated),
        )
        for cap in CAPABILITIES
    )
    return Catalog(
        agents=(AgentDef(
            id=DEFAULT_AGENT_ID,
            label=DEFAULT_AGENT_LABEL,
            description=DEFAULT_AGENT_DESCRIPTION,
            capabilities=tuple(c.key for c in capabilities),
        ),),
        capabilities=capabilities,
    )


# ===========================================================================
# 读 / 写（读侧按 mtime 缓存；写侧原子替换）
# ===========================================================================

def assembly_path(space_id: str | None = None) -> Path:
    """装配文件路径（``workspace/<space>/assembly.json``）。"""
    return get_workspace_dir(space_id, "") / ASSEMBLY_FILENAME


_cache: dict[str, tuple[tuple[int, int] | None, Catalog]] = {}


def load_catalog(space_id: str | None = None) -> Catalog:
    """读当前装配目录。文件不存在 / 读不动 / 坏 JSON 都回落到**种子**，绝不抛。

    每个模型调用都会走这里，所以按 ``(mtime_ns, size)`` 缓存；用户保存后文件变化，
    下一次调用自然重读。
    """
    space = space_id or get_space_id()
    path = assembly_path(space)

    try:
        stat = path.stat()
        stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None

    cached = _cache.get(space)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    catalog = default_catalog()
    if stamp is not None:
        try:
            catalog = Catalog.from_raw(json.loads(path.read_text("utf-8")))
        except Exception as exc:  # noqa: BLE001 —— 配置文件坏了不该拦对话
            logger.warning("[assembly] %s 读取失败，按默认目录继续: %s", path, exc)
            catalog = default_catalog()
        # 旧版本（v1 的"开关式"文件）/ 手工改空的文件：里面没有智能体与能力，
        # 直接用默认目录，别给用户一个空壳（下次保存会写成 v2）
        if catalog.is_empty:
            logger.info("[assembly] %s 里没有智能体/能力，按默认目录播种", path)
            catalog = default_catalog()

    _cache[space] = (stamp, catalog)
    return catalog


def save_catalog(catalog: Catalog, space_id: str | None = None) -> Catalog:
    """写装配文件（临时文件 + 原子替换），并刷新缓存。"""
    space = space_id or get_space_id()
    path = assembly_path(space)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, path)

    invalidate_cache()
    logger.info("[assembly] 已保存: %d 个智能体 / %d 项能力",
                len(catalog.agents), len(catalog.capabilities))
    return load_catalog(space)


def reset_catalog(space_id: str | None = None) -> Catalog:
    """恢复默认：删掉装配文件（下次读取自动用代码清单重新播种）。"""
    path = assembly_path(space_id or get_space_id())
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    invalidate_cache()
    logger.info("[assembly] 已恢复默认装配目录")
    return load_catalog(space_id)


def invalidate_cache() -> None:
    _cache.clear()


# ===========================================================================
# 候选池：工具（代码里有的）与技能（skills/ 下的）
# ===========================================================================

_tool_catalog_cache: dict[str, dict] = {}


def tool_catalog() -> list[dict]:
    """可装配的工具候选池 —— 清单里声明过的全部符号，按模块分组给页面用。

    工具是 Python 函数，界面造不出来，所以只能从这里挑。每条给出：符号引用、
    来源模块、工具名（一个符号可能导出多个工具）、说明（工具自己的 docstring 首行）。
    """
    from src.app.agents.capabilities import CAPABILITIES

    seen: dict[str, dict] = {}
    for cap in CAPABILITIES:
        for spec in cap.tool_specs():
            if spec in _tool_catalog_cache:
                entry = _tool_catalog_cache[spec]
            else:
                entry = _describe_symbol(spec)
                _tool_catalog_cache[spec] = entry
            if entry:
                seen[spec] = entry
    return list(seen.values())


def _describe_symbol(spec: str) -> dict | None:
    from src.app.agents.capabilities import _import_symbol

    module_path, _, symbol = spec.partition(":")
    try:
        resolved = _import_symbol(spec)
    except Exception as exc:  # noqa: BLE001 —— 解析不到就如实标注，别假装有
        return {"symbol": spec, "module": module_path, "export": symbol, "names": [],
                "description": "", "missing": True, "error": str(exc)}
    items = list(resolved) if isinstance(resolved, (list, tuple)) else [resolved]
    return {
        "symbol": spec,
        "module": module_path,
        "export": symbol,
        "names": [getattr(t, "name", symbol) for t in items],
        "description": _first_line(getattr(items[0], "description", "")),
        "missing": False,
    }


def _first_line(text: str) -> str:
    line = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return line[:160]


def catalog_tool_names() -> tuple[str, ...]:
    """候选池里所有工具名（一个符号可能导出多个工具）。

    用于给"需要人工审批"建 ``interrupt_on`` 条目：工具名得先在编译期登记，审批与否
    才由 when 谓词每轮现查。
    """
    names: list[str] = []
    for entry in tool_catalog():
        for name in entry["names"]:
            if name not in names:
                names.append(name)
    return tuple(names)


def skill_catalog() -> list[dict]:
    """可装配的技能候选池（``src/app/skills/<dir>/SKILL.md`` 的 name/description）。"""
    out: list[dict] = []
    if not SKILLS_ROOT.is_dir():
        return out
    for child in sorted(SKILLS_ROOT.iterdir()):
        skill_file = child / "SKILL.md"
        if not child.is_dir() or not skill_file.is_file():
            continue
        try:
            head = skill_file.read_text(encoding="utf-8", errors="replace")[:1200]
        except OSError:
            continue
        name = re.search(r"^name:\s*(.+)$", head, re.MULTILINE)
        desc = re.search(r"^description:\s*(.+)$", head, re.MULTILINE)
        guides = sorted(p.name for p in (child / "guides").glob("*.md")) \
            if (child / "guides").is_dir() else []
        out.append({
            "dir": child.name,
            "name": (name.group(1).strip() if name else child.name),
            "description": (desc.group(1).strip()[:200] if desc else ""),
            "guides": guides,
        })
    return out


# ===========================================================================
# 生效解析（中间件与 API 共用同一份判断）
# ===========================================================================

def active_agent_id(catalog: Catalog | None = None) -> str:
    """本次 run 用哪个智能体：``configurable.agent_id``，缺省 / 认不出 = 默认智能体。"""
    try:
        from langgraph.config import get_config

        configurable = (get_config() or {}).get("configurable") or {}
        requested = str(configurable.get("agent_id") or "").strip()
    except Exception:  # noqa: BLE001 —— 非图执行上下文（单测直接调时）
        requested = ""
    catalog = catalog or load_catalog()
    if requested and catalog.agent(requested):
        return requested
    default = catalog.default_agent()
    return default.id if default else DEFAULT_AGENT_ID


def resolve_agent(catalog: Catalog, agent_id: str | None = None) -> AgentDef:
    """拿到智能体定义（认不出就退回默认；默认也没了就现场兜一个）。"""
    agent = catalog.agent(agent_id) if agent_id else None
    if agent is None:
        agent = catalog.default_agent()
    if agent is None:
        agent = AgentDef(id=DEFAULT_AGENT_ID, label=DEFAULT_AGENT_LABEL,
                         description=DEFAULT_AGENT_DESCRIPTION,
                         capabilities=tuple(c.key for c in catalog.capabilities))
    return agent


def agent_capabilities(catalog: Catalog, agent: AgentDef) -> tuple[CapabilityDef, ...]:
    """智能体装配着的那些能力（按目录顺序，忽略不存在的 key）。"""
    out = [cap for cap in (catalog.capability(k) for k in agent.capabilities) if cap]
    return tuple(out)


def required_integrations(defn: CapabilityDef) -> tuple[str, ...]:
    """这项能力依赖哪些外部依赖（``core/integrations`` 的 key）。

    ``requires`` 是"这些工具依赖谁"的**代码事实**，不写进 assembly.json（用户数据
    里存一份只会多一个会走样的副本），所以统一从代码种子取。用户自建的能力没有
    种子 → 无依赖。
    """
    from src.app.agents.capabilities import CAPABILITY_BY_KEY

    seed = CAPABILITY_BY_KEY.get(defn.key)
    return seed.requires if seed else ()


def to_capability(defn: CapabilityDef):
    """把用户数据转成提示词/工具解析用的 ``Capability``（同一套下游代码）。"""
    from src.app.agents.capabilities import Capability

    return Capability(
        key=defn.key,
        label=defn.label or defn.key,
        description=defn.description,
        skills=defn.skills,
        domain_prompt=defn.domain_prompt,
        tools=defn.tools,
        human_gated=tuple((name, f"{name} 已被设置为需要人工审批") for name in defn.gated),
        requires_repo=defn.requires_repo,
        requires=required_integrations(defn),
    )


_tool_names_cache: dict[str, tuple[str, ...]] = {}


def tool_names(defn: CapabilityDef) -> tuple[str, ...]:
    """一项能力实际会挂上哪些工具名（符号 → 工具对象 → name）。"""
    cached = _tool_names_cache.get(defn.key)
    if cached is not None and len(cached) == len(defn.tools):
        return cached
    from src.app.agents.capabilities import resolve_tools

    names = tuple(t.name for t in resolve_tools((to_capability(defn),)))
    _tool_names_cache[defn.key] = names
    return names


def gated_tool_names(space_id: str | None = None) -> frozenset[str]:
    """当前目录里**所有**能力声明要审批的工具名（审批谓词每轮现查这个）。"""
    catalog = load_catalog(space_id)
    return frozenset(name for cap in catalog.capabilities for name in cap.gated)


def is_tool_gated(tool_name: str, space_id: str | None = None) -> bool:
    """``interrupt_on`` 的 when 谓词：这个工具现在要不要人工审批。

    每次工具调用都会问一次，所以走 mtime 缓存 + frozenset，开销可忽略。
    读不出来时返回 False（不拦）——审批配置读不到不该把整轮 run 卡死。
    """
    try:
        return tool_name in gated_tool_names(space_id)
    except Exception:  # noqa: BLE001
        return False


def enabled_skill_dirs(space_id: str | None = None) -> list[str]:
    """当前智能体看得见的技能目录（各能力声明之并集，保持声明顺序）。"""
    catalog = load_catalog(space_id)
    agent = resolve_agent(catalog, active_agent_id(catalog))
    out: list[str] = []
    for cap in agent_capabilities(catalog, agent):
        for skill in cap.skills:
            if skill not in out:
                out.append(skill)
    return out


def repo_bound_tool_names(catalog: Catalog, agent: AgentDef | None = None) -> frozenset[str]:
    """"必须有本次会话挂载的仓库才可用"的工具名（能力声明 ``requires_repo``）。"""
    caps = agent_capabilities(catalog, agent) if agent else catalog.capabilities
    return frozenset(name for cap in caps if cap.requires_repo for name in tool_names(cap))


# ---------------------------------------------------------------------------
# 编辑期校验：名字不认识的项一律丢掉并回报（界面与目录版本不一致时宁可少改）
# ---------------------------------------------------------------------------

def validate_catalog(catalog: Catalog) -> tuple[Catalog, list[str]]:
    """剔除引用了不存在东西的项，返回 (清理后的目录, 被丢弃的项清单)。"""
    known_tools = {entry["symbol"] for entry in tool_catalog()}
    known_skills = {skill["dir"] for skill in skill_catalog()}
    ignored: list[str] = []

    caps: list[CapabilityDef] = []
    for cap in catalog.capabilities:
        tools = tuple(t for t in cap.tools if t in known_tools)
        ignored += [f"tool:{t}" for t in cap.tools if t not in known_tools]
        skills = tuple(s for s in cap.skills if s in known_skills)
        ignored += [f"skill:{s}" for s in cap.skills if s not in known_skills]
        # 审批项按工具名登记，改完工具集合后可能留下孤儿，这里一起清掉
        names = set(tool_names(replace(cap, tools=tools, skills=skills)))
        gated = tuple(g for g in cap.gated if g in names)
        ignored += [f"gated:{g}" for g in cap.gated if g not in names]
        caps.append(replace(cap, tools=tools, skills=skills, gated=gated))

    valid_keys = {cap.key for cap in caps}
    agents: list[AgentDef] = []
    for agent in catalog.agents:
        kept = tuple(k for k in agent.capabilities if k in valid_keys)
        ignored += [f"capability:{k}" for k in agent.capabilities if k not in valid_keys]
        agents.append(replace(agent, capabilities=kept))

    return Catalog(agents=tuple(agents), capabilities=tuple(caps)), sorted(set(ignored))
