from __future__ import annotations

import pytest

from src.app.services import case_docs_service as svc
from src.app.services import case_workflow_service as workflow


VALID = """# 登录用例集

## 登录

#### 正确密码登录 [P0]
<!-- CASE: CASE-A-001; REQ: REQ-A-001; RISK: RISK-A-001 -->
前置：账号已注册
- 输入正确密码 ⇒ 进入首页
"""


STRICT_PACKAGE = {
    "strict": True,
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
    report = svc.lint_case_document(VALID, STRICT_PACKAGE, strict=True)
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["stats"]["requirements_covered"] == 1


def test_strict_lint_reports_missing_metadata_but_legacy_mode_warns():
    legacy = "# t\n\n## g\n\n#### c [P1]\n- a ⇒ b\n"
    compatibility = svc.lint_case_document(legacy)
    strict = svc.lint_case_document(legacy, {"strict": True}, strict=True)
    # Legacy mode accepts old documents but reports metadata as a warning.
    assert compatibility["ok"] is True
    assert any(item["code"] == "CASE_METADATA_MISSING" for item in compatibility["warnings"])
    assert strict["ok"] is False
    assert any(item["code"] == "CASE_METADATA_MISSING" for item in strict["errors"])


def test_invalid_metadata_is_blocking():
    invalid = VALID.replace("CASE-A-001", "case-a-001")
    report = svc.lint_case_document(invalid, STRICT_PACKAGE, strict=True)
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
    report = svc.lint_case_document(VALID, STRICT_PACKAGE, strict=True)
    workflow.record_lint("项目A", report, strict=True)
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
    report = svc.lint_case_document(VALID, STRICT_PACKAGE, strict=True)
    workflow.record_lint(name, report, strict=True)
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
            name, svc.lint_case_document(VALID, STRICT_PACKAGE, strict=True), strict=True
        )
    with pytest.raises(workflow.WorkflowTransitionError):
        workflow.record_review(name, {"verdict": "pass", "issues": []})
    workflow.save_requirement_package(name, STRICT_PACKAGE)
    meta = workflow.load_metadata(name)
    assert meta["review_calls_total"] == 0
    workflow.record_lint(
        name, svc.lint_case_document(VALID, STRICT_PACKAGE, strict=True), strict=True
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
