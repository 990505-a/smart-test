---
name: unity-ui-test
description: Unity 客户端自动化测试技能（通用，与具体游戏无关）。经标准 MCP 桥操作 Unity：按名字/路径/组件查场景对象、读组件字段、点控件、写文本、等对象、读 Console 报错、截图、执行任意 C#，并把跑通的流程沉淀成可回归的 Python 用例脚本。当用户需要探索 Unity 界面、复现/验证某个客户端功能、把手工点测变成用例、或排查"点了没反应"这类问题时触发。
---

# Unity 自动化（通用桥）

平台**不含任何游戏侧代码**：Unity 工程里装一个 MCP 桥包（如 CoplayDev/unity-mcp
的「MCP for Unity」），由它连到平台的 Unity MCP 服务器（启动器里的 unity-mcp，
默认 :5016）。所有操作经 MCP 说话：对象查询、编辑器控制、任意 C#。

**为什么这样做**：旧版靠游戏自己提供的 Lua 桥（LuaRemoteServer）执行任意 Lua，
窗口名、点击方式、GM 命令全是那款游戏的知识 —— 换一款游戏整套作废。现在游戏特有
的知识只沉淀在**用例脚本**里，工具本身对任何 Unity 项目通用。

## 前置条件

1. 桥在线：`unity_status` 返回 `available=true`（否则去启动器启 unity-mcp）。
2. Unity 编辑器已连上：status 的 `editor` 不为 null。
3. 要操作**运行时**界面（窗口/按钮/文本）时必须在 Play Mode：
   `unity_editor("play")`，然后 `unity_wait_for("<主界面标志物>")`。
   编辑器模式下的对象只有场景资产，没有跑起来的游戏逻辑。

## 探索流程（照这个顺序，不要跳步）

1. `unity_status` —— 桥、Unity、是否 Play Mode。
   状态不对（进不了 Play、界面卡在某个面板、上一条用例把游戏留在半路）就先
   **`unity_reset(scene=…, wait_for=…)`** 把它拉回起点，别在半坏的状态上硬试。
2. **`unity_hierarchy()`** —— 先看全貌：路径 / 是否显示 / 组件 / **界面上的文本**
   一次摊开。要钻某个面板就 `unity_hierarchy(root="MainCanvas/NormalUI")`。
   **别猜对象名**："TalkUI / UI / UIRoot / Talk" 这样一个个试，每轮一次往返，还可能
   全部落空（实测就是这么把一轮探索拖长的）。
3. **中文界面按界面上的字找**：`unity_find_by_text("背包")` —— 返回写着这句话的对象，
   以及**往上最近的可点祖先**（uGUI 按钮的标签挂在子节点上，那个祖先就是要点的东西）。
   搜不到多半是那个界面当前没打开。
4. 读内容：面板/列表用 `unity_object_text("BagUIPanel(Clone)")`（整棵子树的文字）；
   单个控件的组件与字段用 `unity_object("<路径或名字>")`。
   需要**按组件**找（如所有按钮）或已知确切名字时用 `unity_find_objects`。
5. 操作：`unity_click("<路径>")` / `unity_set_text("<路径>", "...")`。
6. `unity_wait_for("<路径>")` 等结果出现/消失（别用 sleep 硬等）。
7. **`unity_console()`** —— Unity 侧异常不会让调用失败，只会写进 Console。
   不读它就会把"点了个寂寞"当成通过。
8. `unity_screenshot("xxx.png")` 存证（截图落在本次运行目录里）。

## 什么时候该"看一眼"（视觉核验）

读组件回答的是"某个对象在不在、它上面写了什么"；**"界面到底长什么样、有没有那个按钮"
只有图能回答**。看图这条路平台是通的、模型也有视觉能力，成本是两步：

```python
p = unity_screenshot("now.png")   # 返回图片路径（相对路径 = workspace/default/unity-auto/screenshots）
# 紧接着 read_file(p) —— 图片会以图像形式给你，你就能真的看到界面
```

四个必须看一眼的场合：

1. **不确定界面上有没有**某个入口/按钮 —— 别用"按名字查不到"推断"没有"：名字可能是
   拼音、可能是运行时克隆的、也可能压根不是一个独立对象；
2. **打开面板/切页之后**，确认它真的打开了 —— 被别的层遮住、渲染成空白、动画没走完，
   这些查对象都查不出来；
3. **操作"点了没反应"**时 —— 先截图看现场，比继续猜便宜得多；
4. **断言失败**时 —— 先看图确认是不是断言自己写错了（平台失败时也会自动留一张
   `failure.png`，连同"走到哪一步"一起写进 `failure.txt`）。

