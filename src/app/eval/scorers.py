"""Scorers for the eval runner (测评模块).

Same three-tier split as dsh-eval-automation, because the tiers answer
different questions and fail differently:

1. **确定性打分器** — reproducible, free, no network. These are the workhorses
   and the only thing a regression gate should block on.
2. **LLM-as-judge** — for criteria with no crisp rule ("did it actually verify
   the page, or guess?"). Adds a signal; never the sole gate.
3. **Langfuse 人工标注** —校准 judge 本身, done in the UI, not here.

A scorer sees one item plus its {@link RunRecord} and returns zero or more
scores in Langfuse's vocabulary. Scorers are plain classes so a suite can mix
the shipped ones with its own.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from src.app.core.config import settings
from src.app.eval.dataset import EvalItem
from src.app.eval.tracing import RunTrace

logger = logging.getLogger(__name__)

ScoreValue = float | str | bool


@dataclass
class ScoreResult:
    """One score, already in Langfuse's vocabulary."""

    name: str
    value: ScoreValue
    data_type: str  # NUMERIC | BOOLEAN | CATEGORICAL
    comment: str | None = None


@dataclass
class RunRecord:
    """What the scorers get to see about one executed item."""

    item: EvalItem
    trace: RunTrace
    duration_ms: int
    error: str | None = None
    # 执行期产生的证据（playwright artifacts 等），由 runner 汇总
    evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def final_response(self) -> str:
        return self.trace.output or ""

    @property
    def tool_names(self) -> list[str]:
        return [span.name for span in self.trace.tools]

    @property
    def tool_error_count(self) -> int:
        return sum(1 for span in self.trace.tools if span.is_error)


class Scorer(Protocol):
    name: str

    async def score(self, record: RunRecord) -> list[ScoreResult]: ...


async def score_run(scorers: list[Scorer], record: RunRecord) -> list[ScoreResult]:
    """Collect every scorer's output.

    One scorer throwing degrades to a CATEGORICAL note rather than losing the
    whole item — a judge endpoint being down must not void the deterministic
    scores that did compute.
    """
    out: list[ScoreResult] = []
    for scorer in scorers:
        try:
            out.extend(await scorer.score(record))
        except Exception as exc:  # noqa: BLE001
            logger.warning("scorer %s failed on %s: %s", scorer.name, record.item.id, exc)
            out.append(ScoreResult(
                name=f"{scorer.name}_error", value=str(exc)[:300],
                data_type="CATEGORICAL", comment="打分器抛错，该项未计分"))
    return out


# ---------------------------------------------------------------------------
# Deterministic
# ---------------------------------------------------------------------------

class FinalResponseContains:
    """`task_output_match`: the final answer carries the expected evidence."""

    name = "final-response-contains"
    score_name = "task_output_match"

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        expected = record.item.expected
        if expected is None or not expected.contains:
            return []
        haystack = record.final_response
        hits = [needle for needle in expected.contains if needle in haystack]
        return [ScoreResult(
            name=self.score_name,
            value=bool(hits),
            data_type="BOOLEAN",
            comment=(f"命中 {hits!r}" if hits
                     else f"最终回答未包含任何期望片段: {expected.contains!r}"),
        )]


class ForbiddenContent:
    """`no_forbidden_content`: the answer avoids claims that must not appear."""

    name = "forbidden-content"
    score_name = "no_forbidden_content"

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        expected = record.item.expected
        if expected is None or not expected.not_contains:
            return []
        haystack = record.final_response
        found = [needle for needle in expected.not_contains if needle in haystack]
        return [ScoreResult(
            name=self.score_name,
            value=not found,
            data_type="BOOLEAN",
            comment=(f"出现禁止内容 {found!r}" if found else "未出现禁止内容"),
        )]


class ToolCallSequence:
    """`tool_sequence`: the run used the tools the task implies, in order."""

    name = "tool-call-sequence"
    score_name = "tool_sequence"

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        expected = record.item.expected
        if expected is None or expected.tools is None:
            return []
        actual = record.tool_names
        wanted = expected.tools.sequence
        ok = (actual == wanted if expected.tools.mode == "exact"
              else _is_subsequence(wanted, actual))
        return [ScoreResult(
            name=self.score_name,
            value=ok,
            data_type="BOOLEAN",
            comment=f"期望 {expected.tools.mode} {wanted}；实际 {actual}",
        )]


