"""
启动 Play Mode 并等待主界面加载。

用法: python scripts/enter_game.py [--wait 5] [--host 127.0.0.1] [--port 16666]
"""
import argparse
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from unity_api import UnityClient


def main():
    parser = argparse.ArgumentParser(description="启动 Play Mode 并等待加载")
    parser.add_argument("--wait", type=float, default=5, help="启动后等待秒数")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", type=int, default=16666, help="服务器端口")
    args = parser.parse_args()

    client = UnityClient(host=args.host, port=args.port)

    if not client.is_available():
        print("错误：Unity 服务器不可用，请先启动编辑器和服务器", file=sys.stderr)
        sys.exit(1)

    state = client.editor.get_state()
    if state.get("isPlaying"):
        print("已在 Play Mode 中")
    else:
        print("启动 Play Mode...")
        client.editor.play()
        print(f"等待 {args.wait} 秒让游戏加载...")
        time.sleep(args.wait)
        print("就绪")


if __name__ == "__main__":
    main()
