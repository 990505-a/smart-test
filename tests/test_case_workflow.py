from __future__ import annotations

import pytest

from src.app.services import case_docs_service as svc
from src.app.services import case_workflow_service as workflow


@pytest.fixture(autouse=True)
def _platform_lint_is_strict(monkeypatch):
    """把平台的 lint 严格档固定为开启。

    lint 的严格程度是**平台配置**（``settings.case_lint_strict``）——它既不是文档
    属性、也不再是 ``record_lint()`` 的参数。过去被检文档可以自己写
    ``package_strict: false`` 让覆盖率门禁整段跳过（智能体能借此绕过验收），
    所以这个决定权被收回到平台侧。测试必须显式固定它，否则会跟着 .env 漂移；
    要验非严格分支的用例，在测试体内再 monkeypatch 覆盖即可。
    """
    monkeypatch.setattr(svc.settings, "case_lint_strict", True, raising=False)


VALID = """# 登录用例集

## 登录

#### 正确密码登录 [P0]
<!-- CASE: CASE-A-001; REQ: REQ-A-001; RISK: RISK-A-001 -->
前置：账号已注册
- 输入正确密码 ⇒ 进入首页
"""


# 注意：这里**没有** ``strict`` 字段。需求包不能声明"请宽松地检查我"——
# 严格程度由 settings.case_lint_strict 决定（见上面 fixture 的说明）。
STRICT_PACKAGE = {
    "requirements": [{"id": "REQ-A-001"}],
    "risks": [{"id": "RISK-A-001"}],
    "coverage_plan": [{"requirement_id": "REQ-A-001", "case_ids": ["CASE-A-001"]}],
}


def test_metadata_is_parsed_without_polluting_case_or_steps():
    parsed = svc.parse_cases_md(VALID)
    case = parsed["tree"][0]["cases"][0]
    assert parsed["case_count"] == 1
    assert case["name"] == "正确密码登录"
    assert case["metadata"] == {
        "case_id": "CASE-A-001",
        "requirements": ["REQ-A-001"],
        "risks": ["RISK-A-001"],
    }
    assert case["steps"][0]["action"] == "输入正确密码"


def test_strict_lint_accepts_traceable_document():
    report = svc.lint_case_document(VALID, STRICT_PACKAGE)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["stats"]["requirements_covered"] == 1


def test_missing_metadata_blocks_when_platform_is_strict_and_warns_when_not(monkeypatch):
    """缺元数据在两档下的表现：严格档阻断，非严格档降级为告警。

    两档的切换现在是**平台开关**（settings.case_lint_strict），所以两条分支都
    要显式覆盖它——这也正是这条测试存在的意义：证明档位是平台侧说了算的。
    """
    legacy = "# t\n\n## g\n\n#### c [P1]\n- a ⇒ b\n"

    monkeypatch.setattr(svc.settings, "case_lint_strict", True, raising=False)
    strict = svc.lint_case_document(legacy)
    assert strict["ok"] is False
    assert any(item["code"] == "CASE_METADATA_MISSING" for item in strict["errors"])

    monkeypatch.setattr(svc.settings, "case_lint_strict", False, raising=False)
    lenient = svc.lint_case_document(legacy)
    assert lenient["ok"] is True
    assert any(item["code"] == "CASE_METADATA_MISSING" for item in lenient["warnings"])


def test_invalid_metadata_is_blocking():
    invalid = VALID.replace("CASE-A-001", "case-a-001")
    report = svc.lint_case_document(invalid, STRICT_PACKAGE)
    assert report["ok"] is False
    assert any(item["code"] == "METADATA_ID_INVALID" for item in report["errors"])


def test_sidecar_revision_and_optimistic_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "get_workspace_dir", lambda *args, **kwargs: tmp_path)
    first = svc.save_doc("项目A", VALID)
    assert first["revision"] == 1
    second = svc.save_doc("项目A", VALID + "\n")
    assert second["revision"] == 2
    with pytest.raises(workflow.WorkflowConflictError):
        svc.save_doc("项目A", VALID, expected_revision=1)
    with pytest.raises(workflow.WorkflowConflictError):
        svc.save_doc("项目A", VALID, expected_hash="not-current")


