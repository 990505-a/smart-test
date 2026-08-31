---
name: unity-auto-test
description: Unity 客户端自动化测试工具。通过 HTTP API 和 Python 封装远程控制 Unity 编辑器、执行 Lua 代码、查询/操控 UI、模拟按钮点击、截图验证、执行 GM 命令。当用户需要测试 Unity 游戏功能、操控 UI 窗口、点击按钮、查询游戏状态、截图验证界面、执行 GM 指令搭建测试环境时触发。
---

# Unity Auto Test

通过 LuaRemoteServer（HTTP 端口 16666）远程控制 Unity 编辑器，实现客户端 UI 自动化测试与 GM 命令执行。

## 技能目录结构

本技能为自包含结构，所有代码和文档都在此目录下。以下路径均**相对于本 SKILL.md 所在目录**（下称 `SKILL_DIR`）。

```
SKILL_DIR/                          ← 本 SKILL.md 所在目录
├── SKILL.md                        ← 本文件
├── python/                         ← Python 模块
│   ├── unity_api.py                # 核心层 — HTTP API 薄封装
│   ├── ui.py                       # 操控层 — 搜索点击、窗口管理、等待、Tab 切换
│   ├── text_reader.py              # 文本层 — TMP 文本读取、按文本查找按钮、等待/断言
│   ├── inspector.py                # 检查层 — 窗口状态快照、UI 树、按钮清单
│   └── gm.py                      # GM 层 — GM 命令封装（等级/道具/战斗/时间等）
├── scripts/                        ← 可直接运行的脚本
│   ├── enter_game.py               # 启动 Play Mode
│   ├── wait_and_play.py            # 等待服务器就绪
│   ├── test_hud_tabs.py            # 测试底部 Tab 切换
│   └── explore_ui.py               # 探索当前 UI 状态
└── guides/                         ← 操作指南（按需阅读）
```

## 前置条件

1. **Unity 编辑器已打开** — 项目已加载
2. **LuaRemoteServer 已启动** — 在 Unity 中 `Tools > LuaTestTool` 窗口点击 Start Server
3. **服务器可达**

## 路径约定与初始化

本 Skill 中所有代码示例使用 `SKILL_DIR` 表示本 SKILL.md 所在目录的绝对路径。使用时根据实际读取路径替换。

### Python 代码初始化模板

```python
import sys, os

# SKILL_DIR = 本 SKILL.md 所在目录的绝对路径（由读取 SKILL.md 时确定）
SKILL_DIR = os.path.dirname(os.path.abspath("<SKILL.md 的实际路径>"))
sys.path.insert(0, os.path.join(SKILL_DIR, "python"))

from unity_api import UnityClient
from ui import UI
from text_reader import TextReader
from inspector import Inspector
from gm import GM

client = UnityClient()
ui = UI(client)
tr = TextReader(client)
ins = Inspector(client)
gm = GM(client)
```

### 运行脚本

脚本内部已用相对路径处理模块导入，可从任何位置运行：

```bash
python <SKILL_DIR>/scripts/explore_ui.py
python <SKILL_DIR>/scripts/test_hud_tabs.py --screenshot-dir ./screenshots
```

## 四层 API 架构

### 核心层 — `python/unity_api.py`

与 HTTP 接口 1:1 映射的薄封装，一般不直接使用。

```python
client = UnityClient()  # 默认 localhost:16666
```

四个子模块：

- `client.editor` — 编辑器控制（play/stop/pause/state）
- `client.lua` — Lua 执行（exec/exec_sync/eval）
- `client.hierarchy` — 场景层级（search/children/components/click）
- `client.screenshot` — 截图（capture）

### 操控层 — `python/ui.py`（推荐优先使用）

高频 UI 操作的封装，绝大多数测试场景都应使用此层。

```python
ui = UI(client)
```

核心能力：

- **搜索点击** — `find_and_click(name)`, `click_close(window_name=...)` ← 传 window_name 时单次 Lua 调用
- **Lua 点击** — `lua_click(instance_id)` ← 通过 onClick:Invoke() 点击，绕过 hierarchy.click 限制
- **文本定位点击** — `find_and_click_by_text(text, window_name=...)` ← 单次 Lua 调用完成查找+点击
- **通用 Tab 切换** — `switch_tab_by_text(tab_text, window_name=...)`, `switch_tab_and_verify(...)`
- **窗口管理** — `open_window()`, `close_window()`, `is_window_shown()`
- **等待机制** — `wait_for_window()`, `wait_for_node()`, `wait_for_hierarchy_window()`
- **组合操作** — `switch_hud_tab()`, `open_and_verify()`, `click_and_wait_window()`
- **allow_multiple** — `get_shown_instances(window_name)` ← 列出同名窗口所有显示中的实例
- **物品弹窗** — `close_all_item_info()` ← 一次关闭所有 ItemInfoBase 子类弹窗
- **子树搜索** — `find_in_children(parent_id, name)` ← 可靠的 Lua 子树搜索，替代 hierarchy.search parent

