"""进程内快速失败（熔断）。

解决的是一个很具体的浪费：外部依赖挂了之后，**每一次调用仍然老老实实等满超时**。
LightRAG 检索 120s、代码图谱工具调用 45s——一个多步任务碰上服务没起，光等超时就能
耗掉几分钟，而且每一步都要重新等一遍。

所以这里只做**快速失败**：连续失败到阈值后，短时间内直接返回失败，不再走网络。

**不做自动重试。** 理由在 ``middleware/run_guards.py`` 里写过了：工具失败一律转成
ToolMessage 交回模型判断（``handle_tool_error=True``），自动重放有副作用的工具
（执行命令、批准用例、写文件）语义不明确。快速失败和自动重试是两件事，这里只做前者。

**只挂"短查询"类调用。** 长任务（全量索引 1800s、脚本执行 300s）不挂：失败一次
不代表服务不可用，挂上会误伤正常的长失败。所以接入点是显式的布尔参数，不是按超时
阈值猜。

阈值与冷却走 ``settings.circuit_breaker_*``（``fail_max <= 0`` 表示关闭熔断，退化成
原来的"每次都试"）。

进程内状态：和 ``eval/live.py`` 的 ``LIVE`` 集合同样口径——单 worker 部署下它是权威的，
多 worker 时每个进程各自计数（退化但不会出错）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from src.app.core.config import settings


@dataclass
class _State:
    fails: int = 0
    open_until: float = 0.0


class Guard:
    """一个外部依赖的快速失败开关。每个 service 一个实例（模块级单例）。"""

    def __init__(self, name: str, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.name = name
        self._state = _State()
        # 可注入的时钟：测试里换成假时钟就能精确验证冷却窗口，不用真的 sleep
        self._clock = clock

    def blocked(self) -> str | None:
        """调用前问一句：现在能不能打。

        返回 ``None`` 表示放行；否则是给调用方（最终是给模型/用户）的说明，
        直接当 ``error`` 文本用。
        """
        remaining = self._state.open_until - self._clock()
        if remaining <= 0:
            return None
        return (f"{self.name} 连续失败 {self._state.fails} 次，"
                f"{remaining:.0f} 秒内不再尝试（熔断中）；"
                f"确认服务恢复后会自动重试")

    def ok(self) -> None:
        """调用成功：清零。"""
        self._state = _State()

    def fail(self) -> None:
        """调用失败：累计；到阈值就打开冷却窗口。

        冷却期过后的第一次调用会被放行（半开探针）——但计数不清零，所以探针再失败
        就立刻重新打开，不用再攒够阈值。
        """
        limit = settings.circuit_breaker_fail_max
        if limit <= 0:
            return
        self._state.fails += 1
        if self._state.fails >= limit:
            self._state.open_until = (
                self._clock() + max(0, settings.circuit_breaker_reset_timeout)
            )