class ToolErrorBudget:
    """`tool_errors`: a guard against agents that burn the budget on failures."""

    name = "tool-error-budget"
    score_name = "tool_errors"

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        expected = record.item.expected
        if expected is None or expected.max_tool_errors is None:
            return []
        count = record.tool_error_count
        budget = expected.max_tool_errors
        return [ScoreResult(
            name=self.score_name,
            value=count,
            data_type="NUMERIC",
            comment=f"工具报错 {count} 次，预算 ≤{budget}",
        )]


class EvidenceExists:
    """`evidence_exists`: the run left the artifact the item asked for.

    Only exact relative paths and single-`*` wildcards are honoured — a full
    glob engine would be a dependency for no extra expressiveness.
    """

    name = "evidence-exists"
    score_name = "evidence_exists"

    def __init__(self, available: Any = None) -> None:
        # ``available`` 是「本次运行实际产出的证据路径集合」，由 runner 传入；
        # 缺省时退化为文件系统检查（本地跑测试用）。
        self._available = available

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        expected = record.item.expected
        if expected is None or not expected.evidence:
            return []
        pattern = expected.evidence
        names = [str(entry.get("name") or entry.get("path") or "") for entry in record.evidence]
        if self._available is not None:
            found = any(_wildcard_match(pattern, name) for name in names)
        else:
            found = any(_wildcard_match(pattern, name) for name in names) if names else False
        return [ScoreResult(
            name=self.score_name,
            value=found,
            data_type="BOOLEAN",
            comment=(f"命中 {pattern}" if found
                     else f"未产出匹配 {pattern} 的证据；实际 {names[:8]}"),
        )]


def deterministic_scorers(available_evidence: Any = None) -> list[Scorer]:
    return [
        FinalResponseContains(),
        ForbiddenContent(),
        ToolCallSequence(),
        ToolErrorBudget(),
        EvidenceExists(available_evidence),
        WebUiExecutionResults(),
    ]


def _tool_results(record: RunRecord, tool_name: str) -> list[dict[str, Any]]:
    """Pull parsed JSON payloads out of a tool's spans.

    Tool outputs are stringified when they land in the trace, so this re-hydrates
    them; anything unparsable is skipped rather than guessed at.
    """
    payloads: list[dict[str, Any]] = []
    for span in record.trace.tools:
        if span.name != tool_name:
            continue
        raw = span.output
        if not isinstance(raw, str):
            if isinstance(raw, dict):
                payloads.append(raw)
            continue
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    return payloads


class WebUiExecutionResults:
    """`webui_case_pass_rate` — did the agent's own Playwright runs actually pass?

    This is the scorer that measures *execution*, as opposed to
    `task_output_match` which measures the final answer. It reads the
    ``report.stats`` the Playwright CLI produced inside the run, so it can only
    fire when the agent really executed the specs.
    """

    name = "webui-execution-results"
    score_rate = "webui_case_pass_rate"
    score_all_passed = "webui_cases_all_passed"
    tool_name = "webui_run_spec"

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        payloads = _tool_results(record, self.tool_name)
        if not payloads:
            return []
        expected_total = 0
        unexpected_total = 0
        runs = 0
        statuses: list[str] = []
        for payload in payloads:
            stats = (payload.get("report") or {}).get("stats") or {}
            expected = int(stats.get("expected") or 0)
            unexpected = int(stats.get("unexpected") or 0)
            skipped = int(stats.get("skipped") or 0)
            if expected == 0 and unexpected == 0 and skipped == 0:
                continue
            runs += 1
            expected_total += expected
            unexpected_total += unexpected
            statuses.append(str(payload.get("status")))

        if runs == 0:
            return []
        total = expected_total + unexpected_total
        rate = expected_total / total if total else 0.0
        return [
            ScoreResult(name=self.score_rate, value=round(rate, 4), data_type="NUMERIC",
                        comment=f"{runs} 次执行：通过 {expected_total} / 失败 {unexpected_total}"
                                f"（status={statuses}）"),
            ScoreResult(name=self.score_all_passed,
                        value=unexpected_total == 0 and expected_total > 0,
                        data_type="BOOLEAN",
                        comment="全部用例通过" if unexpected_total == 0
                                else f"仍有 {unexpected_total} 条用例失败"),
        ]


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    if not needle:
        return True
    index = 0
    for value in haystack:
        if value == needle[index]:
            index += 1
            if index == len(needle):
                return True
    return False


