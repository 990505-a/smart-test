"""Agent 图内部嵌套 LLM 调用的流式隔离。

背景：LangGraph 运行期间（stream_mode 含 messages），工具或中间件内部
直接 ``model.ainvoke(...)`` 的嵌套调用会继承父 run 的回调链，其输出
chunk 会被当作主对话消息流式推给前端 —— 用户会在聊天里看到评审器的
原始 JSON、上下文压缩摘要（## SESSION INTENT）等内部产物。

修复方式：给内部模型包一层 ``_IsolatedModel``，调用时强制
``callbacks=[]`` 覆盖继承的回调管理器，使嵌套调用从父 run 的
tracing/streaming 中消失（LangChain ensure_config 的合法逃生门：
显式非 None 的 callbacks 会覆盖继承值）。

deepagents 的 ``create_deep_agent`` 在基座栈内部自建
SummarizationMiddleware（用主模型做摘要，无注入参数），因此通过替换
``deepagents.graph.create_summarization_middleware`` 工厂把摘要模型包上
隔离层。评审器（case_review_service）的隔离在同文件内直接配置。
"""

from __future__ import annotations

from langchain_core.runnables import RunnableBinding


class _IsolatedModel(RunnableBinding):
    """包装模型：ainvoke/astream 时剥离继承的父 run 回调。"""

    async def ainvoke(self, input, config=None, **kwargs):  # noqa: A002
        merged = dict(config or {})
        merged["callbacks"] = []  # 覆盖（而非合并）继承的回调管理器
        return await self.bound.ainvoke(input, merged, **kwargs)

    def invoke(self, input, config=None, **kwargs):  # noqa: A002
        merged = dict(config or {})
        merged["callbacks"] = []
        return self.bound.invoke(input, merged, **kwargs)


def install() -> None:
    """把 deepagents 基座栈里的摘要模型替换为隔离包装。幂等。

    注意不能在工厂入口包模型：``create_summarization_middleware`` 校验
    ``model`` 必须是 ``BaseChatModel``，RunnableBinding 包装会直接
    GraphLoadError。正确姿势是先用真实模型构造（过校验），再把中间件
    内部的 ``_summary_model``（``model.with_retry()`` 的产物）换成隔离包装。
    """
    import deepagents.graph as graph

    if getattr(graph.create_summarization_middleware, "_isolation_installed", False):
        return
    original = graph.create_summarization_middleware

    def isolated_factory(model, *args, **kwargs):
        middleware = original(model, *args, **kwargs)
        # deepagents 的实现把 langchain 中间件放在 _lc_helper 里，
        # _summary_model 可能在两层中的任意一层。
        for holder in (middleware, getattr(middleware, "_lc_helper", None)):
            inner = getattr(holder, "_summary_model", None)
            if inner is not None:
                holder._summary_model = _IsolatedModel(bound=inner)
                break
        return middleware

    isolated_factory._isolation_installed = True  # type: ignore[attr-defined]
    graph.create_summarization_middleware = isolated_factory
