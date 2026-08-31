"""Tests for the Markdown case-document storage (2026-08 重构).

Covers: parse (heading tree / priority / preconditions / nested steps /
annotation stripping & counting), filename sanitization, file CRUD
roundtrip, and the feishu tree/OPML conversion consuming parsed output.
"""

from __future__ import annotations

import pytest

from src.app.services import case_docs_service as svc

SAMPLE = """\
# 帐号系统_用例集_20260828

## 登录模块

### 账号密码登录

#### 正确账号密码可登录 [P0] ✅
> 好：边界值考虑全

前置：已注册账号

- 输入正确账号密码 ⇒ 进入主界面
- 点击登录按钮 ⇒ 跳转成功
  - 网络异常时 ⇒ 提示网络错误

#### 密码错误提示不暴露具体原因 ❌
> 不好：预期太模糊
- 输入错误密码 ⇒ 提示账号或密码错误

#### 手机号冻结登录 [P1] ⚠️
> 漏测补充：AI 漏了账号状态异常
- 冻结账号登录 ⇒ 提示账号已冻结
"""


class TestParseCasesMd:
    def test_title_and_counts(self):
        r = svc.parse_cases_md(SAMPLE)
        assert r["title"] == "帐号系统_用例集_20260828"
        assert r["case_count"] == 3
        assert r["good"] == 1
        assert r["bad"] == 1
        assert r["warn"] == 1
        assert r["annotated"] is True

    def test_group_tree_structure(self):
        r = svc.parse_cases_md(SAMPLE)
        assert len(r["tree"]) == 1
        login = r["tree"][0]
        assert login["name"] == "登录模块"
        assert [c["name"] for c in login["children"]] == ["账号密码登录"]
        sub = login["children"][0]
        assert sub["children"] == []
        assert len(sub["cases"]) == 3

    def test_case_fields_and_annotation_stripping(self):
        r = svc.parse_cases_md(SAMPLE)
        first = r["tree"][0]["children"][0]["cases"][0]
        # 标注与优先级标记剥离，标题为纯业务标题
        assert first["name"] == "正确账号密码可登录"
        assert first["priority"] == "critical"
        assert first["preconditions"] == "已注册账号"

    def test_nested_steps(self):
        r = svc.parse_cases_md(SAMPLE)
        steps = r["tree"][0]["children"][0]["cases"][0]["steps"]
        assert steps[0]["action"] == "输入正确账号密码"
        assert steps[0]["expected"] == "进入主界面"
        assert steps[1]["children"][0]["action"] == "网络异常时"

    def test_priority_mapping(self):
        r = svc.parse_cases_md(SAMPLE)
        cases = r["tree"][0]["children"][0]["cases"]
        assert [c["priority"] for c in cases] == ["critical", "medium", "high"]

    def test_heading_with_children_keeps_child_cases_drops_own_steps(self):
        md = "# t\n\n## g\nsteps here\n- a ⇒ b\n\n### case\n- c ⇒ d\n"
        r = svc.parse_cases_md(md)
        # ## g 有子标题 → 分组：其直属正文步骤被忽略，子标题 case 正常归属
        assert r["tree"][0]["name"] == "g"
        assert [c["name"] for c in r["tree"][0]["cases"]] == ["case"]
        assert r["tree"][0]["children"] == []

    def test_no_h1_uses_empty_title(self):
        md = "## g\n\n#### case [P2]\n- a ⇒ b\n"
        r = svc.parse_cases_md(md)
        assert r["title"] == ""
        assert r["case_count"] == 1

    def test_unannotated_document(self):
        md = "# t\n\n## g\n\n#### case\n- a ⇒ b\n"
        r = svc.parse_cases_md(md)
        assert r["annotated"] is False
        assert r["good"] == r["bad"] == r["warn"] == 0