def _wildcard_match(pattern: str, name: str) -> bool:
    if "*" not in pattern:
        return pattern == name or name.endswith(pattern)
    regex = "^" + ".*".join(re.escape(part) for part in pattern.split("*")) + "$"
    return re.search(regex, name) is not None


# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

_JUDGE_PROMPT = """你在评估一次自主智能体（agent）的运行结果。**只根据下面的评判标准打分**。

## 评判标准
{criteria}

## 交给智能体的任务
{task}

## 智能体的最终回答
{response}

## 工具调用轨迹
{trajectory}

## 本次运行的客观事实
{facts}

请严格按标准判断，特别注意：
- 智能体是否**真的执行/核实过**，还是凭空作答（轨迹是判断依据）；
- 回答与客观事实是否一致；
- 不要因为任务简单就给高分，也不要因为风格问题扣分。

只返回 JSON：{{"score": <0 到 1 的小数>, "rationale": "<一段中文说明>"}}"""


@dataclass
class JudgeEndpoint:
    base_url: str
    api_key: str
    model: str
    #: 模型名的来源：``judge`` = 独立配置，``llm`` / ``deepseek`` = 继承主 LLM。
    #: 界面必须显示这个——否则用户看到卡片上有个模型名，会以为自己配过。
    source: str = "judge"


def judge_endpoint_from_values(values: dict[str, str] | None = None,
                               llm_values: dict[str, str] | None = None) -> JudgeEndpoint:
    """按生效配置构造裁判端点：``JUDGE_*`` 优先，缺省回退主 LLM。

    ``values`` 来自 ``SettingsService.judge_values()``、``llm_values`` 来自
    ``SettingsService.model_values()``（都是 DB → .env → 进程环境），所以设置页
    保存后**下一个批次立刻生效**；留空的项在这里回退到主 LLM。

    ``llm_values`` 是必须传的（网页/CLI 路径都从设置页解析）：回退若只读
    ``settings.llm_model``（进程环境），容器里会拿到创建时注入的那份 .env——
    于是页面显示「judge：glm-4.7」而 agent 实际跑的是设置页里的 glm-5.3-flash，
    两边分叉且没有任何报错。
    """
    values = values or {}
    llm = llm_values or {}
    judge_model = (values.get("judge_model") or "").strip() or settings.judge_model
    judge_base_url = (values.get("judge_base_url") or "").strip() or settings.judge_base_url
    judge_api_key = (values.get("judge_api_key") or "").strip() or settings.judge_api_key

    main_model = (llm.get("llm_model") or "").strip() or settings.llm_model
    main_base_url = (llm.get("llm_base_url") or "").strip() or settings.llm_base_url
    main_api_key = (llm.get("llm_api_key") or "").strip() or settings.llm_api_key
    fallback_model = (llm.get("deepseek_model") or "").strip() or settings.deepseek_model
    fallback_key = (llm.get("deepseek_api_key") or "").strip() or settings.deepseek_api_key

    model = judge_model or main_model or fallback_model
    source = "judge" if judge_model else ("llm" if main_model else "deepseek")
    return JudgeEndpoint(
        base_url=judge_base_url or main_base_url or "https://api.deepseek.com",
        api_key=judge_api_key or main_api_key or fallback_key,
        model=model,
        source=source,
    )


def judge_endpoint_from_settings() -> JudgeEndpoint:
    """只用进程配置解析（CLI 的兜底路径）。

    会先把 .env 刷新进进程配置（``model_factory.refresh_from_env``），所以宿主机
    上跑 CLI 时也能看到设置页刚保存的模型，而不是启动时那一份。
    网页路径走 ``judge_endpoint_from_values``（带设置页解析的值）。
    """
    try:
        from src.app.agents.testcase.model_factory import refresh_from_env

        refresh_from_env()
    except Exception:  # noqa: BLE001 — 刷新失败不该拦住打分
        logger.debug("refresh_from_env failed", exc_info=True)
    return judge_endpoint_from_values(None, None)


