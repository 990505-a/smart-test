"""AI 生成测评集：从**历史对话的完整记录**里提炼评测用例（测评模块）。

动机：评测集手写成本高，而平台每天都在产生"真实跑过一遍的完整记录"——用户的
原始任务、智能体的每次工具调用与结果、最终答复。这些记录本身就是最好的用例
素材：它们是被真实执行验证过的任务。

流程：

    用户在 /eval 页选一段历史对话（可多个） → 读出 thread_messages 的完整记录
    → 交给主 LLM 提炼成 N 条 {input · expected · judge} → 页面打开编辑器微调 → 保存成 YAML

产物**不直接落盘**：生成结果先回到编辑器，由人来微调后才成为评测集
（"我会按照我的预期去实际微调测评集"）。生成质量因此不必一次到位，可编辑是关键。

LLM 端点复用设置页的主模型配置（``SettingsService.model_values``），带 .env 回退；
裁判/被测 agent 与本生成器三者可以是不同模型，这里只借用主模型的一次结构化调用。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: 交给模型的记录长度上限（超过就保留头尾：开头是任务背景，结尾是结论）
MAX_TRANSCRIPT_CHARS = 60_000
#: 单条工具结果的字符上限（工具输出经常一大坨，全塞进去只会挤掉真正的任务描述）
MAX_TOOL_CHARS = 1_200
#: 一次生成最多几条用例
MAX_ITEMS = 20

_SYSTEM_PROMPT = """你在为「AI 智能体测评平台」整理评测集（回归用例）。

输入是一段**真实跑过的会话记录**（用户任务、智能体的工具调用与结果、最终答复），
以及目标被测智能体的名字。请把它提炼成可重复执行的回归用例。

要求：
1. **自包含**：每条 input 是交给被测智能体的任务原话，脱离本次会话也能执行
   （把当时的必要上下文写进 input，例如需求文档要点、目标地址、项目名）。
2. **只写能判的期望**：expected.contains 选**稳定的事实**（具体数字、字段名、
   文件名、站点名），不要选会变的措辞；不确定就别写。
3. **工具序列**用这次真实用到的关键工具名（subsequence 语义，允许中间夹别的工具）。
4. **judge.criteria 写"判不通过的条件"**（比只写正面要求更有约束力），
   pass 给 0.6~0.8。
5. **不要照抄一次性内容**（临时文件路径、随机 id、当次时间戳）；把它抽象成检查点。
6. 用例之间要有区分度：不要生成语义重复的用例。

只返回 JSON（不要 markdown 代码块），结构：
{"name": "数据集名（英文小写短横线）", "description": "这个集子测什么（中文一句话）",
 "items": [{"id": "item-1", "input": "任务原话",
            "expected": {"contains": ["..."], "not_contains": [],
                          "tools": {"sequence": ["tool_name"], "mode": "subsequence"},
                          "max_tool_errors": 0},
            "judge": {"criteria": "判不通过的条件…", "pass": 0.7}}]}
