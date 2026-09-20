"""接线断言：证明"声明的东西真的接上了"，而不是只测行为。

这个平台出现过的故障有共同形状——**东西建好了，但没接上**：

- 配置项建了，没有任何代码读它（`game_repo_path` / `eval_max_repair`）；
- 端点写了，没有任何调用方（`extract-pdf-text` / `feishu/docs/fetch` / 整条
  `attachments`+`projects`+`configurations` 纵切面）；
- 能力声明了依赖，但依赖是纯文本、没有程序读（`Capability.requires` /
  `mcp_servers`）；
- 同一份字段清单前后端各写一份，必然漂移（`PLATFORM_KEYS` 21 项 vs 前端 15 项）；
- 前端把"填了没用"的输入框摆在设置页上（`game_repo_path`）。

行为测试（给输入 X、断言输出 Z）永远抓不到这一类：它们全都"能跑"。所以这里
全部是**纯静态检查**——毫秒级、不起服务、不连网络，直接进现有 pytest。

**白名单是这套检查的核心设计**：它把"孤立"从意外变成决定。一个东西要么有
调用方/读取方，要么必须被显式列在下面的白名单里并写明理由。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEBUI = ROOT / "webui" / "src"

# ---------------------------------------------------------------------------
# 读取源码（缓存，避免每个测试重复遍历）
# ---------------------------------------------------------------------------
_py_sources: dict[Path, str] | None = None
_web_sources: dict[Path, str] | None = None


def py_sources() -> dict[Path, str]:
    global _py_sources
    if _py_sources is None:
        _py_sources = {
            p: p.read_text(encoding="utf-8", errors="replace")
            for p in (ROOT / "src").rglob("*.py")
            if "__pycache__" not in str(p)
        }
        for extra in ("launcher.py", "start_server.py"):
            p = ROOT / extra
            if p.exists():
                _py_sources[p] = p.read_text(encoding="utf-8", errors="replace")
    return _py_sources


def web_sources() -> dict[Path, str]:
    global _web_sources
    if _web_sources is None:
        _web_sources = {
            p: p.read_text(encoding="utf-8", errors="replace")
            for p in WEBUI.rglob("*")
            if p.suffix in (".ts", ".tsx")
        }
    return _web_sources


def _py_blob() -> str:
    return "\n".join(py_sources().values())


def _web_blob() -> str:
    return "\n".join(web_sources().values())


# ===========================================================================
# 1. 设置项：每个可写的 key 必须有读取方
# ===========================================================================

# 这些 key 被读取，但读法是动态拼接（`getattr(settings, f"langfuse_monitor_{field}")`），
# 静态扫不到整名。见 src/app/monitoring/tracing.py 的 _ENV_FIELDS。
_DYNAMIC_READ_KEYS = {
    "langfuse_monitor_enabled",
    "langfuse_monitor_base_url",
    "langfuse_monitor_public_key",
    "langfuse_monitor_secret_key",
    "langfuse_monitor_environment",
}


def test_every_settings_key_is_read_somewhere():
    """设置页/设置 API 能写的每个 key，都得有代码真的读它。

    「能写没人读」就是设置页上那个"填了没用"的输入框。违反时的修法只有两种：
    接上读取方，或者把这个 key 删掉。
    """
    from src.app.services.settings_service import (
        JUDGE_KEYS,
        LANGFUSE_KEYS,
        LANGFUSE_MONITOR_KEYS,
        MODEL_KEYS,
        PLATFORM_KEYS,
    )

    blob = _py_blob()
    namespaces = {
        "model": MODEL_KEYS,
        "platform": PLATFORM_KEYS,
        "langfuse": LANGFUSE_KEYS,
        "langfuse_monitor": LANGFUSE_MONITOR_KEYS,
        "judge": JUDGE_KEYS,
    }

    unread: list[str] = []
    for namespace, keys in namespaces.items():
        for key in keys:
            if key in _DYNAMIC_READ_KEYS:
                continue
            # 读取形态：settings.<key> / cfg.<key> / self.<key>
            if re.search(r"(?:settings|cfg|config|self)\." + re.escape(key) + r"\b", blob):
                continue
            unread.append(f"{namespace}.{key}")

    assert not unread, (
        "以下设置项可写但没有任何读取方（填了没用）：\n  "
        + "\n  ".join(sorted(unread))
        + "\n修法：接上读取方，或从对应 *_KEYS 里删掉。"
    )


def test_settings_page_fields_match_backend_keys():
    """前端设置页的字段清单必须与后端 PLATFORM_KEYS 一致。

    两份手写清单必然漂移（曾经 21 vs 15），漂移的一个直接后果就是设置页上
    出现了没人读的 `game_repo_path`。增加/删除平台配置时两边一起改；
    确实由**别的页面**提供入口的，登记到下面这张表并写明去处。
    """
    from src.app.services.settings_service import PLATFORM_KEYS

    # key -> 它的 UI 入口在哪（不在这份清单里的必须有去处）
    ui_elsewhere = {
        "codebase_schedule_enabled": "/codebase 页「定时任务」Tab",
        "codebase_interval_hours": "/codebase 页「定时任务」Tab",
        "codebase_analyze_enabled": "/codebase 页「定时任务」Tab",
        # 代码图谱引擎由平台自管安装（services/cbm_install.py）：状态与「安装/升级」
        # 在 /codebase 页，设置页不再摆一个会静默覆盖自管安装的路径输入框。
        # 手动指定路径的逃生口仍在（.env 的 CODEBASE_MEMORY_EXE），且一旦指定，
        # 就绪中心会显示"实际用的是哪个 + 改成平台自管版本"的按钮。
        "codebase_memory_exe": "/codebase 页状态卡（平台自管安装）；仅 .env 可覆盖",
        "codebase_graph_port": "内部实现：图守护由平台按需拉起，默认 9749（.env 可改）",
        # 记忆的两个层级开关都收在 /memories 页：模块开关 + 顶部「记忆总闸」
        # （总闸不是官方概念，是排障闸——关掉它模型连"有记忆"都不知道）
        "memory_enabled": "/memories 页顶部「记忆总闸」开关",
        # LightRAG 的配置全部搬到了 LightRAG 自带界面里的「RAG 设置」页
        # （tools/lightrag-ui，由启动器注入到它的 WebUI 目录；入口也在 /rag 页）。
        # 为什么不在设置页：这些值是**启动 LightRAG 进程的环境变量**，改完必须重启
        # 那几个实例才生效，摆在平台设置页会让人以为存了就生效。
        "lightrag_base_url": "LightRAG 界面「RAG 设置」页（知识库清单决定端口）；.env 仅作种子",
        "lightrag_working_dir": "LightRAG 界面「RAG 设置」页（各库按 workspace 分子目录）",
        "lightrag_llm_base_url": "LightRAG 界面「RAG 设置」页",
        "lightrag_llm_model": "LightRAG 界面「RAG 设置」页",
        "lightrag_llm_api_key": "LightRAG 界面「RAG 设置」页（留空继承主模型）",
        "lightrag_embedding_base_url": "LightRAG 界面「RAG 设置」页",
        "lightrag_embedding_model": "LightRAG 界面「RAG 设置」页",
        "lightrag_embedding_api_key": "LightRAG 界面「RAG 设置」页",
        "lightrag_embedding_dim": "LightRAG 界面「RAG 设置」页（必须与 embedding 模型一致）",
    }

    page = (WEBUI / "app" / "settings" / "page.tsx").read_text(encoding="utf-8")
    block = page.split("const PLATFORM_FIELDS", 1)[1].split("];", 1)[0]
    shown = set(re.findall(r'key:\s*"([^"]+)"', block))

    backend = set(PLATFORM_KEYS)
    missing_ui = backend - shown - set(ui_elsewhere)
    unknown_ui = shown - backend

    assert not missing_ui, (
        "后端可写但设置页没有入口（只能手改 .env）：\n  "
        + "\n  ".join(sorted(missing_ui))
        + "\n修法：加到 PLATFORM_FIELDS，或登记进 ui_elsewhere 说明入口在哪。"
    )
    assert not unknown_ui, (
        "设置页有输入框但后端不接受（保存会被忽略）：\n  "
        + "\n  ".join(sorted(unknown_ui))
    )


# ===========================================================================
# 2. 能力声明：符号 / 技能 / MCP 都得解析得开
# ===========================================================================

def test_capability_tool_symbols_resolve():
    """能力清单里的工具符号必须能解析成真的工具。"""
    from src.app.agents.capabilities import CAPABILITIES

    broken: list[str] = []
    for cap in CAPABILITIES:
        for spec in cap.tool_specs():
            try:
                from src.app.agents.capabilities import _import_symbol

                _import_symbol(spec)
            except Exception as exc:  # noqa: BLE001
                broken.append(f"{cap.key}: {spec} ({type(exc).__name__}: {exc})")

    assert not broken, "能力清单里的工具符号解析失败：\n  " + "\n  ".join(broken)


def test_capability_skills_exist_on_disk():
    """能力声明的技能必须在技能库里有对应目录（否则提示词让模型读一个不存在的文件）。"""
    from src.app.agents.capabilities import CAPABILITIES

    skill_root = ROOT / "src" / "app" / "skills"
    missing: list[str] = []
    for cap in CAPABILITIES:
        for skill in cap.skills:
            if not (skill_root / skill / "SKILL.md").is_file():
                missing.append(f"{cap.key}: {skill}")

    assert not missing, "能力声明的技能在 src/app/skills/ 下不存在：\n  " + "\n  ".join(missing)


def test_capability_mcp_servers_are_registered():
    """能力声明的 MCP server 必须在 MCP 客户端里注册过。

    `mcp_servers` 曾经是个空字段——RAG 的 MCP server 建好了、配置页也有，
    但没有任何能力声明它，于是配好之后 agent 根本用不到。要么真接上，要么别声明。
    """
    from src.app.agents.capabilities import CAPABILITIES

    declared = {s for cap in CAPABILITIES for s in cap.mcp_servers}
    if not declared:
        pytest.skip("当前没有任何能力声明 MCP server（RAG 的接入尚未定案）")

    from src.app.mcp.mcp_client import get_mcp_client  # noqa: F401
    import inspect

    src = inspect.getsource(get_mcp_client.__module__ and __import__(
        "src.app.mcp.mcp_client", fromlist=["x"]))
    unknown = [s for s in declared if f'"{s}"' not in src]
    assert not unknown, (
        "能力声明的 MCP server 没有在 mcp_client 里注册：\n  "
        + "\n  ".join(sorted(unknown))
    )


def test_every_tool_function_is_reachable():
    """每个 @tool 函数都得出现在能力清单（或其解析路径）里。

    不在清单里的 @tool 永远不会进工具面 —— 它只是一段死代码，
    却看起来像个可用工具。
    """
    import src.app.agents  # noqa: F401  确保 agents 包已导入

    tool_files: dict[str, Path] = {}
    for path, text in py_sources().items():
        if "src/app" not in str(path):
            continue
        for match in re.finditer(
            r"@tool(?:\([^)]*\))?\s*\n(?:#[^\n]*\n)*\s*(?:async\s+)?def\s+([a-z_][a-z0-9_]*)",
            text,
        ):
            tool_files[match.group(1)] = path

    agents_blob = "\n".join(
        text for path, text in py_sources().items() if "src/app/agents" in str(path)
    )
    orphans = sorted(
        f"{name} ({path.relative_to(ROOT)})"
        for name, path in tool_files.items()
        if not re.search(r"\b" + re.escape(name) + r"\b", agents_blob)
    )

    assert not orphans, (
        "以下 @tool 函数不在能力清单里，永远不会进工具面：\n  "
        + "\n  ".join(orphans)
        + "\n修法：在 agents/capabilities.py 里声明，或删掉这个工具。"
    )


# ===========================================================================
# 3. HTTP 端点：每个 /api/v2 路由都得有调用方
# ===========================================================================

# 这些端点**有意**没有前端调用方，保留给外部脚本 / 验收测试 / 反向代理。
# 加进来时必须写明用途，否则下一个读代码的人没法判断它是不是又一个孤儿。
_EXTERNAL_ENDPOINTS = {
    "/api/v2/auth/login": "外部脚本与 Playwright 验收测试登录用（界面已无登录）",
    "/api/v2/auth/logout": "同上",
    "/api/v2/auth/me": "同上",
    "/api/v2/auth/users": "用户管理 API，界面未提供入口（外部脚本用）",
    "/api/v2/auth/change-password": "同上",
    "/api/v2/auth/change-username": "同上",
    "/api/v2/agents/reload": "装配页「重新加载工具池」经启动器转发（非直连）",
    "/api/v2/web-ui-auto/report/{run_id}/{sig}/{path:path}": "浏览器直取的签名 URL，由 <iframe>/download 发起",
    "/api/v2/web-ui-auto/artifact/{run_id}/{path:path}": "同上（进程内直出产物）",
    "/api/v2/unity-auto/artifact/{run_id}/{index}": "同上：<img>/<video> 的签名 URL，由后端产物清单直接给出",
    "/api/v2/rag/settings": "LightRAG 自带界面里的「RAG 设置」页调用（静态页在 tools/lightrag-ui，"
                            "由启动器注入到它的 WebUI 目录）——不在 Next 前端里，故静态扫不到",
}


def _route_regex(route: str) -> str:
    """把 FastAPI 路径转成能在前端源码里搜的宽松正则（路径参数匹配任意片段）。"""
    stripped = route[len("/api/v2"):]
    parts = re.split(r"(\{[^}]+\})", stripped)
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        out.append(r"[^`\"'?\s]{0,120}" if part.startswith("{") else re.escape(part))
    return "".join(out)


def test_every_api_route_has_a_caller():
    """每个 /api/v2 路由要么被前端调用，要么在 _EXTERNAL_ENDPOINTS 里写明理由。

    孤儿的代价不是"多几行代码"：`extract-pdf-text` 被注释当成"前端兜底"引用了
    三个月，而前端从来没调过它——文档和现实脱节得毫无察觉。
    """
    from src.app.api import api_router

    routes = sorted({r.path for r in api_router.routes if r.path.startswith("/api/v2")})
    blob = _web_blob()

    orphans: list[str] = []
    for route in routes:
        if route in _EXTERNAL_ENDPOINTS:
            continue
        if re.search(_route_regex(route), blob):
            continue
        # 兜底：前端常把最后一段当变量传（如 useWorkflowAction("lint") 拼
        # `/case-docs/${name}/${path}`），此时整条路径搜不到，但末段字面量在。
        tail = route.rstrip("/").rsplit("/", 1)[-1]
        if not tail.startswith("{") and re.search(r'["\'`]' + re.escape(tail) + r'["\'`]', blob):
            continue
        orphans.append(route)

    assert not orphans, (
        "以下端点没有任何前端调用方，也不在白名单里：\n  "
        + "\n  ".join(orphans)
        + "\n修法：接上前端，删掉，或加进 _EXTERNAL_ENDPOINTS 并写明用途。"
    )


# ===========================================================================
# 4. 前端 API 层：导出的 hook 得有使用方
# ===========================================================================

def test_lib_api_exports_are_used():
    """webui/src/lib/api/*.ts 里导出的每个 hook 都要有人用。

    整个 `useConfigurations.ts`（6 个 hook + 一整套后端 API）曾经完全没有 UI，
    却一直躺在那里像是可用功能。
    """
    api_dir = WEBUI / "lib" / "api"
    if not api_dir.is_dir():
        pytest.skip("没有 lib/api 目录")

    others = "\n".join(
        text for path, text in web_sources().items()
        if path.parent.name != "api" or path.suffix == ".tsx"
    )
    orphans: list[str] = []
    for path in sorted(api_dir.glob("*.ts")):
        text = path.read_text(encoding="utf-8", errors="replace")
        exported = re.findall(
            r"export\s+(?:async\s+)?(?:function|const)\s+([A-Za-z_][A-Za-z0-9_]*)", text
        )
        for name in exported:
            if not re.search(r"\b" + re.escape(name) + r"\b", others):
                orphans.append(f"{name} ({path.name})")

    assert not orphans, (
        "以下 lib/api 导出没有任何使用方：\n  "
        + "\n  ".join(sorted(orphans))
        + "\n修法：接上页面，或删掉。"
    )


# ---------------------------------------------------------------------------
# 外部依赖：注册表是唯一描述处，其余三处必须与它一致
# ---------------------------------------------------------------------------
# 这一组针对的是本文开头那个"四处描述、无人对齐"的病：同一个依赖写在
# (1) 设置页字段 (2) 启动器服务表 (3) MCP 清单 (4) 能力里的中文散文。
# 现在描述收敛到 core/integrations.py 的注册表，下面证明其余各处跟着它走。

def test_integration_launch_names_exist_in_launcher():
    """注册表里能"一键启动"的依赖，启动器里必须有同名服务。

    以前 playwright 执行器就是反例：命令在仓库里、依赖也现成，却不在启动器
    服务表里，只能手工跑脚本 —— 于是"重启机器后 Web-UI 自动化连不上"成了偶发故障。

    服务名现在是**现算**的（知识库按注册表一库一条，见 services/rag_kbs.py），
    静态正则扫不到动态拼出来的名字，所以这里直接问启动器要服务表。
    """
    import importlib.util
    import sys

    from src.app.core import integrations

    spec = importlib.util.spec_from_file_location("_launcher_under_test",
                                                 ROOT / "launcher.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 必须先登记进 sys.modules：launcher.py 里有 dataclass，而 dataclasses 是通过
    # sys.modules[cls.__module__] 找注解所在模块的，没登记就会 AttributeError。
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        declared = {s.name for s in module._default_services()}
    finally:
        sys.modules.pop(spec.name, None)
    missing = [i.launch for i in integrations.INTEGRATIONS
               if i.launch and i.launch not in declared]
    assert not missing, (
        f"注册表声明可启动但启动器没有这些服务：{missing}\n"
        "修法：在 launcher.py 的 _default_services() 里加一条 ServiceSpec。"
    )


def test_capability_requires_are_registered_integrations():
    """能力声明的依赖 key 必须在注册表里存在。

    ``requires`` 从中文散文改成机器可读的 key 之后，"写错一个 key"会静默失效
    （查不到 → 当成没依赖 → 工具照给）—— 这条把它变成硬失败。
    """
    from src.app.agents.capabilities import CAPABILITIES
    from src.app.core import integrations

    unknown = sorted({key for cap in CAPABILITIES for key in cap.requires
                      if key not in integrations.BY_KEY})
    assert not unknown, (
        f"能力里引用了未登记的外部依赖：{unknown}\n"
        "修法：在 core/integrations.py 的 INTEGRATIONS 里登记，或改对 key。"
    )


def test_integration_settings_keys_are_real():
    """注册表登记的 settings_keys 必须是真实配置项（没有错别字）。"""
    from src.app.core import integrations
    from src.app.core.config import Settings

    fields = set(Settings.model_fields)
    unknown = sorted({key for item in integrations.INTEGRATIONS
                      for key in item.settings_keys if key not in fields})
    assert not unknown, f"注册表里的 settings_keys 不是配置项：{unknown}"


def test_every_integration_has_probe_and_fix_hint():
    """每一行都要能探活、能给出人话补救办法 —— 否则就绪中心那行是死的。"""
    from src.app.core import integrations

    broken = [i.key for i in integrations.INTEGRATIONS
              if i.probe is None or not i.fix_hint.strip() or not i.absent_effect.strip()]
    assert not broken, f"这些依赖缺 probe/fix_hint/absent_effect：{broken}"


def test_every_install_key_has_an_installer():
    """注册表声明的 ``install`` 键，API 的分派表里必须有同名实现。

    反例就是这次修掉的：注册表给 playwright 填了 ``install="playwright"``，而 API 里
    还是 ``if item.install != "codebase-memory"`` 的写死判断 —— 前端按钮**会出现**
    （它只看 ``item.install`` 有没有值），点下去却回"不支持平台内安装"。用户看到的是
    "有个按钮，点了没用"，比没有按钮更糟。这条把它变成硬失败。
    """
    from src.app.api.v2.integrations import INSTALLERS
    from src.app.core import integrations

    declared = {i.install for i in integrations.INTEGRATIONS if i.install}
    missing = sorted(declared - set(INSTALLERS))
    assert not missing, (
        f"注册表声明了平台内安装但 API 没有实现：{missing}\n"
        "修法：在 api/v2/integrations.py 的 INSTALLERS 里加一条，或去掉注册表的 install。"
    )
    orphan = sorted(set(INSTALLERS) - declared)
    assert not orphan, f"INSTALLERS 里有注册表没声明的键（永远不会被调到）：{orphan}"


def test_not_applicable_setting_key_roundtrip():
    """「不适用」标记的键名规则与真值解析。

    这个标记决定"这一项算不算缺失"，写错键名会让标记静默失效（用户点了按钮、
    刷新后还是红的），所以把规则本身钉住。
    """
    from src.app.core import integrations

    assert integrations.na_setting_key("unity") == "na_unity"
    for truthy in ("1", "true", "ON", "yes", " Yes "):
        assert integrations._is_truthy(truthy), f"{truthy!r} 应判为真"
    for falsy in ("", "0", "false", "off", None, "no"):
        assert not integrations._is_truthy(falsy), f"{falsy!r} 应判为假"


def test_not_applicable_is_fail_open_on_db_error(monkeypatch):
    """读标记失败时按"没有标记"处理（fail-open）。

    反过来的话（读不到就当全部不适用），一次读库抖动会把用户真正的故障悄悄藏起来
    —— 就绪中心宁可多显示一个待办，也不能瞒报。
    """
    import asyncio

    from src.app.core import integrations

    class Boom:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("库连不上")

    monkeypatch.setattr("src.app.db.database.async_session_factory", Boom)
    assert asyncio.run(integrations.not_applicable_keys()) == set()


def test_optional_dependencies_are_the_only_ones_markable_na():
    """必选依赖不该出现在"可标记不适用"的范围内（前端按钮的判据）。

    必选件缺了就是真故障，给它一条"标记为不适用"的逃避路径等于允许把故障藏起来。
    这条锁定判据本身：markable = 未就绪 + optional。
    """
    from src.app.core import integrations

    required = [i.key for i in integrations.INTEGRATIONS if not i.optional]
    assert required, "至少应有一个必选依赖（对话模型）"
    # 前端 ReadinessCenter 的按钮条件是 `!ready && optional && !na`，
    # 这里只钉住"必选件存在且不该被标记"这个前提，避免有人把 optional 全改 True
    assert "llm" in required, "对话模型必须是必选（缺了所有智能体都不工作）"


def test_unity_capability_is_lua_free():
    """Unity 能力不能再依赖游戏侧的 Lua 桥（2026-09 换成了通用 MCP 桥）。

    旧版整包建立在 LuaRemoteServer 上：执行任意 Lua、窗口名、GM 命令全是那一款
    游戏的知识，换游戏就作废。这条守住三件事：工具名里没有 lua、技能目录不带
    vendored python 层、能力声明的 MCP server 真的在客户端里注册过。
    """
    from src.app.agents.capabilities import CAPABILITY_BY_KEY

    unity = CAPABILITY_BY_KEY["unity"]
    lua_tools = [t for t in unity.tools if "lua" in t.lower()]
    assert not lua_tools, f"Unity 能力里还有 Lua 工具：{lua_tools}"

    skill_dir = ROOT / "src" / "app" / "skills" / "unity-ui-test"
    stray = sorted(p.name for p in skill_dir.rglob("*.py"))
    assert not stray, f"unity-ui-test 里还有 vendored python 层：{stray}"

    assert unity.mcp_servers == ("unity",)
    assert "unity" in (ROOT / "src" / "app" / "mcp" / "mcp_client.py").read_text(encoding="utf-8")


def test_unity_bridge_is_the_only_unity_transport():
    """旧配置项（unity_host / unity_port）必须删干净：留着就会有页面往里写值，
    而桥只读 UNITY_MCP_*，表现为"改了不生效"。"""
    from src.app.core.config import Settings
    from src.app.services.settings_service import PLATFORM_KEYS

    fields = set(Settings.model_fields)
    assert not {"unity_host", "unity_port"} & fields
    assert not {"unity_host", "unity_port"} & set(PLATFORM_KEYS)
    assert {"unity_mcp_url", "unity_mcp_transport",
            "unity_mcp_command", "unity_mcp_server"} <= fields


def test_env_reload_sits_above_memory_injection_in_the_onion():
    """``.env`` 热更新中间件必须在记忆注入之外（更靠外 = 先执行）。

    为什么是硬约束：记忆中间件在 ``before_agent`` 就按 ``settings.memory_enabled``
    算出"这次读哪些文件"，而 ``.env`` 是热更新中间件在读。两者顺序反了，用户刚在
    「Agent 记忆」页关掉总闸，第一轮仍会注入记忆（实测过：关闸后第一轮 state 里
    还有 6 份 memory_contents）——页面写的"下一轮生效"就成了假的。
    """
    from src.app.agents.harness import build_middleware
    from src.app.middleware.live_model_reload import LiveModelReloadMiddleware
    from src.app.middleware.memory_injection import MemoryInjectionMiddleware

    order = [type(m) for m in build_middleware()]
    assert LiveModelReloadMiddleware in order, "热更新中间件不在洋葱里"
    assert MemoryInjectionMiddleware in order, "记忆中间件不在洋葱里"
    assert order.index(LiveModelReloadMiddleware) < order.index(MemoryInjectionMiddleware), (
        "热更新中间件必须排在记忆中间件之前（更靠外），否则总闸要等下一轮才生效")


def test_hot_reload_wrapper_runs_at_agent_start():
    """光有顺序不够：热更新还必须在 ``before_agent`` 也刷一次。

    ``wrap_model_call`` 里的那次发生在 before_agent 之后，救不了 sources。
    """
    from src.app.middleware.live_model_reload import LiveModelReloadMiddleware

    cls = LiveModelReloadMiddleware
    assert callable(getattr(cls, "before_agent", None))
    assert callable(getattr(cls, "abefore_agent", None))