class LlmJudge:
    """One structured-output call per item, scored 0..1 against the criteria."""

    name = "llm-judge"

    def __init__(self, endpoint: JudgeEndpoint | None = None, pass_threshold: float = 0.7,
                 transport: Any = None) -> None:
        self.endpoint = endpoint or judge_endpoint_from_settings()
        self.pass_threshold = pass_threshold
        self._transport = transport or self._default_transport

    async def _default_transport(self, prompt: str) -> str:
        if not self.endpoint.api_key:
            raise RuntimeError("llm-judge: 未配置 JUDGE_API_KEY / LLM_API_KEY / DEEPSEEK_API_KEY")
        url = f"{self.endpoint.base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.post(url, headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.endpoint.api_key}",
            }, json={
                "model": self.endpoint.model,
                "messages": [{"role": "user", "content": prompt}],
                # json_object 模式：所有 OpenAI 兼容端点都支持，严格
                # json_schema 并非如此；verdict 形状由 parse_verdict 兜底校验。
                "response_format": {"type": "json_object"},
            })
            if response.status_code >= 300:
                raise RuntimeError(
                    f"llm-judge: endpoint {response.status_code}: {response.text[:200]}")
            body = response.json()
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError("llm-judge: 模型返回空内容")
        return content

    async def score(self, record: RunRecord) -> list[ScoreResult]:
        judge = record.item.judge
        if judge is None:
            return []
        verdict = parse_verdict(await self._transport(self._build_prompt(judge.criteria, record)))
        threshold = judge.pass_threshold or self.pass_threshold
        return [
            ScoreResult(name="llm_judge", value=verdict["score"], data_type="NUMERIC",
                        comment=verdict["rationale"]),
            ScoreResult(name="llm_judge_pass", value=verdict["score"] >= threshold,
                        data_type="BOOLEAN",
                        comment=f"score {verdict['score']} vs threshold {threshold}"),
        ]

    async def probe(self) -> dict[str, Any]:
        """连通性自检：走与真实打分**完全相同**的通道（JSON 模式 + 解析）。

        为什么不用一句"你好"探活：裁判的契约是按 JSON 回话。端点能连、但回自由
        文本时，问题会在批次跑到一半才暴露（每条用例变成执行异常）。这里直接验契约。
        """
        prompt = '你是评委。请只输出 JSON：{"score": 0.9, "rationale": "连通性自检"}'
        raw = await self._transport(prompt)
        verdict = parse_verdict(raw)
        return {"raw": raw[:200], "score": verdict["score"],
                "rationale": verdict["rationale"]}

    def _build_prompt(self, criteria: str, record: RunRecord) -> str:
        trajectory = "\n".join(
            f"- {span.name} {json.dumps(span.arguments, ensure_ascii=False, default=str)[:160]}"
            f" -> {'ERROR: ' if span.is_error else ''}{str(span.output)[:160]}"
            for span in record.trace.tools
        ) or "(无工具调用)"
        facts = [
            f"- 工具调用 {len(record.trace.tools)} 次，其中报错 {record.tool_error_count} 次",
            f"- LLM 步数 {len(record.trace.steps)}，耗时 {record.duration_ms / 1000:.1f}s",
        ]
        if record.evidence:
            facts.append(f"- 产出证据文件 {len(record.evidence)} 个："
                         + ", ".join(str(e.get("name")) for e in record.evidence[:6]))
        if record.error:
            facts.append(f"- 运行报错：{record.error[:300]}")
        return _JUDGE_PROMPT.format(
            criteria=criteria, task=record.item.input,
            response=record.final_response or "(空)", trajectory=trajectory,
            facts="\n".join(facts),
        )


def parse_verdict(raw: str) -> dict[str, Any]:
    """Parse and clamp the judge verdict; malformed output raises (contained upstream)."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"llm-judge: verdict 不是对象: {raw[:200]}")
    score = parsed.get("score")
    if isinstance(score, str):
        try:
            score = float(score)
        except ValueError as exc:
            raise ValueError(f"llm-judge: score 无法解析: {score!r}") from exc
    if not isinstance(score, (int, float)):
        raise ValueError(f"llm-judge: 缺少数值 score: {raw[:200]}")
    rationale = parsed.get("rationale") or parsed.get("reason") or ""
    return {"score": min(1.0, max(0.0, float(score))), "rationale": str(rationale)[:2_000]}
