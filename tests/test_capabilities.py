"""能力清单与装配器测试（harness）。

这次改造的核心承诺是"专项能力来自数据，而不是写死在 agent 模块里"。这个文件锁住
那几条性质，免得日后又长回硬编码：

- 清单里声明的工具**都能解析**（符号写错会静默降级，必须测）；
- 通用智能体的工具面 = 对话页能力的并集，且**不**混进专属入口的能力；
- 人工审批项按能力合并进 interrupt_on；
- 提示词由清单生成：多能力有分诊表，单能力不假装自己是通用智能体；
- 加一条能力就够 —— 不需要改 agent 模块（这条由"清单是唯一来源"间接保证）。
"""

from __future__ import annotations

import pytest

from src.app.agents.capabilities import (
    CAPABILITIES,
    CAPABILITY_BY_KEY,
    CHAT_CAPABILITIES,
    build_capability_prompt,
    build_interrupt_on,
    build_system_prompt,
    inventory,
    resolve_missing,
    resolve_tools,
)
from src.app.agents.harness import GENERAL_AGENT_NAME, build_agent, build_backend


class TestManifestIntegrity:
    def test_every_declared_tool_resolves(self):
        """清单里任何一个符号写错都要在这里炸，而不是运行时静默少一个工具。"""
        assert resolve_missing() == []

    def test_capability_keys_are_unique(self):
        keys = [c.key for c in CAPABILITIES]
        assert len(keys) == len(set(keys))

    def test_every_capability_has_label_and_description(self):
        for cap in CAPABILITIES:
            assert cap.label and cap.description, cap.key
            # description 是分诊依据，空着模型就没法路由
            assert len(cap.description) > 8, cap.key

    def test_chat_capabilities_are_a_subset(self):
        assert {c.key for c in CHAT_CAPABILITIES} <= {c.key for c in CAPABILITIES}
        assert len(CHAT_CAPABILITIES) >= 3

    def test_capability_is_hashable(self):
        """frozen 数据类要真的能当键用（曾经因为持有 dict 而不可哈希）。"""
        assert len(set(CAPABILITIES)) == len(CAPABILITIES)
        assert CAPABILITY_BY_KEY["webui"] in set(CAPABILITIES)

    def test_capability_skills_are_real_dirs(self):
        from pathlib import Path

        skills_root = Path(__file__).resolve().parents[1] / "src" / "app" / "skills"
        for cap in CAPABILITIES:
            for skill in cap.skills:
                assert (skills_root / skill / "SKILL.md").is_file(), \
                    f"{cap.key} 指向的技能不存在: {skill}"


class TestToolResolution:
    def test_resolve_tools_dedups_and_flags_errors(self):
        tools = resolve_tools()
        names = [t.name for t in tools]
        assert len(names) == len(set(names)), "工具重名（重复挂载）"
        assert all(getattr(t, "handle_tool_error", False) is True for t in tools), \
            "工具错误应回给模型重试，而不是炸掉整轮 run"

    def test_codebase_tools_are_repo_gated(self):
        """代码分析也是对话页能力了（输入框旁的「代码图谱仓库」选择器挂上就能用），
        但它声明 ``requires_repo`` —— 构建期挂上、没挂仓库时**不进工具面**
        （可见性由 middleware/assembly.py 按"这次 run 挂没挂仓库"决定）。"""
        codebase = CAPABILITY_BY_KEY["codebase"]
        assert codebase.requires_repo is True
        assert codebase in CHAT_CAPABILITIES

        # 构建期确实全挂上了（否则"装回来"要重启）
        chat = {t.name for t in resolve_tools(CHAT_CAPABILITIES)}
        assert {"repo_architecture", "trace_symbol"} <= chat

        # 只有它需要仓库上下文；别的能力不该被这条规则误伤
        assert [c.key for c in CHAT_CAPABILITIES if c.requires_repo] == ["codebase"]

    def test_all_three_families_are_present(self):
        chat = {t.name for t in resolve_tools(CHAT_CAPABILITIES)}
        assert {"save_case_document", "lint_case_document"} <= chat
        assert {"unity_status", "unity_find_objects"} <= chat
        assert {"webui_run_spec", "webui_save_script"} <= chat

    def test_memory_tools_expand_from_a_module_export(self):
        """``extra_tool_modules`` 引用的是列表，应展开成多个工具。"""
        chat = {t.name for t in resolve_tools(CHAT_CAPABILITIES)}
        assert {"save_memory", "search_memories"} <= chat


