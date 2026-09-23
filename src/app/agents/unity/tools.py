"""Unity 自动化工具（Unity 自动化模块）。

工具面 = 三类**通用**原语 + 用例沉淀，全部经 ``services/unity_bridge.py`` 走标准
MCP 到一个 Unity MCP 服务器（CoplayDev/unity-mcp 等）。没有一条依赖某个游戏的
Lua 框架或 GM 命令 —— 换游戏只需要重新探索、重新沉淀用例，工具不用改。

- 探索：`unity_status` / `unity_find_objects` / `unity_object` / `unity_console*`
- 执行：`unity_editor` / `unity_start_line`（起跑线检查，只读）/ `unity_click` / `unity_set_text` /
  `unity_wait_for` / `unity_screenshot` / `unity_exec_csharp`（任意 C#，通用逃逸口）/
  `unity_run_tests`
- 认路：`unity_mcp_tools`（服务器实际提供什么）/ `unity_mcp_call`（原样调用）
- 沉淀：`unity_generate_script` → `unity_run_script` → `unity_save_script` →
  `unity_list_scripts` / `unity_get_script`

读法：先 `unity_status` 看桥与 Play Mode；探索时优先 `unity_find_objects` +
`unity_object`（对象与组件），拿不准就 `unity_console` 看报错；控件点不动时用
`unity_exec_csharp` 自己写两行 C#（`cs_click` 的兜底策略就是它）。
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.app.services import unity_service


# ---------------------------------------------------------------------------
# 探索
# ---------------------------------------------------------------------------

@tool
async def unity_status() -> dict:
    """检查 Unity 自动化桥（MCP 服务器 + Unity 编辑器）状态。

    返回 available / server / flavor / tool_count / editor / is_playing /
    external_changes_dirty / editor_stale / can_run_gated_tools / advice。
    做任何操作前先调它：`available=False` 就是桥没起（去启动器启动 unity-mcp），
    `editor` 里没有 isPlaying 说明 Unity 编辑器还没连上，`is_playing=False`
    时场景里的**运行时对象还不存在** —— **直接告诉用户「请先在 Unity 里点 Play」**
    并等确认；平台不代管进退 Play（会触发域重载）。

    **`external_changes_dirty=True` 时不要再发那批"会被桥重编译"的工具**：工程里有
    Unity 还没导入的外部改动，此时 `unity_find_objects` / `unity_object` / 起跑线
    检查等一批工具会让**桥自己**「刷新并请求重编译」= 一次域重载 —— Play 中做这件事
    会把编辑器卡死在 Reloading Domain（2026-09-23 实测整机断电）。这个标记是**latch**：
    **在 Unity 里 Ctrl+R / Assets ▸ Refresh all 清不掉它**。要清理就调
    `unity_sync_assets`（只刷新、不重编译；Play 中会拒绝，先让用户退出 Play），
    或重启 unity-mcp 服务。

    `advice` 是照着做就行的下一步；`editor_stale=True`（有实例但读不到状态）说明
    编辑器正在重载 / 刚掉线 —— 等它回来，别继续发命令。
    """
    return await unity_service.status()


@tool
async def unity_sync_assets() -> dict:
    """清掉"工程里有未导入的外部改动"这个标记（**只刷新，不请求重编译**）。

    什么时候用：`unity_status` 报 `external_changes_dirty=True`（那批工具被拦、
    或者用户刚拉过代码 / 改过资源）。这个标记是桥进程内存里的 latch，
    **Ctrl+R / Assets ▸ Refresh all 清不掉**，只有桥自己的刷新会清它。

    前提：**不能在 Play 中做**（刷新会打断这一局）—— 在 Play 里调用会被拒，
    请先让用户在 Unity 里退出 Play。清完再继续原来的活（进 Play 要用户手动点）。
    """
    return await unity_service.sync_assets()


@tool
async def unity_emergency_stop() -> dict:
    """急停：取消所有正在跑的 Unity 用例 + 卸掉编辑器上的录制钩子。

    什么时候用：用户说"停下"、"我中断了但 Unity 还在动"，或者怀疑有残留的
    录制/截图钩子还在驱动编辑器。**不会**动 Play Mode（那是用户的）。
    返回 cancelled_runs（被取消的运行目录）与 disarmed（两个钩子的收尾结果）。
    """
    return await unity_service.stop_all_runs()


@tool
async def unity_find_objects(name: str = "", path: str = "", component: str = "",
                             tag: str = "", limit: int = 50) -> dict:
    """在场景里查对象（通用对象模型的第一步，替代"猜层级"）。

    三种查法，按需组合：
    - `name`：**精确匹配**（实测：name="SystemButton" 命中 1 个，name="System" 命中 0 个）——
      名字差一个字、多一个尾空格都查不到。查不中时平台会自动按 `path` 再搜一次；
    - `path`：层级路径，写半截也行（服务器按后缀匹配，如 "BagWindow/Title"）；
    - `component`：有某个组件的对象，如 component="Button"（找全部按钮）。

    含**未激活**对象（很多窗口是 setActive(false) 藏起来的），所以"这个界面存不存在"
    也问它。**返回 0 条不等于出错**（卡片成功、object_count=0）：那是关键词不对，
    换关键词或改走 path/component；中文游戏的对象名多是英文/拼音，直接按界面上的
    中文找的话用 `unity_click("<可见文本>")`（查找链：名字 → 全路径 → 后缀 → 可见文本）。
    """
    return await unity_service.find_objects(name=name, path=path, component=component,
                                            tag=tag, limit=limit)


@tool
async def unity_hierarchy(root: str = "", depth: int = 3, max_nodes: int = 80) -> dict:
    """看场景（或某棵子树）的层级：路径 / 是否显示 / 组件 / 界面上的文本。

    **探索界面的第一步就用它**，别一个个猜对象名 —— 实测猜名字（TalkUI / UI / UIRoot …）
    每次一轮往返还可能全部落空，而这一条调用就把结构摊开了。

    - 不给 `root`：整个场景（广度优先，超出 `max_nodes` 时先保住上层，再往下钻）；
    - 给 `root`（名字或路径，如 "MainCanvas"）：只看那棵子树，面板结构一目了然；
    - 看到中文界面上的字，直接配合 `unity_find_by_text` 定位，不用管对象名叫什么。
    """
    return await unity_service.hierarchy(root, depth, max_nodes)


@tool
async def unity_find_by_text(text: str, root: str = "", limit: int = 20) -> dict:
    """按**界面上显示的文字**找对象 —— 中文游戏的入口（对象名是拼音/英文，文字才是线索）。

    返回每处命中：写着这句话的对象路径、它现在是否可见、以及**往上最近的可点祖先**
    （返回的"可点祖先"直接拿去 `unity_click`；空 = 那个位置没有点击处理器）。
    搜不到多半是那个界面当前没打开（面板是停用的，文本不在场景里生效的那份上）。
    """
    return await unity_service.find_by_text(text, root, limit)


@tool
async def unity_object_text(target: str) -> dict:
    """读对象**及其全部子孙**的文本：问"这个面板/列表现在显示什么"用它。

    比 `unity_object` 更适合面板/列表：容器自己身上常挂着无关的 text/value
    （实测某面板自己回的是 "1023799" 这种 id），这个工具收的是整棵子树的文字。
    """
    return await unity_service.object_text(target)


@tool
async def unity_object(target: str, component: str = "") -> dict:
    """读一个对象的详情：层级路径、是否激活、组件清单、组件的 text/value/interactable 等字段。

    `target` 传对象名或层级路径（先 `unity_find_objects` / `unity_find_by_text` 确认唯一）。
    读文本断言、找按钮是否可点、确认某个组件在不在，都用它。服务器没有检查工具时会自动
    退回通用 C# 反射，所以对任何 Unity 版本都可用。要看整棵子树的文字用 `unity_object_text`。
    """
    return await unity_service.object_info(target, component)


@tool
async def unity_console(action: str = "get", filter_text: str = "",
                        limit: int = 50, types: str = "all") -> dict:
    """读/清 Unity Console（探索时最值钱的一条：报错优先于猜测）。

    - action="get"（默认）读日志，action="clear" 清空；
    - `filter_text` 传给服务器做过滤（如 "error" / "Exception"）；
    - `types` 默认 "all"（error,warning,log）—— 服务器默认只给 error/warning，
      不显式要的话 Debug.Log 一条都看不到；
    - 点击或操作后**先看这里**：Unity 侧异常不会让 HTTP 调用失败，只会安静地
      写进 Console —— 不读就会把"点了个寂寞"当成通过。
    """
    return await unity_service.console(action, filter_text, limit, types)


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

#: 会触发 Unity 域重载（或强制重编译）的编辑器动作 —— 平台禁止 agent 调用。
#: 硬规则（2026-09-21）：**永远不触发域重载**。重载期间桥是断的（平台只能盲等
#: 超时），大工程上实测卡死过（Reloading Domain busy 9 分钟+，最后重启编辑器）。
#: 这些动作留给用户手动做——agent 遇到"不在 Play 模式"要如实告诉用户，而不是自己进。
_EDITOR_ACTIONS_BLOCKED = {
    "play": "进入 Play Mode 会触发 Unity 域重载（可能卡住编辑器），平台已禁用该操作。"
            "请**手动在 Unity 里点 Play**，之后所有操作都建立在此之上（游戏没在跑时"
            "先让用户 Play，不要自己尝试）。",
    "stop": "退出 Play Mode 会触发 Unity 域重载，平台已禁用——需要停下游戏时请让用户手动操作。",
    "refresh": "刷新资产会触发脚本重编译与域重载，平台已禁用——改完 Assets 后请让用户手动刷新。",
    # 这两个动作走插件的包部署路径：内部就是 AssetDatabase.Refresh(ForceUpdate)
    # + 重编译，和 refresh 同一条命（2026-09-22 补）。
    "deploy_package": "部署包会刷新资产并触发重编译/域重载，平台已禁用。",
    "restore_package": "还原包会刷新资产并触发重编译/域重载，平台已禁用。",
}

#: 会触发域重载的**工具名**（按名字拦，绕开方言差异）。2026-09-22 补：
#: 之前只拦了 ``manage_editor`` 的动作和 C# 片段，于是 ``unity_mcp_call`` 直接点名
#: ``refresh_unity`` 就能溜过去 —— 那是插件"刷新 + 请求重编译"的工具，
#: 参数 ``compile="request"`` 就是一次实打实的域重载（插件在连接断开时还会打印
#: "Connection lost during compile (expected - domain reload triggered)"）。
_TOOLS_BLOCKED = {
    "refresh_unity": "插件的刷新工具（可带 compile=request → 重编译 → 域重载），平台已禁用。",
    "assets-refresh": "同 refresh_unity（ivan 方言）。",
    "manage_script": "写/改 C# 脚本会触发重编译与域重载，平台已禁用；测试脚本请用 unity_run_script。",
}

#: 逃逸口护栏：命中这些片段的 C# / MCP 调用会触达"进/退 Play、重编译、刷新资产"，
#: 平台一律拒绝（硬规则：永远不触发域重载）。不是防恶意——是防"助手自作聪明"：
#: 专用工具已经拦了 play/stop/refresh，但逃逸口（exec_csharp / mcp_call）还能绕过，
#: 这里把直白的写法也堵上。
_RELOAD_FORBIDDEN_FRAGMENTS = (
    "isplaying =",                  # EditorApplication.isPlaying = true/false
    "enterplaymode",
    "exitplaymode",
    "executeMenuItem",              # 菜单里可能有 Play/Refresh
    "requestscriptcompilation",
    "compilescripts(",
    "assetdatabase.refresh(",
    "EditorApplication.ExitPlaymode",
)

#: 参数级片段：JSON 里带不带空格两种写法都要认（比对前先把空白压掉）。
#: ``refresh_unity`` 的 ``compile=request`` 与 ``manage_script`` 的立即刷新，
#: 效果都是"请求重编译"，属于同一条红线。
_RELOAD_FORBIDDEN_COMPACT = (
    '"compile":"request"',
    '"refresh":"immediate"',
    '"refresh":"sync"',
)


def _reload_trigger_hit(text: str) -> str | None:
    """命中返回命中的片段（用于报错说明），否则 None。"""
    low = (text or "").lower()
    for frag in _RELOAD_FORBIDDEN_FRAGMENTS:
        if frag.lower() in low:
            return frag
    compact = "".join(low.split())
    for frag in _RELOAD_FORBIDDEN_COMPACT:
        if frag in compact:
            return frag
    # MCP 的 manage_editor 只允许只读/无害动作
    return None


@tool
async def unity_editor(action: str) -> dict:
    """看 Unity 编辑器状态：**只支持 state**（isPlaying / isPaused）。

    play / stop / refresh **已禁用**（会触发域重载——平台的硬规则是"永远不触发
    reload"：重载期间平台联系不上编辑器只能盲等超时，大工程上实测卡死过）。需要
    游戏跑起来时：先看 state，若 isPlaying=false，**直接告诉用户"请先在 Unity 里
    点 Play"** 并等确认；不要自己想办法进 Play。

    想看"现在是不是用例的起跑线"用 `unity_start_line`（只读检查）；**平台不复位**：
    不在起跑线时把 `instruction` 告诉用户，由用户复位后再继续。
    """
    blocked = _EDITOR_ACTIONS_BLOCKED.get((action or "").strip().lower())
    if blocked:
        return {"success": False, "error": blocked}
    return await unity_service.editor_action(action)


@tool
async def unity_start_line(scene: str = "", wait_for: str = "") -> dict:
    """按需查一下**当前在不在用例要求的起跑线**（**只读**，平台不强制、不拦）。

    平台不做复位（2026-09-22 起），也**不检查**起跑线 —— 起跑线只在运行输出里提示
    一行，在不在由用户自己把握。这个工具是给"想看一眼"用的：探索到一半不确定、
    或某条用例挂了怀疑是起点不对时查一次。

    用法：给 `scene`（起跑场景路径或名字）与/或 `wait_for`（起跑线标志物，判"到了"
    就靠它）。返回 `at_start_line=false` 时把 `instruction` 告诉用户（该回到哪个场景/
    界面、等哪个对象出现），由用户决定怎么处理 —— **不要**自己动手改游戏状态，也
    不要为了"必须到位"反复轮询它。

    不在 Play Mode 时会如实返回（运行时对象还不存在）：提示用户"先在 Unity 里点 Play"。
    """
    return await unity_service.start_line(scene=scene, wait_for=wait_for)


@tool
async def unity_click(target: str) -> dict:
    """点一个 UGUI 控件（Button 优先 onClick，其次 ExecuteEvents 指针点击）。

    `target` 传控件名或层级路径，例如 "LoginWindow/StartButton"。
    失败会明确区分"对象不存在"与"没有点击处理器"（后者说明它不是按钮，
    该点它的父节点或换 `unity_exec_csharp` 调它的方法）。
    """
    return await unity_service.click(target)


@tool
async def unity_set_text(target: str, text: str) -> dict:
    """给带文本的控件写值（反射找可写的 text 属性，TMPro / 旧版 UI / 输入框都行）。

    输入框类控件写完通常还要触发提交（回车或点确定按钮），本工具只负责写值。
    """
    return await unity_service.set_text(target, text)


@tool
async def unity_wait_for(target: str, timeout_s: float = 10.0,
                         state: str = "present") -> dict:
    """等对象出现（state="present"）或消失（state="absent"），超时返回 success=False。

    比 `time.sleep` 稳：轮询真实场景状态，UI 动画/加载慢也不会假失败。
    """
    return await unity_service.wait_for(target, timeout_s, state)


@tool
async def unity_screenshot(save_path: str | None = None) -> dict:
    """截一张 Game View 截图（含 Screen Space Overlay 的 UI），返回**图片路径**。

    **想"看一眼"就紧接着 `read_file` 这个路径** —— 图片会以图像形式给你，你就能真的
    看到界面。什么时候该看：
    - 不确定界面上**有没有**某个按钮/入口、或者布局对不对（读组件只能回答"这个对象在
      不在"，回答不了"玩家看不看得见、摆得对不对"）；
    - 打开一个面板之后，确认它真的打开了（而不是被别的层挡住、或者渲染成空白）；
    - 断言失败/操作没反应时——先截图看现场，比继续猜便宜得多。

    **判据**：同一条线索上你已经连续调了 8 个左右 Unity 工具（`unity_hierarchy` /
    `unity_find_by_text` / `unity_object_info` / `unity_exec_csharp` …）还没结论，
    就**别继续找** —— 先截一张图。纯探索没有结论时，一图胜过一次猜测，这是硬规则。

    **Play 才能截到画面**：截图截的是"渲染出来的最后一帧"，所以
    - 在 Play Mode：随时可截，一直可用（含 UI）；
    - 不在 Play：Game View 没有帧，编辑器侧只会报"不在 Play / 场景里没有相机" ——
      这时改用 `unity_hierarchy` / `unity_find_by_text` / `unity_object_text` 读结构，
      或者请用户点 Play。不要反复重试截图。

    精确定位（点哪个对象、读哪段文字）仍然用 `unity_hierarchy` / `unity_find_by_text` /
    `unity_object_text`：文字是给"点哪儿"用的，图是给"到底是不是这样"用的。

    **你的模型读不了图时**（返回值说图片被省略 / 只给了占位符）：把 `path` 原样贴给
    用户让他看，然后根据他的回答决定下一步 —— 千万别假装自己看过图。
    """
    out = await unity_service.screenshot(save_path)
    if out.get("success") and out.get("path"):
        # 提示写在返回值里而不只是 docstring：模型未必回头读文档，但一定读结果
        out["hint"] = "要看这张图就紧接着 read_file 这个 path（图片会以图像形式给你）"
    return out


@tool
async def unity_exec_csharp(code: str) -> dict:
    """在 Unity 编辑器里执行**任意 C# 语句**（通用逃逸口，取代旧的"执行任意 Lua"）。

    传给它的 `code` 是语句序列（不是完整类），可以直接用 `UnityEngine.*` 全名；
    返回值里 `result` 是平台约定的 JSON 片段（用 `UnityEngine.Debug.Log("UNITY_BRIDGE:" + json)` 回传）。

    什么时候用它：工具面覆盖不到的操作（拖拽、滑动、打开某个面板、调某个游戏的
    业务方法、造前置数据）。写法示例见技能 `unity-ui-test` 的「C# 逃逸口」一节。

    平台硬规则：**永不触发域重载**——进/退 Play、重编译脚本、刷新资产都会被拒绝，
    这些动作由用户在 Unity 里手动做。
    """
    hit = _reload_trigger_hit(code)
    if hit:
        return {"success": False, "error": (
            f"拒绝执行：代码里有触发域重载的操作（命中 {hit!r}）。平台永不触发 reload"
            "（重载期间桥是断的，可能卡死编辑器）；进/退 Play、刷新资产请让用户手动做。")}
    return await unity_service.exec_csharp(code)


@tool
async def unity_run_tests(mode: str = "PlayMode", filter_text: str = "",
                          timeout_s: float = 300.0) -> dict:
    """跑工程里已有的 Unity Test Framework 测试（PlayMode / EditMode），轮询到结束。

    平台上沉淀的用例是 Python 脚本（走 `unity_run_script`）；这个工具用于工程里
    本来就有的 C# 测试（回归时最省事）。`filter_text` 按测试名过滤。
    """
    return await unity_service.run_tests(mode, filter_text, timeout_s)


# ---------------------------------------------------------------------------
# 认路（换服务器/换版本时的逃生口）
# ---------------------------------------------------------------------------

@tool
async def unity_mcp_tools(refresh: bool = False) -> dict:
    """列出 Unity MCP 服务器提供的**全部工具**（含入参 schema）。

    用途：某个操作平台的包装工具报错说"没有对应的工具/参数不对"时，用它可以看清
    这台服务器实际有什么、参数叫什么，然后用 `unity_mcp_call` 直接调。
    换一台 MCP 服务器（或它升级改了工具名）时，这里是第一现场。
    """
    return await unity_service.mcp_tools(refresh)


@tool
async def unity_mcp_call(tool: str, arguments: str = "{}") -> dict:
    """原样调用 Unity MCP 服务器上的任意工具（不经过平台方言适配的逃生口）。

    - `tool`：工具名，如 "manage_gameobject" / "gameobject-create"；
    - `arguments`：JSON 字符串，参数名以 `unity_mcp_tools` 返回的 schema 为准。

    例：`unity_mcp_call("manage_scene", '{"action": "get_loaded_scenes"}')`

    参数名不叫 `args` 是刻意的：langchain 生成工具 schema 时会把名为 `args`
    的参数转成 pydantic 内部保留名 `v__args`（可变参数容器），生成出来的
    schema 与函数签名对不上，任何调用都抛 TypeError。
    """
    import json as _json

    if isinstance(arguments, str):
        try:
            parsed = _json.loads(arguments) if arguments.strip() else {}
        except _json.JSONDecodeError as exc:
            return {"success": False, "error": f"arguments 不是合法 JSON: {exc}"}
    else:
        parsed = arguments

    blocked_tool = _TOOLS_BLOCKED.get((tool or "").strip().lower())
    if blocked_tool:
        return {"success": False, "error": (
            f"拒绝执行：{tool} 会触发域重载（平台永不触发 reload）。{blocked_tool}")}

    if isinstance(parsed, dict):
        action = str(parsed.get("action") or parsed.get("state") or "").strip().lower()
        if (tool or "").strip().lower() in ("manage_editor", "editor_action") and action in (
                "play", "stop", "refresh", "deploy_package", "restore_package"):
            return {"success": False, "error": (
                f"拒绝执行：manage_editor/{action} 会触发域重载（平台永不触发 reload）。"
                "请让用户在 Unity 里手动操作（进/退 Play、刷新资产）。")}
        hit = _reload_trigger_hit(_json.dumps(parsed, ensure_ascii=False))
        if hit:
            return {"success": False, "error": (
                f"拒绝执行：参数里有触发域重载的操作（命中 {hit!r}）。平台永不触发 reload。")}
    return await unity_service.mcp_call(tool, parsed)


# ---------------------------------------------------------------------------
# 用例沉淀
# ---------------------------------------------------------------------------

@tool
async def unity_generate_script(intent: str, extra_requirements: str = "") -> dict:
    """把测试意图写成第一版用例脚本（草稿，**必须实跑验证**后再入库）。

    生成的是 python 脚本，驱动 prelude 注入的 `u` 客户端（见技能 unity-ui-test）。
    拿回 content 后：`unity_run_script(content=...)` 实跑 → 失败就改 → 通过了再
    `unity_save_script` 入库。
    """
    return await unity_service.generate_script(intent=intent,
                                               extra_requirements=extra_requirements)


@tool
async def unity_run_script(script_id: str = "", content: str = "",
                           name: str = "") -> dict:
    """跑一份 Unity 用例脚本（同步，返回 exit_code / status / output / screenshots）。

    - 传 `script_id`：跑库里那条（页面「执行」按钮是后台跑并记历史，这里是同步拿结果）；
    - 传 `content`：跑一段即时代码（探索/验证新写法时用，不入库）。

    退出码语义：0 = passed；1 = 断言失败（用例问题）；其余 = error（桥/环境问题，
    看 output 里的 `ERROR:` 行）。**失败先看 `unity_console` 的报错**，别急着改脚本。

    平台不做复位、也**不检查**起跑线：output 开头只有一行"这条用例要求从哪儿开始"的
    提示，在不在由用户自己把握。跑挂了先看是不是起点不对（可用 `unity_start_line`
    按需查），别自己去动游戏状态。

    **没走通时看返回值里的 `failure`**（结构化摘要：挂在哪一步、证据文件在哪、
    `kind` 是哪一类），按它决定下一步 —— 走不通不等于"这条用例没法跑"：
      * `kind="case"`（用例自己的问题）：**改用例再跑**，别放弃。读 `failure.artifacts`
        里的 `failure.txt` / `failure.png` / `steps.jsonl` 定位（对象改名了？等待不够？
        流程本来就变了？），改完 `unity_run_script` 重跑；跑通后 `unity_save_script`
        覆盖同一条（传 `script_id`）。修 3 轮仍不过就把证据和结论报给用户。
      * `kind="environment"`（桥/编辑器/工程的问题）：**不要动用例** —— 这类失败改用例
        是白改。看 `failure.errors`，该请用户点 Play / 刷工程 / 起服务就直说。
      * `kind="timeout"`：`failure.step` 是最后在等的那一步；是等待上限太短（改用例）
        还是环境卡住（查环境），按现场判断。
    """
    from src.app.db.database import async_session_factory

    if not content:
        if not script_id:
            return {"success": False, "error": "script_id 与 content 至少给一个"}
        async with async_session_factory() as db:
            row = await unity_service.get_script(db, script_id)
            if row is None:
                return {"success": False, "error": f"脚本不存在: {script_id}"}
            content, name = row.content, row.name
        script_id = script_id or "adhoc"
    result = await unity_service.run_unity_script(script_id or "adhoc", name or "adhoc", content)
    result["success"] = result["status"] == "passed"
    return result


@tool
async def unity_save_script(name: str, content: str, module: str = "",
                            description: str = "", script_id: str = "") -> dict:
    """把一份跑通过的用例入库，出现在「Unity 自动化」页并可一键执行。

    **改库里的用例**：传 `script_id` 就是更新那条（内容变了自动 version+1），
    不要新建一份，否则同一场景会有两条互相漂移的用例。流程：
    `unity_list_scripts` 找 id → `unity_get_script` 读回源码 → 改 →
    `unity_run_script` 验证 → 带 `script_id` 调本工具覆盖。

    本工具的契约是"**已验证才入库**"：平台按"这份内容有没有跑通过"定状态 ——
    跑通过（`unity_run_script` 里 exit 0 过）→ `status=active`；没跑通过 → 落 `draft`
    并在返回值里 `verified=false` 说清楚。所以正常顺序是：
    **改用例 → 跑通 → 保存**，不要保存没验证过的内容冒充可用用例。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        try:
            row = await unity_service.save_script(
                db, script_id=script_id or None, name=name, content=content,
                module=module or None, description=description or None, status="active")
        except LookupError as exc:
            return {"success": False, "error": str(exc)}
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
    verified = unity_service.passed_before(row.content or content)
    out = {"success": True, "script_id": str(row.id), "name": row.name,
           "updated": bool(script_id), "version": row.version,
           "status": row.status, "verified": verified}
    if not verified:
        out["hint"] = ("这份内容还没跑通过，已存为 draft（不是 active）。先用 "
                       "unity_run_script 跑通再保存覆盖一次；跑不通就照失败摘要改用例。")
    return out


