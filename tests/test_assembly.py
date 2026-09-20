"""装配目录（智能体 → 能力 → 工具/技能/权限）的测试。

覆盖三层：
1. 存储 ``services/assembly_service.py`` —— 播种、往返、坏文件降级、校验、恢复默认
2. 中间件 ``middleware/assembly.py`` —— 按智能体过滤工具面、重写能力段、技能并集
3. 装配面 —— 一个 graph 服务任意多个智能体；旧 graph 不受影响
"""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import SystemMessage

from src.app.agents.capabilities import (
    CAPABILITY_BY_KEY,
    CAPABILITIES,
    CAPABILITY_SECTION_CLOSE,
    CAPABILITY_SECTION_OPEN,
    CHAT_CAPABILITIES,
    build_system_prompt,
    resolve_tools,
)
from src.app.core.config import settings
from src.app.services import assembly_service as asm

# ------------------------------------------------------------------ fixtures


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """把 workspace 指到 tmp，装配文件随之隔离。"""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "ws")
    asm.invalidate_cache()
    yield tmp_path / "ws"
    asm.invalidate_cache()


def _request(tools, system_message):
    """真 ModelRequest（不是桩）：中间件只碰 system_message 与 tools 两个字段。"""
    from langchain.agents.middleware.types import ModelRequest

    return ModelRequest(
        model=None,
        messages=[],
        system_message=SystemMessage(content=system_message),
        tool_choice=None,
        tools=list(tools),
        response_format=None,
        state={},
        runtime=None,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """假装本次会话挂载了一个仓库（代码分析的图谱工具需要它才出现）。"""
    from src.app.agents import workspace_backend

    path = tmp_path / "repo"
    path.mkdir()
    monkeypatch.setattr(workspace_backend, "mounted_workspace_path", lambda: str(path))
    return path


def _no_repo(monkeypatch):
    """明确"没挂仓库"（不依赖测试环境恰好有没有 run 上下文）。"""
    from src.app.agents import workspace_backend

    monkeypatch.setattr(workspace_backend, "mounted_workspace_path", lambda: "")


def _all_tools():
    return resolve_tools(CAPABILITIES)


def _middleware():
    from src.app.middleware.assembly import AssemblyToolsMiddleware

    return AssemblyToolsMiddleware()


def _names(tools):
    return sorted(getattr(t, "name", "?") for t in tools)


def _agent(id_: str, *caps: str, label: str = "", description: str = "") -> asm.AgentDef:
    return asm.AgentDef(id=id_, label=label or id_, description=description,
                        capabilities=tuple(caps))


def _cap(key: str, **kw) -> asm.CapabilityDef:
    return asm.CapabilityDef(key=key, label=kw.pop("label", key), **kw)


# ------------------------------------------------------------------ 存储层


def test_seeds_from_the_code_manifest(ws):
    """文件不存在 → 用代码清单播种：一个通用智能体 + 全部能力。"""
    catalog = asm.load_catalog()
    assert [a.id for a in catalog.agents] == [asm.DEFAULT_AGENT_ID]
    assert {c.key for c in catalog.capabilities} == {c.key for c in CAPABILITIES}
    assert catalog.agent(asm.DEFAULT_AGENT_ID).capabilities == tuple(c.key for c in CAPABILITIES)
    # 技能与审批项都从清单里带过来了
    testcase = catalog.capability("testcase")
    assert "testcase-workflow" in testcase.skills
    assert "large-system-testing" in testcase.skills
    assert set(testcase.gated) == {"approve_case_document", "release_case_document"}


def test_save_then_load_roundtrip(ws):
    asm.save_catalog(asm.Catalog(
        agents=(_agent("ops", "webui", label="上线助手", description="只管 Web-UI"),),
        capabilities=(_cap("webui", label="Web-UI 自动化", tools=("x:y",), skills=("web-ui-test",)),),
    ))
    catalog = asm.load_catalog()
    assert [a.id for a in catalog.agents] == ["ops"]
    assert catalog.agent("ops").label == "上线助手"
    assert catalog.capability("webui").tools == ("x:y",)
    assert asm.assembly_path().is_file()


def test_external_edit_is_picked_up(ws):
    """另一个进程改了文件（FastAPI 保存 / 手工编辑）→ 下一轮读到新的。"""
    asm.save_catalog(asm.Catalog(
        agents=(_agent("a", "webui"),),
        capabilities=(_cap("webui", tools=("m:s",)),),
    ))
    assert asm.load_catalog().capability("webui").tools == ("m:s",)

    path = asm.assembly_path()
    payload = json.loads(path.read_text("utf-8"))
    payload["capabilities"][0]["tools"] = ["other:tool"]
    path.write_text(json.dumps(payload), "utf-8")

    assert asm.load_catalog().capability("webui").tools == ("other:tool",)


def test_broken_file_falls_back_to_seed(ws):
    path = asm.assembly_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ 这不是 JSON", "utf-8")
    asm.invalidate_cache()

    catalog = asm.load_catalog()  # 不抛
    assert {c.key for c in catalog.capabilities} == {c.key for c in CAPABILITIES}


def test_old_format_file_falls_back_to_seed(ws):
    """旧版（v1 开关式）文件里没有智能体/能力 → 按默认目录播种，别给空壳。"""
    path = asm.assembly_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "capabilities": {},
                                "tools_disabled": [], "skills_disabled": []}), "utf-8")
    asm.invalidate_cache()

    catalog = asm.load_catalog()
    assert catalog.agents and catalog.capabilities


