# Docker 部署说明

本文件说明如何用 Docker 运行智能测试平台。容器化方案与仓库原有的
`launcher.py` 服务控制台**一一对应**，只是把「宿主进程」换成了「容器」。

## 快速开始

```bash
cd ~/Documents/smart-test
docker compose up -d --build      # 首次构建 + 启动（约 5-8 分钟）
docker compose ps                 # 四个服务应为 (healthy)

# 可选工作台（默认不启动）
docker compose --profile dsh up -d --build dsh     # DeepSeek Harness
docker compose --profile rag up -d lightrag        # 平台内 LightRAG
```

启动完成后：

| 入口 | 地址 |
| --- | --- |
| 平台界面 | http://localhost:5013 |
| 平台 API 文档 | http://localhost:5012/docs |
| LangGraph Studio | http://localhost:5011/ui |
| LangGraph 健康检查 | http://localhost:5011/ok |
| 平台 API 健康检查 | http://localhost:5012/health |
| Playwright 执行器 | http://localhost:5015/health |
| dsh 工作台（profile `dsh`） | http://localhost:3081/?token=…（token 见 `docker compose logs dsh`） |
| Langfuse 测评面板 | http://localhost:3000（由 eval-platform 栈提供，非本 compose） |
| **公网（门户）** | https://smarttest.h3comfyui.art （Basic Auth `admin` / 见 `~/h3services/Caddyfile`，之后再用平台账号登录） |

默认管理员账号取自 `.env` 的 `AUTH_DEFAULT_ADMIN_USERNAME` / `AUTH_DEFAULT_ADMIN_PASSWORD`
（当前为 `admin` / `admin123`，首次登录后请及时修改）。

常用命令：

```bash
docker compose logs -f fastapi     # 跟踪某个服务日志
docker compose restart fastapi     # 重启单个服务
docker compose down                # 停止（数据保留）
docker compose up -d --build       # 改代码后重建
```

## 服务拓扑

| 容器 | 端口 | 镜像 | 说明 |
| --- | --- | --- | --- |
| `smart-test-langgraph` | 5011 | `smart-test-backend` | 智能体运行时。5 个 graph：`smart_test_agent`（通用，对话页唯一入口）+ `testcase_agent`/`unity_agent`/`webui_agent`（旧会话兼容）+ `codebase_agent` |
| `smart-test-fastapi` | 5012 | `smart-test-backend` | 平台 API、认证、用例库、测评批次、定时调度 |
| `smart-test-webui` | 5013 | `smart-test-webui` | Next.js 生产构建（`next start`） |
| `smart-test-playwright` | 5015 | `smart-test-playwright` | **Web-UI 自动化的执行引擎**：独占 Playwright CLI + 浏览器，经 HTTP 暴露 |
| `smart-test-dsh` | 3081→3080 | `smart-test-dsh` | DeepSeek Harness 工作台（profile `dsh`，可选） |
| `smart-test-lightrag` | 5014 | `smart-test-backend` | 平台内 LightRAG（profile `rag`，可选） |

后端两个常驻服务**共用同一个镜像**（`smart-test-backend`），只是启动命令不同，
所以首次构建后再次 `up` 不会重复下载依赖。

### 为什么 Playwright 要单独一个容器

后端是 python，没有 Node 运行时；而 Playwright 的浏览器是一套重且与 OS 强绑定的
依赖（chromium + webkit + 十几个 libnss3/libatk 之类的系统库）。把它塞进后端镜像
会让后端为了一个可选能力背上一整套浏览器工具链，且版本耦合（镜像 tag 必须与
`@playwright/test` 版本一致，否则 CLI 拒绝启动浏览器）。

所以拆成 sidecar：它独占工具链，通过 `tools/playwright-runner/server.mjs` 暴露
三个接口 —— `POST /run`（跑 `playwright test`，回 JSON 报告 + 产物清单）、
`POST /screenshot`（跑 `playwright screenshot`）、`POST /cli`（白名单子命令透传）。
后端 service 层经 `PLAYWRIGHT_RUNNER_URL` 调用它。

