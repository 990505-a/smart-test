"""增量影响分析测试（代码图谱）。

覆盖三件事：变更采集（清单快照 + 差集 + 文件类型过滤）、提示词构造、
以及编排语义——首次只建基线、无变更不烧 token、LLM 失败不影响索引本身。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.app.db.database as db_module
from src.app.core.config import settings
from src.app.db.database import Base
from src.app.db.models.codebase import CodebaseImpactReport, CodebaseRepo
from src.app.services import codebase_analysis_service as analysis


@pytest_asyncio.fixture
async def db_factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    # 服务模块用自己的名字引用 factory，必须一并替换
    monkeypatch.setattr(analysis, "async_session_factory", factory)
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def isolate_reports_dir(monkeypatch, tmp_path):
    """报告与清单都写进临时目录，别碰真实 workspace/。"""
    monkeypatch.setattr(settings, "workspace_dir", tmp_path / "ws")


@pytest.fixture
def repo_tree(tmp_path):
    """一个假仓库：两个源文件 + 一个必须被跳过的 node_modules。"""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.lua").write_text("x" * 10, encoding="utf-8")
    (root / "src" / "b.gs").write_text("y" * 20, encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "c.lua").write_text("skipped", encoding="utf-8")
    return root


async def _make_repo(factory, root: Path, **over) -> str:
    async with factory() as s:
        repo = CodebaseRepo(
            repo_path=str(root),
            display_name=over.pop("display_name", "测试仓库"),
            file_type_mode=over.pop("file_type_mode", "all"),
            file_types=over.pop("file_types", []),
            auto_increment=over.pop("auto_increment", True),
            auto_analyze=over.pop("auto_analyze", False),
        )
        s.add(repo)
        await s.commit()
        return str(repo.id)


# ---------------------------------------------------------------------------
# 变更采集
# ---------------------------------------------------------------------------

class TestScanManifest:
    def test_skips_ignored_dirs_and_records_metadata(self, repo_tree):
        files, truncated = analysis.scan_manifest(str(repo_tree))
        assert sorted(files) == ["src/a.lua", "src/b.gs"]
        assert truncated is False
        # [mtime 秒, size]
        assert files["src/a.lua"][1] == 10
        assert files["src/b.gs"][1] == 20

    def test_include_mode_keeps_only_listed_extensions(self, repo_tree):
        files, _ = analysis.scan_manifest(str(repo_tree), mode="include", file_types=["lua"])
        assert sorted(files) == ["src/a.lua"]

    def test_exclude_mode_drops_listed_extensions(self, repo_tree):
        files, _ = analysis.scan_manifest(str(repo_tree), mode="exclude", file_types=[".gs"])
        assert sorted(files) == ["src/a.lua"]

    def test_limit_reports_truncation(self, repo_tree):
        files, truncated = analysis.scan_manifest(str(repo_tree), limit=1)
        assert truncated is True
        assert len(files) == 1

    def test_missing_directory_degrades_to_empty(self, tmp_path):
        files, truncated = analysis.scan_manifest(str(tmp_path / "nope"))
        assert files == {} and truncated is False


class TestDiffManifests:
    def test_added_modified_deleted(self):
        prev = {"a.lua": [1, 10], "b.gs": [2, 20], "gone.lua": [3, 30]}
        cur = {"a.lua": [1, 10], "b.gs": [9, 20], "new.lua": [4, 40]}
        d = analysis.diff_manifests(prev, cur)
        assert d["added"] == ["new.lua"]
        assert d["modified"] == ["b.gs"]      # mtime 变了
        assert d["deleted"] == ["gone.lua"]   # a.lua 未变，不在任何一类

    def test_identical_manifests_have_no_changes(self):
        m = {"a.lua": [1, 10]}
        assert not analysis.has_changes(
            {"counts": {k: len(v) for k, v in analysis.diff_manifests(m, m).items()}} 
        )


# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def _repo(self, root) -> CodebaseRepo:
        return CodebaseRepo(repo_path=str(root), display_name="m72",
                            file_type_mode="all", file_types=[])

    def test_lists_changes_and_names_project(self, repo_tree):
        from src.app.services.codebase_service import project_name

        prompt = analysis.build_prompt(self._repo(repo_tree), {
            "counts": {"added": 2, "modified": 1, "deleted": 1, "files_total": 9},
            "added": ["n1.lua", "n2.lua"], "modified": ["m.lua"], "deleted": ["d.lua"],
            "truncated": False, "first_round": False, "git": None,
        })
        assert project_name(str(repo_tree)) in prompt  # 图谱项目名，智能体查图要用
        assert "新增 2 个文件" in prompt and "删除 1 个文件" in prompt
        assert "n1.lua" in prompt and "d.lua" in prompt
        assert "不是 git 仓库" in prompt
        assert "不要修改仓库里" in prompt  # 只读纪律必须写进提示

    def test_includes_git_diff_when_available(self, repo_tree):
        prompt = analysis.build_prompt(self._repo(repo_tree), {
            "counts": {}, "added": [], "modified": [], "deleted": [],
            "truncated": False, "first_round": False,
            "git": {"base": "a" * 40, "head": "b" * 40,
                    "name_status": ["M\tsrc/a.lua"], "stat": "1 file changed"},
        })
        assert "git 行级变更" in prompt and "M\tsrc/a.lua" in prompt

    def test_flags_truncated_scan(self, repo_tree):
        prompt = analysis.build_prompt(self._repo(repo_tree), {
            "counts": {}, "added": [], "modified": [], "deleted": [],
            "truncated": True, "first_round": False, "git": None,
        })
        assert "截断" in prompt

    def test_long_lists_are_capped(self, repo_tree):
        names = [f"f{i}.lua" for i in range(analysis.PROMPT_LIST_CAP + 25)]
        prompt = analysis.build_prompt(self._repo(repo_tree), {
            "counts": {"added": len(names)}, "added": names,
            "modified": [], "deleted": [],
            "truncated": False, "first_round": False, "git": None,
        })
        assert "另有 25 个未列出" in prompt


class TestSummarize:
    def test_picks_first_meaningful_line(self):
        md = "# 标题\n\n**结论**：这次改动主要是 `登录协议` 重构。\n后续内容"
        assert analysis._summarize(md) == "结论：这次改动主要是 登录协议 重构。"

    def test_skips_list_items_but_keeps_bold_leads(self):
        """`- x` 是列表项要跳过；`**结论**` 是加粗开场白，不能当列表项吞掉。"""
        md = "# 报告\n\n- 第一项\n- 第二项\n\n**结论**：登录链路有风险。"
        assert analysis._summarize(md) == "结论：登录链路有风险。"

    def test_skips_code_fence_and_quote(self):
        md = "> 引用\n\n```\ncode\n```\n实际结论在一行"
        assert analysis._summarize(md) == "实际结论在一行"

    def test_falls_back_to_raw_text(self):
        assert analysis._summarize("只是一行") == "只是一行"


# ---------------------------------------------------------------------------
# 编排语义
# ---------------------------------------------------------------------------

class TestRunImpactAnalysis:
    @pytest.mark.asyncio
    async def test_first_round_only_builds_baseline(self, db_factory, repo_tree):
        """首次分析不调 LLM：没有基线可比，先落一份清单。"""
        repo_id = await _make_repo(db_factory, repo_tree)
        calls = []
        analysis.run_agent_once = _recorder(calls)

        res = await analysis.run_impact_analysis(repo_id, trigger="manual", force=True)

        assert res["status"] == "skipped" and "首次分析" in res["reason"]
        assert calls == []
        assert analysis.load_manifest(repo_id) is not None

    @pytest.mark.asyncio
    async def test_no_changes_skips_without_llm(self, db_factory, repo_tree):
        repo_id = await _make_repo(db_factory, repo_tree)
        await analysis.run_impact_analysis(repo_id, trigger="manual")  # 建基线
        calls = []
        analysis.run_agent_once = _recorder(calls)

        res = await analysis.run_impact_analysis(repo_id, trigger="scheduled")

        assert res["status"] == "skipped" and "无文件变更" in res["reason"]
        assert calls == []

    @pytest.mark.asyncio
    async def test_force_runs_even_without_changes(self, db_factory, repo_tree):
        repo_id = await _make_repo(db_factory, repo_tree)
        await analysis.run_impact_analysis(repo_id, trigger="manual")
        analysis.run_agent_once = _recorder([], output="## 结论\n一切正常。")

        res = await analysis.run_impact_analysis(repo_id, trigger="manual", force=True)

        assert res["status"] == "success"
        report = await _get_report(db_factory, res["report_id"])
        assert report.status == "success"
        assert "一切正常" in report.content_md
        assert report.summary

    @pytest.mark.asyncio
    async def test_runs_on_real_change_and_records_counts(self, db_factory, repo_tree):
        repo_id = await _make_repo(db_factory, repo_tree)
        await analysis.run_impact_analysis(repo_id, trigger="manual")
        (repo_tree / "src" / "new.lua").write_text("brand new", encoding="utf-8")
        analysis.run_agent_once = _recorder([], output="报告正文")

        res = await analysis.run_impact_analysis(repo_id, trigger="scheduled")

        assert res["status"] == "success"
        assert res["counts"]["added"] == 1
        report = await _get_report(db_factory, res["report_id"])
        assert report.changes["added"] == ["src/new.lua"]
        # 落盘了一份可读的 Markdown
        assert report.file_path and Path(report.file_path).is_file()

    @pytest.mark.asyncio
    async def test_agent_failure_is_recorded_not_raised(self, db_factory, repo_tree):
        repo_id = await _make_repo(db_factory, repo_tree)
        await analysis.run_impact_analysis(repo_id, trigger="manual")
        (repo_tree / "src" / "new.lua").write_text("x", encoding="utf-8")
        analysis.run_agent_once = _recorder([], fail="LLM 挂了")

        res = await analysis.run_impact_analysis(repo_id, trigger="scheduled")

        assert res["success"] is False
        report = await _get_report(db_factory, res["report_id"])
        assert report.status == "failed" and "LLM 挂了" in report.error

    @pytest.mark.asyncio
    async def test_report_thread_id_is_a_valid_uuid(self, db_factory, repo_tree):
        """传给 LangGraph 的 thread_id 必须是 UUID，否则服务端 422 拒建线程。"""
        import uuid as uuid_mod

        repo_id = await _make_repo(db_factory, repo_tree)
        tid = analysis._impact_thread_id(uuid_mod.UUID(repo_id), None)
        assert uuid_mod.UUID(tid) == uuid_mod.UUID(tid)  # 可解析
        # 确定性：同一 (仓库, 运行) 推导出同一个线程，重复分析不造孤儿会话
        assert tid == analysis._impact_thread_id(uuid_mod.UUID(repo_id), None)
        other = analysis._impact_thread_id(uuid_mod.uuid4(), None)
        assert other != tid

    @pytest.mark.asyncio
    async def test_missing_repo_is_reported(self, db_factory):
        res = await analysis.run_impact_analysis(
            "00000000-0000-0000-0000-000000000000", trigger="manual")
        assert res["success"] is False and res["error"] == "仓库不存在"


class TestAnalyzeAfterRound:
    @pytest.mark.asyncio
    async def test_global_switch_off_does_nothing(self, db_factory, repo_tree, monkeypatch):
        repo_id = await _make_repo(db_factory, repo_tree, auto_analyze=True)
        monkeypatch.setattr(settings, "codebase_analyze_enabled", False)
        calls = []
        analysis.run_agent_once = _recorder(calls)

        out = await analysis.analyze_after_round(
            [{"repo_id": repo_id, "success": True, "auto_analyze": True}])

        assert out == [] and calls == []

    @pytest.mark.asyncio
    async def test_per_repo_flag_off_is_skipped(self, db_factory, repo_tree, monkeypatch):
        repo_id = await _make_repo(db_factory, repo_tree, auto_analyze=False)
        monkeypatch.setattr(settings, "codebase_analyze_enabled", True)
        calls = []
        analysis.run_agent_once = _recorder(calls)

        out = await analysis.analyze_after_round(
            [{"repo_id": repo_id, "success": True, "auto_analyze": False}])

        assert out == [] and calls == []

    @pytest.mark.asyncio
    async def test_failed_index_is_not_analyzed(self, db_factory, repo_tree, monkeypatch):
        repo_id = await _make_repo(db_factory, repo_tree, auto_analyze=True)
        monkeypatch.setattr(settings, "codebase_analyze_enabled", True)
        calls = []
        analysis.run_agent_once = _recorder(calls)

        out = await analysis.analyze_after_round(
            [{"repo_id": repo_id, "success": False, "auto_analyze": True}])

        assert out == [] and calls == []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _recorder(calls: list, *, output: str = "报告", fail: str | None = None):
    async def _fake(prompt: str, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if fail:
            return {"success": False, "output": "", "error": fail, "model": "m"}
        return {"success": True, "output": output, "error": None, "model": "test-model"}
    return _fake


async def _get_report(factory, report_id: str) -> CodebaseImpactReport:
    async with factory() as s:
        return (await s.execute(
            select(CodebaseImpactReport)
            .where(CodebaseImpactReport.id == __import__("uuid").UUID(report_id))
        )).scalars().first()
