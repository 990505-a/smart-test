"""Eval dataset format (测评模块).

Same YAML shape as dsh-eval-automation's `datasets/*.yaml`, so a dataset is
portable between the two systems:

```yaml
name: douban-movie-webui
description: 豆瓣电影 H5 站点 Web-UI 自动化测评
agent: webui_agent            # LangGraph assistant (图) 名
items:
  - id: home-001
    input: 打开豆瓣电影首页…            # 交给被测 agent 的任务
    expected:                          # 确定性打分器读这一段
      contains: ['列表']
      tools: { sequence: [webui_run_spec], mode: subsequence }
      evidence: 'artifacts/*.png'
    judge:                             # LLM-as-judge 读这一段
      criteria: …
      pass: 0.7
```

An item with no `expected` and no `judge` still runs — it just produces no
scores, which is useful while authoring cases.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# 默认数据集目录：项目根的 datasets/
DEFAULT_DATASET_DIR = Path(__file__).parent.parent.parent.parent / "datasets"


@dataclass
class ToolExpectation:
    sequence: list[str] = field(default_factory=list)
    mode: str = "subsequence"  # subsequence | exact


@dataclass
class Expectations:
    """Deterministic assertions the scorer layer can check without a model."""

    contains: list[str] = field(default_factory=list)
    not_contains: list[str] = field(default_factory=list)
    tools: ToolExpectation | None = None
    evidence: str | None = None
    max_tool_errors: int | None = None


@dataclass
class JudgeSpec:
    criteria: str
    pass_threshold: float = 0.7


@dataclass
class EvalItem:
    id: str
    input: str
    expected: Expectations | None = None
    judge: JudgeSpec | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # 镜像到 Langfuse 后回填，用于把 trace 挂进 DatasetRun
    langfuse_item_id: str | None = None


@dataclass
class EvalDataset:
    name: str
    items: list[EvalItem]
    description: str | None = None
    agent: str = "webui_agent"
    # 每条用例允许的重试/自修复轮数，覆盖 settings.eval_max_repair
    max_repair: int | None = None
    path: Path | None = None


def load_dataset(path: str | Path) -> EvalDataset:
    """Parse a dataset YAML; every structural error names the offending item."""
    target = Path(path)
    if not target.is_absolute():
        if not target.exists():
            target = DEFAULT_DATASET_DIR / target.name
        if not target.exists():
            target = DEFAULT_DATASET_DIR / str(path)
    if not target.exists():
        raise FileNotFoundError(f"数据集不存在: {path}")

    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    name = raw.get("name")
    if not isinstance(name, str) or name == "":
        raise ValueError(f"{target}: 缺少 name 字段")

    raw_items = raw.get("items") or []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"{target}: items 为空")

    items = [_parse_item(entry, index, target) for index, entry in enumerate(raw_items)]
    duplicate = _first_duplicate([item.id for item in items])
    if duplicate is not None:
        raise ValueError(f"{target}: 用例 id 重复: {duplicate}")

    return EvalDataset(
        name=name,
        items=items,
        description=raw.get("description"),
        agent=str(raw.get("agent") or "webui_agent"),
        max_repair=raw.get("max_repair"),
        path=target,
    )


def _parse_item(entry: Any, index: int, path: Path) -> EvalItem:
    if not isinstance(entry, dict):
        raise ValueError(f"{path}: items[{index}] 不是映射")
    item_id = entry.get("id") or f"item-{index + 1}"
    instruction = entry.get("input")
    if not isinstance(instruction, str) or instruction.strip() == "":
        raise ValueError(f"{path}: 用例 {item_id} 缺少 input")

    expected_raw = entry.get("expected") or {}
    expected = Expectations(
        contains=list(expected_raw.get("contains") or []),
        not_contains=list(expected_raw.get("not_contains") or []),
        evidence=expected_raw.get("evidence"),
        max_tool_errors=expected_raw.get("max_tool_errors"),
        tools=_parse_tools(expected_raw.get("tools")),
    ) if expected_raw else None

    judge_raw = entry.get("judge") or {}
    judge = JudgeSpec(
        criteria=str(judge_raw.get("criteria")),
        pass_threshold=float(judge_raw.get("pass", 0.7)),
    ) if judge_raw.get("criteria") else None

    return EvalItem(
        id=str(item_id), input=instruction, expected=expected, judge=judge,
        metadata=dict(entry.get("metadata") or {}),
    )


def _parse_tools(raw: Any) -> ToolExpectation | None:
    if not isinstance(raw, dict):
        return None
    sequence = [str(name) for name in (raw.get("sequence") or [])]
    if not sequence:
        return None
    mode = str(raw.get("mode") or "subsequence")
    if mode not in ("subsequence", "exact"):
        raise ValueError(f"tools.mode 只能是 subsequence / exact，收到 {mode}")
    return ToolExpectation(sequence=sequence, mode=mode)


def _first_duplicate(values: list[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def item_id_for(dataset_name: str, item_id: str) -> str:
    """Deterministic Langfuse dataset-item id — the API upserts on ``id``.

    Same convention as the dsh runner, so re-running a dataset updates items in
    place instead of accumulating a new copy every time.
    """
    import re

    safe = re.sub(r"[^A-Za-z0-9_-]", "-", f"smart-test-{dataset_name}-{item_id}")
    return safe[:255]


# ---------------------------------------------------------------------------
# 写回：页面上的「评测集编辑器」用这套把结构化数据落成 YAML
# ---------------------------------------------------------------------------

class _Dumper(yaml.SafeDumper):
    """多行字符串用 ``|`` 块写出来——用例的 input / criteria 都是长中文，
    转义成一行 ``'…\n…'`` 就没法读了。"""


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _represent_str)


def dataset_payload(dataset: EvalDataset, *, file: str | None = None) -> dict:
    """EvalDataset → 可编辑的结构化 JSON（形状与 YAML 一一对应）。"""
    items: list[dict[str, Any]] = []
    for item in dataset.items:
        entry: dict[str, Any] = {"id": item.id, "input": item.input}
        expected = item.expected
        if expected is not None:
            block: dict[str, Any] = {}
            if expected.contains:
                block["contains"] = list(expected.contains)
            if expected.not_contains:
                block["not_contains"] = list(expected.not_contains)
            if expected.tools is not None and expected.tools.sequence:
                block["tools"] = {"sequence": list(expected.tools.sequence),
                                  "mode": expected.tools.mode}
            if expected.max_tool_errors is not None:
                block["max_tool_errors"] = expected.max_tool_errors
            if expected.evidence:
                block["evidence"] = expected.evidence
            if block:
                entry["expected"] = block
        if item.judge is not None:
            entry["judge"] = {"criteria": item.judge.criteria,
                              "pass_threshold": item.judge.pass_threshold}
        if item.metadata:
            entry["metadata"] = dict(item.metadata)
        items.append(entry)

    payload: dict[str, Any] = {"name": dataset.name, "items": items}
    if dataset.description:
        payload["description"] = dataset.description
    payload["agent"] = dataset.agent
    if dataset.max_repair is not None:
        payload["max_repair"] = dataset.max_repair
    if file is not None:
        payload["file"] = file
    return payload


def dumps_dataset(payload: dict) -> str:
    """结构化数据 → YAML 文本（带一行说明头，方便手改后仍知道它从哪来）。"""
    body = {"name": payload.get("name")}
    if payload.get("description"):
        body["description"] = payload["description"]
    body["agent"] = payload.get("agent") or "webui_agent"
    if payload.get("max_repair") is not None:
        body["max_repair"] = payload["max_repair"]
    body["items"] = payload.get("items") or []

    header = ("# 由平台「评测集」页面保存；直接手改也可以，页面会读回。\n"
              "# 字段说明见 eval-course/reference/dataset-and-gate.html 或 EVAL.md。\n")
    return header + yaml.dump(body, Dumper=_Dumper, allow_unicode=True, sort_keys=False,
                              width=100, default_flow_style=False)


def save_dataset(path: Path, payload: dict) -> EvalDataset:
    """写盘后立刻回读校验：宁可保存时报错，也不要等到跑批次才炸。

    校验在临时文件上做、通过了才替换原文件——否则一次写坏的编辑会把原来
    那个能跑的数据集直接抹掉。
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps_dataset(payload), encoding="utf-8")
    try:
        dataset = load_dataset(tmp)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return load_dataset(path)