本机开发（不用容器）时：

```bash
./tools/playwright-runner/start-local.sh   # 首次会自动装依赖与 chromium
```

### 为什么 dsh 单独一个容器

dsh 只需要 Node，但平台给 dsh 配的 MCP 工具桥（`src/app/mcp_servers/*.py`）是
**stdio 子进程**，必须由 python + 平台依赖拉起。所以 `Dockerfile.dsh` 基于后端
镜像、再拷入 Node 二进制（多阶段从 `node:22-slim` 取，避免 apt 拉 Node），
这样 preset 里 `command: /app/.venv/bin/python -m src.app.mcp_servers.agent_tools_server`
可以直接跑通。

**dsh 拒绝 `--host 0.0.0.0`**（它明确说这会 "expose remote code execution to the
network"，是有意的安全围栏）。容器要发布端口就得绕过去，但正确的绕法是**不绕过
围栏本身**：dsh 只监听容器内 `127.0.0.1:3081`，入口脚本用 socat 在 `0.0.0.0:3080`
上做一层回环转发，对外可见性完全由 compose 的端口发布决定。

### 为什么不需要 Postgres / Redis / Neo4j / Milvus

CLAUDE.md 的「技术栈」一节列了这些基础设施，但**当前代码不依赖它们**：

- 数据库是 SQLite（`aiosqlite`，`src/app/core/config.py` 的 `database_url`）
- LangGraph 以内存模式运行（`start_server.py` 里 `DATABASE_URI=:memory:`、
  `LANGGRAPH_RUNTIME_EDITION=inmem`），线程状态不跨重启保留

因此 compose 里没有这些服务。若后续代码切到 PostgreSQL，再补对应容器即可。

## 数据持久化

| 宿主路径 | 容器路径 | 内容 |
| --- | --- | --- |
| `./docker-data/smart_test_platform.db` | `/data/smart_test_platform.db` | 平台 SQLite 库（用户、用例、会话元数据） |
| `./workspace` | `/app/workspace` | 用例、上传文件、记忆、LightRAG 数据 |
| `./logs` | `/app/logs` | 各服务日志落盘 |
| `./workspace/default/web-ui-auto/runs` | `/work/runs`（playwright 容器） | Playwright 执行产物：截图、trace、report.json |
| `./docker-data/dsh-home` | `/home/dsh`（dsh 容器） | dsh 的 `settings.yaml` 与会话数据 |

`docker-data/` 里的库是从仓库根目录的同名库**播种**而来，保留了原有数据；
之后容器内的写入都会落在宿主机该文件上，删容器不丢数据。

> 注意：不要在宿主机同时用 `launcher.py` 起同一套服务——5011-5013 端口会冲突，
> 且两个进程同时写 SQLite 有锁竞争风险。

## 关键配置点

### 1. 容器间地址必须用服务名

`.env` 里的 `LANGGRAPH_API_URL=http://localhost:5011` 是给**宿主**用的。
在容器里 `localhost` 指向容器自身，所以 compose 对 FastAPI 容器覆盖为：

```yaml
LANGGRAPH_API_URL: http://langgraph:5011
```

`webui` 容器的服务端路由（`/api/upload-to-workspace`）同理，覆盖为
`PYTHON_API_URL=http://fastapi:5012`。

Web-UI 自动化还有第三条：agent 跑在 **langgraph** 容器里，它要调 playwright 容器，
所以 `langgraph` 与 `fastapi` 两个服务都必须把 `PLAYWRIGHT_RUNNER_URL` 覆盖为
`http://playwright:5015`（`.env` 里的 `127.0.0.1:5015` 只对宿主有效）。

