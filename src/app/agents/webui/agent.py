"""兼容 shim：旧的「Web-UI 自动化」单能力 graph.

只为历史会话续跑保留。装配全部来自 ``agents/capabilities.py``，本文件不再持有工具
列表与提示词。新会话请用 ``smart_test_agent``。
"""

from src.app.agents.capabilities import CAPABILITY_BY_KEY
from src.app.agents.harness import build_agent

agent = build_agent(
    (CAPABILITY_BY_KEY["webui"],),
    name="webui_agent",
    default_dir_name="web-ui",
)