### 文本层 — `python/text_reader.py`

读取 UI 节点的 TMP（TextMeshProUGUI）文本，用于验证界面数据展示、通过文本区分同名按钮。

```python
tr = TextReader(client)
```

核心能力：

- **富文本剥离** — 所有方法支持 `strip_tags=True`，自动去除 `<color=...>`/`<size=...>` 标签
- **定向读取** — `get_text(node_name, ...)`, `get_texts(...)` ← 按节点名定向查找，找到即返回（不再全量扫描）
- **按索引读取** — `get_text_at(node_name, index, ...)` 精确定位列表/网格中第 N 个同名节点
- **进度条解析** — `get_progress(...)` 解析 `当前值/总量` 格式，`assert_progress(...)` 支持比值/绝对值断言
- **数值断言** — `get_number(...)`, `get_numbers(...)`, `assert_number(...)` 支持 eq/gt/gte/lt/lte 比较
- **正则断言** — `assert_text_pattern(pattern, ...)` 适用于含动态数字/时间的文本
- **批量断言** — `assert_text(...)` 精确/包含匹配，`assert_text_at(index, ...)` 按索引断言
- **按钮文本** — `find_button_by_text(text, ...)` ← Lua 侧早停匹配，找到立即返回（不再拉全量按钮列表）
- **等待文本** — `wait_for_text(...)`, `wait_for_text_change(...)` ← 使用定向快速路径
- **instance_id** — 所有方法支持 `instance_id=...` 参数，精确指定 allow_multiple 窗口的某个实例
- **调试打印** — `print_all_texts(...)`, `print_button_texts(...)`

### 检查层 — `python/inspector.py`

UI 状态观察与调试。

```python
ins = Inspector(client)
```

核心能力：

- **窗口状态** — `get_shown_windows()`, `get_shown_windows_detail()` ← 返回含 instanceID 的详情
- **UI 树** — `dump_tree(id, depth=3)` ← 单次 Lua 调用序列化子树，替代逐节点 HTTP 请求
- **按钮清单** — `print_buttons(parent=id)`
- **窗口检查** — `inspect_window("WindowName")`
- **游戏数据** — `eval_game_var()`, `print_hero_info()` ← 单次 Lua 调用获取所有字段

### GM 层 — `python/gm.py`

远程执行 GM 命令，封装 `GmD.lua` 中的常用指令。底层通过 `client.lua.exec()` 构造 Lua 代码调用 `GameServer:gm(...)` 发送到服务端。

```python
gm = GM(client)
```

核心能力：

- **等级与解锁** — `set_level()`, `set_all_unlock()`, `set_standard_char()`
- **道具与背包** — `clone_item()`, `add_base_items()`, `drop_all()`, `query_item_amount()`
- **属性与战斗** — `full_hp_mp()`, `set_ent_kill_in_one()`, `kill_all_entity()`, `add_buff()`
- **时间操控** — `shift_add_one_day()`, `refresh_daily()`, `show_server_time()`
- **任务** — `assign_task()`, `accept_task()`, `finish_task()`, `clear_task()`
- **机器人/怪物** — `add_robot()`, `clear_robots()`, `add_monster()`
- **灵兽** — `add_pet()`, `remove_pet()`, `pet_full_energy()`
- **功法/神通** — `add_gongfa()`, `add_shentong()`, `skill_unlock_all()`
- **秘境/地图** — `unlock_temple()`, `unlock_grid_map()`
- **道院** — `create_test_gangs()`, `set_self_gang_owner()`, `set_gang_level()`
- **底层调用** — `raw()`, `eval()`, `gm()` 用于执行未封装的自定义指令

## 操作指南

根据用户的操作意图，阅读对应的 guide 文件获取详细用法和示例：


| 用户意图                                             | Guide 文件                                             |
| ------------------------------------------------ | ---------------------------------------------------- |
| 启动/停止游戏、暂停/恢复、查询编辑器状态                        | [guides/editor-control.md](guides/editor-control.md) |
| 执行 Lua 代码、查询运行时变量、调用游戏逻辑                     | [guides/lua-execution.md](guides/lua-execution.md)   |
| 查找 UI 节点、点击按钮、打开/关闭窗口、切换 Tab                | [guides/ui-operations.md](guides/ui-operations.md)   |
| **读取 TMP 文本、通过文本定位按钮、验证文本内容、等待文本变化** | [guides/text-reading.md](guides/text-reading.md)     |
| 探索 UI 结构、查看窗口列表、打印按钮清单                       | [guides/inspection.md](guides/inspection.md)         |
| 截取游戏画面、验证 UI 状态                                | [guides/screenshot.md](guides/screenshot.md)         |
| 执行 GM 命令、搭建测试环境、操控角色/道具/时间                  | [guides/gm-commands.md](guides/gm-commands.md)       |
| 运行已有测试脚本或编写新脚本                                 | [guides/scripts.md](guides/scripts.md)               |