> 这个坑踩过一次：compose 的 `environment` 优先于 `env_file`，但**只对写了覆盖的
> 那个服务生效**。当时只给 `fastapi` 加了覆盖，agent 所在的 `langgraph` 拿到的还是
> `.env` 的 `127.0.0.1`，表现为 agent 报「无法连接 playwright runner」而宿主
> curl 5015 一切正常。

### 2. 浏览器侧地址仍用 localhost

前端 `webui/src/lib/config.ts` 里硬编码了 `http://localhost:5011` / `:5012`，
这是**浏览器**发起的请求。因为 compose 把这两个端口发布到了宿主机，
浏览器访问 localhost 即可正常工作，无需改动。

### 3. 宿主上的 LightRAG 与 embedding 服务

`.env` 里 `LIGHTRAG_BASE_URL=http://127.0.0.1:5014`、
`LIGHTRAG_EMBEDDING_BASE_URL=http://127.0.0.1:7997/v1` 指向**宿主机**上由
eval-platform 栈提供的服务。容器内 `127.0.0.1` 不通，故 compose 把
`LIGHTRAG_BASE_URL` 改写为 `host.docker.internal:5014`（`extra_hosts` 已放行）。

RAG 功能不可用不影响平台启动——`/rag` 页面会显示「服务不可达」，属预期降级。
若要把 LightRAG 也放进容器：

```bash
LIGHTRAG_BASE_URL_IN_DOCKER=http://lightrag:5014 \
  docker compose --profile rag up -d
```

该 profile 下的 `lightrag` 服务会用 `host.docker.internal:7997/v1` 取 embedding
（前提是宿主上的 MLX embedding 服务在跑）。

## 本机环境适配记录

构建过程中遇到并已解决的问题，换环境部署时可能需要重新评估：

1. **Docker Desktop 注入的代理不可用**
   本机 Docker Desktop 会把宿主代理注入容器
   （`HTTP_PROXY=http://host.docker.internal:7897`），该代理对 npm 与 Debian
   源返回 502 / 连接重置，而宿主与容器**均可直连外网**。
   故 compose 在构建期与运行期都清空了代理变量（见文件头部
   `x-no-proxy-build` / `x-no-proxy-env`）。

2. **npm 官方源慢且会中断**
   `npm ci` 走官方源实测约 3s/请求并出现 `ECONNRESET`，改用国内镜像
   （`registry.npmmirror.com`，229ms）。构建参数 `NPM_REGISTRY` 可覆盖，
   传 `https://registry.npmjs.org` 即回到官方源。
   锁文件里的 `resolved` 地址会同步改写，否则仍会回源官方。

3. **PyPI 官方源慢**
   `uv sync` 走官方源单包 20-90s，60 个包 15 分钟仍未完成；改用清华源后
   整个构建不到 3 分钟。构建参数 `UV_INDEX_URL_OVERRIDE` 可覆盖为
   `https://pypi.org/simple`。同时加了 `--mount=type=cache` 缓存下载，
   中断后重跑不必重下。

4. **镜像不含 git**
   基础镜像已自带 `ca-certificates`，未装 `git`（安装需访问 Debian 源，
   当前不通）。若要让 agent 在容器内执行 git 操作
   （`permission_gate.py` 的 git 白名单），取消 `Dockerfile.backend` 中
   对应行的注释并确保能访问 Debian 源。

## 未容器化的部分

以下能力依赖宿主环境，容器内要么按需自启、要么不可用：

- **记忆**（2026-09-17 起）：无需外部服务，记忆就是工作区里的 Markdown
  （`workspace/<space>/memory/*.md`）；旧的 EverOS 服务条目见下方历史说明。
- **EverOS 记忆服务（已移除）**：`EVEROS_HOST=127.0.0.1`，由 FastAPI 进程在**自身容器内**
  用 `/app/.venv/bin/everos` 按需拉起，无需额外容器。
