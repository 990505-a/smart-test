# Scripts Guide

运行已有测试脚本或编写新脚本。

所有脚本位于 `scripts/` 目录下（相对于 SKILL_DIR），支持 `--host` 和 `--port` 参数。

## 已有脚本

### enter_game.py — 启动游戏

```bash
python <SKILL_DIR>/scripts/enter_game.py
python <SKILL_DIR>/scripts/enter_game.py --wait 10
```

### wait_and_play.py — 等待服务器就绪

```bash
python <SKILL_DIR>/scripts/wait_and_play.py --timeout 60
```

### explore_ui.py — 探索 UI 状态

```bash
# 查看所有窗口
python <SKILL_DIR>/scripts/explore_ui.py

# 检查指定窗口
python <SKILL_DIR>/scripts/explore_ui.py --window CharacterWindow

# 打印节点树
python <SKILL_DIR>/scripts/explore_ui.py --tree -146484 --depth 2

# 打印按钮
python <SKILL_DIR>/scripts/explore_ui.py --buttons --parent -146422 --active-only

# 角色信息 + 截图
python <SKILL_DIR>/scripts/explore_ui.py --hero --screenshot hero.png
```

### test_hud_tabs.py — 测试 Tab 切换

```bash
python <SKILL_DIR>/scripts/test_hud_tabs.py --screenshot-dir D:/vibetest/screenshots
```

依次点击底部导航栏每个 Tab，验证对应窗口是否打开，截图记录。退出码 0 = 全部通过，1 = 有失败。

## 编写新脚本

在 `scripts/` 目录下新建 `.py` 文件，遵循以下模板：

```python
"""
脚本简介。

用法: python scripts/my_test.py [--host 127.0.0.1] [--port 16666]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from unity_api import UnityClient, UnityAPIError
from ui import UI
from inspector import Inspector


def main():
    parser = argparse.ArgumentParser(description="脚本说明")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=16666)
    args = parser.parse_args()

    client = UnityClient(host=args.host, port=args.port)
    if not client.is_available():
        print("ERROR: Unity 服务器不可用")
        sys.exit(1)

    ui = UI(client)
    ins = Inspector(client)

    # === 编写测试逻辑 ===

    # 打开窗口
    ui.open_window("CharacterWindow")

    # 验证
    assert ui.is_window_shown("CharacterWindow"), "窗口未打开"

    # 点击按钮
    wnd = ui.find_node("CharacterWindow")
    ui.find_and_click("btn_equip", parent=wnd["instanceID"])

    # 截图
    ui.screenshot("D:/vibetest/screenshots/test_result.png")

    # 清理
    ui.close_window("CharacterWindow")

    print("测试通过")


if __name__ == "__main__":
    main()
```

关键点：

1. **路径注入** — `sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))` 使用相对路径导入 python/ 模块
2. **连接检查** — 开头 `client.is_available()` 确认服务器
3. **统一参数** — `--host` / `--port`
4. **退出码** — 成功 0，失败 1
5. **三层都可用** — `client`（核心）、`ui`（操控）、`ins`（检查）按需组合

