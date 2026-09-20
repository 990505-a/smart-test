"""能力清单 (capability manifest) —— 平台智能体的装配数据层.

这是"一个通用智能体、专项能力来自工具/CLI/MCP/Skill"的落点：**能力是数据**，
不是一个写死的 agent 模块。加一个能力（比如将来的接口探索执行）= 在
``CAPABILITIES`` 里加一条，通用智能体自动获得它的工具、领域提示词与技能指引，
**不需要新建 agent、不需要注册新 graph、不需要动前端**。

设计要点
--------
- **工具用符号引用**（``"模块路径:符号名"``）而不是 import 对象：清单因此可序列化
  （`GET /api/v2/agents` 直接吐出去），也避免 capability → tools → agent 的循环导入。
  解析发生在 ``resolve_tools()``，那里是"工具从哪来"的唯一 seam。
- **为什么是平铺而不是子智能体**：deepagents 的 isolated 子智能体只收到一句
  description，拿不到对话历史（``subagents.py:766-768``），而本平台的流程是多轮的
  （"第 3 条用例改一下"）。fork 模式保留历史但仍是 beta、提示词为追加语义、且禁止
  再委派。平铺下对话历史完整。代价如实标注：**技能绑定是提示级而非访问控制级** ——
  模型看得见所有 skill，靠 ``build_system_prompt`` 的分诊表引导它读哪一个。
  真要"某能力看不见某技能"，那需要子智能体，届时在 ``Capability.subagent`` 上扩展。
- **MCP 是可选 seam**：平台自己的工具本来就在进程内（``mcp_servers/agent_tools_server.py``
  也只是薄封装复用它们），走 MCP 是绕路。``mcp_servers`` 字段留给**外部/第三方**
  server，由 ``resolve_tools()`` 经 langchain-mcp-adapters 拉取。
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

from src.app.core.config import settings

logger = logging.getLogger(__name__)


# ===========================================================================
# 数据模型
# ===========================================================================

@dataclass(frozen=True)
class Capability:
    """一项专项能力。字段全是数据，可被 API 序列化、可被页面渲染。"""

    key: str
    """稳定标识（也用于 UI 锚点与日志）。"""

    label: str
    """中文短名，给页面用。"""

    description: str
    """一句话说明这个能力干什么。

    它同时是**分诊依据**：``build_system_prompt`` 会把它列进分诊表，模型据此判断
    用户的请求该走哪个能力族。写好这几句话 = 调好路由。
    """

    domain_prompt: str
    """领域提示词片段，拼进通用智能体的系统提示（不单独成 agent）。"""

    skills: tuple[str, ...] = ()
    """这个能力会用到哪些技能（``src/app/skills/<dir>``）。

    一个能力可以带多个技能（用例生成要 testcase-workflow + large-system-testing +
    三个 lark-*）。模型看得见的技能清单 = **当前智能体各能力声明的技能之并集** ——
    所以技能不再是一个独立的库，而是能力的一部分（"不再单独显示技能库"）。
    """

    tools: tuple[str, ...] = ()
    """工具符号引用：``"模块路径:符号名"``。这是"工具从哪来"的唯一声明处。"""

    extra_tool_modules: tuple[str, ...] = ()
    """整模块导出的工具列表名，如 ``"…memory_tools:MEMORY_TOOLS"``（一个模块给一组）。"""

    cli_allow: tuple[str, ...] = ()
    """声明式 CLI 白名单（预留）。真正的执行器白名单在 runner 侧，
    这里只做"这个能力会用哪些 CLI 子命令"的可见性登记。"""

    mcp_servers: tuple[str, ...] = ()
    """外部 MCP server 名（预留 seam，见模块 docstring）。平台自有工具不走这里。"""

    requires: tuple[str, ...] = ()
    """这个能力依赖哪些外部依赖 —— 写 ``core/integrations.py`` 注册表里的 key。

    机器可读是关键：装配层据此判断"依赖不在线时别把这些工具交给模型"，提示词里的
    依赖段也从注册表取 label / fix_hint 渲染。以前这里是中文散文（"Unity Editor
    在线（某个端口上的桥…）"），只有人能看懂，于是每个页面只能各写各的探针
    （/rag/status、/codebase/status、/eval/status…），四处描述互不知情。
    """

    human_gated: tuple[tuple[str, str], ...] = ()
    """需要人工审批的工具 → 审批卡片上显示的说明（(工具名, 原因) 对）。

    刻意用元组而不是 dict：本类 frozen，持有 dict 会让它不可哈希（没法放进集合、
    也没法当字典键）。``dict(cap.human_gated)`` 在需要映射的地方再转。
    """

    in_chat: bool = True
    """是否属于对话页的通用智能体。``False`` 表示它有自己的专属入口。"""

    home: str = ""
    """专属入口在哪（给页面看）。``in_chat=False`` 的能力靠它进入；
    ``in_chat=True`` 但另有专属页面的（代码分析）也填，页面上两个入口都展示。"""

    requires_repo: bool = False
    """工具是否**必须**有"本次会话挂载的仓库"才可用。

    ``True`` 的能力（代码分析）挂到对话页后，没选仓库时它的工具**不进工具面**——
    那些工具靠 ``configurable.workspace_path`` 解析目标仓库，没挂载时它们调什么都
    会立刻返回降级提示，白白占工具位、还会让模型先试错一轮。与其给 4 个必然报错
    的工具，不如让它们按上下文出现（见 middleware/assembly.py）。
    """

    def tool_specs(self) -> tuple[str, ...]:
        return (*self.tools, *self.extra_tool_modules)


# ===========================================================================
# 能力清单 —— 加能力就加这里
# ===========================================================================

_TESTCASE_DOMAIN = """\
### 用例生成