- **Unity 自动化（Unity 自动化模块）**：需要两个进程，都与容器无关 ——
  Unity Editor（有桌面的那台机器）和 Unity MCP 桥（`unity-mcp`，默认宿主机 :5016）。
  Unity 工程里的「MCP for Unity」包主动连到桥，所以桥跑哪儿都行，只要 Unity 连得到：
  桥在容器里就把 5016 映射出来，并把 `UNITY_MCP_URL` 指到宿主机地址。
  注意它与 **Web-UI 自动化**是两件事：后者跑在 playwright 容器里，容器内完全可用。
- **codebase-memory（代码图谱）**：官方已提供 **linux-amd64/arm64** 构建，平台按当前系统
  自行安装（`services/cbm_install.py`，「代码图谱」页一键装/升级）。容器部署时把
  `tools/codebase-memory/` 挂进容器（或让 `CODEBASE_MEMORY_EXE` 指向容器内路径）；
  索引存储写在 `workspace/`，与宿主实例共享同一份时**不要同时跑两个索引进程**。
- **Langfuse（测评追踪）**：**不在本 compose 里**——它是独立一套栈（本机跑在
  `~/Documents/eval-platform` 的 docker，:3000）。
  想自己起一套的话，推荐直接用**配套的汉化版**（界面中英切换，本平台配套 fork，
  基线 v4.36.1；v3 汉化版在同仓库的 `main` 分支）：

  ```bash
  git clone -b v4-zh https://github.com/990505-a/eval_puls.git
  cd eval_puls
  docker build -f web/Dockerfile -t langfuse/langfuse:4.36.1-zh \
    --build-arg http_proxy= --build-arg https_proxy= \
    --build-arg HTTP_PROXY= --build-arg HTTPS_PROXY= .
  ```

  它**只替换 web 一个镜像**，postgres / clickhouse / minio / redis 与数据卷都不动，
  所以是在官方 compose 上换一行 `image:` 的事，不是另一套部署方式。注意 worker 必须
  与 web 同主版本，**不要退回 `:3`**：

  ```yaml
  langfuse-web:
    image: langfuse/langfuse:4.36.1-zh                  # 原为 docker.io/langfuse/langfuse:4
  langfuse-worker:
    image: docker.io/langfuse/langfuse-worker:4
  ```

  注意这个 tag **没有发布到任何 registry**（它挂在官方 Docker Hub 组织名下，
  `docker pull` 会拿到官方原版或 not found），所以要按上面那样本地构建。
  不想要汉化就用官方一键自建：
  `git clone --depth=1 https://github.com/langfuse/langfuse.git && cd langfuse && docker compose up`。

  **v4 的写模式必须留 `dual`**。平台的测评上报是手写 ingestion 事件
  （`eval/langfuse_client.py` 自己拼 `trace-create`/`span-create` 走
  `POST /api/public/ingestion`），而 v4 的 `LANGFUSE_MIGRATION_V4_WRITE_MODE=events_only`
  会对这类事件返回 400（`score-create` 除外）。症状很难查：批次页看着正常、分数也在，
  但轨迹一条没有、trace 直链全是空的。将来上报迁到 OTel 或官方 SDK 后再切 `events_only`。

  容器内的平台要访问它，用 `LANGFUSE_BASE_URL_IN_DOCKER=http://host.docker.internal:3000`。
  **不配也能跑测评**：分数照常落 `eval_batches`/`eval_case_results`，只是没有 trace 直链。
- **飞书 lark-cli**：需要宿主已安装并登录 `lark-cli`。

## 排查

```bash
# 看某服务为什么没起来
docker compose logs --tail=100 langgraph

# 进容器手查
docker exec -it smart-test-fastapi bash

# 容器内验证到 LangGraph 的连通性
docker exec smart-test-fastapi python -c \
  "import urllib.request; print(urllib.request.urlopen('http://langgraph:5011/ok', timeout=5).read())"

# 端口被占用时改映射（只改宿主侧）
#   ports: ["15013:5013"]

# Web-UI 自动化专用排查：先看执行器，再看 agent 所在的容器能不能到它
curl -s http://localhost:5015/health | python3 -m json.tool
docker exec smart-test-langgraph python -c \
  "import asyncio,sys; sys.path.insert(0,'/app'); from src.app.services import playwright_service as p; print(asyncio.run(p.status()))"
```