**根据用户的需求读取对应的 guide 文件并按其中的指引操作。** 不要一次性读取所有 guide。

## 游戏 UI 架构速查

### Canvas2D 层级（从低到高）


| Layer   | 路径               | 用途                          |
| ------- | ---------------- | --------------------------- |
| Battle  | Canvas2D/Battle  | 战斗 UI（MainWindow）           |
| Back    | Canvas2D/Back    | 主界面背景（HudWindow、ChatWindow） |
| Normal  | Canvas2D/Normal  | 普通弹窗                        |
| Top     | Canvas2D/Top     | 高级弹窗（HudMoneyWindow）        |
| TopMost | Canvas2D/TopMost | 最高层（ScreenEvent、GM）         |


### 底部导航栏 Tab

HudWindow 底部 7 个 Tab 位于 `HudWindow(Clone)/layout/` 下：


| Tab 名称    | 打开的窗口            |
| --------- | ---------------- |
| character | CharacterWindow  |
| gongfa    | GongfaRoomWindow |
| wild      | —（BigMapWindow）  |
| house     | HouseRoomWindow  |
| gang      | GangRoomWindow   |
| mmo       | MMORoomWindow    |
| clan      | ClanRoomWindow   |


### 常见关闭按钮命名

按优先级：`btn_close` → `img_btn_close` → `BtnClose` → `btn_close_bg`

## 按钮点击策略

游戏框架使用 `listen_button_clicked` 注册按钮回调（底层仍通过 `btn.onClick:AddListener`），但 `hierarchy.click()` 基于 C# `ExecuteEvents.Execute` 在某些情况下无法触发。根据场景选择合适的点击方式：

| 策略 | 方法 | 适用场景 | 说明 |
|------|------|---------|------|
| **Lua onClick** | `ui.lua_click(instance_id)` | 通用游戏按钮 | 通过 Lua `onClick:Invoke()` 触发，最可靠 |
| **Lua 文本查找+点击** | `ui.find_and_click_by_text(text, window_name=...)` | 按文本区分按钮 | 单次 Lua 调用完成查找和点击 |
| **Hierarchy 点击** | `ui.click(instance_id)` / `ui.find_and_click(name)` | 标准 Unity 按钮 | 通过 C# ExecuteEvents，部分按钮可能不响应 |
| **直接关闭** | `ui.click_close(window_name=...)` | 关闭窗口 | 直接调用 UI.close()，不依赖按钮点击 |
| **业务逻辑绕过** | `client.lua.exec("Widget方法()")` | 按钮无法触发时 | 直接调用 Lua 业务函数 |

**推荐优先级**：Lua onClick → 文本查找+点击 → hierarchy.click → 业务逻辑绕过

## allow_multiple 窗口

游戏中部分窗口配置了 `allow_multiple = true`，可同时存在多个实例（如堆叠的物品信息弹窗）。

**配置了 allow_multiple 的常见窗口**：
`ItemInfoSimpleWindow`, `ItemInfoDetailWindow`, `ItemInfoChooseWindow`, `EquipmentInfoWindow`,
`ItemSourceWindow`, `GongfaShentongInfoWindow`, `GongfaXinfaInfoWindow`, `MessageBoxWindow`,
`CommonResultWindow`

**操作方式**：

```python
# 列出某窗口所有正在显示的实例
instances = ui.get_shown_instances("ItemInfoSimpleWindow")
# → [{"name": "ItemInfoSimpleWindow", "instanceID": 12345}, ...]

# 用 instance_id 精确操作某个实例的文本
tr.get_text("text_name", instance_id=instances[0]["instanceID"])

# 一次关闭所有物品信息弹窗
ui.close_all_item_info()

# 获取所有显示中窗口的详细信息（含 instanceID）
details = ins.get_shown_windows_detail()
```

**所有 ItemInfoBase 子类**（8 个）：
`ItemInfoSimpleWindow`, `ItemInfoDetailWindow`, `ItemInfoChooseWindow`,
`EquipmentInfoWindow`, `ItemInfoEquipSoulWindow`, `DaoHuoDetailsRewardWindow`,
`ShopBatchBuyItemsWindow`, `CommonItemSellWindow`

## 错误处理

- `UnityAPIError` — 所有 API 错误的统一异常类型，向用户报告错误内容
- 连接失败 — 提示用户检查 Unity 编辑器和服务器状态
- `"game is not running"` — 需先 `client.editor.play()` 进入 Play Mode
- `"Button not found"` / `"inactive"` — 按钮不存在或未激活，需确认场景和窗口状态