需求澄清 → 用例 MD 文档 → Lint → 独立复核 → 人工批准/发布。产物入库到
「用例库」，可用飞书导图交付。

- **先读证据再动手**：读需求文件（用户一般只给文件名，去 `requirements/` 找；
  上传的 PDF/Markdown 按消息里的绝对路径读），再读通用工作流 Skill。
  不能把模型常识当成产品规则。
- **先存需求包再生成**：`save_requirement_package` 记录目标/REQ-ID/验收例子/范围/
  风险/未知项/覆盖计划；未解决的高风险项必须标 blocking，不要把猜测写成事实。
- **机器可追踪**：每条用例标题下用 HTML 注释存元数据
  `<!-- CASE: CASE-…; REQ: REQ-…; RISK: RISK-… -->`；标题保持纯业务标题。
- **保存后必须 Lint**：`lint_case_document` 报 blocking error 就先修（自动修复最多 2 轮）。
  Lint 不过只能报草稿，不得声称已通过。
- **独立复核**：`review_case_document` 是评审器给的**问题清单**，不是你自评。
- 批准/发布是不可逆业务动作，会弹审批卡片由用户确认。
"""

_UNITY_DOMAIN = """\
### Unity 客户端自动化

经**标准 MCP** 操作 Unity（对象查询 / 编辑器控制 / 任意 C#）——与具体游戏无关：
"这个游戏怎么登入、按钮叫什么"靠现场探索、沉淀成用例，不写死在工具里。

- 动手前先 `unity_status`：桥不在（available=false）就如实报告，不要反复重试。
- 运行时对象只在 Play Mode 存在：`unity_editor("play")` → `unity_wait_for("<登录窗/主界面>")`。
- **探索顺序（照这个来，别猜对象名）**：
  1. `unity_hierarchy()` 看全貌 —— 路径 / 是否显示 / 组件 / **界面上的文本**一次摊开；
     要钻某个面板就 `unity_hierarchy(root="MainCanvas/NormalUI")`。猜名字（"TalkUI"/"UI"）
     又慢又容易全落空。
  2. 中文界面直接用界面上的字找：`unity_find_by_text("背包")` —— 返回写着这句话的对象
     与**往上最近的可点祖先**（uGUI 按钮的标签挂在子节点上，那个祖先就是要点的东西）。
  3. 读面板内容用 `unity_object_text("BagUIPanel(Clone)")`（整棵子树的文字）；读单个控件
     的组件/字段用 `unity_object`。
  4. 再操作（`unity_click` / `unity_set_text`）→ `unity_wait_for` → 断言。
  `unity_find_objects` 留着按**组件**找（`component="Button"`）或已知名字精确查。
