#!/usr/bin/env bash
# 把平台与 Langfuse 清空成「干净环境」（教学/演示用）。
#
#   bash tools/reset-data.sh            # 备份后清理
#   DRY_RUN=1 bash tools/reset-data.sh  # 只打印将要做什么
#
# 删什么：
#   - 平台库里的业务数据：评测批次与用例结果、Web-UI/Unity/接口自动化脚本与执行记录、
#     会话与消息、登录令牌、附件、代码图谱、项目/工作区、配置表
#   - 运行时产物目录：workspace/default/web-ui-auto/runs（截图/录像/报告）、eval-runs（实时进度现场）
#   - Langfuse 的内容：traces / observations / scores / events / dataset run items（ClickHouse）
#     与 datasets / dataset_items / dataset_runs（Postgres）
#
# 保留什么（否则环境"干净"到没法用）：
#   - 平台账号（users）与设置（settings_kv：模型、judge、Langfuse 配置）——这些是接线，不是数据
#   - Langfuse 的项目与 API 密钥（清了就得重新建项目换密钥，测评上报会断）
#   - 仓库里的东西：datasets/*.yaml、技能（src/app/skills）、记忆（workspace/default/memory）、
#     测试用例素材（workspace/default/cases）——它们不是运行期数据
#
# 备份落在 $BACKUP_ROOT（默认 ~/smart-test-backups/<时间戳>/）：两个 SQLite 库、Langfuse 的
# pg_dump 与 ClickHouse 导出、以及被删目录的**文件清单与文本产物**（截图/录像这类大二进制
# 只记清单，不复制——真要留就不会来清空）。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
DRY_RUN="${DRY_RUN:-0}"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/smart-test-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_ROOT/$STAMP"

# 平台库里的业务表（保留 users / settings_kv；表不存在就跳过）
BUSINESS_TABLES=(
  eval_case_results eval_batches
  web_ui_script_runs web_ui_scripts
  unity_script_runs unity_scripts
  api_script_runs api_scripts
  thread_messages thread_infos
  auth_tokens attachments
  codebase_index_runs codebase_repos
  workspaces projects configurations api_doc_imports
)
# 运行时产物目录（相对仓库根）
RUNTIME_DIRS=(workspace/default/web-ui-auto/runs workspace/default/eval-runs)
# Langfuse ClickHouse 表（schema_migrations 保留）
CH_TABLES=(traces observations scores events_full events_core dataset_run_items_rmt blob_storage_file_log observations_batch_staging)

run() { if [ "$DRY_RUN" = "1" ]; then echo "  [dry-run] $*"; else eval "$@"; fi }

echo "== 清空前盘点 =="
echo "平台库: $(ls -la docker-data/smart_test_platform.db 2>/dev/null | awk '{print $5" bytes"}')"
for d in "${RUNTIME_DIRS[@]}"; do
  [ -d "$d" ] && echo "$d: $(find "$d" -type f | wc -l | tr -d ' ') 个文件, $(du -sh "$d" | cut -f1)"
done
echo "Langfuse: $(docker exec eval-platform-lf-clickhouse-1 clickhouse-client --query \
  "select sum(rows) from system.parts where active and database='default' and table in ('traces','observations','scores')" 2>/dev/null) 条 trace/observation/score 行"

if [ "$DRY_RUN" = "1" ]; then
  echo; echo "== 将要执行 =="
  run "mkdir -p $OUT"
  run "cp docker-data/smart_test_platform.db $OUT/"
  run "docker exec eval-platform-lf-postgres-1 pg_dump -U postgres -d postgres > $OUT/langfuse-postgres.sql"
  run "docker exec eval-platform-lf-clickhouse-1 clickhouse-client --query 'SELECT * FROM traces FORMAT JSONEachRow' > $OUT/langfuse-traces.ndjson"
  run "rm -rf ${RUNTIME_DIRS[*]}"
  exit 0
fi

echo; echo "== 1/4 备份 → $OUT =="
mkdir -p "$OUT"
[ -f docker-data/smart_test_platform.db ] && cp docker-data/smart_test_platform.db "$OUT/platform-docker.db"
[ -f smart_test_platform.db ] && cp smart_test_platform.db "$OUT/platform-host.db"
docker exec eval-platform-lf-postgres-1 pg_dump -U postgres -d postgres > "$OUT/langfuse-postgres.sql" 2>/dev/null \
  && echo "  langfuse Postgres → langfuse-postgres.sql ($(wc -c < "$OUT/langfuse-postgres.sql" | tr -d ' ') bytes)"
for t in traces observations scores dataset_run_items_rmt; do
  docker exec eval-platform-lf-clickhouse-1 clickhouse-client --query "SELECT * FROM $t FORMAT JSONEachRow" \
    > "$OUT/langfuse-$t.ndjson" 2>/dev/null || true