### Web-UI 自动化跑不起来时的排查顺序

| 现象 | 检查 |
| --- | --- |
| `无法连接 playwright runner` | agent 所在容器的 `PLAYWRIGHT_RUNNER_URL` 是否为 `http://playwright:5015`（见「关键配置点 1」） |
| `Executable doesn't exist at /ms-playwright/...` | runner 镜像里浏览器没装好；`docker exec smart-test-playwright ./node_modules/.bin/playwright install --with-deps chromium` |
| runner 在线但 0 个用例 | spec 文件名不匹配 `testMatch`（默认 `**/*.spec.@(js\|mjs\|ts)`） |
| 用例超时 | `WEB_UI_CASE_TIMEOUT_S` / `WEB_UI_RUN_TIMEOUT_S`（.env）与 runner 的 `RUN_TIMEOUT_MS` 是否太小 |
| 截图取不到 | 产物落在 `workspace/default/web-ui-auto/runs/<runId>/artifacts/`，宿主机可直接看 |

改动前端代码后需要重建 webui 镜像（生产构建已打包进镜像）：

```bash
docker compose up -d --build webui
```


## 公网访问（注册到 h3comfyui.art 门户）

本机的公网入口是 cloudflared 隧道 + caddy 密码代理，配置都在 `~/h3services/`。
平台已按这套既有约定注册，接线如下：

```
公网 ──> cloudflared(隧道 728f927d…, ~/.cloudflared/config.yml)
          └─ smarttest.h3comfyui.art ──> caddy(:8189, h3services/Caddyfile 的 @smarttest 段)
                                            ├─ /lg/*  → 127.0.0.1:5011  (LangGraph)
                                            ├─ /py/*  → 127.0.0.1:5012  (FastAPI)
                                            └─ /*     → 127.0.0.1:5013  (Next.js 前端)
```

### 为什么是一个域名 + 路径前缀，而不是三个子域

前端是浏览器直接调 LangGraph 与 FastAPI 的。如果给三个子域，就是三个跨域源，
还得在每个页面里手工填服务器地址。放在同一域名下按前缀分流后：浏览器侧全是
**同源**请求——不跨域、Basic 凭据随同源自动带上、前端零配置。

前端侧的对应逻辑在 `webui/src/lib/config.ts`：当页面不是从回环地址打开时，
默认地址自动解析为 `${origin}/lg` 与 `${origin}/py`（本机直连仍用
`localhost:5011/5012`，行为不变）。

### 一个必须记住的坑：两个鉴权层抢同一个头

平台自己有 JWT 登录，前端原本用 `Authorization: Bearer <token>` 调 API。
但 caddy 的 Basic Auth **也用 `Authorization`**：浏览器会自动带上 Basic 凭据，
前端再显式设 Bearer 就把 Basic 顶掉了，反代直接 401——
现象是「本地全好，一挂门户所有需要登录的接口全挂」。

解法不是去掉 Basic Auth（`/lg/*` 的 LangGraph 是 noop 鉴权，裸奔等于把
agent 执行权公开、白烧模型配额），而是**把应用 token 挪到独立头**：

- 前端统一发 `X-Auth-Token: <jwt>`（`config.ts` 的 `AUTH_HEADER` / `authHeaders()`）
- 后端两种都接受，`X-Auth-Token` 优先（`src/app/api/v2/auth.py::_extract_token`）

这样两层鉴权互不干扰，本机直连与公网访问走同一套代码，不必按环境分支。

### 看护

`~/h3services/daemon.sh` 每 30 秒巡检一次，新增的 `ensure_smarttest()` 会在
前端端口(5013)消失时执行 `docker compose up -d` 兜底（幂等，不会重建在跑的容器）。
四个容器本身的 `restart: unless-stopped` + healthcheck 负责单容器级别的自愈。