- **该看一眼就看一眼**：读组件只能回答"这个对象在不在、写了什么"，回答不了"界面上到底
  有没有、长什么样"。不确定有没有入口 / 刚打开一个面板 / 点了没反应 / 断言失败时，
  `unity_screenshot()` 拿路径 → `read_file(那个路径)` 看图（模型有视觉能力，这条链路是通的）。
  **图判断"是不是这样"，文本（hierarchy / find_by_text）决定"点哪儿"** —— 别只用一种。
- **操作后必看 `unity_console`**：Unity 侧异常不会让调用失败，只会安静地写进
  Console —— 不读就会把"点了个寂寞"当成通过。
- **复位（回到起点）**：`unity_reset(scene=…, wait_for=…)` = 退 Play → 打开起跑场景 →
  再进 Play → 等标志物回来。探索走到一半想重来时用它（**别自己拼 stop/play**：少了
  "等标志物回来"这一步，后面全在跟半加载的界面较劲）。
- 工具面覆盖不到时用 `unity_exec_csharp` 写两行 C#（拖拽/滑动/调业务方法/造前置
  数据）；服务器换了或升级后包装工具报"参数不对"，用 `unity_mcp_tools` 看真实
  工具与 schema，再 `unity_mcp_call` 直接调 —— 这条路永远不用改平台代码。
- **沉淀用例要写起跑线**：用例里声明模块级常量
  `RESET = {"scene": "<起跑场景路径>", "wait_for": "<起跑线标志物>"}`（普通游戏就是
  "打开哪张地图/哪个界面 + 等哪个对象出现"）。平台每次执行前自动复位到那儿，
  用例之间互不污染。不写也能跑：跑通一次后平台会记住当时现场并自动兜底，但显式写
  下来才算把前置说清楚了（手工前置 —— "先打开某个场景再进 Play" —— 应该变成 RESET，
  而不是写在注释里让人照着做）。
- 沉淀：跑通的脚本 `unity_save_script` 入库；改库里的用例要先 `unity_get_script`
  读回源码，验证后带 `script_id` 覆盖，不要新建第二份（否则同一场景两条用例漂移）。
"""

_WEBUI_DOMAIN = """\
### Web / H5 自动化

Playwright CLI 驱动：先定位（locator）→ 再操作（action）→ 后断言（assert）。
执行器是平台的 playwright-runner sidecar。

- 任何执行前先 `webui_runner_status` 确认 runner 在线；离线就报告，不要反复重试。
- `webui_run_spec` 是核心：传 spec 全文，拿回 status / report.tests[] / artifacts / output。
- 入库：跑通后 `webui_save_script`。**改库里的用例**：`webui_list_scripts` 找 id →
  `webui_get_script` 读回源码 → 改 → 验证 → 带 `script_id` 覆盖（版本号自动 +1），
  不要新建一份，否则同一场景会有两条互相漂移的用例。
- 对话页的执行是临时执行，签不出分享链接；报告里写运行目录相对路径即可。
"""

_CODEBASE_DOMAIN = """\
### 代码分析

对着**本次会话挂载的仓库**（工作区说明里给的那个路径）做代码问答：功能定位、调用链、
影响面。图谱工具与文件工具是两条腿：

- 图谱可用时（该仓库已在「代码图谱」建索引）：`repo_architecture` 看整体，
  `graph_search` 找符号 → `trace_symbol` 追调用链 → `read_symbol` 读定义源码。
  结构化答案比 grep 可靠，涉及"谁调用它 / 改了会影响谁"时优先走图谱。
- **图谱不可用就退回文件工具**：没挂载仓库、或仓库没建索引时，用
  `grep` / `glob` / `read_file` 按绝对路径读。用户临时让你看一个没注册过的仓库，
  直接问他要绝对路径然后 grep/read，不要因为"没索引"就拒绝。
- **只读**：绝不修改被分析仓库的任何文件（改写它需要用户审批，也不该顺手做）。
  要落盘产物写到工作区或产物目录。
- 结论给 `文件路径:行号` 或符号名当证据；检索不到就如实说，不要凭常识编。
"""

_RAG_DOMAIN = """\
### 知识库

平台知识库（LightRAG）里存的是**已经入库的需求文档、历史用例与项目约定**。问
"文档里是怎么规定的""以前有没有类似场景"时先检索，不要凭记忆答。

- **先确认在线**：`rag_health`（可带 `kb`）；不在线就如实报告并让用户在「知识库」页
  启动，不要反复重试同一件事。
