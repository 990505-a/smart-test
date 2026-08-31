# UI Operations Guide

查找 UI 节点、点击按钮、打开/关闭窗口、切换底部导航栏 Tab。

这是最常用的 guide，覆盖绝大多数 UI 自动化测试场景。

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
from ui import UI

client = UnityClient()
ui = UI(client)
```

## 搜索并点击按钮

### 最常用：find_and_click

按名称搜索按钮并点击，一步完成。自动过滤 active 状态。

```python
# 点击名为 btn_equip 的按钮
ui.find_and_click("btn_equip")

# 限定在某个窗口子树下搜索（避免同名按钮冲突）
ui.find_and_click("btn_equip", parent=window_instance_id)

# 自定义点击后等待时间
ui.find_and_click("btn_equip", wait=2.0)
```

### 只搜索不点击

```python
btn = ui.find_button("btn_close", parent=window_id)
if btn:
    print(f"找到: {btn['name']} (id={btn['instanceID']}, active={btn['active']})")
```

### 获取所有按钮

```python
buttons = ui.find_all_buttons(parent=window_id, active_only=True)
for b in buttons:
    print(f"  {b['name']} ({b['instanceID']})")
```

### 搜索任意 GameObject（不限定 Button）

```python
node = ui.find_node("layout", parent=hud_id)
```

### 点击关闭按钮

**推荐：传 `window_name` 直接通过 UI.close() 关闭（单次 Lua 调用，最高效）：**

```python
ui.click_close(window_name="CharacterWindow")
```

也可以通过 hierarchy 搜索关闭按钮（自动尝试 btn_close → img_btn_close → BtnClose → btn_close_bg）：

```python
ui.click_close(parent=window_id)
```

### Lua 层按钮点击

`hierarchy.click()` 对部分使用 `listen_button_clicked` 注册回调的按钮可能无效。
使用 `lua_click()` 通过 `onClick:Invoke()` 直接触发：

```python
btn = ui.find_button("btn_equip", parent=window_id)
ui.lua_click(btn["instanceID"])
```

## 窗口管理

### 打开窗口

```python
ui.open_window("CharacterWindow")           # 默认等待 2 秒
ui.open_window("CharacterWindow", wait=3.0)  # 自定义等待
```

### 关闭窗口

```python
ui.close_window("CharacterWindow")           # 默认等待 1 秒
```

### 隐藏/显示（不销毁实例）

```python
ui.hide_window("ChatWindow")
ui.show_window("ChatWindow")
```

### 查询窗口状态

```python
if ui.is_window_shown("CharacterWindow"):
    print("窗口已打开")
```

### 打开并验证

```python
success = ui.open_and_verify("BaggageWindow")
assert success, "窗口打开失败"
```

### 关闭并验证

```python
success = ui.close_and_verify("BaggageWindow")
assert success, "窗口关闭失败"
```

## 等待机制

UI 操作通常是异步的，需要等待加载完成。

### 等待窗口出现

```python
appeared = ui.wait_for_window("BaggageWindow", timeout=10.0)
```

### 等待窗口关闭

```python
closed = ui.wait_for_window_close("BaggageWindow", timeout=5.0)
```

### 等待节点出现

```python
node = ui.wait_for_node("loading_complete", timeout=15.0)
if node:
    print("加载完成")
```

### 点击按钮后等待窗口弹出

```python
ui.click_and_wait_window("btn_settings", "CombatSetWindow", parent=main_window_id)
```

## 切换底部导航栏 Tab

HudWindow 底部有 7 个 Tab：character, gongfa, wild, house, gang, mmo, clan。

```python
# 自动查找 HudWindow layout 并点击（最简写法）
ui.switch_hud_tab("character")

# 手动指定 layout ID（避免重复搜索，性能更好）
ui.switch_hud_tab("gongfa", hud_layout_id=-146484)
```

Tab 与窗口的对应关系：


| Tab       | 打开的窗口            |
| --------- | ---------------- |
| character | CharacterWindow  |
| gongfa    | GongfaRoomWindow |
| wild      | —（打开大地图）         |
| house     | HouseRoomWindow  |
| gang      | GangRoomWindow   |
| mmo       | MMORoomWindow    |
| clan      | ClanRoomWindow   |


## 截图

```python
ui.screenshot("test_result.png")
```

## 底层 API（需要更细粒度控制时）

如果 `ui.py` 的封装不能满足需求，可以直接使用核心层：

```python
# 搜索
results = client.hierarchy.search(name="BtnStart", type="Button")

