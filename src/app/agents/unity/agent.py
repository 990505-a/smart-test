"""兼容 shim：旧的「Unity 自动化」单能力 graph.

只为历史会话续跑保留。装配（工具 / 提示词 / 中间件 / 审批）全部来自
``agents/capabilities.py``，本文件不再持有工具列表与提示词 —— 那正是这次改造要
消除的东西：装配只有一个可读处。

新会话请用 ``smart_test_agent``。若确认没有会话再指向它，删掉 ``graph.json`` 里
对应条目即可。
"""

from src.app.agents.capabilities import CAPABILITY_BY_KEY
from src.app.agents.harness import build_agent

agent = build_agent(
    (CAPABILITY_BY_KEY["unity"],),
    name="unity_agent",
    default_dir_name="unity",
)