- **一个库一个项目**：平台里可以有多个知识库（每个是独立实例，数据互不可见），
  例如"若依后台"和"群侠传"各一个。动手前先 `rag_list_kbs` 看有哪些库，再按项目
  选 `kb`；库名不确定就问用户，别猜——问错库会拿到别的项目的资料或空手而归，
  而这两种看起来都像"知识库里没有"。
- **检索带来源**：`rag_query`（默认 hybrid）。把回答连同 references 里的出处一起转述；
  检索不到就说"知识库里没有"，不要用常识补成事实。
- **入库**：用户说"记进知识库/存起来"时，贴的文本用 `rag_ingest_text`（给个能认出来的
  `file_source`），文件用 `rag_ingest_file`（走绝对路径）。入库是**异步解析**，
  刚返回成功时还检索不到，用 `rag_list_documents` 看解析状态。写哪个库必须问清楚：
  资料进错库等于放进了另一个项目。
- **它和工作区是两回事**：知识库里只有显式入库过的东西。工作区的文件用
  `read_file` / `grep` 直接读，不要指望它已经进了知识库。
- **平台里不做的事**：删除文档、重新解析、图谱可视化与实体/关系编辑都在 LightRAG
  自带界面里做（「知识库」页有直达地址），平台侧只做展示与检索验证。