done
echo "  langfuse ClickHouse → langfuse-*.ndjson ($(cat "$OUT"/langfuse-*.ndjson | wc -l | tr -d ' ') 行)"
for d in "${RUNTIME_DIRS[@]}"; do
  [ -d "$d" ] || continue
  name="$(echo "$d" | tr '/' '_')"
  find "$d" -type f -exec ls -l {} \; | awk '{print $5"\t"$NF}' > "$OUT/$name.filelist.tsv" 2>/dev/null || true
  mkdir -p "$OUT/$name-text"
  # 小体积文本产物（报告/日志/实时现场）留一份，便于对照；截图/录像只进清单
  find "$d" -type f \( -name 'report.json' -o -name 'progress.ndjson' -o -name 'stdout.log' \
       -o -name 'live.ndjson' -o -name 'live.log' \) -size -2M | while read -r f; do
    mkdir -p "$OUT/$name-text/$(dirname "$f")"
    cp "$f" "$OUT/$name-text/$f"
  done
  echo "  $d → $name.filelist.tsv + $name-text/"
done

echo; echo "== 2/4 清空平台业务表（保留 users / settings_kv）=="
# 直接用本机 venv 跑：库就是仓库里的 docker-data/smart_test_platform.db 这个文件，
# 两种部署模式共用同一份，不必借道容器（2026-09 起 fastapi 也默认跑在本机）。
.venv/bin/python - <<PY
import asyncio
from sqlalchemy import text
from src.app.db.database import engine
TABLES = "${BUSINESS_TABLES[*]}".split()

async def main():
    async with engine.begin() as conn:
        names = {r[0] for r in (await conn.execute(text("select name from sqlite_master where type='table'"))).all()}
        for table in TABLES:
            if table not in names:
                print(f"  跳过 {table}（表不存在）"); continue
            before = (await conn.execute(text(f'select count(*) from "{table}"'))).scalar()
            if before:
                await conn.execute(text(f'delete from "{table}"'))
                print(f"  {table}: 删除 {before} 行")
    kept = {}
    async with engine.connect() as conn:
        for table in ("users", "settings_kv"):
            kept[table] = (await conn.execute(text(f'select count(*) from "{table}"'))).scalar()
    print("  保留:", kept)
asyncio.run(main())
PY

echo; echo "== 3/4 清空运行时产物目录 =="
for d in "${RUNTIME_DIRS[@]}"; do
  # 只删**目录里的内容**，绝不删目录本身：`web-ui-auto/runs` 是直接 bind-mount 进
  # playwright 容器的（容器内 /work/runs）。删掉再重建目录会换掉 inode，容器的挂载
  # 就指向了那个已删除的旧 inode——之后 runner 在容器里能看到一个空目录，写文件却
  # 报 "Directory nonexistent"，所有执行请求都会卡死（实测踩过）。
  if [ -d "$d" ]; then
    count=$(find "$d" -mindepth 1 | wc -l | tr -d ' ')
    echo "  清空 $d 的内容（保留目录本身，避免解开容器挂载）: $count 项"
    find "$d" -mindepth 1 -delete
  fi
done

echo; echo "== 4/4 清空 Langfuse 内容（保留项目与密钥）=="
for t in "${CH_TABLES[@]}"; do
  docker exec eval-platform-lf-clickhouse-1 clickhouse-client --query "TRUNCATE TABLE IF EXISTS $t" 2>/dev/null \
    && echo "  ClickHouse truncate $t" || echo "  跳过 $t"
done
docker exec eval-platform-lf-postgres-1 psql -U postgres -d postgres -q -c "
  delete from dataset_items;
  delete from dataset_runs;
  delete from datasets;
" && echo "  Postgres: datasets / dataset_items / dataset_runs 已清空"

echo; echo "== 清空后 =="
.venv/bin/python - <<'PY'
import asyncio
from sqlalchemy import text
from src.app.db.database import engine
async def main():
    async with engine.connect() as conn:
        for table in ("eval_batches", "eval_case_results", "web_ui_scripts", "web_ui_script_runs",
                      "thread_infos", "auth_tokens", "users", "settings_kv"):
            n = (await conn.execute(text(f'select count(*) from "{table}"'))).scalar()
            print(f"  {table}: {n}")
asyncio.run(main())
PY
docker exec eval-platform-lf-clickhouse-1 clickhouse-client --query \
  "select '  langfuse traces='||count(*) from traces union all select '  langfuse scores='||count(*) from scores" 2>/dev/null
docker exec eval-platform-lf-postgres-1 psql -U postgres -d postgres -t -c \
  "select '  langfuse datasets='||count(*) from datasets union all select '  langfuse projects='||count(*) from projects" 2>/dev/null
echo; echo "备份：$OUT"
