"""
测试 HudWindow 底部导航栏 Tab 切换。

验证点击每个 Tab 后对应窗口是否正确打开/关闭。

用法: python scripts/test_hud_tabs.py [--host 127.0.0.1] [--port 16666] [--screenshot-dir ./screenshots]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from unity_api import UnityClient, UnityAPIError
from ui import UI
from inspector import Inspector


TABS_TO_TEST = [
    ("character", "CharacterWindow"),
    ("gongfa",    "GongfaRoomWindow"),
    ("house",     "HouseRoomWindow"),
    ("clan",      "ClanRoomWindow"),
    ("gang",      "GangRoomWindow"),
]


def run_test(client: UnityClient, screenshot_dir: str):
    ui = UI(client)
    ins = Inspector(client)

    os.makedirs(screenshot_dir, exist_ok=True)

    state = client.editor.get_state()
    if not state.get("isPlaying"):
        print("ERROR: 游戏未运行，请先进入 Play Mode")
        sys.exit(1)

    print("=== 测试开始：HudWindow Tab 切换 ===\n")
    print("当前显示窗口:")
    for w in ins.get_shown_windows():
        print(f"  - {w}")
    print()

    hud_node = ins.find_window_node("HudWindow")
    if not hud_node:
        print("ERROR: HudWindow 未找到")
        sys.exit(1)

    layout = ui.find_node("layout", parent=hud_node["instanceID"])
    if not layout:
        print("ERROR: HudWindow/layout 未找到")
        sys.exit(1)

    layout_id = layout["instanceID"]
    print(f"HudWindow layout id: {layout_id}\n")

    passed = 0
    failed = 0

    for tab_name, expected_window in TABS_TO_TEST:
        print(f"--- Tab: {tab_name} → 期望窗口: {expected_window} ---")

        try:
            ui.find_and_click(tab_name, parent=layout_id, wait=2.0)
        except UnityAPIError as e:
            print(f"  FAIL: 按钮点击失败 - {e}")
            failed += 1
            continue

        shown = ui.is_window_shown(expected_window)
        if not shown:
            shown = ui.wait_for_window(expected_window, timeout=3.0)

        screenshot_path = os.path.join(screenshot_dir, f"tab_{tab_name}.png")
        try:
            ui.screenshot(screenshot_path)
            print(f"  截图: {screenshot_path}")
        except Exception:
            print(f"  截图失败")

        if shown:
            print(f"  PASS: {expected_window} 已显示")
            passed += 1
        else:
            print(f"  FAIL: {expected_window} 未显示")
            failed += 1

        print()

    print(f"=== 测试完成: {passed} passed / {failed} failed ===")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="测试 HudWindow Tab 切换")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=16666)
    parser.add_argument("--screenshot-dir", default="D:/vibetest/screenshots")
    args = parser.parse_args()

    client = UnityClient(host=args.host, port=args.port)
    if not client.is_available():
        print("ERROR: Unity 服务器不可用")
        sys.exit(1)

    success = run_test(client, args.screenshot_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