@tool
async def unity_get_script(script_id: str) -> dict:
    """读取已入库用例的**完整源码**（改库里的用例之前必须先读它）。"""
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        row = await unity_service.get_script(db, script_id)
        if row is None:
            return {"success": False, "error": f"脚本不存在: {script_id}"}
        return {"success": True, "id": str(row.id), "name": row.name,
                "module": row.module, "description": row.description,
                "status": row.status, "version": row.version, "content": row.content}


@tool
async def unity_list_scripts() -> dict:
    """列出已入库的 Unity 用例（id / 名称 / 模块 / 状态 / 版本，只有元数据）。"""
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        rows = await unity_service.list_scripts(db)
        return {"success": True, "scripts": [
            {"id": str(r.id), "name": r.name, "module": r.module,
             "status": r.status, "version": r.version}
            for r in rows
        ]}


# ---------------------------------------------------------------------------
# 手动录制（玩家自己点，平台录成用例）
# ---------------------------------------------------------------------------

@tool
async def unity_record_start(name: str = "") -> dict:
    """开始**手动录制**：用户在 Unity 里自己点游戏，平台把操作录下来。

    什么时候用：用户说"我自己点一遍，你把它变成用例"、"录一段操作"时。
    顺序要求（必须说给用户）：**先在 Unity 里点 Play**，再调本工具 ——
    进 Play 会触发域重载，先录后 Play 的话前面那段会丢（平台会自动重挂钩子）。

    录制的是语义目标（对象路径 / 输入框最终文本），不是坐标；停止后用
    `unity_record_to_script` 生成 draft 用例，跑通验证后才算可用。
    """
    out = await unity_service.record_ui_start(name)
    if not out.get("success"):
        return {"success": False, "error": out.get("error"),
                "hint": out.get("hint") or "先让用户把 Unity 进 Play，再试"}
    return {"success": True, "recording_id": out["id"],
            "hint": "已开始录制：请用户在 Unity 里正常操作，完成后调 unity_record_stop"}