分工记牢：**图用来判断"是不是这样"，文本用来决定"点哪儿"** —— 先 `unity_hierarchy` /
`unity_find_by_text` 定位，截图确认，再动手。反过来（只读组件不看图）会在"界面到底有没有"
这类问题上绕远路；只看图不读文本则点不准。

## 沉淀用例（这才是交付物）

脚本是**纯 Python**，prelude 已经注入好 `u`（Unity 客户端）与 `UnityBridgeError`：
不要 import、不要构造客户端、不要写 `if __name__`。

```python
# 用例：打开背包并校验等级文本
# 起跑线：平台每次执行前会先复位到这里（退 Play → 这张地图 → 再进 Play → 等 HUD）
RESET = {"scene": "Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity",
         "wait_for": "SystemButton"}

u.expect_exists("MainHud", timeout=20)          # 等主界面
u.click("MainHud/BottomBar/BagButton")          # 操作
u.expect_exists("BagWindow", timeout=10)        # 等窗口
u.expect_text("BagWindow/Title", "背包")         # 断言具体期望值
u.screenshot("bag_open.png")                    # 存证
print("PASS: 背包窗口打开且标题正确")
```

客户端 API 速查：

| 方法 | 作用 |
| --- | --- |
| `u.status()` / `u.is_playing()` | 桥与编辑器状态 |
| `u.hierarchy(root="", depth=3, max_nodes=80)` | 看（子）树：路径/可见/组件/文本（探索第一步） |
| `u.find_by_text("背包")` | 按界面上的字找对象 + 它的可点祖先 |
| `u.subtree_text("BagUIPanel(Clone)")` | 读整棵子树的文本（"这个面板现在显示什么"） |
| `u.play()` / `u.stop()` / `u.pause()` | 编辑器控制（`play()` 会等到真的进 Play Mode） |
| `u.reset(scene=, wait_for=, mode="hard"/"soft")` | **复位到起跑线**（见下节） |
| `u.active_scene()` / `u.load_scene(path)` | 当前打开的场景（`{name, path}`）/ 编辑模式下打开场景 |
| `u.find_objects(name=, path=, component=, tag=, limit=)` | 查对象（返回 dict） |
| `u.object(target)` / `u.object_text(target)` | 读组件详情 / 读所有文本属性拼接 |
| `u.exists(target)` | 存在性（bool，不抛错） |
| `u.click(target)` / `u.set_text(target, text)` | 操作控件（失败抛 `UnityBridgeError`） |
| `u.wait_for(target, timeout=, state="present"/"absent")` | 等出现/消失（超时抛 `AssertionError`） |
| `u.expect_exists` / `u.expect_absent` / `u.expect_text(target, "包含")` | 断言（失败抛 `AssertionError`） |
| `u.console(filter_text=, limit=)` / `u.errors()` | 读 Console（`errors()` 只取报错） |
| `u.screenshot("name.png")` | 截图，返回路径（相对路径 = 落在本次运行目录） |
| `u.record_start(fps=)` / `u.record_stop()` / `u.recording_scope("run.mp4")` | 录像（默认已开，见下节） |
| `u.capture_failure("failure.png")` | 手动抓失败现场（截图 + 上下文文本） |
| `u.trace_to(path)` / `u.steps()` | 步骤轨迹落盘 / 读本次已记录的步骤 |
| `u.exec_csharp(code)` | 执行任意 C# 语句 |
| `u.run_tests(mode="PlayMode", filter_text=)` | 跑工程里的 C# 测试 |
| `u.tools()` / `u.call(tool, args)` | 看/直接调 MCP 服务器上的任意工具 |

退出码即结论：0 = 通过，1 = 断言失败（用例问题），2 = 桥/环境问题。
**失败先看 `u.errors()`**，再决定改脚本还是报环境问题。

## 起跑线与复位（用例从哪儿开始）

用例之间**必须能各跑各的**：上一条把游戏停在背包里、主角站在地图另一头，下一条不能
接着那个状态跑。平台的做法是执行前**复位**：退 Play → 打开起跑场景 → 再进 Play →
等标志物回来，然后才跑用例主体。这件事有两处要落：

**1）用例声明起跑线**（写在文件顶部的模块级常量，不是调用）：

