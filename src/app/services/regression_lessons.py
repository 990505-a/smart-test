"""把回归执行的失败蒸馏成可复用的经验（执行结果回灌）。

方案文档里都有"执行结果回灌"这一环，但只有平台真的接了执行器：一次回归跑出来的
失败原因，是**下一次生成用例时最值钱的输入**——它说明在这份 SUT 上，什么样的步骤
与断言是行不通的。

这里刻意只做蒸馏，不做归档：
- 按错误签名合并同一根因（5 条用例因为同一个原因挂掉 → 只记一条）；
- 剥掉 ANSI 色码、expect 框架噪声与堆栈，只留一句话；
- 已经记过的签名不再重复写，避免 failures.md 被同一件事刷屏。

记忆是给下一次生成读的，不是日志仓库。
"""

from __future__ import annotations

import re

from src.app.core.workspace import get_space_id
from src.app.services import memory_service

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_FAIL_RE = re.compile(r"^[✗✘]\s+(?P<title>.+?)\s+\[(?P<status>\w+),\s*\d+ms\]")

#: 每条记忆里最多列几个失败用例标题，其余折成"等 N 条"
_MAX_TITLES = 3
#: 一次运行最多写入几条不同根因，防止一次大崩盘把记忆写满
_MAX_ENTRIES = 4


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def distill_failures(output: str) -> list[dict[str, object]]:
    """抽出失败用例并把同一错误签名的合并成一条。

    Returns:
        [{"error": 错误摘要, "titles": [用例标题, ...]}, ...]，按出现顺序。
    """
    lines = _strip_ansi(output).splitlines()
    grouped: dict[str, dict[str, object]] = {}
    for index, line in enumerate(lines):
        match = _FAIL_RE.match(line.strip())
        if not match:
            continue
        title = match.group("title").strip()
        error = ""
        # 失败行之后紧跟缩进的错误块，取其中第一行有内容的作为摘要
        for probe in range(index + 1, min(index + 7, len(lines))):
            candidate = lines[probe]
            if _FAIL_RE.match(candidate.strip()) or candidate.startswith("--- "):
                break
            if candidate.strip():
                error = candidate.strip()
                break
        error = re.sub(r"^Error:\s*", "", error)
        # expect(received).toBeTruthy() 这类框架噪声对"下次怎么做"没有帮助，去掉；
        # "页面文本：…" 是断言失败时打印的现场快照，几百字符且每次不同，
        # 留着既撑爆记忆又让去重失效。
        error = re.sub(r"expect\(.*?\)\.\w+\(\)", "", error).strip()
        error = re.split(r"；?页面文本[：:]", error)[0].strip()
        signature = error[:110] or "(无错误信息)"
        entry = grouped.setdefault(signature, {"error": signature, "titles": []})
        entry["titles"].append(title)  # type: ignore[union-attr]
    return list(grouped.values())


def _already_recorded(module_text: str, key: str) -> bool:
    """去重键是**用例标题**而不是错误文本。

    同一条用例在不同轮次失败时，断言消息几乎每次都不同（期望值、现场快照都会变），
    用错误文本去重会让同一件事反复写进记忆。用例名是稳定的，用它做键。
    """
    probe = key[:60]
    return bool(probe) and probe in module_text


def record_regression_lessons(
    output: str,
    *,
    target: str = "",
    script_name: str = "",
    space_id: str | None = None,
) -> list[str]:
    """把一次 Web-UI 回归的失败写进 failures.md，返回实际写入的签名列表。

    只记录**失败**；全通过时不写任何东西——记忆里塞"今天都通过了"是纯噪音。
    """
    failures = distill_failures(output)
    if not failures:
        return []

    space = space_id or get_space_id()
    try:
        existing = memory_service.read_module("failures", space_id=space)
    except Exception:  # noqa: BLE001 — 读不到就当作空，不阻断记录
        existing = ""

    written: list[str] = []
    for item in failures:
        if len(written) >= _MAX_ENTRIES:
            break
        signature = str(item["error"])
        titles = [str(t) for t in item["titles"]]  # type: ignore[union-attr]
        # 去重键用第一条用例名：错误文本每轮都变，用例名稳定
        if _already_recorded(existing, titles[0] if titles else signature):
            continue
        shown = "、".join(titles[:_MAX_TITLES])
        if len(titles) > _MAX_TITLES:
            shown += f" 等 {len(titles)} 条"
        where = f"（{script_name} → {target}）" if script_name or target else ""
        body = (
            f"回归实测失败{where}：{shown}。断言给出的原因是：「{signature}」。\n\n"
            f"  **下次怎么做**：先分清是哪种情况——①这条断言假设的行为在被测系统上不成立"
            f"（属真实缺陷或产品差异，应固化进需求或假设）；②断言本身写错了"
            f"（选择器、取值、否定条件写得不严谨，属用例缺陷）。两种都要先实测该路径再写断言，"
            f"不要把「系统应该会提示 / 元素应该可点 / 列表里不该出现某字样」当成默认成立。"
        )
        try:
            memory_service.append_entry("failures", body, space_id=space, source="regression")
            written.append(signature)
        except Exception:  # noqa: BLE001 — 回灌失败不该影响执行结果的记录
            continue
    return written