"""


def _content_to_text(content: Any, limit: int) -> str:
    if isinstance(content, str):
        return content[:limit]
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)[:limit]
    return str(content or "")[:limit]


def render_transcript(rows: list[Any], *, title: str = "") -> str:
    """thread_messages 行 → 给模型看的记录文本（人类可读、工具调用可追溯）。"""
    lines: list[str] = []
    if title:
        lines.append(f"# 会话：{title}")
    for row in rows:
        msg_type = getattr(row, "msg_type", "")
        body = _content_to_text(getattr(row, "content", ""), 4_000)
        if msg_type == "human":
            lines.append(f"\n## 用户\n{body}")
        elif msg_type == "ai":
            tool_names: list[str] = []
            raw_calls = getattr(row, "tool_calls", None)
            if raw_calls:
                try:
                    for call in json.loads(raw_calls):
                        if isinstance(call, dict):
                            tool_names.append(str(call.get("name") or ""))
                except (ValueError, TypeError):
                    pass
            if body.strip():
                lines.append(f"\n## 智能体\n{body}")
            if tool_names:
                lines.append(f"（本轮调用工具：{', '.join(n for n in tool_names if n)}）")
        elif msg_type == "tool":
            name = getattr(row, "name", None) or "tool"
            lines.append(f"\n### 工具结果 {name}\n{body[:MAX_TOOL_CHARS]}")
    transcript = "\n".join(lines).strip()
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        head = transcript[: MAX_TRANSCRIPT_CHARS // 2]
        tail = transcript[-MAX_TRANSCRIPT_CHARS // 2:]
        transcript = f"{head}\n\n…（中段省略：记录过长）…\n\n{tail}"
    return transcript


def _extract_json(text: str) -> dict:
    """模型偶尔会裹一层 ```json 或加解释文字——抠出第一个完整 JSON 对象。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except ValueError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回 JSON") from None
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("模型返回的不是 JSON 对象")
    return data


def _clean_list(value: Any, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        text = str(entry).strip()
        if text and text not in out:
            out.append(text[:200])
        if len(out) >= limit:
            break
    return out


def normalize_items(raw_items: Any, *, max_items: int = MAX_ITEMS) -> list[dict]:
    """模型输出 → 数据集 payload 的 items 形状（空壳字段丢掉）。"""
    if not isinstance(raw_items, list):
        return []
    items: list[dict] = []
    seen_inputs: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            continue
        task = str(raw.get("input") or "").strip()
        if not task or task in seen_inputs:
            continue
        seen_inputs.add(task)
        entry: dict[str, Any] = {
            "id": str(raw.get("id") or f"item-{index}").strip() or f"item-{index}",
            "input": task,
        }
        expected = raw.get("expected") if isinstance(raw.get("expected"), dict) else {}
        block: dict[str, Any] = {}
        contains = _clean_list(expected.get("contains"))
        if contains:
            block["contains"] = contains
        not_contains = _clean_list(expected.get("not_contains"))
        if not_contains:
            block["not_contains"] = not_contains
        tools = expected.get("tools") if isinstance(expected.get("tools"), dict) else {}
        sequence = _clean_list(tools.get("sequence"))
        if sequence:
            block["tools"] = {
                "sequence": sequence,
                "mode": "exact" if str(tools.get("mode")) == "exact" else "subsequence",
            }
        max_errors = expected.get("max_tool_errors")
        if isinstance(max_errors, (int, float)):
            block["max_tool_errors"] = int(max_errors)
        if block:
            entry["expected"] = block
        judge = raw.get("judge") if isinstance(raw.get("judge"), dict) else {}
        criteria = str(judge.get("criteria") or "").strip()
        if criteria:
            try:
                threshold = float(judge.get("pass", judge.get("pass_threshold", 0.7)))
            except (TypeError, ValueError):
                threshold = 0.7
            entry["judge"] = {"criteria": criteria, "pass_threshold": min(max(threshold, 0.0), 1.0)}
        items.append(entry)
        if len(items) >= max_items:
            break
    return items


def build_prompt(*, transcript: str, agent: str, count: int, focus: str = "",
                 name_hint: str = "") -> str:
    parts = [
        f"目标被测智能体：`{agent}`",
        f"请生成 {count} 条评测用例。",
    ]
    if name_hint:
        parts.append(f"数据集名建议：{name_hint}")
    if focus.strip():
        parts.append(f"额外要求（用户指定）：{focus.strip()}")
    parts.append("\n---\n以下是会话记录：\n\n" + transcript)
    return "\n".join(parts)


async def generate_items(*, transcript: str, agent: str, count: int,
                         base_url: str, api_key: str, model: str,
                         focus: str = "", name_hint: str = "",
                         timeout: float = 180.0) -> dict:
    """一次结构化调用 → 数据集 payload（不含 file）。"""
    if not api_key or not base_url:
        raise ValueError("缺少主 LLM 配置（LLM_BASE_URL / LLM_API_KEY），无法生成")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(
                transcript=transcript, agent=agent, count=count,
                focus=focus, name_hint=name_hint)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        response = await client.post(url, headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }, json=payload)
        if response.status_code >= 300:
            raise RuntimeError(f"生成失败：endpoint {response.status_code}: {response.text[:300]}")
        body = response.json()
    content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
    if not content:
        raise RuntimeError("生成失败：模型返回空内容")
    data = _extract_json(content)
    items = normalize_items(data.get("items"), max_items=max(1, min(count, MAX_ITEMS)))
    if not items:
        raise RuntimeError("生成失败：模型没有产出可用用例（请换一段记录或补充要求）")
    name = str(data.get("name") or name_hint or "ai-generated").strip()
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "ai-generated"
    return {
        "name": name,
        "description": str(data.get("description") or "").strip()[:300],
        "agent": agent,
        "items": items,
    }


def suggested_file(name: str, datasel_dir: Path | None = None) -> str:
    """给生成的数据集挑一个不冲突的文件名（同名就加 -2/-3）。"""
    base = re.sub(r"[^a-z0-9-]+", "-", (name or "ai-generated").lower()).strip("-") or "ai-generated"
    candidate = f"{base}.yaml"
    if datasel_dir is None:
        return candidate
    index = 2
    while (datasel_dir / candidate).exists():
        candidate = f"{base}-{index}.yaml"
        index += 1
    return candidate