"""

CAPABILITIES: tuple[Capability, ...] = (    Capability(
        key="testcase",
        label="用例生成",
        description="需求分析、测试用例设计与入库、用例文档的 Lint/复核/批准发布、飞书导图交付。",
        skills=("testcase-workflow", "large-system-testing", "lark-doc", "lark-drive", "lark-shared"),
        domain_prompt=_TESTCASE_DOMAIN,
        tools=(
            "src.app.agents.testcase.tools.case_doc_tools:save_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:read_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:list_case_documents",
            "src.app.agents.testcase.tools.case_doc_tools:save_requirement_package",
            "src.app.agents.testcase.tools.case_doc_tools:lint_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:review_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:get_case_workflow_status",
            "src.app.agents.testcase.tools.case_doc_tools:approve_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:release_case_document",
            "src.app.agents.testcase.tools.case_doc_tools:get_beijing_timestamp",
            "src.app.agents.testcase.tools.feishu_tools:export_project_mindmap",
            "src.app.agents.testcase.tools.feishu_tools:check_feishu_status",
        ),
        extra_tool_modules=("src.app.agents.testcase.tools.memory_tools:MEMORY_TOOLS",),
        # 键名对应 core/integrations.py 的注册表（唯一描述处）：装配层据此在依赖
        # 不在线时把这些工具挡在工具面外，提示词里也会写明缺什么、怎么补。
        requires=("feishu",),
        human_gated=(
            ("approve_case_document", "批准用例文档需要你确认（批准后该版本不可再改）"),
            ("release_case_document", "发布用例文档需要你确认（发布为内部正式版本）"),
        ),
    ),
    Capability(
        key="unity",
        label="Unity 自动化",
        description="经标准 MCP 操作 Unity：对象查询、控件操作、编辑器控制、任意 C#、用例脚本沉淀与回归。",
        skills=("unity-ui-test",),
        domain_prompt=_UNITY_DOMAIN,
        tools=(
            "src.app.agents.unity.tools:unity_status",
            "src.app.agents.unity.tools:unity_find_objects",
            "src.app.agents.unity.tools:unity_hierarchy",
            "src.app.agents.unity.tools:unity_find_by_text",
            "src.app.agents.unity.tools:unity_object_text",
            "src.app.agents.unity.tools:unity_object",
            "src.app.agents.unity.tools:unity_console",
            "src.app.agents.unity.tools:unity_editor",
            "src.app.agents.unity.tools:unity_reset",
            "src.app.agents.unity.tools:unity_click",
            "src.app.agents.unity.tools:unity_set_text",
            "src.app.agents.unity.tools:unity_wait_for",
            "src.app.agents.unity.tools:unity_screenshot",
            "src.app.agents.unity.tools:unity_exec_csharp",
            "src.app.agents.unity.tools:unity_run_tests",
            "src.app.agents.unity.tools:unity_mcp_tools",
            "src.app.agents.unity.tools:unity_mcp_call",
            "src.app.agents.unity.tools:unity_generate_script",
            "src.app.agents.unity.tools:unity_run_script",
            "src.app.agents.unity.tools:unity_save_script",
            "src.app.agents.unity.tools:unity_get_script",
            "src.app.agents.unity.tools:unity_list_scripts",
        ),
        # 这一整套工具走的是外部的 Unity MCP 服务器（见 services/unity_bridge.py）：
        # 声明出来既让 /mcp 页能看到它，也让"依赖不在线就把工具挡在工具面外"生效。
        mcp_servers=("unity",),
        requires=("unity",),
    ),
    Capability(
        key="webui",
        label="Web-UI 自动化",
        description="浏览器 UI 用例：写/跑 Playwright spec、截图核验、失败定位、用例入库与回归。",
        skills=("web-ui-test",),
        domain_prompt=_WEBUI_DOMAIN,
        tools=(
            "src.app.agents.webui.tools:webui_runner_status",
            "src.app.agents.webui.tools:webui_generate_spec",
            "src.app.agents.webui.tools:webui_run_spec",
            "src.app.agents.webui.tools:webui_screenshot",
            "src.app.agents.webui.tools:webui_cli",
            "src.app.agents.webui.tools:webui_save_script",
            "src.app.agents.webui.tools:webui_get_script",
            "src.app.agents.webui.tools:webui_list_scripts",
        ),
        cli_allow=("install", "pdf", "cr"),
        requires=("playwright",),
    ),
    Capability(
        key="codebase",
        label="代码分析",
        description="对着一个仓库做代码问答：功能定位、调用链、影响面（图谱工具 + 文件工具）。",
        skills=(),
        domain_prompt=_CODEBASE_DOMAIN,
        tools=(
            "src.app.agents.codebase.tools:repo_architecture",
            "src.app.agents.codebase.tools:graph_search",
            "src.app.agents.codebase.tools:trace_symbol",
            "src.app.agents.codebase.tools:read_symbol",
        ),
        # 只登记"图谱引擎在不在"：已建索引与否要看本次挂的仓库，那是每轮动态的，
        # 由工具自己的降级提示兜（没索引时它会说"改用 grep/read_file"）。
        requires=("codebase-memory",),
        # 对话页唯一入口：输入框旁的「代码图谱仓库」选择器挂一个「代码图谱」里注册的仓库，
        # 那次会话就用它当工作目录。requires_repo=True 保证没挂仓库时这 4 个图谱工具
        # 不进工具面 —— 它们那时只会返回降级提示，给了只会让模型白试一轮。
        #
        # 没有专属页面入口：/codebase 页原来的「AI 分析」Tab 已删除（2026-09，与对话页
        # 重复）。那条线现在只剩无头的那一半 —— 索引后自动跑的「增量影响分析」
        # （services/codebase_analysis_service.py，走 codebase_agent graph，报告在
        # 定时任务 Tab 里看）。
        in_chat=True,
        requires_repo=True,
    ),
    Capability(
        key="rag",
        label="知识库",
        description="检索已入库的需求文档/历史用例/项目约定，也可把资料存进知识库。",
        skills=(),
        domain_prompt=_RAG_DOMAIN,
        tools=(
            "src.app.agents.rag.tools:rag_list_kbs",
            "src.app.agents.rag.tools:rag_health",
            "src.app.agents.rag.tools:rag_query",
            "src.app.agents.rag.tools:rag_ingest_text",
            "src.app.agents.rag.tools:rag_ingest_file",
            "src.app.agents.rag.tools:rag_list_documents",
        ),
        # 与代码分析同一个道理：这里登记的是"知识库本体在不在"。依赖不在线时该能力的
        # 工具会被藏掉、并在提示词里写明缺什么（middleware/assembly.py::_offline_tools）
        # —— 给了必然失败的工具只会让模型白试一轮、还以为平台坏了。
        # LightRAG 是启动器里 autostart=False 的服务，用户中途启起来后，就绪快照
        # 下次刷新（TTL 20s）工具就会回来，不需要重启。
        requires=("lightrag",),
        # 页面入口是 /rag：那里管入库与检索验证；这里给的是智能体侧的读写面。
        home="/rag",
        in_chat=True,
    ),
)

CAPABILITY_BY_KEY: dict[str, Capability] = {c.key: c for c in CAPABILITIES}

CHAT_CAPABILITIES: tuple[Capability, ...] = tuple(c for c in CAPABILITIES if c.in_chat)


# ===========================================================================
# 工具解析 —— "工具从哪来"的唯一 seam
# ===========================================================================

_tool_cache: dict[str, Any] = {}


def _import_symbol(spec: str) -> Any:
    module_path, _, symbol = spec.partition(":")
    if not symbol:
        raise ValueError(f"工具引用缺少符号名: {spec!r}（应形如 '包.模块:符号'）")
    return getattr(importlib.import_module(module_path), symbol)


def resolve_tools(capabilities: tuple[Capability, ...] = CAPABILITIES) -> list[Any]:
    """把清单里的符号引用解析成 ``BaseTool`` 列表（去重保序）。

    单个符号解析失败**不让整体崩**：记 warning 并跳过，这样清单里引用了还没实现的
    工具时，其它能力照常可用（装配页会把缺失如实显示出来）。
    """
    seen: dict[int, Any] = {}
    for cap in capabilities:
        for spec in cap.tool_specs():
            if spec in _tool_cache:
                resolved = _tool_cache[spec]
            else:
                try:
                    resolved = _import_symbol(spec)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("capability %s: 工具 %s 解析失败: %s", cap.key, spec, exc)
                    continue
                _tool_cache[spec] = resolved
            items = resolved if isinstance(resolved, (list, tuple)) else [resolved]
            for item in items:
                seen[id(item)] = item
    tools = list(seen.values())
    for tool in tools:
        # 任一工具报错都回给模型让它改，而不是炸掉整轮 run
        tool.handle_tool_error = True
    return tools


def resolve_missing(capabilities: tuple[Capability, ...] = CAPABILITIES) -> list[dict]:
    """清单里解析不到的工具（装配页要如实显示，不要假装装配完整）。"""
    missing: list[dict] = []
    for cap in capabilities:
        for spec in cap.tool_specs():
            try:
                _import_symbol(spec)
            except Exception as exc:  # noqa: BLE001
                missing.append({"capability": cap.key, "tool": spec, "error": str(exc)})
    return missing


def build_upload_namespace() -> str:
    """会话上传目录名。历史沿用小写 ``testcase``（前端与后端都写死了这个值，
    改它会让已上传的文件路径失效），与"智能体叫什么都行"解耦。"""
    return "testcase"


# ===========================================================================
# 提示词组装
# ===========================================================================

_TRIAGE_HEADER = """\
# 任务分诊（先做这一步）