```python
# RESET：平台每次执行前复位到这里。普通游戏就是"开哪张地图/哪个界面 + 等哪个对象"
RESET = {"scene": "Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity",
         "wait_for": "SystemButton",       # 起跑线标志物（HUD 上的「系统」按钮）
         "timeout": 180}                   # 可选：大工程冷启动慢就放宽
```

- `scene` 给场景**路径或名字**；与当前打开的一致就**不重复打开**（避免脏场景的保存
  对话框卡住编辑器）。写了 RESET 就不再需要"先手动打开某场景再进 Play"这类注释里的人
  工前置 —— 那正是它要取代的东西。
- `wait_for` 是**复位完成的判定**（`u.wait_for` 的语义），别用 sleep 猜大工程要多久。
- `RESET = False` = 这条用例不复位（接着现场跑，比如"接着上一条继续"的链式用例）。
- 环境变量 `UNITY_RESET=0` 可以全局关掉复位。

**2）没写 RESET 的用例**：平台会在它**跑通一次之后**记住当时的现场
（`start_state.json`：起跑场景 + 轨迹里第一个成功的 `wait_for`），下一轮自动回到那里。
所以老用例不改也能有复位；但**显式写下来才算把前置说清楚**（这也是评审时能看懂的那份
"这条用例从哪儿开始"）。

**想立刻重来一遍**（探索走了一半、或者手动复现时）：直接用 `u.reset(...)`，
别自己拼 stop/play —— 少了"等标志物回来"那一步，后面全在跟半加载的界面较劲：

```python
u.reset(scene="Assets/Mods/SAMPLE/Maps/GameMaps/01_moqiaoshanzhuang.unity",
        wait_for="SystemButton")     # 等 HUD 回来，复位才算完成
u.reset(mode="soft")                 # 轻复位：只在 Play 内重载当前场景
```

两种复位方式的取舍（`mode`）：

| | 做了什么 | 什么时候够用 |
| --- | --- | --- |
| `hard`（默认） | 退 Play → 开场景 → 再进 Play | **真复位**：场景对象、常驻单例、静态缓存、网络会话全重来。慢（一遍冷启动） |
| `soft` | Play 内 `SceneManager.LoadScene` 重载当前场景 | 只想把地图/界面拉回起点，几秒钟。**静态状态与 DontDestroyOnLoad 的常驻对象不清**，换场景也不行 |

复位失败按**环境问题**处理（退出码 2，页面标 error 而不是 failed）：起跑线没回来
说明游戏/场景没准备好，那不是"功能不对"。复位也会记进步骤轨迹（第一行 `reset`），
页面上历史详情里能看见。

## 存证：用例不用自己抓证据（平台自动给）

与 Playwright 那边同构 —— **trace/截图/录像都是 runner 的事，不是 spec 的事**。
经平台跑的每次执行都自动留下四样东西，页面上「历史 → 看详情」就能看：

| 产物 | 从哪来 | 用途 |
| --- | --- | --- |
| `steps.jsonl` 步骤轨迹 | 桥自动记每个动作/断言（成功失败都记） | 回答"走到哪一步挂的" |
| 截图 | 用例里的 `u.screenshot()` + 失败时自动补一张 `failure.png` | 界面长什么样 |
| `run.mp4` 录像 | 编辑器侧逐帧采、平台侧 ffmpeg 合成（**默认开**） | 交互过程/动画类的失败 |
| `failure.txt` 失败现场 | 挂掉时自动写：报错、最后 25 步、控制台摘录、相关对象文本 | 一眼定位，不用翻日志 |

所以**用例只管写操作和断言**，不用为了"留证据"到处插截图；只在关键节点插
`u.screenshot("01_hud.png")` 让人看得更顺手（文件名用 `01_xx` 便于排序）。

要调整的话：

```python
u.record_stop(keep=False)              # 这次执行不留录像（也可用 UNITY_RECORD=0 全局关）
with u.recording_scope("login.mp4"):   # 只录某一段
    u.click("LoginButton")
u.capture_failure("my_failure.png")    # 想在自己认定的关键点抓现场
```

三个实测约束（不是 bug，是编辑器的现实）：

- **帧里带着 Game View 的工具条**（`Scene|Game`、FPS 之类）：`ScreenCapture` 抓的是
  整个 Game View 窗口，只有相机渲染那条路才干净 —— 但那条路会漏掉 Screen Space
  Overlay 的 UI，两害相权取其轻。
- **实际帧率 3~10fps**：受编辑器主循环节拍限制（每个 MCP 调用还会占住主线程），
  短用例（1 秒级）的录像就是几百毫秒一小段。所以**录像用来补"过程"，定位主要靠
  步骤轨迹 + 截图**。合成时按**实测速率**写帧率，不会快放。
