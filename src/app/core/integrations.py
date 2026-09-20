"""外部依赖注册表（平台自己之外需要接的东西，唯一一份描述）。

背景：同一个依赖过去被写在**四个互不相干的地方** —— 设置页字段（用户要填什么）、
`launcher.py::_default_services`（进程谁管）、`api/v2/mcp.py::_server_registry`
（MCP 清单，仅供展示）、`Capability.requires`（中文散文，机器读不了）。没有任何东西
保证这四处一致，于是每个集成最后都表现为"设置页几个字段 + 某个页面一句不可达"，
用户看到的全是待办。

这张表把描述收敛到一处，其余全部派生：

* ``probe`` —— 该依赖现在到底能不能用（原来散在四个 ``/status`` 路由里各写各的）
* ``fix_hint`` —— 缺了怎么补（原来每个页面自己写"请打开启动器…"）
* ``launch`` —— 启动器里的服务名，能一键启动的就不该让用户跳出去
* ``install`` —— 平台能自己装的就别让用户找二进制
* ``settings_keys`` —— 归属字段（有测试保证这些键真的被读到）

``Capability.requires`` 里写的就是这里的 ``key``，装配层据此在依赖不在线时把该能力的
工具挡在工具面外（见 middleware/assembly.py）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

import httpx

from src.app.core.config import settings

logger = logging.getLogger(__name__)

Kind = Literal["bundled", "local_service", "external"]
"""bundled=仓库内自带/平台自管安装；local_service=本机常驻服务；external=平台外的东西。"""


@dataclass(frozen=True)
class Integration:
    key: str
    label: str
    kind: Kind
    optional: bool
    """False = 缺了平台就残废（主模型）；True = 缺了只是少一块能力。"""
    summary: str
    absent_effect: str
    """没有它时用户会失去什么——就绪中心要显示的就是这句话。"""
    fix_hint: str
    probe: Callable[[], Awaitable[dict]] = field(repr=False, default=None)  # type: ignore[assignment]
    launch: str | None = None
    install: str | None = None
    settings_keys: tuple[str, ...] = ()


# ===========================================================================
# 探针：把各模块已有的状态查询统一成 {"ready": bool, "detail": str, "error": str|None}
# ===========================================================================

async def _probe_playwright() -> dict:
    from src.app.services import playwright_service

    st = await playwright_service.status()
    return {"ready": bool(st.get("available")),
            "detail": f"runner {st.get('version') or '在线'} · 浏览器 "
                      f"{len(st.get('browsers') or [])} 个" if st.get("available") else "",
            "error": st.get("error") or st.get("hint"),
            "url": settings.playwright_runner_url}


def unity_looks_absent() -> bool:
    """本机看起来没装 Unity（Hub / 编辑器都没找到）。

    **只用来生成提示**，不参与状态判定：部署形态太杂（容器里的平台看不到宿主装没装
    Unity、Unity 也可能装在另一台机器上），判错的代价是把真问题藏起来。所以这里
    只是"要不要提醒用户可以标记为不适用"的依据。
    """
    import os
    import sys
    from pathlib import Path

    if sys.platform == "darwin":
        candidates = ["/Applications/Unity Hub.app", "/Applications/Unity/Hub/Editor"]
    elif sys.platform.startswith("win"):
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates = [os.path.join(pf, "Unity Hub"),
                      os.path.join(pf, "Unity", "Hub", "Editor")]
    else:
        candidates = [os.path.expanduser("~/Unity/Hub/Editor"), "/opt/unity"]
    return not any(Path(c).exists() for c in candidates)


async def _probe_unity() -> dict:
    from src.app.services import unity_bridge

    st = await unity_bridge.status()
    # 这台机器上没 Unity 时，附一句"可以标记为不适用"——否则用户只能一直看着
    # 一个修不好的未就绪项，而不知道有个开关能把它降级成中性状态。
    na_hint = ("这台机器未检测到 Unity（Hub/编辑器）；如果它只当服务端用、不跑 Unity 自动化，"
               "可以点本行右侧「标记为不适用」"
               ) if unity_looks_absent() else None
    if not st.get("available"):
        return {"ready": False, "detail": "", "error": st.get("error") or st.get("hint"),
                "endpoint": settings.unity_mcp_url, "na_hint": na_hint}
    server = st.get("server") or {}
    editor = st.get("editor") or {}
    summary = (f"{server.get('name') or 'Unity MCP'} {server.get('version') or ''}".strip()
               + f" · {st.get('tool_count', 0)} 个工具")
    if not st.get("unity_connected"):
        # 桥在 ≠ 能用：Unity 工程里没装/没连 Bridge 包时，任何工具调用都会回
        # "Unity session not available"。这时报"就绪"是骗人的，标成未就绪并说清原因。
        return {"ready": False, "detail": summary,
                "error": "桥在线，但 Unity 编辑器未连接（工程里装「MCP for Unity」包并连上它）",
                "endpoint": settings.unity_mcp_url, "na_hint": na_hint}
    instances = st.get("instances") or []
    who = ""
    if instances:
        first = instances[0]
        who = f"{first.get('name') or 'Unity'} ({first.get('unity_version') or '?'})"
        if len(instances) > 1:
            who += f" 等 {len(instances)} 个实例"
    state = "Play Mode 中" if editor.get("isPlaying") else "未进入 Play Mode"
    detail = " · ".join(x for x in (summary, who, state) if x)
    return {"ready": True, "detail": detail,
            "error": None, "endpoint": settings.unity_mcp_url}


async def _probe_codebase() -> dict:
    from src.app.services import codebase_service

    st = await codebase_service.status()
    install = st.get("install") or {}
    detail = ""
    if st.get("available"):
        detail = f"{install.get('installed_version') or '已安装'} · "
        detail += f"{len(st.get('projects') or [])} 个已建库项目"
    error = st.get("error")
    # "装好了但配置指着别处"是最容易白折腾半小时的一种：平台把新版装进
    # tools/codebase-memory/，.env 却还指着旧的 GS exe。必须明说。
    if not st.get("exe_present") and install.get("installed_version"):
        error = (f"新版 {install['installed_version']} 已装在 {install.get('managed_dir')}，"
                 f"但 CODEBASE_MEMORY_EXE 指向 {install.get('configured_exe')}（该路径不存在）。"
                 f"把这一项清空即用平台自管版本")
    return {"ready": bool(st.get("available")),
            "detail": detail,
            "error": error,
            "exe": st.get("exe"),
            "exe_present": st.get("exe_present"),
            # 键名必须是 install_state：probe_all 会把探针结果 update 进 payload，
            # 而 "install" 那个位置放的是**安装器键名**（codebase-memory / playwright）。
            # 这里叫 install 的话会把键名覆盖成这个字典，前端读的 install_state
            # 永远是空 —— 「升级」按钮与"自备 exe 覆盖了自管安装"的提示都不会出现。
            "install_state": install}


async def _probe_lightrag() -> dict:
    from src.app.services import lightrag_service

    rows = await lightrag_service.kbs_status()
    online = [r for r in rows if r["reachable"]]
    ready = bool(online)
    detail = ""
    if ready:
        # 多库时只说"在线"是不够的：用户要知道**哪几个**库的实例起来了。
        shown = "、".join(f"{r['label']}(:{r['port']})" for r in online[:4])
        detail = (f"{len(online)}/{len(rows)} 个知识库在线 · {shown}"
                  if len(rows) > 1 else f"知识库在线（{online[0]['base_url']}）")
    error = None if ready else (
        rows[0].get("error") if rows else "还没有配置任何知识库")
    return {"ready": ready,
            "detail": detail,
            "error": error,
            "url": rows[0]["base_url"] if rows else settings.lightrag_base_url,
            "kbs": [{k: r.get(k) for k in ("key", "label", "port", "reachable", "documents")}
                    for r in rows],
            # embedding key 缺失时服务能起但没有向量能力，这里顺带提示
            "embedding_configured": bool(settings.lightrag_embedding_api_key)}


async def _probe_langfuse() -> dict:
    from src.app.db.database import async_session_factory
    from src.app.eval.langfuse_client import langfuse_client_for
    from src.app.services.settings_service import SettingsService

    # 走测评同一条解析路径（设置页优先、.env 兜底），避免两处判断不一致
    async with async_session_factory() as db:
        client = langfuse_client_for(await SettingsService(db).langfuse_values())
    if not client.enabled:
        # 这是设计上的"可选"：不配就只落本地，不该显示成故障
        return {"ready": False, "detail": "", "error": None,
                "reason": "未配置（选填：不配则测评结果只落本地，不上报 trace）",
                "configured": False}
    ok = client._get("/api/public/projects") is not None  # noqa: SLF001 — 只做探活
    host = client.host
    client.close()
    return {"ready": ok,
            "detail": f"已连接（{host}）" if ok else "",
            "error": None if ok else f"配置了但连不上 {host}",
            "configured": True}


async def _probe_feishu() -> dict:
    from src.app.services import feishu_service

    st = await feishu_service.auth_status()
    ready = bool(st.get("available") and st.get("logged_in"))
    user = st.get("user")
    return {"ready": ready,
            "detail": (f"已登录（{user}）" if user else "已登录") if ready else "",
            "error": st.get("error"),
            "install_hint": st.get("install_hint")}


async def _probe_llm() -> dict:
    model = settings.llm_model or settings.deepseek_model
    key = settings.llm_api_key or settings.deepseek_api_key
    base = settings.llm_base_url or "https://api.deepseek.com/v1"
    return {"ready": bool(key),
            "detail": f"{model} @ {base}" if key else "",
            "error": None if key else "未配置 API Key（设置页「模型」）"}


# ===========================================================================
# 注册表
# ===========================================================================
# 「能力依赖」是本平台的功能；「外部平台」是可选增强。就绪中心按这个分组展示。

INTEGRATIONS: tuple[Integration, ...] = (
    Integration(
        key="playwright",
        label="Playwright 执行器",
        kind="bundled",
        optional=False,
        summary="Web-UI 自动化的浏览器侧执行器（仓库自带 tools/playwright-runner）",
        absent_effect="Web-UI 自动化能力整体不可用（网页测试/回归跑不了）",
        fix_hint="在启动器(:5010)启动 playwright 服务，再点本行「安装」装 chromium；"
                 "Linux 宿主机的系统依赖需 root（安装失败时会给可复制的 sudo 命令）",
        probe=_probe_playwright,
        launch="playwright",
        install="playwright",
    ),
    Integration(
        key="unity",
        label="Unity 自动化桥",
        kind="local_service",
        optional=True,
        summary="通用 Unity 自动化桥（标准 MCP：CoplayDev/unity-mcp 等）；平台工具与沉淀的用例脚本都经它操作 Unity",
        absent_effect="Unity 自动化能力不可用（Web-UI 自动化与其余功能不受影响）",
        fix_hint="在启动器启动 unity-mcp（:5016，需 uv）；Unity 工程里装「MCP for Unity」包，"
                 "Transport 选 HTTP(Remote) 并指向本机 5016",
        probe=_probe_unity,
        launch="unity-mcp",
        settings_keys=("unity_mcp_url", "unity_mcp_transport",
                       "unity_mcp_command", "unity_mcp_server"),
    ),
    Integration(
        key="codebase-memory",
        label="代码知识图谱",
        kind="bundled",
        optional=True,
        summary="本地代码图谱引擎（官方 codebase-memory-mcp，平台按当前平台自动安装）",
        absent_effect="代码图谱能力不可用（符号检索/调用链/架构总览；grep 与读文件仍可用）",
        fix_hint="在「代码图谱」页点「安装/升级」，或让平台下载官方 release",
        probe=_probe_codebase,
        install="codebase-memory",
        settings_keys=("codebase_memory_exe", "codebase_graph_port", "codebase_version"),
    ),
    Integration(
        key="lightrag",
        label="LightRAG 知识库",
        kind="local_service",
        optional=True,
        summary="RAG 知识库本体（图谱+向量检索）。一个知识库 = 一个实例 + 一个 workspace"
                "（数据互不可见），由启动器托管；清单在 LightRAG 界面的「RAG 设置」页里改",
        absent_effect="知识库检索/入库不可用（其余能力不受影响）",
        fix_hint="点本行右侧「启动」（或启动器 :5010）；首次需配 embedding key"
                 "与 LLM 端点（LightRAG 界面的「RAG 设置」页，或 .env）",
        probe=_probe_lightrag,
        launch="lightrag",
        settings_keys=("lightrag_base_url", "lightrag_working_dir",
                       "lightrag_llm_base_url", "lightrag_llm_model",
                       "lightrag_llm_api_key",
                       "lightrag_embedding_base_url", "lightrag_embedding_model",
                       "lightrag_embedding_api_key", "lightrag_embedding_dim"),
    ),
    Integration(
        key="langfuse",
        label="Langfuse（测评追踪）",
        kind="external",
        optional=True,
        summary="测评 trace 与分数的可视化面板（自建 docker 栈，默认 :3000；有中文汉化版）",
        absent_effect="测评照常跑、分数照常落本地，只是少一条 trace 直链与远端数据集",
        # 平台不自带这套栈：本机已经有一份（~/Documents/eval-platform 的 docker 栈，
        # :3000），再在本仓库 compose 里起一份会撞端口、还得多养 6 个容器。所以这一行
        # 只需回答「去哪拿」，而不是自己维护一份 YAML。
        #
        # 汉化版是配套的 fork（eval_puls，界面中英切换）。它**只换 web 一个镜像**，
        # worker/postgres/clickhouse/minio/redis 与数据卷都不动——是替换件，不是另一套
        # 部署方式，因此值得写在原版前面：中文用户拿到手就能读。
        #
        # 「未发布镜像」四个字是必要的：tag 挂在官方 Docker Hub 组织名下
        # （langfuse/langfuse:*-zh），但没有推上去，`docker pull` 会拿到官方原版或
        # not found。不写清楚，用户会先在 pull 上撞一次墙才回来找构建命令。
        #
        # 后半句的 dual 写模式是给 v4 打的补丁，值得占这一行：本平台的测评上报是
        # **手写 ingestion 事件**（langfuse_client.py，自己拼 trace-create/span-create
        # 走 POST /api/public/ingestion），而 v4 的 events_only 模式会对这类事件
        # 返回 400。症状是「分数上得去、轨迹上不去、批次页看着正常但 trace 直链是空的」
        # ——正是这个仓库最想避免的那种静默失败，所以在配置入口就说破。
        fix_hint="汉化版（配套 fork，界面中英切换，基线 v4.36.1）：git clone -b v4-zh "
                 "https://github.com/990505-a/eval_puls，再 docker build -f web/Dockerfile "
                 "-t langfuse/langfuse:4.36.1-zh .，compose 里只换 langfuse-web 的 image"
                 "（未发布镜像，需本地构建；worker 留在官方 :4）。v4 的写模式要留 "
                 "dual：本平台手写 ingestion 事件，events_only 会让轨迹静默丢失。"
                 "起好后在设置页填 key",
        probe=_probe_langfuse,
        settings_keys=("langfuse_enabled", "langfuse_base_url", "langfuse_public_key",
                       "langfuse_secret_key", "langfuse_environment"),
    ),
    Integration(
        key="feishu",
        label="飞书（lark-cli）",
        kind="external",
        optional=True,
        summary="用例文档导出到飞书思维导图 / 从飞书文档拉需求",
        absent_effect="用例导出与需求拉取不可用（用例在平台内照常编写）",
        fix_hint="npm install -g @larksuite/cli 后在设置页发起登录（需 Node.js）",
        probe=_probe_feishu,
        settings_keys=("lark_cli_bin", "lark_cli_identity"),
    ),
    Integration(
        key="llm",
        label="对话模型",
        kind="external",
        optional=False,
        summary="平台的主模型（任意 OpenAI 兼容端点，留空回退 DeepSeek 官方）",
        absent_effect="所有智能体对话都不工作",
        fix_hint="在设置页「模型」填 API Key（或 .env 的 DEEPSEEK_API_KEY）",
        probe=_probe_llm,
        settings_keys=("llm_model", "llm_base_url", "llm_api_key"),
    ),
)

BY_KEY: dict[str, Integration] = {i.key: i for i in INTEGRATIONS}


async def probe(key: str) -> dict:
    """单个依赖的就绪状态；未知 key 返回 not-ready 而不是抛异常。"""
    item = BY_KEY.get(key)
    if item is None:
        return {"key": key, "ready": False, "error": f"未登记的外部依赖: {key}"}
    try:
        result = await item.probe()
    except Exception as exc:  # noqa: BLE001 — 探针失败不该让整页 500
        logger.warning("集成 %s 探针失败: %s", key, exc)
        return {"key": key, "ready": False, "error": f"探针异常：{exc}"}
    return {"key": key, "label": item.label, "kind": item.kind,
            "optional": item.optional, "summary": item.summary,
            "absent_effect": item.absent_effect,
            "fix_hint": item.fix_hint, "launch": item.launch,
            "install": item.install, **result}


async def probe_all() -> list[dict]:
    """所有依赖的就绪状态（并发探活；页面一屏看完）。"""
    import asyncio

    na_keys, results = await asyncio.gather(
        not_applicable_keys(),
        asyncio.gather(*(probe(i.key) for i in INTEGRATIONS)))
    return [{**item, "not_applicable": True} if item.get("key") in na_keys else item
            for item in results]


# ===========================================================================
# 「这台机器不跑它」——不适用标记
# ===========================================================================
# 为什么需要：远端服务器上永远不会有 Unity 编辑器，那条依赖就永远挂在"未就绪"。
# 一个修不好的红项会让用户怀疑整页的可信度（"其他绿的是不是也不准"）。
# 标记后降级成中性的「不适用」：不进 blocking、不给动作按钮、随时可恢复。
#
# 存 settings_kv(platform, na_<key>)="1"：这是**按部署**的事实（哪台机器跑什么），
# 与 .env 无关，所以只写库、不同步 .env。
#
# 刻意不自动判定："本机没装 Unity"这种推断一旦判错，代价是把真问题藏起来；
# 只把它当**提示**（见 _probe_unity 的 na_hint），决定权留给用户。

_NA_NAMESPACE = "platform"
_NA_PREFIX = "na_"


def na_setting_key(key: str) -> str:
    """该依赖的「不适用」标记在 settings_kv 里的键名。"""
    return f"{_NA_PREFIX}{key}"


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "on", "yes")


async def not_applicable_keys() -> set[str]:
    """已标记为「不适用」的依赖 key。

    读不到就当空集（fail-open）：宁可多显示一个待办，也不要因为一次读库失败
    把用户真正的故障悄悄藏起来。
    """
    try:
        from src.app.db.database import async_session_factory
        from src.app.services.settings_service import SettingsService

        defaults = {na_setting_key(i.key): "" for i in INTEGRATIONS}
        async with async_session_factory() as db:
            values = await SettingsService(db).get_namespace(_NA_NAMESPACE, defaults)
        return {k[len(_NA_PREFIX):] for k, v in values.items()
                if k.startswith(_NA_PREFIX) and _is_truthy(v)}
    except Exception as exc:  # noqa: BLE001 — 就绪中心不该因为读库失败整页报错
        logger.warning("读取「不适用」标记失败: %s", exc)
        return set()


async def set_applicability(key: str, applicable: bool) -> dict:
    """标记/取消某个依赖的「不适用」。返回更新后的单条状态。"""
    if key not in BY_KEY:
        return {"success": False, "error": f"未登记的外部依赖: {key}"}
    try:
        from src.app.db.database import async_session_factory
        from src.app.services.settings_service import SettingsService

        async with async_session_factory() as db:
            await SettingsService(db).set(
                _NA_NAMESPACE, na_setting_key(key), None if applicable else "1")
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"写入标记失败: {exc}"}
    return {"success": True, "item": await probe(key), "applicable": applicable}


# ===========================================================================
# 就绪缓存：装配层每轮都要问"这个能力依赖的东西在线吗"
# ===========================================================================
# 探针是网络调用（Unity 还要问一次 Play Mode），不能每轮都打。TTL 内复用上次结果：
# 依赖刚起来时最多晚 TTL 秒才恢复工具面，这个代价换掉"每轮一次探活"很划算。

_READINESS_TTL = 20.0
_readiness: dict[str, tuple[float, bool]] = {}


async def ensure_fresh(keys: "set[str] | frozenset[str] | tuple[str, ...]") -> None:
    """过期就重探（并发）。探不出来的按"就绪"处理——宁可多给工具，也别因为
    一次探活抖动把能力藏掉。"""
    import asyncio
    import time

    now = time.monotonic()
    stale = [k for k in keys
             if k in BY_KEY and now - _readiness.get(k, (0.0, True))[0] > _READINESS_TTL]
    if not stale:
        return
    results = await asyncio.gather(*(probe(k) for k in stale))
    for item in results:
        _readiness[item["key"]] = (time.monotonic(), bool(item.get("ready")))


def readiness_snapshot(keys: "set[str] | frozenset[str] | tuple[str, ...]") -> dict[str, bool | None]:
    """缓存里的就绪状态；``None`` = 还没探过（调用方按"就绪"处理）。"""
    return {k: (_readiness[k][1] if k in _readiness else None) for k in keys}


def missing_reason(key: str) -> str:
    """未就绪时给模型/用户的一句话（用注册表里的固定说法）。"""
    item = BY_KEY.get(key)
    return f"{item.label}：{item.fix_hint}" if item else key


# ===========================================================================
# 启动器代理：能一键启动的依赖，由后端转调启动器（:5010）
# ===========================================================================
# 浏览器直连启动器会撞跨端口 CORS，所以统一由后端转发——与
# api/v2/agents.py 的"重启 LangGraph"是同一条路子（那边也改用这个函数）。

async def launcher_action(service: str, action: str) -> dict:
    """让启动器对某个服务做 start/stop/restart；永不抛异常。"""
    url = f"{settings.launcher_url.rstrip('/')}/api/services/{service}/{action}"
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            resp = await client.post(url)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
    except Exception as exc:  # noqa: BLE001 — 起不来不该 500，要给一句人话
        return {"success": False,
                "error": f"启动器不可达（{settings.launcher_url}）：{exc}",
                "hint": "容器模式没有启动器(:5010)，请用 compose 启动对应服务。"}
