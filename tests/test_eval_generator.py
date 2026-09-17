"""AI 生成测评集的纯逻辑测试（记录渲染 / 输出清洗 / 文件建议名）。

不测真实 LLM 调用：模型输出千变万化，稳定的部分是"怎么把记录喂进去"和
"怎么把模型吐回来的东西洗干净"——这两段出错的代价最高（脏数据会写成评测集）。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.app.eval import generator


def _row(msg_type: str, content: str, **kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        msg_type=msg_type, content=content,
        tool_calls=kwargs.get("tool_calls"), name=kwargs.get("name"),
    )


class TestRenderTranscript:
    def test_renders_roles_and_tool_calls(self):
        rows = [
            _row("human", "给登录功能写 3 条测试点"),
            _row("ai", "先看需求", tool_calls=json.dumps([{"name": "save_case_document"}])),
            _row("tool", "已保存 cases/login.md", name="save_case_document"),
            _row("ai", "完成，共 3 条"),
        ]
        text = generator.render_transcript(rows, title="登录用例")
        assert "# 会话：登录用例" in text
        assert "## 用户\n给登录功能写 3 条测试点" in text
        assert "本轮调用工具：save_case_document" in text
        assert "### 工具结果 save_case_document" in text
        assert text.count("## 智能体") == 2

    def test_list_content_blocks_are_flattened(self):
        rows = [_row("ai", [{"type": "text", "text": "第一段"}, {"type": "text", "text": "第二段"}])]
        text = generator.render_transcript(rows)
        assert "第一段" in text and "第二段" in text

    def test_long_transcript_keeps_head_and_tail(self):
        # 单条消息先被裁到 4k，所以要让**总长**超限：堆够消息条数
        rows = [_row("human", "开头")] + [
            _row("ai", f"回答 {i} " + "x" * 3_500) for i in range(20)
        ] + [_row("ai", "结尾")]
        text = generator.render_transcript(rows)
        assert len(text) <= generator.MAX_TRANSCRIPT_CHARS + 200
        assert "中段省略" in text
        assert text.startswith("## 用户\n开头")
        assert text.rstrip().endswith("结尾")


class TestNormalizeItems:
    def test_keeps_well_formed_items(self):
        raw = [{
            "id": "reset-001", "input": "验证跨天重置覆盖 04:59/05:00/05:01",
            "expected": {"contains": ["05:00"], "tools": {"sequence": ["webui_run_spec"]},
                         "max_tool_errors": 1},
            "judge": {"criteria": "少一个时间点判不通过", "pass": 0.8},
        }]
        items = generator.normalize_items(raw)
        assert items[0]["id"] == "reset-001"
        assert items[0]["expected"]["contains"] == ["05:00"]
        assert items[0]["expected"]["tools"]["mode"] == "subsequence"
        assert items[0]["judge"]["pass_threshold"] == 0.8

    def test_drops_empty_and_duplicate_inputs(self):
        raw = [
            {"input": "  "},
            {"id": "a", "input": "同一个任务"},
            {"id": "b", "input": "同一个任务"},
        ]
        items = generator.normalize_items(raw)
        assert len(items) == 1 and items[0]["id"] == "a"

    def test_empty_expected_and_judge_are_not_kept(self):
        items = generator.normalize_items([{"input": "任务", "expected": {}, "judge": {"criteria": "  "}}])
        assert "expected" not in items[0] and "judge" not in items[0]

    def test_marks_are_capped(self):
        items = generator.normalize_items([{"input": f"任务 {i}"} for i in range(50)], max_items=5)
        assert len(items) == 5

    def test_unknown_mode_falls_back_to_subsequence(self):
        items = generator.normalize_items([{
            "input": "任务", "expected": {"tools": {"sequence": ["a"], "mode": "weird"}},
        }])
        assert items[0]["expected"]["tools"]["mode"] == "subsequence"


class TestExtractJson:
    def test_fenced_json(self):
        assert generator._extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_surrounding_prose(self):
        assert generator._extract_json('好的，结果如下：\n{"a": 1}\n希望有帮助') == {"a": 1}


class TestSuggestedFile:
    def test_slugifies_and_dedupes(self, tmp_path):
        assert generator.suggested_file("My WebUI Set") == "my-webui-set.yaml"
        (tmp_path / "my-webui-set.yaml").write_text("")
        assert generator.suggested_file("My WebUI Set", tmp_path) == "my-webui-set-2.yaml"


class TestPrompt:
    def test_includes_agent_count_and_focus(self):
        prompt = generator.build_prompt(
            transcript="## 用户\n任务", agent="webui_agent", count=3, focus="只保留失败修复类")
        assert "webui_agent" in prompt and "3 条" in prompt and "只保留失败修复类" in prompt
