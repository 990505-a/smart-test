from __future__ import annotations

import pytest

from src.app.services.case_review_service import _decode_report


def test_decode_review_report_normalizes_and_forces_blocking_verdict():
    report = _decode_report(
        "```json\n"
        '{"verdict":"pass","summary":"ok","issues":[{"severity":"high",'
        '"code":"CONTRADICTION","case_id":"CASE-A-001"}]}\n'
        "```"
    )
    assert report["verdict"] == "needs_revision"
    assert report["issues"][0]["severity"] == "high"


def test_decode_review_report_rejects_invalid_shape():
    with pytest.raises(ValueError):
        _decode_report('{"verdict":"pass","issues":{"bad":true}}')
    with pytest.raises(ValueError):
        _decode_report('{"verdict":"pass","issues":[{"severity":"critical"}]}')
    with pytest.raises(ValueError):
        _decode_report("not json")
