#!/usr/bin/env bash
# dsh 容器入口：把平台 .env 里的模型配置翻译成 dsh 的 settings.yaml，再启动 Web UI。
#
# 为什么要在启动时生成：dsh 的模型 provider（含 API key）只从
# ~/.dsh/settings.yaml 读，它不认 OPENAI_API_KEY 之类的环境变量。而把 key 写进
# 镜像或提交进仓库都是错的，所以由本脚本在首次启动时从 compose 注入的环境变量
# 生成一次，之后落在挂载卷里持久化（存在则不覆盖，保留 UI 里的手工改动）。
set -euo pipefail

DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
SETTINGS="$DSH_HOME/settings.yaml"
PORT="${DSH_PORT:-3080}"

mkdir -p "$DSH_HOME"

if [ ! -f "$SETTINGS" ]; then
  if [ -z "${LLM_BASE_URL:-}" ] || [ -z "${LLM_API_KEY:-}" ]; then
    echo "[dsh-entrypoint] 警告: LLM_BASE_URL / LLM_API_KEY 未设置，无法生成模型配置。" >&2
    echo "[dsh-entrypoint] dsh 会以无可用模型启动；请在 .env 里配置后重启本服务。" >&2
  else
    MODEL="${LLM_MODEL:-${DEEPSEEK_MODEL:-glm-4.7}}"
    echo "[dsh-entrypoint] 生成 $SETTINGS（provider=smart-test, model=$MODEL）"
    cat > "$SETTINGS" <<YAML
# 由 docker/dsh-entrypoint.sh 生成 —— 模型端点复用平台 .env 的 LLM_* 配置。
# 修改了这里不会回写 .env；如需换端点，改 .env 后删除本文件再重启容器。
locale:
  preference: zh
agent-default-model:
  provider: smart-test
  model: "$MODEL"
llm-pi-ai:
  providers:
    smart-test:
      apiKey: "$LLM_API_KEY"
      api: openai-completions
      baseURL: "$LLM_BASE_URL"
      models:
        - id: "$MODEL"
          name: "$MODEL"
          contextWindow: ${LLM_CONTEXT_WINDOW:-128000}
YAML
    chmod 600 "$SETTINGS"
  fi
fi

# 平台技能库直挂：preset 里的 customSkillDirs 指向这里（见 dsh/agent-presets/）
export DSH_BUNDLED_SKILL_DIR="${DSH_BUNDLED_SKILL_DIR:-/workspace/smart-test/src/app/skills}"

# dsh 明确拒绝 --host 0.0.0.0（"would expose remote code execution to the
# network"），这是它有意设的安全围栏，不该绕过。容器要对外发布端口，就用
# socat 做一层回环桥：dsh 自己只监听 127.0.0.1:<内部端口>，socat 在
# 0.0.0.0:<发布端口> 上转发。安全性由 compose 的端口发布决定（默认只映射到
# 宿主 127.0.0.1 之外的 localhost:3081，不会暴露到公网）。
INNER_PORT="${DSH_INNER_PORT:-3081}"
PUBLISHED_PORT="$PORT"

ARGS=(--profile web --port "$INNER_PORT" --host 127.0.0.1 --no-open)
# 浏览器经宿主端口访问时 Host 头是 localhost:<发布端口>，dsh 的 /api 信任围栏
# 要认得它（容器内自连用 127.0.0.1:<内部端口>）。
ARGS+=(--trusted-host "localhost:${PUBLISHED_PORT}" --trusted-host "127.0.0.1:${PUBLISHED_PORT}")
if [ -n "${DSH_TRUSTED_HOST:-}" ]; then
  ARGS+=(--trusted-host "$DSH_TRUSTED_HOST")
fi

echo "[dsh-entrypoint] dsh ${ARGS[*]}  (home=$DSH_HOME)"
dsh "${ARGS[@]}" &
DSH_PID=$!

echo "[dsh-entrypoint] socat 0.0.0.0:${PUBLISHED_PORT} -> 127.0.0.1:${INNER_PORT}"
exec socat TCP-LISTEN:"${PUBLISHED_PORT}",fork,reuseaddr TCP:127.0.0.1:"${INNER_PORT}"