- **编辑器与平台不同机时录不了**：帧是 Unity 写在它自己的临时目录里、平台读盘合成
  （截图能跨机是因为走 MCP 回传，帧太多不走）。这种情况输出里会有一行
  `WARN: 录像没有合成：帧目录不在本机…`，不影响用例判定。

存证出问题**绝不改判用例结果**：ffmpeg 缺失、录像合成失败、现场截图失败都只写
`WARN`，退出码仍由断言说了算。

## C# 逃逸口

工具面覆盖不到的操作（拖拽、滑动、长按、点非 UGUI 的 3D 物体、调游戏的业务方法、
造前置数据）用 `unity_exec_csharp` / `u.exec_csharp`。约定：**结果用
`UnityEngine.Debug.Log("UNITY_BRIDGE:" + json)` 回传**，平台会把它解析成 `result`。
`code` 是**语句序列**（不是完整类），类型写全名，不用 `using`。

```csharp
// 例：把某个对象拖到目标位置（通用做法，不需要游戏侧接口）
var __src = UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)
    .Where(g => g.name == "ItemSlot").FirstOrDefault();
UnityEngine.Debug.Log("UNITY_BRIDGE:{\"ok\":" + (__src != null ? "true" : "false") + "}");
```

平台内置的 C# 片段（可直接照抄思路，也可在自定义代码里用）：
- 点击：先 `Button.onClick.Invoke()`，再退回 `ExecuteEvents` 指针点击（判定 +
  区分"对象不存在"与"没有点击处理器"）；
- 写文本：反射找可写 `text` 属性（不依赖 TMPro 是否安装）；
- 读对象：反射遍历组件，回传 `text` / `value` / `isOn` / `interactable`。

## 实测要点（这些坑踩过一次，别再踩）

- **C# 片段是「方法体」**：`execute_code` 把代码当方法体编译，**必须 return**，
  返回值经 `data.result` 回来（对象会被序列化成 JSON）。平台的内置片段已经这样写。
  默认编译器是 **CodeDom**（Roslyn 通常没装）→ 只用 C# 5 以内的语法：
  别用字符串插值 `$"..."`、`?.`、表达式体成员；匿名委托 `delegate { }` 可以。
  实测报错长这样：`not all code paths return a value`。
- **定位可以写半截路径**：平台按 名字 → 全路径 → 后缀匹配 依次找，
  所以 `SmokeButton/Label` 和 `SmokeCanvas/SmokeButton/Label` 都能命中；
  服务器的 `by_path` 查询本身也收半截路径。
- **Console 默认只给 error/warning**（服务器的默认），平台的 `unity_console`
  默认传 `types="all"` —— 想只看日志就传 `types="log"`，否则 Debug.Log 一条都看不到。
- **域重载（改脚本/装包触发）会清掉两样东西**：动态 C# 里挂的事件监听器，
  以及 Console 的历史缓冲。表现是"点了按钮但看不到日志"——重新挂监听再点即可，
  不是链路坏了。
- **复位只重开场景，不碰游戏的存档/服务器数据**：退 Play 再进 Play 能清掉内存里的
  一切，但**已经写进存档的进度**（主角升级了、任务做完了、道具用掉了）不会自己回来。
  要连存档一起回滚，得用游戏自己的机制（系统菜单的「载入游戏」、GM 命令、或者把存档
  文件还原）—— 用 `u.exec_csharp` 调游戏的读档接口，或先快照存档文件。
- **打开场景时如果它"脏"了，编辑器可能弹保存对话框卡住**（模态框会挡住 MCP 的执行
  线程）。所以复位里**同名场景不重复打开**；自己的脚本里 `load_scene` 之前先看
  `u.active_scene()` 的 `is_dirty`。


- **失败有两种写法**：MCP 的 `isError`，以及 **200 + 正文 `{"success": false}`**
  （这台服务器是后者）。平台已经统一成 `success=false` + `error`，所以看
  `error` 字段就行 —— 出现 `no_unity_session` / "Unity session not available"
  一律是**环境问题**（Unity 没连上），不是用例失败，别去改脚本。
- **工具组默认是关的**：`execute_code`（组 `scripting_ext`）与 `run_tests`（组
  `testing`）不在默认工具清单里。平台在第一次用到时自动激活；手动排查用
  `unity_mcp_call("manage_tools", '{"action": "list_groups"}')`。