def test_reset_removes_file(ws):
    asm.save_catalog(asm.Catalog(agents=(_agent("solo"),), capabilities=()))
    assert asm.load_catalog().agent("solo") is not None
    asm.reset_catalog()
    assert not asm.assembly_path().exists()
    assert asm.load_catalog().agent(asm.DEFAULT_AGENT_ID) is not None


def test_from_raw_ignores_junk():
    catalog = asm.Catalog.from_raw({
        "agents": [{"id": "ok", "capabilities": ["a", 3]}, {"nope": 1}, "junk"],
        "capabilities": [{"key": "a", "tools": ["t", 5], "skills": "not-a-list",
                          "gated": ["g"]}, {"label": "无 key"}],
    })
    assert [a.id for a in catalog.agents] == ["ok"]
    assert catalog.agent("ok").capabilities == ("a",)
    assert catalog.capability("a").tools == ("t",)
    assert catalog.capability("a").skills == ()
    assert catalog.capability("a").gated == ("g",)


# ------------------------------------------------------------------ 校验


def test_validate_drops_unknown_references(ws):
    clean, ignored = asm.validate_catalog(asm.Catalog(
        agents=(_agent("a", "webui", "不存在的能力"),),
        capabilities=(
            _cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec", "no.such:tool"),
                 skills=("web-ui-test", "no-such-skill"), gated=("webui_run_spec", "no_such_tool")),
        ),
    ))
    assert clean.capability("webui").tools == ("src.app.agents.webui.tools:webui_run_spec",)
    assert clean.capability("webui").skills == ("web-ui-test",)
    # 审批项按"改完之后的工具集合"收敛：不在能力里的工具名会被摘掉
    assert clean.capability("webui").gated == ("webui_run_spec",)
    assert clean.agent("a").capabilities == ("webui",)
    assert "tool:no.such:tool" in ignored
    assert "skill:no-such-skill" in ignored
    assert "capability:不存在的能力" in ignored
    assert "gated:no_such_tool" in ignored


# ------------------------------------------------------------------ 解析


def test_resolve_agent_falls_back_to_default(ws):
    catalog = asm.Catalog(agents=(_agent("a", "webui"), _agent("b")),
                          capabilities=(_cap("webui"),))
    assert asm.resolve_agent(catalog, "a").id == "a"
    assert asm.resolve_agent(catalog, "不存在").id == "a"      # 第一个 = 默认
    assert asm.resolve_agent(catalog, None).id == "a"
    assert [c.key for c in asm.agent_capabilities(catalog, catalog.agent("a"))] == ["webui"]
    assert asm.agent_capabilities(catalog, catalog.agent("b")) == ()


def test_active_agent_id_reads_configurable(ws, monkeypatch):
    import langgraph.config as lg_config

    catalog = asm.Catalog(agents=(_agent("a", "webui"), _agent("b")), capabilities=(_cap("webui"),))
    monkeypatch.setattr(lg_config, "get_config",
                        lambda: {"configurable": {"agent_id": "b"}})
    assert asm.active_agent_id(catalog) == "b"

    monkeypatch.setattr(lg_config, "get_config",
                        lambda: {"configurable": {"agent_id": "不存在"}})
    assert asm.active_agent_id(catalog) == "a"   # 认不出就退回默认