判断用户这次要的是哪一类活儿，然后**先读对应技能的 SKILL.md** 再动手
（技能正文按需加载，不要一次读完；读哪个技能看下表）。一件请求里混了多类时，
按需要的顺序逐类处理。

| 任务族 | 什么时候走它 | 先读的技能 |
|---|---|---|
"""

#: 能力段（分诊表 + 领域规则 + 依赖）的边界标记。
#: 装配中间件每轮按当前开关替换整段；它不是给模型看的，是给替换逻辑定位的。
CAPABILITY_SECTION_OPEN = "<!--@capabilities-->"
CAPABILITY_SECTION_CLOSE = "<!--/@capabilities-->"

_RULES = """\
# 跨能力的铁律

- **只读被测对象**：不改被测站点的数据（不发评论、不登录、不下单）、不改被测仓库的
  源码文件。需要落盘产物时写到工作区或产物目录。
- **不为了通过而削弱断言**：数据会变的推荐位改成结构断言，不要删断言。
- **如实报告**：失败就是失败，不得只报喜；检索/证据不足时明说"现有证据不足以确定"。
- **标注证据**：涉及代码或用例的结论都要给 `文件路径:行号` 或符号名。
- **不可逆动作先问**：批准/发布用例、影响同服玩家的 GM 命令等，走审批或直接向用户确认。
- 所有输出使用中文。
"""


def build_capability_prompt(capabilities: tuple[Capability, ...],
                           *, general: bool = True,
                           identity: tuple[str, str] | None = None,
                           readiness: dict[str, bool | None] | None = None) -> str:
    """提示词的**动态段**：智能体身份 + 分诊表 + 各能力领域段 + 依赖。

    这段随"现在跑的是哪个智能体、它装配了什么"变化 —— 换个智能体、或卸掉一条能力
    后，这里就该没有它的分诊行与领域规则（工具没了却还在提示词里教它用，只会让模型
    去调一个不存在的工具）。所以 ``build_system_prompt`` 把它包在边界标记里，由装配
    中间件每轮替换。

    ``identity`` 是这个智能体自己的名字与说明（用户可编辑）：用户建的"接口测试助手"
    不该和默认的"通用测试助手"自我介绍成同一个。

    ``readiness`` 是各依赖的在线状态（``core/integrations`` 的就绪快照）。给了就在
    依赖段里写明"就绪/未就绪 + 怎么补"，模型才知道该如实说"现在做不了"而不是反复
    重试；不给（构建期静态提示词）就只列依赖名字。
    """
    header = ""
    if identity and (identity[0] or identity[1]):
        label, description = identity
        header = (f"# 你是「{label or '未命名智能体'}」\n\n"
                  f"{description.strip()}\n\n" if description.strip()
                  else f"# 你是「{label or '未命名智能体'}」\n\n")
    # 没有技能的也列出来（第三列写 —）：分诊表同时是"当前有哪些能力"的清单，
    # 漏掉一条会让模型以为那个领域没装配（代码分析就没有技能目录）。
    rows = "\n".join(
        f"| {c.label} | {c.description} | "
        f"{'、'.join(f'`{s}`' for s in c.skills) if c.skills else '—'} |"
        for c in capabilities
    )
    triage = (_TRIAGE_HEADER + rows + "\n") if (general and rows) else ""
    if not triage and not rows and general:
        triage = ("# 当前没有启用任何专项能力\n\n"
                  "用户可以在「智能体装配」页（/agents）装配能力、工具与技能。"
                  "在他装配之前，只能用通用工具（文件 / shell / 检索）帮忙。\n")
    domains = "\n".join(c.domain_prompt.strip() for c in capabilities if c.domain_prompt)
    deps = [_dependency_line(c, readiness) for c in capabilities if c.requires]
    deps_block = ("\n# 能力依赖（不在线时如实报告，不要反复重试）\n\n"
                  + "\n".join(deps) + "\n") if deps else ""
    return header + triage + domains + "\n" + deps_block


def _dependency_line(capability: Capability,
                     readiness: dict[str, bool | None] | None) -> str:
    """一行依赖说明；有就绪快照时带上状态与补救办法（文案来自注册表，不再各写各的）。"""
    from src.app.core import integrations

    parts: list[str] = []
    for key in capability.requires:
        item = integrations.BY_KEY.get(key)
        label = item.label if item else key
        state = (readiness or {}).get(key)
        if state is True:
            parts.append(f"{label}（就绪）")
        elif state is False:
            parts.append(f"{label}（**未就绪** —— {item.fix_hint if item else '需先安装/启动'}）")
        else:
            parts.append(label)
    return f"- {capability.label}：{'；'.join(parts)}"


def build_system_prompt(capabilities: tuple[Capability, ...] = CHAT_CAPABILITIES,
                        *, target_url: str | None = None,
                        repair_budget: int | None = None,
                        general: bool | None = None) -> str:
    """把清单拼成一个智能体的系统提示。

    结构：角色 → [能力段] → 环境 → 铁律。加一条 Capability 就多一段，不需要改这个函数。

    能力段被 ``CAPABILITY_SECTION_OPEN/CLOSE`` 包起来：通用智能体的装配中间件靠这对
    标记在**每轮模型调用前**把整段换成"当前启用中的能力"那版（用户能在 /agents 页
    装卸能力，见 ``middleware/assembly.py``）。中间件不在时留着的就是构建期那版，
    行为与过去一致 —— 标记本身是 HTML 注释，对模型无副作用。

    ``general`` 决定角色措辞与是否给分诊表：默认按能力数推断，通用智能体显式传 True
    （它卸载到只剩一条能力时仍然是通用智能体，不该变成"本会话只负责 X"）。
    """
    if general is None:
        general = len(capabilities) > 1
    section = build_capability_prompt(capabilities, general=general)

    budget = repair_budget if repair_budget is not None else settings.web_ui_max_repair
    env_block = f"""

