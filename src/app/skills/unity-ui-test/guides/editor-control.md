# Editor Control Guide

控制 Unity 编辑器的播放状态。

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
client = UnityClient()
```

## 操作前检查

执行任何编辑器操作前，先查询当前状态：

```python
state = client.editor.get_state()
# {"isPlaying": True, "isPaused": False}
```

根据当前状态决定下一步操作，避免重复切换。

## 可用操作

### 启动 Play Mode

```python
client.editor.play()  # 返回 "playing"
```

启动后需等待游戏初始化完成再执行后续操作：

```python
import time
client.editor.play()
time.sleep(5)  # 等待场景和 UI 加载
```

也可使用现有脚本（路径相对于 SKILL_DIR）：

```bash
python <SKILL_DIR>/scripts/enter_game.py --wait 5
```

### 停止 Play Mode

```python
client.editor.stop()  # 返回 "stopped"
```

### 暂停/恢复切换

```python
client.editor.pause()  # 返回 "paused" 或 "resumed"
```

这是切换操作——正在运行则暂停，已暂停则恢复。

### 查询状态

```python
state = client.editor.get_state()
# {"isPlaying": True, "isPaused": False}
```

### 检查服务器可用性

```python
if client.is_available():
    print("服务器就绪")
else:
    print("服务器不可用，请启动 Unity 编辑器")
```

## 等待服务器就绪

如果 Unity 编辑器尚未完全启动，可使用等待脚本：

```bash
python <SKILL_DIR>/scripts/wait_and_play.py --timeout 60
```

## 注意事项

- Play Mode 切换后不要立即执行 Lua 代码，需等待初始化完成（建议 3-5 秒）
- Lua 执行（exec/exec_sync/eval）和按钮点击（click）要求游戏处于 Play Mode
- 截图接口在非 Play Mode 下也可使用

