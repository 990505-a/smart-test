# Screenshot Guide

截取 Unity Game 窗口画面用于验证 UI 状态。

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
from ui import UI

client = UnityClient()
ui = UI(client)
```

## 截图方式

### 通过 ui.py（推荐）

```python
ui.screenshot("test_result.png")
```

### 通过核心层

```python
client.screenshot.capture("test_result.png")
```

### 通过命令行

```bash
python <SKILL_DIR>/scripts/explore_ui.py --screenshot current.png
```

## 使用场景

### 操作后验证

每个关键操作后截图，用于人工复核或自动比对：

```python
ui.find_and_click("btn_equip", parent=window_id)
ui.screenshot("after_click_equip.png")
```

### 多步骤记录

测试流程中每个步骤都留档：

```python
import os
SCREENSHOT_DIR = "D:/vibetest/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

steps = [
    ("打开角色面板", lambda: ui.open_window("CharacterWindow")),
    ("点击装备按钮", lambda: ui.find_and_click("btn_equip", parent=wnd_id)),
    ("关闭面板",     lambda: ui.close_window("CharacterWindow")),
]
for i, (desc, action) in enumerate(steps):
    action()
    ui.screenshot(f"{SCREENSHOT_DIR}/step{i}_{desc}.png")
```

### 带时间戳

```python
import time
SCREENSHOT_DIR = "D:/vibetest/screenshots"
filename = f"{SCREENSHOT_DIR}/{time.strftime('%Y%m%d_%H%M%S')}.png"
ui.screenshot(filename)
```

## 注意事项

- 需要场景中存在至少一个 Camera，优先使用 Camera.main
- 截图分辨率与相机像素尺寸一致
- 截图超时时间为 5 秒
- 截图返回 PNG 二进制数据，自动保存为文件
- 无可用相机时抛出 `UnityAPIError("no camera found or game view is empty")`