def test_skill_dirs_are_the_union_of_the_agents_capabilities(ws, monkeypatch):
    import langgraph.config as lg_config

    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"), _agent("cases", "testcase")),
        capabilities=(
            _cap("webui", skills=("web-ui-test",)),
            _cap("testcase", skills=("testcase-workflow", "lark-doc")),
        ),
    ))
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "web"}})
    assert asm.enabled_skill_dirs() == ["web-ui-test"]
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "cases"}})
    assert asm.enabled_skill_dirs() == ["testcase-workflow", "lark-doc"]


def test_repo_bound_tools_follow_the_capability_flag(ws):
    catalog = asm.Catalog(
        agents=(_agent("c", "codebase", "webui"),),
        capabilities=(_cap("codebase", requires_repo=True, tools=(
            "src.app.agents.codebase.tools:trace_symbol",
        )), _cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",))),
    )
    bound = asm.repo_bound_tool_names(catalog, catalog.agent("c"))
    assert bound == frozenset({"trace_symbol"})


def test_tool_pool_covers_the_manifest(ws):
    pool = {n for entry in asm.tool_catalog() for n in entry["names"]}
    from src.app.agents.capabilities import resolve_tools

    assert {t.name for t in resolve_tools(CAPABILITIES)} == pool
    assert asm.skill_catalog()[0]["dir"]


# ------------------------------------------------------------------ 中间件


def test_middleware_keeps_only_the_agents_capability_tools(ws, repo, monkeypatch):
    import langgraph.config as lg_config

    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"), _agent("cases", "testcase")),
        capabilities=(
            _cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",)),
            _cap("testcase", tools=("src.app.agents.testcase.tools.case_doc_tools:save_case_document",)),
        ),
    ))
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "web"}})
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))

    names = _names(_middleware()._apply(request).tools)
    assert names == ["webui_run_spec"]


def test_middleware_keeps_framework_tools(ws, repo, monkeypatch):
    """没有归属的工具（框架自带的文件 / shell / 子智能体）不该被误伤。"""
    import langgraph.config as lg_config
    from langchain_core.tools import tool

    @tool
    def i_am_not_in_the_pool() -> str:
        """框架侧工具。"""
        return "ok"

    asm.save_catalog(asm.Catalog(agents=(_agent("web", "webui"),),
                                 capabilities=(_cap("webui"),)))
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "web"}})
    request = _request([*_all_tools(), i_am_not_in_the_pool],
                       build_system_prompt(CAPABILITIES, general=True))

    names = _names(_middleware()._apply(request).tools)
    assert "i_am_not_in_the_pool" in names


def test_repo_bound_tools_hidden_without_repo(ws, monkeypatch):
    """能力声明了依赖仓库，但这次 run 没挂仓库 → 它的工具不进工具面。"""
    _no_repo(monkeypatch)
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "codebase", "webui"),),
        capabilities=(
            _cap("codebase", requires_repo=True,
                 tools=("src.app.agents.codebase.tools:trace_symbol",)),
            _cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",)),
        ),
    ))
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))

    names = _names(_middleware()._apply(request).tools)
    assert "trace_symbol" not in names
    assert "webui_run_spec" in names


def test_repo_bound_tools_visible_with_repo(ws, repo):
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "codebase"),),
        capabilities=(_cap("codebase", requires_repo=True,
                           tools=("src.app.agents.codebase.tools:trace_symbol",)),),
    ))
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))
    assert "trace_symbol" in _names(_middleware()._apply(request).tools)


# ---------------------------------------------- 外部依赖不在线时收起工具面


def _set_readiness(monkeypatch, **states):
    """把就绪缓存塞成指定状态（键 = integrations 注册表的 key）。"""
    import time

    from src.app.core import integrations

    cache = {k: (time.monotonic(), v) for k, v in states.items()}
    monkeypatch.setattr(integrations, "_readiness", cache, raising=False)


def test_offline_dependency_hides_that_capabilitys_tools(ws, repo, monkeypatch):
    """依赖不在线 → 该能力的工具不进工具面。

    与 requires_repo 同一条道理：给了模型它就会去试，试了必然失败，还会让用户
    以为"平台坏了"。缺什么、怎么补写在提示词的依赖段里。
    """
    _set_readiness(monkeypatch, playwright=False)
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "webui", "testcase"),),
        capabilities=(
            _cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",)),
            _cap("testcase", tools=("src.app.agents.testcase.tools.case_doc_tools:save_case_document",)),
        ),
    ))
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))
    names = _names(_middleware()._apply(request).tools)

    assert "webui_run_spec" not in names          # playwright 不在线
    assert "save_case_document" in names          # 飞书依赖没声明在这条能力上，不受影响


