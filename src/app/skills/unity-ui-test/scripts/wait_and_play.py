"""
等待 Unity 服务器就绪后进入 Play Mode。

用法: python scripts/wait_and_play.py [--timeout 30] [--host 127.0.0.1] [--port 16666]
"""
import argparse
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))
from unity_api import UnityClient


def main():
    parser = argparse.ArgumentParser(description="等待服务器就绪后启动 Play Mode")
    parser.add_argument("--timeout", type=int, default=30, help="最大等待秒数")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", type=int, default=16666, help="服务器端口")
    args = parser.parse_args()

    client = UnityClient(host=args.host, port=args.port)
    start = time.time()

    print(f"等待 Unity 服务器 ({args.host}:{args.port})...")
    while time.time() - start < args.timeout:
        if client.is_available():
            print("服务器已就绪，启动 Play Mode...")
            client.editor.play()
            print("Play Mode 已启动")
            return
        time.sleep(1)

    print(f"超时：{args.timeout} 秒内未连接到服务器", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
