# Inspection Guide

探索 UI 结构、查看窗口列表、打印按钮清单、检查组件和游戏数据。

用于编写测试脚本前的信息收集，以及测试过程中的状态验证和问题排查。

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
from inspector import Inspector

client = UnityClient()
ins = Inspector(client)
```

## 查看窗口状态

### 获取所有窗口

```python
windows = ins.get_all_windows()
# {"HudWindow": "shown", "CharacterWindow": "hidden", ...}
```

### 只获取显示中/隐藏的窗口

```python
shown = ins.get_shown_windows()   # ["HudWindow", "ChatWindow", ...]
hidden = ins.get_hidden_windows() # ["HudMoneyWindow", ...]
```

### 获取显示中窗口的详细信息（含 instanceID）

```python
details = ins.get_shown_windows_detail()
# [{"name": "HudWindow", "instanceID": -52136}, ...]

# 用于追踪 allow_multiple 窗口的多个实例
for d in details:
    print(f"{d['name']} (id={d['instanceID']})")
```

### 格式化打印

```python
ins.print_shown_windows()
```

输出：

```
=== Windows (8 shown / 2 hidden) ===
  [shown]  ChatWindow
  [shown]  HudWindow
  [hidden] HudMoneyWindow
```

## 检查窗口结构

### 一键检查（最常用）

打印窗口的节点树和按钮清单：

```python
ins.inspect_window("CharacterWindow")
```

输出：

```
============================================================
Window: CharacterWindow (id=-112430, active=True)
============================================================

--- Tree ---
|-- adapter (-112440)
|   |-- go_character (-112460)
|   `-- go_equip (-112500)
`-- go_bottom (-112600)

--- Buttons ---
=== Buttons (12 active / 0 inactive) ===
name                                  instanceID  active  scene
---------------------------------------------------------------------------
btn_equip                                -106158       Y  main
btn_shentong                             -110296       Y  main
```

### 只看按钮

```python
ins.inspect_window("CharacterWindow", button_only=True)
```

## 打印节点树

**推荐使用 `dump_tree`**（单次 Lua 调用，返回格式化字符串）：

```python
# 单次 Lua 调用序列化子树（约 150-300ms，不随节点数线性增长）
tree = ins.dump_tree(-146422, depth=3, active_only=True)
print(tree)
```

也可以用 `print_tree`（底层已自动使用 `dump_tree`）：

```python
ins.print_tree(-146422, depth=2)
ins.print_tree(-146422, depth=3, active_only=True)
```

## 打印按钮清单

```python
# 某窗口下所有按钮
ins.print_buttons(parent=-146422)

# 只看 active 的
ins.print_buttons(parent=-146422, active_only=True)
```

## 查看组件

```python
ins.print_components(-146498)
```

输出：

```
=== Components (id=-146498) ===
  [-] RectTransform (UnityEngine.RectTransform)
  [Y] Button (UnityEngine.UI.Button)
  [Y] UIStateController (UGUIJszx.UIStateController)
```

## 查询游戏数据

```python
# 求值任意 Lua 表达式
level = ins.eval_game_var("HeroD.data.level")

# 打印角色基础信息
ins.print_hero_info()
```

## 命令行方式

也可以通过 `scripts/explore_ui.py` 脚本直接使用（路径相对于 SKILL_DIR）：

```bash
# 查看所有窗口
python <SKILL_DIR>/scripts/explore_ui.py

# 检查指定窗口
python <SKILL_DIR>/scripts/explore_ui.py --window CharacterWindow

# 打印节点树
python <SKILL_DIR>/scripts/explore_ui.py --tree -146484 --depth 2

# 打印按钮
python <SKILL_DIR>/scripts/explore_ui.py --buttons --parent -146422

# 角色信息
python <SKILL_DIR>/scripts/explore_ui.py --hero

# 截图
python <SKILL_DIR>/scripts/explore_ui.py --screenshot current.png
```

## 典型工作流

### 1. 开发新测试前的探索

```python
# 先看有哪些窗口
ins.print_shown_windows()

# 检查目标窗口
ins.inspect_window("GangRoomWindow")

# 记下按钮名称和 ID → 编写 ui.find_and_click() 调用
```

### 2. 测试中验证状态

```python
from ui import UI
ui = UI(client)

ui.switch_hud_tab("character")

# 用 Inspector 验证
shown = ins.get_shown_windows()
assert "CharacterWindow" in shown
```

### 3. 排查测试失败

```python
# 截图看当前画面
client.screenshot.capture("debug.png")

# 查看窗口状态
ins.print_shown_windows()

# 按钮存在吗？是 active 吗？
ins.print_buttons(parent=window_id, active_only=False)
```

## 注意事项

- `dump_tree` / `print_tree` 使用单次 Lua 调用序列化整棵子树，性能不受节点数影响（约 150-300ms）
- `get_all_windows` 使用 `UI.get_all_windows()` 框架 API，正确处理 `allow_multiple` 窗口
- `get_shown_windows_detail` 返回含 instanceID 的完整信息，适用于精确追踪多实例窗口
- `find_window_node` 通过搜索 hierarchy 实现，搜索的是 GameObject 名称（含 "(Clone)" 后缀）
- 需要游戏在 Play Mode 才能执行 Lua 相关操作

