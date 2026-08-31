# Lua Execution Guide

在 Unity 运行时执行 Lua 代码、查询游戏数据。

## 前提条件

游戏必须处于 Play Mode（`client.editor.get_state()["isPlaying"] == True`），否则返回 `"game is not running"` 错误。

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
client = UnityClient()
```

## 三种执行模式

### exec — 异步执行（协程模式）

代码自动包裹在 `dispatch_co(function() ... end)` 中。适用于需要异步加载、yield、网络请求的操作。

```python
# 打开窗口（涉及异步资源加载）
client.lua.exec("UI.open('CharacterWindow')")

# 关闭窗口
client.lua.exec("UI.close('CharacterWindow')")
```

### exec_sync — 同步执行

不包裹协程，适用于简单的即时操作和查询。

```python
# 简单打印
client.lua.exec_sync('print("hello")')

# 批量查询窗口状态
code = """local r = ''
for k,v in pairs(UI._windows) do
    local st = 'hidden'
    if v.is_show and v:is_show() then st = 'shown' end
    r = r .. k .. '=' .. st .. ','
end
print(r)"""
output = client.lua.exec_sync(code)
```

### eval — 求值表达式

获取变量或表达式的值，内部包裹为 `print(pts(<expression>))`。

```python
level = client.lua.eval("HeroD.data.level")       # "85"
is_shown = client.lua.eval("UI.is_wnd_show('HudWindow')")  # "true"
```

## 选择指南


| 场景                       | 推荐          |
| ------------------------ | ----------- |
| 打开/关闭窗口（`UI.open/close`） | `exec`      |
| 发送网络请求、涉及 yield          | `exec`      |
| 读取变量值                    | `eval`      |
| 简单打印/计算                  | `exec_sync` |
| 批量状态查询                   | `exec_sync` |


## 更便捷的方式

对于常见的窗口操作和状态查询，建议使用 `python/ui.py` 和 `python/inspector.py` 的封装，避免手写 Lua 代码：

```python
from ui import UI
from inspector import Inspector

ui = UI(client)
ins = Inspector(client)

# 等价于 client.lua.exec("UI.open('CharacterWindow')")
ui.open_window("CharacterWindow")

# 等价于 client.lua.eval("UI.is_wnd_show('CharacterWindow')") == "true"
ui.is_window_shown("CharacterWindow")

# 批量查询所有窗口状态
ins.get_shown_windows()
```

## 发送多行 Lua 代码

复杂的 Lua 代码可以用 Python 多行字符串直接发送：

```python
code = """
local wnd = UI.query_shown_window("HudWindow")
if wnd then
    print("HudWindow is shown, id=" .. tostring(wnd._instance_id))
else
    print("HudWindow not found")
end
"""
result = client.lua.exec_sync(code)
```

## 注意事项

- 所有方法超时时间为 10 秒，长时间操作可能超时
- Lua 中的 `print()` 输出会作为返回值的 `output` 字段返回
- 错误信息包含 Lua 堆栈跟踪，可用于定位问题
- 使用 `exec` 时，代码在协程中执行，其中的错误不一定立即返回