### 改了门户侧哪些文件

| 文件 | 改动 |
| --- | --- |
| `~/.cloudflared/config.yml` | 新增 `smarttest.h3comfyui.art` ingress |
| `~/h3services/Caddyfile` | 新增 `@smarttest` 段（Basic Auth + 三路分流，SSE `flush_interval -1`） |
| `~/h3services/panel_server.py` | 新增「🧪 智能测试平台」卡片 + `/api/status` 健康检查 + pill 刷新 |
| `~/h3services/daemon.sh` | 新增 `ensure_smarttest()` 看护 |
| Cloudflare DNS | `cloudflared tunnel route dns` 建的 CNAME（指向隧道） |

改动前都按仓库惯例备份为 `*.bak-HHMMSS`。

---

## Web-UI 自动化：执行存证与官方报告

这一块的目标是「跑完看得见过程」——只给一个通过/失败和一个日志框，等于没做存证。

### 产物链路

```
playwright test 在 sidecar 里跑
  ├── artifacts/             spec 里手动截的图
  ├── test-results/          失败截图 / trace.zip / video.webm / error-context.md
  └── html-report/           官方 HTML 报告（自包含：截图与 trace 都在里面）
        │  runs 目录挂在 ./workspace，后端容器直接读磁盘
        ▼
FastAPI 签名路由
  GET /api/v2/web-ui-auto/artifact/{run_id}/{path}?sig=...      单个产物
  GET /api/v2/web-ui-auto/report/{run_id}/{sig}/index.html      官方报告（含 trace 回放）
```

**为什么用签名 URL 而不是 token**：`<img>` / `<video>` / 新标签页里的报告都是
浏览器自己发起的请求，带不上前端设置的 `X-Auth-Token`。签名（`core/share_link.py`，
HMAC + 过期时间）只对那一条执行有效，默认 7 天；`SHARE_LINK_SECRET` 不配置时用
进程内随机密钥，重启后旧链接失效。

**为什么签名放在报告的路径里而不是查询串**：报告是一整个目录，`index.html` 里的
资源引用全是相对路径，浏览器请求 `data/xxx.json`、`trace/index.html` 时会保留前缀，
签名跟着过去；放查询串则只有入口那一次带得上，子资源全 403。

### 顺带修掉的三个「静默失真」

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| JSON 报告里用例状态是 `expected`/`unexpected` | 前端判 `!== 'passed'`，**通过的用例全显示成失败** | runner 出口统一归一化成 `passed`/`failed` |
| `forbidOnly: false` + 残留 `test.only` | 只跑 1 条却报「全绿」，退出码 0 | 改 `forbidOnly: true`，直接报错 |
| `console.log` 不落 `output` | 技能文档教的「侦察 spec 打印 DOM」拿不到任何输出 | 回传 `result.stdout` 与每条用例的 `stdout` |

### 验收

浏览器级验收在 `tools/playwright-runner/acceptance/`（见该目录 README）：
真实 Chromium 打开页面，断言图表渲染、签名截图解码成功（`naturalWidth > 0`）、
官方报告与 trace 回放可打开、匿名上下文也能用分享链接打开报告。夹具用例跑完即删。

### 执行过程可见（实时进度）

原先点「执行」是**点火即忘**：整轮（含自修复）跑完才写库，执行期间前端一片空白，
用户只能干等、靠刷新。现在改成三段式：

```
点执行 → 立刻落一条 status=running 的执行记录（含本次运行目录名）
       → sidecar 边跑边写两份文件：
            progress.ndjson   自定义 reporter 逐条用例落事件（总数/状态/耗时）
            stdout.log        CLI 原样输出
       → 前端轮询 GET /api/v2/web-ui-auto/runs/{id}/progress（2s）
            ↓
         跑完把 running 记录回填成终态，自修复轮另起新行
```

几个刻意的选择：