# 环境

- 默认被测站点（Web/H5）：`{target_url or settings.web_ui_default_target_url}`
- 默认设备：`{settings.web_ui_default_device}`（要看桌面版就在工具里传 `desktop=true`）
- 各能力的自修复/重跑预算：最多 {budget + 1} 次执行（初次 + {budget} 轮修正），
  与平台的自动修复预算一致；仍然失败就如实报告，不要无限重试同一份 spec。
- 工作目录就是 shell 的 cwd；文件工具用绝对路径或相对路径都行。
- 需要隔离上下文的重活儿（翻大量文件、多步调研）派 `general-purpose` 子智能体去做，
  它只回结论，中间过程不占你的上下文。
"""

    if general:
        role = (
            "你是一位资深游戏测试专家（测试架构师），面向游戏项目（Unity + Lua 客户端、"
            "C# 服务端）与 Web/H5 站点开展测试工作。\n\n"
            "你是一个**通用智能体**：专项能力全部挂在你的工具面上，由你判断该用哪一类，"
            "不需要用户先声明模式。用户可以自己装卸能力和工具（平台「智能体装配」页），"
            "所以**当前有哪些能力、哪些工具，以下面的能力清单为准** —— 清单里没有的领域"
            "就是没装配，如实说明而不是去找工具试。\n\n"
        )
    else:
        only = capabilities[0] if capabilities else None
        role = (
            f"你是资深游戏测试专家，本会话只负责 **{only.label}**：{only.description}\n\n"
            "动手前先读对应技能的 SKILL.md（正文按需加载，不要一次读完），"
            "严格遵循其中的方法论，它优先于你的通用判断。\n\n"
        ) if only else ""

    return (role
            + CAPABILITY_SECTION_OPEN + "\n" + section + CAPABILITY_SECTION_CLOSE + "\n"
            + env_block + "\n" + _RULES)


def build_interrupt_on(capabilities: tuple[Capability, ...] = CHAT_CAPABILITIES):
    """合并人工审批项，与权限门（execute/写文件）的规则一起交给 ``interrupt_on``。

    "哪些工具要审批"现在是**用户数据**（能力编辑器里勾），所以给候选池里每个工具都
    登记一条 ``when`` 谓词条目，每轮现查装配目录 —— 勾一下下一轮就生效。清单里的
    ``human_gated`` 退化为种子值（播种到装配目录里），这里不再单独加静态条目，
    避免同一工具出现两份规则。
    """
    from src.app.middleware.permission_gate import (
        build_interrupt_on as _base,
        dynamic_gate_entries,
    )
    from src.app.services.assembly_service import catalog_tool_names

    return {**_base(None), **dynamic_gate_entries(catalog_tool_names())}


# ===========================================================================
# 装配清单（API / 页面用）
# ===========================================================================

def inventory(capabilities: tuple[Capability, ...] = CAPABILITIES) -> dict:
    """把清单变成可序列化的装配描述 —— 这就是"我装配了什么"的答案。"""
    missing = {(m["capability"], m["tool"]) for m in resolve_missing(capabilities)}
    items: list[dict] = []
    for cap in capabilities:
        tools = []
        for spec in cap.tool_specs():
            module_path, _, symbol = spec.partition(":")
            try:
                resolved = _import_symbol(spec)
                names = ([t.name for t in resolved]
                         if isinstance(resolved, (list, tuple)) else [resolved.name])
            except Exception:  # noqa: BLE001
                names = [symbol]
            tools.append({
                "symbol": spec,
                "module": module_path,
                "export": symbol,
                "names": names,
                "missing": (cap.key, spec) in missing,
            })
        items.append({
            "key": cap.key,
            "label": cap.label,
            "description": cap.description,
            "skills": list(cap.skills),
            "in_chat": cap.in_chat,
            "home": cap.home,
            "requires_repo": cap.requires_repo,
            "tool_count": sum(len(t["names"]) for t in tools),
            "tools": tools,
            "cli_allow": list(cap.cli_allow),
            "mcp_servers": list(cap.mcp_servers),
            "requires": list(cap.requires),
            "human_gated": dict(cap.human_gated),
        })
    return {
        "capabilities": items,
        "chat_capability_keys": [c.key for c in CHAT_CAPABILITIES],
        "missing_tools": sorted(f"{c}:{t}" for c, t in missing),
    }