def test_release_requires_lint_and_review(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "get_workspace_dir", lambda *args, **kwargs: tmp_path)
    svc.save_doc("项目A", VALID)
    workflow.save_requirement_package("项目A", STRICT_PACKAGE)
    report = svc.lint_case_document(VALID, STRICT_PACKAGE)
    workflow.record_lint("项目A", report)
    with pytest.raises(workflow.WorkflowTransitionError):
        workflow.transition("项目A", "approved", actor="u1")
    workflow.record_review("项目A", {"verdict": "pass", "issues": []})
    approved = workflow.transition("项目A", "approved", actor="u1")
    assert approved["lifecycle_status"] == "approved"
    released = workflow.transition("项目A", "released", actor="u1")
    assert released["lifecycle_status"] == "released"


def _prepare_reviewable(tmp_path, monkeypatch, name="项目A"):
    monkeypatch.setattr(svc, "get_workspace_dir", lambda *args, **kwargs: tmp_path)
    svc.save_doc(name, VALID)
    workflow.save_requirement_package(name, STRICT_PACKAGE)
    report = svc.lint_case_document(VALID, STRICT_PACKAGE)
    workflow.record_lint(name, report)
    return name


def test_review_cap_is_cumulative_across_saves(tmp_path, monkeypatch):
    """修复循环（改→存→复核）不能绕开累计复核上限。"""
    name = _prepare_reviewable(tmp_path, monkeypatch)
    for round_no in range(workflow.MAX_REVIEW_CALLS):
        # 每轮都模拟：复核 → 内容修改保存（review_round 清零）
        workflow.record_review(name, {"verdict": "needs_revision", "issues": [
            {"severity": "high", "code": "MISSING_COVERAGE"}
        ]})
        meta = workflow.load_metadata(name)
        assert meta["review_calls_total"] == round_no + 1
        svc.save_doc(name, VALID + f"\n<!-- 轮次{round_no}占位 -->\n" if round_no == 0 else VALID + "\n")
    with pytest.raises(workflow.WorkflowTransitionError, match="上限"):
        workflow.record_review(name, {"verdict": "needs_revision", "issues": []})


def test_review_quota_resets_on_requirement_package_update(tmp_path, monkeypatch):
    """用户补充需求答复（需求包更新）后，复核配额重新计。"""
    name = _prepare_reviewable(tmp_path, monkeypatch)
    for _ in range(workflow.MAX_REVIEW_CALLS):
        workflow.record_review(name, {"verdict": "needs_revision", "issues": [
            {"severity": "high", "code": "MISSING_COVERAGE"}
        ]})
        workflow.record_lint(
            name, svc.lint_case_document(VALID, STRICT_PACKAGE)
        )
    with pytest.raises(workflow.WorkflowTransitionError):
        workflow.record_review(name, {"verdict": "pass", "issues": []})
    workflow.save_requirement_package(name, STRICT_PACKAGE)
    meta = workflow.load_metadata(name)
    assert meta["review_calls_total"] == 0
    workflow.record_lint(
        name, svc.lint_case_document(VALID, STRICT_PACKAGE)
    )
    workflow.record_review(name, {"verdict": "pass", "issues": []})
    assert workflow.load_metadata(name)["review_status"] == "passed"


def test_review_service_blocks_before_model_call_when_over_quota(tmp_path, monkeypatch):
    """超限时 review 服务在调用模型前就拒绝（省一次 LLM 开销）。"""
    import asyncio

    from src.app.services import case_review_service as review_svc

    name = _prepare_reviewable(tmp_path, monkeypatch)
    meta = workflow.load_metadata(name)
    meta["review_calls_total"] = workflow.MAX_REVIEW_CALLS
    workflow.save_metadata(name, meta)

    def _no_model(*a, **k):  # 模型必须不被调用
        raise AssertionError("model must not be invoked over quota")

    monkeypatch.setattr(review_svc, "build_chat_model", _no_model)
    with pytest.raises(workflow.WorkflowTransitionError, match="上限"):
        asyncio.run(review_svc.review_case_document(name))
