"""Unity 自动化工具（Unity 自动化模块）。

工具面 = 三类**通用**原语 + 用例沉淀，全部经 ``services/unity_bridge.py`` 走标准
MCP 到一个 Unity MCP 服务器（CoplayDev/unity-mcp 等）。没有一条依赖某个游戏的
Lua 框架或 GM 命令 —— 换游戏只需要重新探索、重新沉淀用例，工具不用改。

- 探索：`unity_status` / `unity_find_objects` / `unity_object` / `unity_console*`
- 执行：`unity_editor` / `unity_reset`（回到起点）/ `unity_click` / `unity_set_text` /
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

    返回 available / server / flavor / tool_count / editor / is_playing。
    做任何操作前先调它：`available=False` 就是桥没起（去启动器启动 unity-mcp），
    `editor` 里没有 isPlaying 说明 Unity 编辑器还没连上，`is_playing=False`
    时场景里的**运行时对象还不存在**（先 `unity_editor("play")`）。
    """
    return await unity_service.status()


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

@tool
async def unity_editor(action: str) -> dict:
    """控制 Unity 编辑器：play / pause / stop / state / refresh。

    - play 进 Play Mode（运行时对象此时才存在）；stop 退出；pause 暂停；state 只看状态；
    - refresh 刷新资产（改完 Assets 后要它才会重新导入）。

    进 Play Mode 后别立刻操作：用 `unity_wait_for` 等登录窗/主界面出现。
    只是想"从头再来一遍"就别自己拼 stop/play —— 用 `unity_reset`。
    """
    return await unity_service.editor_action(action)


@tool
async def unity_reset(scene: str = "", wait_for: str = "", timeout: float = 120.0,
                      mode: str = "hard") -> dict:
    """**复位**：把游戏拉回起点（退 Play → 打开起跑场景 → 再进 Play → 等标志物）。

    什么时候用它：
    - 探索/复现走到一半，想把游戏清干净重来；
    - 上一个用例把游戏留在半路（面板开着、战斗打到一半），下一条用例要从头开始。

    参数：`scene` 给起跑场景（路径或名字，如 "Assets/Mods/SAMPLE/Maps/GameMaps/
    01_moqiaoshanzhuang.unity"；不给就用当前打开的那个，**同名不会重复打开**）；
    `wait_for` 给起跑线标志物（如 HUD 上的 "SystemButton"），复位完成的判定就是
    它回来了 —— 别用 sleep 猜；`mode="soft"` 只在 Play 内重载当前场景（快，但静态
    状态与常驻单例不清），换场景必须用默认的 hard。

    沉淀用例时**不用把这个调用写进用例**：用例里声明模块级常量
    `RESET = {"scene": "...", "wait_for": "..."}`，平台每次执行前自动复位；
    没声明的用例，平台会用"上次跑通时的起跑线"兜底。
    """
    return await unity_service.reset(scene=scene, wait_for=wait_for, timeout=timeout,
                                     mode=mode)


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

    精确定位（点哪个对象、读哪段文字）仍然用 `unity_hierarchy` / `unity_find_by_text` /
    `unity_object_text`：文字是给"点哪儿"用的，图是给"到底是不是这样"用的。
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
    """
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
async def unity_mcp_call(tool: str, args: str = "{}") -> dict:
    """原样调用 Unity MCP 服务器上的任意工具（不经过平台方言适配的逃生口）。

    - `tool`：工具名，如 "manage_gameobject" / "gameobject-create"；
    - `args`：JSON 字符串，参数名以 `unity_mcp_tools` 返回的 schema 为准。

    例：`unity_mcp_call("manage_scene", '{"action": "get_loaded_scenes"}')`
    """
    import json as _json

    if isinstance(args, str):
        try:
            parsed = _json.loads(args) if args.strip() else {}
        except _json.JSONDecodeError as exc:
            return {"success": False, "error": f"args 不是合法 JSON: {exc}"}
    else:
        parsed = args
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

    本工具的契约是"已验证才入库"，所以存为 status=active。
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
        return {"success": True, "script_id": str(row.id), "name": row.name,
                "updated": bool(script_id), "version": row.version}


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


UNITY_AGENT_TOOLS = [
    unity_status,
    unity_hierarchy,
    unity_find_by_text,
    unity_object_text,
    unity_find_objects,
    unity_object,
    unity_console,
    unity_editor,
    unity_reset,
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
]