def test_online_dependency_keeps_tools(ws, repo, monkeypatch):
    _set_readiness(monkeypatch, playwright=True)
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "webui"),),
        capabilities=(_cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",)),),
    ))
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))
    assert "webui_run_spec" in _names(_middleware()._apply(request).tools)


def test_unknown_readiness_keeps_tools(ws, repo, monkeypatch):
    """还没探过（首次对话 / 同步路径）不能把工具藏掉——宁可多给，不可误伤。"""
    _set_readiness(monkeypatch)  # 缓存空
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "webui"),),
        capabilities=(_cap("webui", tools=("src.app.agents.webui.tools:webui_run_spec",)),),
    ))
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))
    assert "webui_run_spec" in _names(_middleware()._apply(request).tools)


def test_capability_section_marks_offline_dependency(ws, repo, monkeypatch):
    """提示词的依赖段要写明"未就绪 + 怎么补"，文案取自注册表。"""
    from src.app.core import integrations

    _set_readiness(monkeypatch, playwright=False)
    asm.save_catalog(asm.Catalog(
        agents=(_agent("all", "webui"),),
        capabilities=(_cap("webui", label="Web-UI 自动化",
                           tools=("src.app.agents.webui.tools:webui_run_spec",)),),
    ))
    result = _middleware()._apply(
        _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True)))
    prompt = result.system_message.content

    assert "能力依赖" in prompt
    assert "未就绪" in prompt
    assert integrations.BY_KEY["playwright"].label in prompt
    assert integrations.BY_KEY["playwright"].fix_hint in prompt


def test_user_built_capability_has_no_dependencies(ws, repo, monkeypatch):
    """用户自建的能力没有代码种子 → 无 depends，不受依赖开关影响。"""
    monkeypatch.setattr(asm, "_catalog_cache", None, raising=False)
    asm.save_catalog(asm.Catalog(
        agents=(_agent("mine", "my-cap"),),
        capabilities=(_cap("my-cap", tools=("src.app.agents.webui.tools:webui_run_spec",)),),
    ))
    _set_readiness(monkeypatch, playwright=False, unity=False, feishu=False)
    request = _request(_all_tools(), build_system_prompt(CAPABILITIES, general=True))
    assert "webui_run_spec" in _names(_middleware()._apply(request).tools)


def test_middleware_rewrites_capability_section_with_identity(ws, repo):
    """能力段换成这个智能体的那版：身份 + 它自己的能力（分诊行与领域规则）。"""
    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui", label="Web 测试助手", description="只做浏览器用例"),),
        capabilities=(_cap("webui", label="Web-UI 自动化", domain_prompt="### Web / H5 自动化\n\n只做 locator。",
                           skills=("web-ui-test",), tools=("src.app.agents.webui.tools:webui_run_spec",)),),
    ))
    prompt = build_system_prompt(CAPABILITIES, general=True)
    result = _middleware()._apply(_request(_all_tools(), prompt))
    new_prompt = result.system_message.content

    assert "你是「Web 测试助手」" in new_prompt
    assert "只做浏览器用例" in new_prompt
    assert "只做 locator。" in new_prompt
    assert "Web-UI 自动化" in new_prompt
    # 别的能力的分诊行与领域段都消失了
    assert "Unity 客户端自动化" not in new_prompt
    assert "| Unity 自动化 |" not in new_prompt
    assert "| 用例生成 |" not in new_prompt
    # 槽位、环境段、铁律都还在
    assert CAPABILITY_SECTION_OPEN in new_prompt
    assert CAPABILITY_SECTION_CLOSE in new_prompt
    assert "# 跨能力的铁律" in new_prompt
    assert "# 环境" in new_prompt


def test_middleware_rewrites_when_content_is_block_list(ws, repo):
    """真实请求里 ``system_message.content`` 是**内容块列表**（langchain 组装提示词
    时这么放），只认 str 的实现会让提示词整段不换。"""
    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"),),
        capabilities=(_cap("webui", domain_prompt="### 只有浏览器", tools=()),),
    ))
    prompt = build_system_prompt(CAPABILITIES, general=True)
    request = _request(_all_tools(), [{"type": "text", "text": prompt}])

    content = _middleware()._apply(request).system_message.content
    assert isinstance(content, list)
    text = "".join(b["text"] for b in content)
    assert "### 只有浏览器" in text
    assert "Unity 客户端自动化" not in text


