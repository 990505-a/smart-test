"""
探索当前游戏 UI 状态。

打印当前窗口列表、指定窗口的按钮清单、UI 节点树等信息，
用于开发测试脚本前的信息收集。

用法:
    python scripts/explore_ui.py                          # 打印所有窗口状态
    python scripts/explore_ui.py --window CharacterWindow  # 检查指定窗口
    python scripts/explore_ui.py --tree -97534 --depth 2   # 打印节点树
    python scripts/explore_ui.py --buttons --parent -146422 # 打印某节点下的按钮
    python scripts/explore_ui.py --hero                    # 打印角色信息
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from unity_api import UnityClient
from inspector import Inspector


def main():
    parser = argparse.ArgumentParser(description="探索游戏 UI 状态")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=16666)
    parser.add_argument("--window", type=str, help="检查指定窗口（名称）")
    parser.add_argument("--tree", type=int, metavar="ID", help="打印节点树（instanceID）")
    parser.add_argument("--depth", type=int, default=3, help="节点树深度")
    parser.add_argument("--buttons", action="store_true", help="打印按钮清单")
    parser.add_argument("--parent", type=int, help="限定搜索/树的父节点")
    parser.add_argument("--active-only", action="store_true", help="只显示 active 节点")
    parser.add_argument("--hero", action="store_true", help="打印角色信息")
    parser.add_argument("--screenshot", type=str, metavar="PATH", help="截图保存路径")
    args = parser.parse_args()

    client = UnityClient(host=args.host, port=args.port)
    if not client.is_available():
        print("ERROR: Unity 服务器不可用")
        sys.exit(1)

    ins = Inspector(client)
    did_something = False

    if args.screenshot:
        client.screenshot.capture(args.screenshot)
        print(f"截图已保存: {args.screenshot}")
        did_something = True

    if args.hero:
        ins.print_hero_info()
        print()
        did_something = True

    if args.window:
        ins.inspect_window(args.window, button_only=args.buttons)
        did_something = True

    if args.tree is not None:
        print(f"\n=== 节点树 (root={args.tree}, depth={args.depth}) ===")
        ins.print_tree(args.tree, depth=args.depth, active_only=args.active_only)
        did_something = True

    if args.buttons and not args.window:
        ins.print_buttons(parent=args.parent, active_only=args.active_only)
        did_something = True

    if not did_something:
        ins.print_shown_windows()
        print()
        state = client.editor.get_state()
        print(f"编辑器状态: isPlaying={state.get('isPlaying')}, isPaused={state.get('isPaused')}")


if __name__ == "__main__":
    main()
