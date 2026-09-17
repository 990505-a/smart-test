#!/usr/bin/env bash
# 本机（非容器）启动 playwright runner，供后端 PLAYWRIGHT_RUNNER_URL 调用。
#
#   ./tools/playwright-runner/start-local.sh
#
# 容器部署时不需要这个脚本 —— docker-compose 的 `playwright` 服务用的是
# 官方 playwright 镜像（浏览器与系统依赖预装），见 Dockerfile.playwright。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

if [ ! -d "$HERE/node_modules" ]; then
  echo "==> 安装依赖（首次）"
  (cd "$HERE" && npm install --registry=https://registry.npmmirror.com --no-audit --no-fund)
fi

if ! ls "${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}" >/dev/null 2>&1; then
  echo "==> 安装 chromium（首次，约 80MB，走 npmmirror 二进制镜像）"
  (cd "$HERE" && PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright \
     ./node_modules/.bin/playwright install chromium)
fi

export PW_HOME="$HERE"
export RUNS_ROOT="${RUNS_ROOT:-$ROOT/workspace/default/web-ui-auto/runs}"
export PORT="${PORT:-5015}"
mkdir -p "$RUNS_ROOT"

echo "==> playwright runner on :$PORT  (runs=$RUNS_ROOT)"
exec node "$HERE/server.mjs"