- **对象查询只回 instance id**：`find_gameobjects` 给的是 id，详情要按 id 读资源
  （平台已自动补全，并把 `count`/`detailed` 一起给你 —— 真游戏一次能查回几十个，
  数字对不上就是被 `limit` 截了）。要更多就自己读
  `mcpforunity://scene/gameobject/{id}/components`。
- **截图默认不返回图片**：`include_image` 默认 false，平台已显式打开并把长边放到
  1568（默认 640 看不清小字）。
- **一次响应可能含多个事件**（先日志通知再结果）且是 CRLF 行尾 —— 平台已按行解析，
  自己写 MCP 客户端时要当心。
- **Console 的 `count` 要传字符串**（服务器自己的兼容性要求，平台已处理）。

## 真游戏实测（三个开源工程跑通后补的）

- **进 Play 用 `u.play()`，别用 C# 写 `EditorApplication.isPlaying = true`**。后者会让
  延迟初始化跑不完：实测 Chop Chop 的 `IEnumerator Start()` 没执行完，菜单按钮的
  UnityAction 全是 null，点哪个都 NullReferenceException —— 看着像"游戏坏了"，其实
  是入场方式不对。`u.play()` 走的是编辑器的 Play 动作，没有这个问题。
- **服务器按路径查是「后缀」匹配**：`find_objects(path="ItemsList")` 只回 ItemsList
  **自己**，一个子孙都不回。所以"这个列表/面板里现在有什么"要用
  `u.object_text("ItemsList")` —— 它会把整棵子树的文本按顺序拼起来
  （实测拿到 `'0 Magnet 750 PREMIUM BUY 0 Invincible 1500 5 BUY ...'`，一条断言就能
  看住整页内容）。要拿单个字段再顺着 `find_objects(component="Text")` 过滤路径。
- **截图是 ScreenCapture 出的游戏视图，含 Screen Space - Overlay 的 UI**。
  相机渲染那条路拍不到 Overlay —— 实测 Trash Dash 的商店场景里**根本没有相机**，
  START 按钮就在屏幕坐标上，相机路径的图里却一个 UI 都没有。别用截图"证明"UI 没渲染，
  先用 `find_objects` 看 `activeInHierarchy`。
- **控制台断言按「无新增报错」判，并剔除引擎升级噪音**。老工程升到新编辑器会持续喷
  弃用提示（实测 `is not supported anymore.`），一比全量就永远是红的：
  先记基线 `set(u.errors())`，跑完只比新增的那几条。
- **游戏自己的异常会如实回给你**：点击失败时 `error` 里带异常类型和栈。先看栈是不是
  游戏代码 —— 是的话那是被测对象的问题，别急着改用例（实测 projectZero 点 START
  时游戏自己在 `PlayerData.instance` 上 NRE）。
- **页签/面板会记住上次的状态**：别假设"打开就是默认页"，显式切一遍再断言，
  否则上一轮跑完留下的状态会让用例假失败。
- **键盘输入合成目前不可靠**：真游戏常有"按 Esc 关面板/暂停"这类纯输入交互。实测在编辑器
  里用新版 Input System 的 `QueueStateEvent` 合成 Escape（并放宽了 Game View 焦点规则）
  没能触发游戏的 Cancel 动作 —— 这类"只能用按键关"的界面暂时自动化不了，先在用例里
  绕开（能点到的路径优先），别在这上面反复试。
- **名字两端有空白是正常的**（实测 `Button Settings `）—— 平台比对是 Trim 过的，
  按正常名字写就行。

## 常见坑

- **Play Mode 一重启，之前拿到的对象引用全失效**：每次都要重新按路径查，别缓存。
- **未激活的窗口也在场景里**：`find_objects` 会返回它们 —— 断言"窗口打开"要看
  `activeInHierarchy`，不要只看存在（`exists()` 只回答"在不在场景里"）。
- **同名对象优先挑当前可见的那份**：真游戏里一个 SaveButton 在每个面板各有一份，
  只点名字会点到没激活的那份（通常直接 NRE）。要指定具体一个就写路径。
- **点不动**：多半不是按钮（没有点击处理器）；用 `unity_object` 看组件，
  必要时点它的父节点，或 `exec_csharp` 直接调它的方法。
- **文本读不到**：文本可能在子节点上（`BagWindow/Title/Txt`），顺着层级再查一层；
  `object_text()` 会把整棵子树的 text/value 都拼起来，适合断言"包含"。
- **一律不硬等**：`wait_for` / `expect_*` 自带超时轮询；硬 sleep 只会让用例又慢又飘。