class TestRagCapability:
    """知识库能力：智能体侧的 RAG 读写面（此前只有 dsh 经 MCP 拿得到，平台自己的
    智能体一个 RAG 工具都没有）。"""

    def test_tools_are_present_and_reachable(self):
        rag = CAPABILITY_BY_KEY["rag"]
        assert rag in CHAT_CAPABILITIES
        chat = {t.name for t in resolve_tools(CHAT_CAPABILITIES)}
        assert {"rag_health", "rag_query", "rag_ingest_text",
                "rag_ingest_file", "rag_list_documents"} <= chat

    def test_gated_by_lightrag_but_not_by_repo(self):
        """登记的是"知识库本体在不在"：不在线时工具被藏掉（_offline_tools），
        且它**不**该被 requires_repo 那条规则误伤 —— 知识库跟挂没挂仓库无关。"""
        rag = CAPABILITY_BY_KEY["rag"]
        assert rag.requires == ("lightrag",)
        assert rag.requires_repo is False
        assert [c.key for c in CHAT_CAPABILITIES if c.requires_repo] == ["codebase"]

    def test_bypass_mode_is_accepted(self):
        """平台暴露的查询模式要与服务端一致（1.5.x 起支持 bypass）。"""
        from src.app.services import lightrag_service

        assert "bypass" in lightrag_service.QUERY_MODES


class TestCodebaseCapabilityDoesNotDrift:
    """代码分析是唯一**还没**走 harness 装配的能力（它有自己的 graph 与调优过的提示词），
    但它的工具已在清单里声明。这个测试防止两边悄悄漂开 —— 那正是这次改造要根治的病。
    """

    def test_declared_tools_match_what_the_agent_actually_loads(self):
        from src.app.agents.codebase import agent as codebase_agent_module

        declared = {t.name for t in resolve_tools((CAPABILITY_BY_KEY["codebase"],))}
        actual = {t.name for t in codebase_agent_module._all_tools}
        assert actual == declared, (
            "codebase 清单与 agent 实际挂载的工具不一致："
            f"只在清单里={declared - actual}，只在 agent 里={actual - declared}"
        )


class TestInterruptOn:
    def test_gate_entries_cover_the_whole_tool_pool(self):
        """审批现在是用户数据（能力编辑器里勾），所以每个候选工具都先登记一条，
        由 when 谓词每轮现查目录 —— 勾一下下一轮就生效，不用重启。"""
        from src.app.services.assembly_service import catalog_tool_names, is_tool_gated

        gates = build_interrupt_on()
        # 权限门自己的规则也要在（执行/写文件）
        assert "execute" in gates
        for name in catalog_tool_names():
            assert name in gates, f"{name} 没有登记审批条目"
            assert "when" in gates[name], f"{name} 的审批不是现查的"
        # 种子里的两项默认开着审批，其余默认关
        assert is_tool_gated("approve_case_document") is True
        assert is_tool_gated("release_case_document") is True
        assert is_tool_gated("webui_run_spec") is False