# 点击
client.hierarchy.click(results[0]["instanceID"])

# 查看子节点
children = client.hierarchy.children(instance_id)

# 查看组件
comps = client.hierarchy.components(instance_id)

# 获取场景根节点
roots = client.hierarchy.roots()
```

## 典型测试流程

```python
# 1. 切换到角色 Tab
ui.switch_hud_tab("character")

# 2. 获取 CharacterWindow 节点 ID
wnd = ui.find_node("CharacterWindow")

# 3. 点击窗口内按钮
ui.find_and_click("btn_equip", parent=wnd["instanceID"])
ui.screenshot("equip_panel.png")

# 4. 关闭面板
ui.click_close(parent=wnd["instanceID"])

# 5. 验证已关闭
assert not ui.is_window_shown("CharacterWindow")
```

## 通过 TMP 文本定位并点击按钮

当多个按钮共享同一 GameObject 名称（如多个 `btn_click`、`item-109884`），
但显示文本各不相同时，通过文本内容精确定位目标按钮。

需要额外导入 `TextReader`：

```python
from text_reader import TextReader
tr = TextReader(client)
```

### 直接点击（推荐）

```python
# 精确匹配文本后点击
ui.find_and_click_by_text("宗门公告", window_name="GangRoomWindow")

# 包含匹配（文本作为子串）
ui.find_and_click_by_text("宗门", window_name="GangRoomWindow", exact=False)

# 按钮文本含颜色标签时用 strip_tags（先剥离再匹配）
ui.find_and_click_by_text("衣·灵纱绘羽",
                           window_name="OperateActivityWindow",
                           strip_tags=True)
```

### 先查后点（需要中间步骤时）

```python
btn = tr.find_button_by_text("御魔之境", window_name="GangRoomWindow")
if btn:
    ui.lua_click(btn["instanceID"])  # 推荐用 lua_click 替代 ui.click
```

### 调试：查看窗口内所有按钮文本

```python
tr.print_button_texts(window_name="GangRoomWindow")
```

## 通用 Tab 切换

HudWindow 用 `switch_hud_tab()`；其他含 Tab 结构的窗口（活动、宗门、背包等）
用 `switch_tab_by_text()` 通过显示文本切换。

```python
# 基础切换
ui.switch_tab_by_text("心法道途", window_name="OperateActivityWindow")

# 切换后验证内容加载（推荐）
ui.switch_tab_and_verify(
    "境界奖励",
    window_name="OperateActivityWindow",
    verify_node="title_tex",
    verify_text="累计进行",      # 包含匹配
    verify_timeout=5.0,
)
```

> **详细说明** 请参考 [guides/text-reading.md](text-reading.md)，包含文本读取、进度条、数值、
> 正则断言、等待机制的完整指南。

## allow_multiple 窗口操作

部分窗口可同时存在多个实例（如 `ItemInfoSimpleWindow`、`EquipmentInfoWindow`）：

```python
# 列出所有显示中的实例
instances = ui.get_shown_instances("ItemInfoSimpleWindow")
# [{"name": "ItemInfoSimpleWindow", "instanceID": -12345}, ...]

# 用 instance_id 精确操作某个实例
tr.get_text("text_name", instance_id=instances[0]["instanceID"])

# 一次关闭所有物品弹窗（8 种 ItemInfoBase 子类）
ui.close_all_item_info()
```

## 可靠的子树搜索

`hierarchy.search(parent=X)` 在多窗口场景下可能返回错误结果。
使用 `find_in_children` 通过 Lua 递归搜索：

```python
result = ui.find_in_children(parent_id=window_id, name="btn_close", max_depth=5)
if result:
    ui.lua_click(result["instanceID"])
```

## 注意事项

- **instanceID 是临时的** — 每次游戏重启后会变化，应通过搜索动态获取
- **active 状态** — inactive 的按钮无法点击，find_and_click 会自动检查
- **操作间隔** — 连续操作间建议 0.5-1 秒等待，给 UI 动画留时间
- **窗口互斥** — 某些全屏窗口会互斥，打开一个可能隐藏另一个
- **搜索范围** — 使用 `parent` 参数限定搜索范围可避免同名按钮冲突
- **同名按钮** — 同名按钮用 `find_and_click_by_text` 通过 TMP 文本区分
- **按钮点击** — 优先用 `lua_click()` 或 `find_and_click_by_text()`，`hierarchy.click()` 对部分按钮无效
- **allow_multiple** — 操作 `ItemInfoSimpleWindow` 等多实例窗口时，用 `instance_id` 精确定位