- **运行目录名由后端生成**（`run-<hex>`）再交给 runner。否则目录名要等 runner 分配，
  后端在开跑前就拿不到「进度文件在哪」，也就没法先落 running 记录。
- **进度用自定义 reporter，不解析日志**：`list` reporter 的输出是给人看的、格式会变；
  reporter API 的 `onTestEnd` 给的是结构化数据，前端能直接算「跑到第几条、过了几条」。
- **不引长连接**：进度落在共享的 runs 目录里，后端容器直接读磁盘，前端轮询即可。
- **卡住的记录不当活人**：`running` 超过 `WEB_UI_RUN_TIMEOUT_S + 120s` 标记为
  `stale_running`，前端显示「疑似中断」而不是永远转圈。

界面上对应：用例库「最近结果」列显示运行中 + 看进度入口、执行按钮变「运行中」并禁用、
执行详情里是进度条 + 实时用例流 + CLI 输出尾，跑完自动收敛成结果（不用手动刷新）。
有执行在跑时列表轮询从 10s 提到 2.5s。

### 设置页里的 Langfuse 配置

Langfuse 的 key 对以前只能改 `.env`（要进容器改文件）。现在设置页有「Langfuse（测评追踪）」
一块：地址 / Public Key / Secret Key / 环境标识 / 是否上报，外加**测试连通**（返回项目名、
项目 id、组织、延迟）。Secret 只以 `********` 回显，保存时原样提交即表示"不修改"。

这里有几个不显眼但会咬人的点，都踩过一遍：

| 坑 | 现象 | 处理 |
| --- | --- | --- |
| `.env` 没挂进容器 | 设置页保存时写的是容器内的 `/app/.env`，重建即丢，宿主机 `.env` 从未被改过（模型设置也受此影响） | compose 给 fastapi 挂 `./.env:/app/.env` |
| 容器与宿主视角不同 | `.env` 里是 `127.0.0.1:3000`（宿主 CLI 用），容器内 `127.0.0.1` 指向自己 | 设置页读 `.env` 的**宿主视角**值；`LangfuseClient` 在容器内自动把回环地址换成 `host.docker.internal` |
| 翻译漏在某一处 | 「测试连通」用了表单里的宿主地址但请求发自容器 → 明明能通却报"连不上" | 翻译放在 `LangfuseClient.__init__`（所有调用方的唯一入口） |
| 上报失败没人知道 | key 配错时页面照旧显示"通过、N 条用例有分数"，Langfuse 里一条没有 | 批次输出固定写 `langfuse 上报：trace N 条`；一条都没成功时页面标题栏标红「Langfuse 未上报」 |

### 配置的"两个来源"：DB 与 .env（显示 ≠ 生效）

设置页保存时写**两处**：数据库 `settings_kv`（页面读它显示）+ 仓库 `.env`（进程读它运行）。
`.env` 当时没挂进容器（上表第一行），于是出现过"设置页显示 `glm-5.3-flash`、实际所有 agent
跑 `glm-4.7`"的静默分叉——界面在骗人，而且没有任何报错。踩过的三个点：

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 设置页的模型 ≠ 实际跑的模型 | 保存只写了 DB（`.env` 未挂载，写进了容器内的临时文件） | fastapi 挂 `./.env:/app/.env`；本次把两边**以运行期生效的 .env 为准**对齐回 DB |
| "保存后无需重启即时生效"不成立 | agent 进程的模型热更新是 watch `/app/.env`（`middleware/live_model_reload.py`），而 langgraph 容器里没有这个文件 | 给 langgraph 也挂 `./.env:/app/.env`，这句话才成立 |
| 测评页写着 `judge：glm-4.7`，却找不到在哪配 | 三项 `JUDGE_*` 全空 → 回退主 LLM，而设置页**没有 judge 入口** | 设置页新增「LLM 裁判（测评打分）」+ 自检（走真实打分通道）；`/eval/status` 增加 `source` 字段，界面直接写「独立配置 / 继承主 LLM」 |