class TestSystemPrompt:
    def test_general_prompt_has_triage_table_and_all_domains(self):
        prompt = build_system_prompt(CHAT_CAPABILITIES)
        assert "任务分诊" in prompt
        assert "通用智能体" in prompt
        for cap in CHAT_CAPABILITIES:
            for skill in cap.skills:
                assert skill in prompt, f"{cap.key} 的技能 {skill} 没进分诊表"
        assert "用例生成" in prompt and "Unity" in prompt and "Web" in prompt

    def test_general_prompt_lists_dependencies_honestly(self):
        """构建期的静态提示词只列依赖名字，不断言"现在在线"。

        真实状态由装配中间件每轮注入（见下一个用例）——静态提示词里写死在线状态，
        依赖一变化就成了谎话。
        """
        prompt = build_system_prompt(CHAT_CAPABILITIES)
        assert "能力依赖" in prompt
        assert "Playwright 执行器" in prompt
        assert "（就绪）" not in prompt and "未就绪" not in prompt

    def test_readiness_snapshot_renders_state_and_fix_hint(self):
        """给了就绪快照：在线的标「就绪」，离线的写明「缺什么 + 怎么补」。

        文案取自 core/integrations 注册表（唯一描述处），能力清单不再自己写散文。
        """
        from src.app.core import integrations

        cap = CAPABILITY_BY_KEY["webui"]
        ready = build_capability_prompt((cap,), general=False,
                                        readiness={"playwright": True})
        assert "Playwright 执行器（就绪）" in ready

        offline = build_capability_prompt((cap,), general=False,
                                          readiness={"playwright": False})
        assert "未就绪" in offline
        assert integrations.BY_KEY["playwright"].fix_hint in offline

    def test_readiness_unknown_is_neither_ready_nor_offline(self):
        """没探过（None）不能渲染成"未就绪"——首次对话会误报。"""
        cap = CAPABILITY_BY_KEY["codebase"]
        text = build_capability_prompt((cap,), general=False,
                                       readiness={"codebase-memory": None})
        assert "未就绪" not in text and "（就绪）" not in text
        assert "代码知识图谱" in text

    def test_single_capability_prompt_does_not_claim_to_be_general(self):
        """旧的单能力 graph 只挂一个能力，提示词不能自称"通用智能体"。"""
        prompt = build_system_prompt((CAPABILITY_BY_KEY["unity"],))
        assert "通用智能体" not in prompt
        assert "任务分诊" not in prompt
        assert "Unity" in prompt

    def test_repair_budget_follows_settings(self, monkeypatch):
        from src.app.core.config import settings

        monkeypatch.setattr(settings, "web_ui_max_repair", 4)
        assert "最多 5 次执行" in build_system_prompt(CHAT_CAPABILITIES)

    def test_default_device_follows_settings(self, monkeypatch):
        from src.app.core.config import settings

        monkeypatch.setattr(settings, "web_ui_default_device", "Pixel 5")
        assert "Pixel 5" in build_system_prompt(CHAT_CAPABILITIES)


class TestInventory:
    def test_inventory_reports_tool_sources_and_counts(self):
        inv = inventory()
        by_key = {c["key"]: c for c in inv["capabilities"]}
        assert set(by_key) == {c.key for c in CAPABILITIES}
        assert by_key["webui"]["tool_count"] == 8
        assert by_key["unity"]["tool_count"] == 22   # +hierarchy/find_by_text/object_text/reset
        # 代码分析的唯一交互入口是对话页（挂仓库后可用）；原来的专属页面入口
        # （代码图谱 → AI 分析 Tab）已删除，所以 home 是空的
        assert by_key["codebase"]["in_chat"] is True
        assert by_key["codebase"]["requires_repo"] is True
        assert by_key["codebase"]["home"] == ""
        assert inv["missing_tools"] == []
        assert by_key["testcase"]["human_gated"]
        # 技能现在是能力的一部分（一个能力可带多个）
        assert "testcase-workflow" in by_key["testcase"]["skills"]
        assert by_key["unity"]["skills"] == ["unity-ui-test"]

    def test_inventory_names_the_actual_tools(self):
        """页面要显示"挂了哪些工具"，不能只有数量。"""
        inv = inventory()
        webui = next(c for c in inv["capabilities"] if c["key"] == "webui")
        names = [n for t in webui["tools"] for n in t["names"]]
        assert "webui_run_spec" in names
        assert all(t["module"] and t["export"] for t in webui["tools"])


class TestBuildAgent:
    def test_general_agent_assembles(self):
        agent = build_agent(CHAT_CAPABILITIES)
        assert agent is not None

    def test_single_capability_agent_assembles(self):
        """三个旧 graph 走的就是这条路径。"""
        agent = build_agent((CAPABILITY_BY_KEY["unity"],),
                            name="unity_agent", default_dir_name="unity")
        assert agent is not None

    def test_general_agent_name_is_stable(self):
        assert GENERAL_AGENT_NAME == "smart_test_agent"

    def test_backend_routes_skills_and_artifacts(self, tmp_path, monkeypatch):
        from src.app.core.config import settings

        monkeypatch.setattr(settings, "workspace_dir", tmp_path)
        backend = build_backend()
        assert "/skills/" in backend.routes
        assert "/artifacts/" in backend.routes

    def test_upload_namespace_is_frozen_at_legacy_name(self):
        """上传目录必须沿用历史的 testcase —— 前端与上传接口都写死了它。"""
        from src.app.agents.capabilities import build_upload_namespace

        assert build_upload_namespace() == "testcase"


@pytest.mark.parametrize("cap_key", ["testcase", "unity", "webui"])
def test_each_chat_capability_builds_a_prompt_section(cap_key):
    cap = CAPABILITY_BY_KEY[cap_key]
    assert cap.domain_prompt.strip(), f"{cap_key} 没有领域提示词"
    assert cap.domain_prompt.strip() in build_system_prompt(CHAT_CAPABILITIES)