def test_middleware_keeps_block_extras(ws, repo):
    """块上的附加字段（prompt-cache 断点等）不能因为换正文被丢掉。"""
    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"),),
        capabilities=(_cap("webui", domain_prompt="### 只有浏览器"),),
    ))
    prompt = build_system_prompt(CAPABILITIES, general=True)
    request = _request(_all_tools(), [
        {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}},
    ])
    content = _middleware()._apply(request).system_message.content
    assert content[0]["cache_control"] == {"type": "ephemeral"}


def test_middleware_skips_rewrite_when_section_already_matches(ws, repo, monkeypatch):
    """能力段已经写着这个智能体的那版时，不重建 system message（快路径）。"""
    import langgraph.config as lg_config

    from src.app.agents.capabilities import build_capability_prompt

    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"),),
        capabilities=(_cap("webui", label="Web-UI 自动化", domain_prompt="### Web / H5 自动化",
                           description="浏览器 UI 用例", skills=("web-ui-test",), tools=()),),
    ))
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "web"}})

    # 用装配目录里那份定义算出"这一轮该写成什么"（中间件就是这么算的）
    defn = asm.load_catalog().capability("webui")
    settled = (CAPABILITY_SECTION_OPEN + "\n"
               + build_capability_prompt((asm.to_capability(defn),), general=True,
                                         identity=("web", ""))
               + "\n" + CAPABILITY_SECTION_CLOSE)
    prompt = f"头部\n{settled}\n尾部"
    request = _request(_all_tools(), prompt)

    out = _middleware()._apply(request)
    # 提示词一个字没动（连消息对象都是原来那个）；工具面照常按这个智能体收敛
    assert out.system_message is request.system_message
    assert out.system_message.content == prompt
    assert _names(out.tools) == []


def test_middleware_survives_broken_catalog(ws, monkeypatch):
    _no_repo(monkeypatch)
    path = asm.assembly_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all", "utf-8")
    asm.invalidate_cache()

    prompt = build_system_prompt(CAPABILITIES, general=True)
    request = _request(_all_tools(), prompt)
    result = _middleware()._apply(request)  # 不抛；按播种出来的默认目录筛工具
    assert "trace_symbol" not in _names(result.tools)   # 默认目录有代码分析，但没挂仓库
    assert "webui_run_spec" in _names(result.tools)


def test_skills_middleware_filters_by_agent(ws, monkeypatch):
    import langgraph.config as lg_config

    from src.app.middleware.assembly import LiveSkillsMiddleware

    asm.save_catalog(asm.Catalog(
        agents=(_agent("web", "webui"),),
        capabilities=(_cap("webui", skills=("web-ui-test",)),),
    ))
    monkeypatch.setattr(lg_config, "get_config", lambda: {"configurable": {"agent_id": "web"}})

    middleware = LiveSkillsMiddleware(backend=None, sources=["/skills/"])
    assert middleware.name == "SkillsMiddleware"  # 与官方同名 → 原地替换

    skills = [
        {"name": "web-ui-test", "description": "UI 用例", "path": "/skills/web-ui-test/SKILL.md",
         "allowed_tools": []},
        {"name": "lark-doc", "description": "飞书文档", "path": "/skills/lark-doc/SKILL.md",
         "allowed_tools": []},
    ]
    listed = middleware._format_skills_list(skills)
    assert "web-ui-test" in listed
    assert "lark-doc" not in listed        # 这个智能体的能力没声明它


# ------------------------------------------------------------------ 装配面


def _mounted(graph) -> set[str]:
    """编译产物里真正注册的工具名（ToolNode 的 registry）。"""
    return set(graph.nodes["tools"].bound.tools_by_name)


def test_general_agent_mounts_the_whole_pool(ws):
    """对话页的 graph 把代码里所有工具都挂上（用户建的智能体随时能用它们），
    可见性由每轮的装配解析决定。"""
    from src.app.agents.harness import GENERAL_AGENT_NAME, build_general_agent, build_middleware
    from src.app.middleware.assembly import AssemblyToolsMiddleware, LiveSkillsMiddleware

    agent = build_general_agent()
    mounted = _mounted(agent)
    expected = {t.name for t in resolve_tools(CAPABILITIES)}

    assert expected <= mounted
    assert "trace_symbol" in mounted  # 代码分析的工具也预挂

    middleware = build_middleware(GENERAL_AGENT_NAME, capabilities=CAPABILITIES,
                                  backend=object(), assembly=True)
    kinds = [type(m).__name__ for m in middleware]
    assert "AssemblyToolsMiddleware" in kinds
    assert "LiveSkillsMiddleware" in kinds
    assert isinstance(middleware[0], AssemblyToolsMiddleware)