@tool
async def unity_record_status() -> dict:
    """看录制状态（是否在录 / 已录多少条）。顺带心跳自愈：域重载后自动重挂。"""
    out = await unity_service.record_ui_status()
    return {"success": True, **out}


@tool
async def unity_record_stop() -> dict:
    """停止录制并把操作事件取回平台（落盘到录制目录）。"""
    out = await unity_service.record_ui_stop()
    if not out.get("success"):
        return {"success": False, "error": out.get("error")}
    return {"success": True, "recording_id": out["id"], "events": out["events"],
            "steps": out["steps"], "stats": out.get("stats") or {},
            "hint": "已停止。用 unity_record_to_script 生成用例（draft），跑通后再让用户确认"}


@tool
async def unity_record_to_script(recording_id: str, name: str = "", save: bool = True) -> dict:
    """把一条录制翻译成平台风格的用例脚本；``save=True`` 时落库成 draft 用例。

    生成的脚本用 ``u.click`` / ``u.drag`` / ``u.set_text`` / ``u.key`` 回放，
    并自动播种断言（首次使用的路径、点击后新出现的面板，标 ``[自动播种]``）。
    契约不变：**跑通一次才算 active** —— 先用 ``unity_run_script`` 跑它，失败就
    照失败摘要改用例，改完覆盖保存。
    """
    from src.app.db.database import async_session_factory

    async with async_session_factory() as db:
        try:
            out = await unity_service.recording_to_script(
                recording_id, name=name or None, save=save, db=db)
        except (ValueError, LookupError) as exc:
            return {"success": False, "error": str(exc)}
    if save:
        return {"success": True, "script_id": out["script_id"], "stats": out["stats"],
                "hint": "已存为 draft：用 unity_run_script 跑通（exit 0）后才算 active"}
    return {"success": True, "script": out["script"], "stats": out["stats"]}


UNITY_AGENT_TOOLS = [
    unity_status,
    unity_sync_assets,
    unity_emergency_stop,
    unity_hierarchy,
    unity_find_by_text,
    unity_object_text,
    unity_find_objects,
    unity_object,
    unity_console,
    unity_editor,
    unity_start_line,
    unity_click,
    unity_set_text,
    unity_wait_for,
    unity_screenshot,
    unity_exec_csharp,
    unity_run_tests,
    unity_mcp_tools,
    unity_mcp_call,
    unity_generate_script,
    unity_run_script,
    unity_save_script,
    unity_get_script,
    unity_list_scripts,
    unity_record_start,
    unity_record_status,
    unity_record_stop,
    unity_record_to_script,
]
