"""通用测试智能体 (接口自动化模块之外的统一对话入口).

平台对话页**唯一**的智能体：需求分析、用例生成、Unity 客户端自动化、Web/H5 自动化
都在它一个工具面上，由它自己判断该用哪一类 —— 用户不需要先选模式。

专项能力不在这里硬编码，而在 ``agents/capabilities.py`` 的能力清单里：加一个能力
（比如将来的接口探索执行）只需在清单里加一条，本文件不用动。
装配逻辑在 ``agents/harness.py``。
"""

from src.app.agents.harness import GENERAL_AGENT_NAME, build_general_agent

agent = build_general_agent()