def test_legacy_graphs_do_not_take_the_assembly_middleware(ws):
    """旧会话的单能力 graph 不受装配目录影响（它们是"老样子"）。"""
    from src.app.agents.harness import build_agent, build_middleware

    agent = build_agent((CAPABILITY_BY_KEY["unity"],), name="unity_agent",
                        general=False, assembly=False)
    mounted = _mounted(agent)
    assert "unity_status" in mounted
    assert "webui_run_spec" not in mounted
    assert "trace_symbol" not in mounted

    kinds = [type(m).__name__ for m in build_middleware("unity_agent", "unity",
                                                       capabilities=(CAPABILITY_BY_KEY["unity"],))]
    assert "AssemblyToolsMiddleware" not in kinds
    assert "LiveSkillsMiddleware" not in kinds


def test_prompt_has_capability_slot():
    """提示词里留着能力段槽位（中间件靠它整段替换）；单能力（旧 graph）也有。"""
    general = build_system_prompt(CHAT_CAPABILITIES)
    assert general.count(CAPABILITY_SECTION_OPEN) == 1
    assert general.index(CAPABILITY_SECTION_OPEN) < general.index(CAPABILITY_SECTION_CLOSE)

    single = build_system_prompt((CAPABILITY_BY_KEY["unity"],))
    assert "只负责 **Unity 自动化**" in single
    assert "任务分诊" not in single  # 单能力不给分诊表（原有语义）


# ------------------------------------------------------------------ API


def test_api_view_and_roundtrip(ws):
    import asyncio

    from src.app.api.v2.agents import CatalogUpdate, catalog_view, delete_catalog, put_catalog

    view = catalog_view()
    assert [a["id"] for a in view["agents"]] == [asm.DEFAULT_AGENT_ID]
    assert view["tool_catalog"] and view["skill_catalog"]
    assert view["is_default"] is True

    payload = CatalogUpdate(
        agents=[],
        capabilities=[{"key": "api-explore", "label": "接口探索执行",
                       "description": "扫接口、跑用例", "domain_prompt": "### 接口探索",
                       "tools": ["src.app.agents.webui.tools:webui_run_spec", "不存在:工具"],
                       "skills": ["web-ui-test", "没有的技能"],
                       "gated": ["webui_run_spec"], "requires_repo": False}],
    )
    out = asyncio.run(put_catalog(payload, user=None))
    data = out.data
    assert data["ignored"] and "tool:不存在:工具" in data["ignored"]
    agent = data["agents"][0]
    assert agent["id"] == asm.DEFAULT_AGENT_ID          # 没给智能体 → 补默认的
    assert agent["capabilities"] == ["api-explore"]
    cap = data["capabilities"][0]
    assert cap["key"] == "api-explore"
    assert cap["tool_names"] == ["webui_run_spec"]
    assert cap["skills"] == ["web-ui-test"]
    assert cap["gated"] == ["webui_run_spec"]
    assert data["is_default"] is False

    out2 = asyncio.run(delete_catalog(user=None))
    assert out2.data["is_default"] is True
    assert {c["key"] for c in out2.data["capabilities"]} == {c.key for c in CAPABILITIES}


def test_reload_endpoint_calls_the_launcher(ws, monkeypatch):
    """「重新加载工具池」= 让后端去点启动器的 restart（容器模式没有启动器 → 说人话）。"""
    import asyncio

    import httpx

    from src.app.api.v2 import agents as agents_api
    from src.app.core.config import settings

    calls: list[str] = []

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"started": True, "pid": 4321}

    class _Client:
        def __init__(self, **_kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def post(self, url: str):
            calls.append(url)
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "launcher_url", "http://127.0.0.1:5010")

    out = asyncio.run(agents_api.reload_agent_service(user=None))
    assert out.success is True
    assert out.data["restarted"] is True
    assert out.data["pid"] == 4321
    assert calls == ["http://127.0.0.1:5010/api/services/langgraph/restart"]

    # 启动器不可达 → 不抛异常，返回一句人话 + 手动重启提示
    class _Boom(_Client):
        async def post(self, url: str):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)
    out2 = asyncio.run(agents_api.reload_agent_service(user=None))
    assert out2.success is False
    assert out2.data["restarted"] is False
    assert "启动器不可达" in out2.data["error"]
    assert "手动重启" in out2.data["hint"]