class TestFilenameSafety:
    def test_illegal_chars_replaced(self):
        cleaned = svc.sanitize_name('a<b>:"/\\|?*b')
        for ch in '<>:"/\\|?*':
            assert ch not in cleaned
        assert cleaned.startswith("a_") and cleaned.endswith("_b")

    def test_top_level_cases_fall_into_ungrouped(self):
        md = "# t\n\n#### case\n- a ⇒ b √\n- c ⇒ d X\n"
        r = svc.parse_cases_md(md)
        assert r["case_count"] == 1
        group = r["tree"][0]
        assert group["name"] == "未分组"
        steps = group["cases"][0]["steps"]
        assert steps[0]["mark"] == "√"
        assert steps[1]["mark"] == "X"

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError):
            svc.sanitize_name("   ")

    def test_reserved_windows_name_prefixed(self):
        assert svc.sanitize_name("CON").startswith("_")


class TestCrudRoundtrip:
    def test_save_read_list_delete(self, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "get_workspace_dir", lambda *a, **k: tmp_path)
        result = svc.save_doc("项目A", SAMPLE)
        assert result["case_count"] == 3

        doc = svc.read_doc("项目A")
        assert doc is not None and doc["content"] == SAMPLE

        docs = svc.list_docs()
        assert [d["name"] for d in docs] == ["项目A"]
        assert docs[0]["annotated"] is True

        assert svc.delete_doc("项目A") is True
        assert svc.read_doc("项目A") is None

    def test_read_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "get_workspace_dir", lambda *a, **k: tmp_path)
        assert svc.read_doc("不存在") is None


class TestFeishuConversion:
    def test_parsed_tree_feeds_mindnote_nodes(self):
        from src.app.services import feishu_service

        parsed = svc.parse_cases_md(SAMPLE)
        nodes = feishu_service.build_tree_nodes(parsed["title"], parsed["tree"])
        texts = [n["texts"][0]["text"]["content"] for n in nodes]
        assert "帐号系统_用例集_20260828" in texts
        assert "正确账号密码可登录" in texts  # 无 ✅ / [P0]
        assert not any("✅" in t or "[P" in t for t in texts)

    def test_parsed_tree_feeds_opml(self):
        from src.app.services import feishu_service

        parsed = svc.parse_cases_md(SAMPLE)
        opml = feishu_service.build_tree_opml(parsed["title"], parsed["tree"])
        assert "<opml" in opml
        assert "✅" not in opml and "❌" not in opml

    def test_build_tree_levels_no_forward_parent_refs(self):
        """飞书 3411001 约束：每层节点的 parent 必须在更早层或外部已存在。"""
        from src.app.services import feishu_service

        parsed = svc.parse_cases_md(SAMPLE)

        # 含根模式：根在第 0 层，无 parent_id 键（_node 省略空父级）
        levels = feishu_service.build_tree_levels(parsed["title"], parsed["tree"])
        assert "parent_id" not in levels[0][0]
        assert "帐号系统" in levels[0][0]["texts"][0]["text"]["content"]

        def assert_ordered(levels, external: set[str]) -> None:
            seen = set(external)
            for level in levels:
                ids = set()
                for n in level:
                    assert n.get("parent_id") in seen, (
                        f"节点 {n['texts'][0]['text']['content'][:12]} 的父级不在更早层")
                    ids.add(n["node_id"])
                seen |= ids

        assert_ordered(levels, {None})

        # 无根模式（模板复制）：整树挂到外部根节点下
        levels2 = feishu_service.build_tree_levels(
            "", parsed["tree"], parent_id="external-root")
        assert_ordered(levels2, {"external-root"})
        total = sum(len(l) for l in levels) - 1
        assert sum(len(l) for l in levels2) == total  # 去根后节点数一致 and "❌" not in opml


class TestAnnotationFlag:
    """用例文档的人工标注检测（标题尾 ✅/❌/⚠️；供前端与记忆链路消费）。"""

    def test_annotated_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(svc, "get_workspace_dir", lambda *a, **k: tmp_path)
        svc.save_doc("未标注", "# t\n\n## g\n\n#### c\n- a ⇒ b\n")
        svc.save_doc("已标注", "# t2\n\n#### c ✅\n- a ⇒ b\n")
        docs = {d["name"]: d for d in svc.list_docs()}
        assert docs["未标注"]["annotated"] is False
        assert docs["已标注"]["annotated"] is True
