"""兼容 shim：旧的「用例生成」单能力 graph.

对话页已合并成一个通用智能体（``smart_test_agent``，见 ``agents/general/agent.py``），
本文件只为**历史会话还能续跑**而保留：现有 `thread_infos.agent == "testcase_agent"`
的会话要继续对话，就得有这个 graph 在。

装配（工具 / 提示词 / 中间件 / 审批）全部来自能力清单，本文件不再持有任何工具列表或
提示词 —— 那正是这次改造要消除的东西：装配只有一个可读处（``agents/capabilities.py``）。

注意行为差异：本 graph 现在用统一的提示词构建器（只挂 testcase 一个能力，因此提示词是
"单一能力"形态，见 ``capabilities.build_system_prompt``），中间件也统一成平台那套
（多了 PDF 上下文与会话上传目录的注入）。历史会话的**消息记录不受影响**，但续跑时的
行为与旧版不完全一致。

新会话请用 ``smart_test_agent``；若确认没有会话再指向它，删除 ``graph.json`` 里对应
条目即可。
"""

from src.app.agents.capabilities import CAPABILITY_BY_KEY
from src.app.agents.harness import build_agent

agent = build_agent(
    (CAPABILITY_BY_KEY["testcase"],),
    name="testcase_agent",
    default_dir_name="testcase",
)
