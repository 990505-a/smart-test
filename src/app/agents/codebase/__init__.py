"""Codebase Analysis Agent package (代码图谱 · 代码分析智能体).

挂在平台「代码图谱」模块里：会话的目标仓库由该页左栏选中的仓库决定（经
configurable.workspace_path 传入），既服务于页面内的多轮问答，也服务于
定时任务触发的无头「增量影响分析」（见 services/codebase_analysis_service.py）。
"""
