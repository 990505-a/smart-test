"""监控（日常智能体使用链路 → Langfuse）测试。

重点不是"上报成功"，而是**上报失败绝不能影响对话**：监控是旁路，配置缺失、
端点挂了、代码有 bug，都不该让 agent 的一次回答失败。所以这里测：
* 未配置时客户端为空、中间件空转
* 采集到的内容（generation / tool span）正确落在一条 trace 上
* trace 带 sessionId（Langfuse 里按会话聚合）
* 上报抛异常被吞掉
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.app.monitoring import tracing


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch):
    """隔离宿主机 .env：监控配置只按测试里给的值解析。"""
    monkeypatch.setattr(tracing, "_read_env_file", lambda: {})
    tracing.invalidate_monitor_env_cache()


class TestConfig:
    def test_usable_only_when_all_three_fields_present(self, monkeypatch):
        monkeypatch.setattr(tracing, "monitor_config", lambda: tracing.MonitorConfig(
            enabled=True, base_url="http://lf:3000", public_key="pk", secret_key="sk",
            environment="monitor"))
        assert tracing.monitor_config().usable is True
        monkeypatch.setattr(tracing, "monitor_config", lambda: tracing.MonitorConfig(
            enabled=True, base_url="http://lf:3000", public_key="pk", secret_key="",
            environment="monitor"))
        assert tracing.monitor_config().usable is False

    def test_client_is_none_when_disabled(self, monkeypatch):
        monkeypatch.setattr(tracing, "monitor_config", lambda: tracing.MonitorConfig(
            enabled=False, base_url="http://lf:3000", public_key="pk", secret_key="sk",
            environment="monitor"))
        assert tracing.monitor_client() is None

    def test_enabled_flag_parsing(self, monkeypatch):
        monkeypatch.setattr(tracing, "_read_env_file", lambda: {
            "LANGFUSE_MONITOR_ENABLED": "false",
            "LANGFUSE_MONITOR_BASE_URL": "http://host.docker.internal:3000",
        })
        config = tracing.monitor_config()
        assert config.enabled is False and config.base_url.endswith(":3000")


class TestTraceBuilding:
    def _middleware(self, monkeypatch) -> tracing.MonitorMiddleware:
        monkeypatch.setattr(tracing, "monitor_config", lambda: tracing.MonitorConfig(
            enabled=True, base_url="http://lf:3000", public_key="pk", secret_key="sk",
            environment="monitor"))
        monkeypatch.setattr(tracing.MonitorMiddleware, "_thread_id", lambda self: "thread-1")
        return tracing.MonitorMiddleware("testcase_agent")

    def test_records_generation_and_tool_span(self, monkeypatch):
        middleware = self._middleware(monkeypatch)
        trace = middleware._start("thread-1")
        assert trace is not None and trace.steps == [] and trace.tools == []

        request = SimpleNamespace(
            model=SimpleNamespace(model_name="glm-5.3-flash"),
            messages=[SimpleNamespace(type="human", content="给登录功能写 3 条测试点")],
        )
        response = SimpleNamespace(result=[SimpleNamespace(
            content="1. 正确登录\n2. 密码错误\n3. 账号锁定", tool_calls=[],
            usage_metadata={"input_tokens": 120, "output_tokens": 42, "total_tokens": 162})])
        middleware._record_generation(request, 0.0, 1.5, response=response)
        middleware._record_tool({"id": "call-1", "name": "save_case_document",
                                "args": {"project_name": "login"}}, 1.6, 2.4, output="ok")

        assert trace.steps[0].model == "glm-5.3-flash"
        assert trace.steps[0].usage == {"input": 120, "output": 42, "total": 162}
        assert "正确登录" in trace.steps[0].output
        assert trace.tools[0].name == "save_case_document"
        assert trace.tools[0].is_error is False

        batch = trace.to_ingestion_batch()
        trace_event = next(e for e in batch if e["type"] == "trace-create")
        assert trace_event["body"]["sessionId"] == "thread-1"
        assert trace_event["body"]["tags"] == ["testcase_agent"]
        assert any(e["type"] == "generation-create" for e in batch)
        assert any(e["type"] == "span-create" for e in batch)

    def test_failed_model_call_is_recorded_as_error_event(self, monkeypatch):
        middleware = self._middleware(monkeypatch)
        trace = middleware._start("thread-1")
        request = SimpleNamespace(model=SimpleNamespace(model_name="m"), messages=[])
        middleware._record_generation(request, 0.0, 1.0, error=RuntimeError("端点 401"))
        assert trace.steps[0].output.startswith("[error]")
        assert any(e["name"] == "model-error" for e in trace.events)

    def test_middleware_records_through_wrap_hooks(self, monkeypatch):
        middleware = self._middleware(monkeypatch)
        request = SimpleNamespace(
            model=SimpleNamespace(model_name="m"),
            messages=[SimpleNamespace(type="human", content="任务")],
        )

        async def handler(_req):
            return SimpleNamespace(result=[])

        asyncio.run(middleware.awrap_model_call(request, handler))
        trace = middleware._traces["thread-1"]
        assert len(trace.steps) == 1


class TestUploadFailureIsSwallowed:
    def test_upload_errors_never_propagate(self, monkeypatch):
        monkeypatch.setattr(tracing, "monitor_config", lambda: tracing.MonitorConfig(
            enabled=True, base_url="http://lf:3000", public_key="pk", secret_key="sk",
            environment="monitor"))
        monkeypatch.setattr(tracing.MonitorMiddleware, "_thread_id", lambda self: "t")

        class Boom:
            def ingest(self, events):
                raise RuntimeError("langfuse 挂了")

            def close(self):
                pass

        monkeypatch.setattr(tracing, "monitor_client", lambda: Boom())
        middleware = tracing.MonitorMiddleware("testcase_agent")
        trace = middleware._start("t")
        trace.steps.append(tracing.StepGeneration(index=1, model="m"))
        middleware._upload(trace)  # 不抛异常

    def test_empty_trace_is_not_uploaded(self, monkeypatch):
        called: list[int] = []
        monkeypatch.setattr(tracing, "monitor_client", lambda: called.append(1))
        middleware = tracing.MonitorMiddleware("testcase_agent")
        middleware._upload(tracing.MonitorTrace(session_id="t#1"))
        assert called == []

    def test_disabled_middleware_does_not_track(self, monkeypatch):
        monkeypatch.setattr(tracing.MonitorMiddleware, "_thread_id", lambda self: "t")
        middleware = tracing.MonitorMiddleware("testcase_agent", enabled=False)
        assert middleware._start("t") is None
        assert middleware._current() is None
