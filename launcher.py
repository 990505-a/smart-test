"""Smart Test Platform — 服务控制台 (Launcher/Supervisor)

独立的进程管理器，与被管理的服务解耦（因此可以重启包括 FastAPI 在内的所有服务）。

- 地址: http://localhost:5010
- 管理对象: LangGraph(:5011) / FastAPI(:5012) / WebUI(:5013) / LightRAG(:5014)
- 能力: 启动/停止/重启、端口探测、进程树查杀（含非本控制台启动的进程）、实时日志（内存环形缓冲 + logs/ 文件落盘）
- 启动: 双击 启动控制台.bat（或 .venv\\Scripts\\python.exe launcher.py）
- 注: MCP 服务（rag/git/codebase-memory/wiki）均为 stdio 按需拉起，不在此管理；
  这里只管常驻服务本体。codebase-memory 的 stdio 会话由 FastAPI/LangGraph
  进程内部持有（见 /codebase 页面）。
"""

from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
import time
import webbrowser
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import socket
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

ROOT = Path(__file__).parent.resolve()
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LAUNCHER_PORT = int(os.environ.get("LAUNCHER_PORT", "5010"))
IS_WIN = sys.platform == "win32"
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

@dataclass
class ServiceSpec:
    name: str
    label: str
    command: list[str]
    cwd: Path
    port: int | None = None            # 用于状态探测（外部实例识别）
    health_note: str = ""
    autostart: bool = True
    env: dict[str, str] | None = None  # 附加环境变量（合并到 os.environ 之上）


@dataclass
class ServiceState:
    spec: ServiceSpec
    proc: asyncio.subprocess.Process | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=4000))
    started_at: float | None = None
    task: asyncio.Task | None = None       # log pump task
    restart_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


SERVICES: dict[str, ServiceState] = {}


def _lightrag_env() -> dict[str, str]:
    """Build the env overlay for lightrag-server from platform settings (.env).

    LLM 走 DeepSeek（OpenAI 兼容），embedding 走 OpenAI 兼容 API
    （默认硅基流动 bge-m3，需 LIGHTRAG_EMBEDDING_API_KEY）。
    """
    try:
        from src.app.core.config import settings as cfg
    except Exception:  # noqa: BLE001 — 控制台保持可独立运行
        return {}
    env = {
        "HOST": "127.0.0.1",
        "PORT": "5014",
        "WORKING_DIR": str(ROOT / cfg.lightrag_working_dir),
        "LLM_BINDING": "openai",
        "LLM_BINDING_HOST": "https://api.deepseek.com/v1",
        "LLM_BINDING_API_KEY": cfg.deepseek_api_key,
        "LLM_MODEL": cfg.lightrag_llm_model or cfg.deepseek_model,
        "EMBEDDING_BINDING": "openai",
        "EMBEDDING_BINDING_HOST": cfg.lightrag_embedding_base_url,
        "EMBEDDING_BINDING_API_KEY": cfg.lightrag_embedding_api_key,
        "EMBEDDING_MODEL": cfg.lightrag_embedding_model,
        "EMBEDDING_DIM": str(cfg.lightrag_embedding_dim),
    }
    return env


def _default_services() -> list[ServiceSpec]:
    specs = [
        ServiceSpec(
            name="langgraph", label="LangGraph 智能体服务 (:5011)",
            command=[PY, "start_server.py"], cwd=ROOT, port=5011,
            health_note="用例生成 / UI 自动化 Agent 运行时",
        ),
        ServiceSpec(
            name="fastapi", label="FastAPI 后端 (:5012)",
            command=[PY, "-m", "uvicorn", "src.app.fastapi_app:app",
                     "--host", "0.0.0.0", "--port", "5012"],
            cwd=ROOT, port=5012,
            health_note="平台 API / 自进化调度",
        ),
        ServiceSpec(
            name="webui", label="Web 前端 Next.js (:5013)",
            command=(["cmd", "/c", "npm", "run", "dev", "--", "-p", "5013"] if IS_WIN
                     else ["npm", "run", "dev", "--", "-p", "5013"]),
            cwd=ROOT / "webui", port=5013,
            health_note="平台界面",
        ),
        ServiceSpec(
            name="lightrag", label="LightRAG 知识库 (:5014)",
            command=[PY, "-m", "lightrag.api.lightrag_server"], cwd=ROOT,
            port=5014, env=_lightrag_env(), autostart=False,
            health_note="RAG 知识库本体（图谱+向量检索）；自带 WebUI /webui；"
                        "需 LIGHTRAG_EMBEDDING_API_KEY（默认硅基流动 bge-m3）",
        ),
    ]
    return specs


def _port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.6):
            return True
    except OSError:
        return False


async def _pid_on_port(port: int) -> int | None:
    """Windows: netstat 找占用端口的 PID。"""
    if not IS_WIN:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "netstat", "-ano", stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except Exception:  # noqa: BLE001
        return None
    for line in out.decode("utf-8", errors="replace").splitlines():
        if f":{port} " in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                pid = int(parts[-1])
                if pid > 0:
                    return pid
    return None


async def _kill_tree(pid: int) -> None:
    if IS_WIN:
        proc = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.communicate()
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _append_log(state: ServiceState, line: str) -> None:
    ts = time.strftime("%H:%M:%S")
    state.logs.append(f"[{ts}] {line.rstrip()}")


async def _pump(state: ServiceState) -> None:
    proc = state.proc
    assert proc is not None and proc.stdout is not None
    try:
        async for raw in proc.stdout:
            _append_log(state, raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        _append_log(state, f"(日志读取中断: {exc})")
    finally:
        rc = await proc.wait() if proc.returncode is None else proc.returncode
        _append_log(state, f"(进程退出 code={rc})")
        _flush_log_file(state)


def _flush_log_file(state: ServiceState) -> None:
    try:
        (LOGS_DIR / f"{state.spec.name}.log").write_text(
            "\n".join(state.logs), encoding="utf-8")
    except OSError:
        pass


async def start_service(name: str) -> dict:
    state = SERVICES.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    async with state.restart_lock:
        if state.proc is not None and state.proc.returncode is None:
            return {"started": True, "note": "已在运行"}
        spec = state.spec
        # 端口被外部进程占用时先接管清理
        if spec.port:
            ext_pid = await _pid_on_port(spec.port)
            if ext_pid:
                _append_log(state, f"端口 {spec.port} 被 PID {ext_pid} 占用，先停止该进程")
                await _kill_tree(ext_pid)
                for _ in range(20):
                    if not _port_listening(spec.port):
                        break
                    await asyncio.sleep(0.5)

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0
        _append_log(state, f"启动: {' '.join(spec.command)}  (cwd={spec.cwd})")
        try:
            state.proc = await asyncio.create_subprocess_exec(
                *spec.command, cwd=str(spec.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
                env={**os.environ, "PYTHONUNBUFFERED": "1", **(spec.env or {})},
            )
        except OSError as exc:
            _append_log(state, f"启动失败: {exc}")
            _flush_log_file(state)
            raise HTTPException(status_code=500, detail=f"启动失败: {exc}")
        state.started_at = time.time()
        if state.task:
            state.task.cancel()
        state.task = asyncio.create_task(_pump(state))
        await asyncio.sleep(0.5)
        return {"started": True, "pid": state.proc.pid}


async def stop_service(name: str) -> dict:
    state = SERVICES.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    async with state.restart_lock:
        stopped = []
        if state.proc is not None and state.proc.returncode is None:
            await _kill_tree(state.proc.pid)
            for _ in range(20):
                if state.proc.returncode is not None:
                    break
                await asyncio.sleep(0.5)
            stopped.append(f"子进程 PID {state.proc.pid}")
        elif state.spec.port and _port_listening(state.spec.port):
            ext_pid = await _pid_on_port(state.spec.port)
            if ext_pid:
                await _kill_tree(ext_pid)
                stopped.append(f"外部进程 PID {ext_pid}")
        _append_log(state, f"(已停止 {'; '.join(stopped) or '本就未运行'})")
        _flush_log_file(state)
        return {"stopped": True, "detail": stopped}


def service_status(state: ServiceState) -> dict:
    ours = state.proc is not None and state.proc.returncode is None
    port_up = _port_listening(state.spec.port) if state.spec.port else None
    if ours:
        status = "running"
    elif port_up:
        status = "external"   # 端口有服务但不是本控制台启动
    else:
        status = "stopped"
    return {
        "name": state.spec.name,
        "label": state.spec.label,
        "status": status,
        "pid": state.proc.pid if ours else None,
        "port": state.spec.port,
        "port_up": port_up,
        "uptime_sec": int(time.time() - state.started_at) if ours and state.started_at else None,
        "note": state.spec.health_note,
        "log_lines": len(state.logs),
    }


# ---------------------------------------------------------------------------
# HTTP API + GUI
# ---------------------------------------------------------------------------

app = FastAPI(title="Smart Test Launcher")


@app.get("/api/services")
async def list_services():
    return {"services": [service_status(s) for s in SERVICES.values()]}


@app.post("/api/services/{name}/{action}")
async def service_action(name: str, action: str):
    if name not in SERVICES:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    if action == "start":
        return await start_service(name)
    if action == "stop":
        return await stop_service(name)
    if action == "restart":
        await stop_service(name)
        await asyncio.sleep(1)
        return await start_service(name)
    raise HTTPException(status_code=400, detail=f"未知操作: {action}")


@app.post("/api/all/{action}")
async def all_actions(action: str):
    if action not in ("start", "stop"):
        raise HTTPException(status_code=400, detail="仅支持 start/stop")
    results = {}
    order = [s.spec.name for s in SERVICES.values()]
    for name in (order if action == "start" else reversed(order)):
        try:
            if action == "start":
                results[name] = await start_service(name)
                await asyncio.sleep(2)  # 按依赖顺序错峰启动
            else:
                results[name] = await stop_service(name)
        except HTTPException as exc:
            results[name] = {"error": exc.detail}
    return {"results": results}


@app.get("/api/logs/{name}")
async def get_logs(name: str, after: int = 0):
    state = SERVICES.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    lines = list(state.logs)
    chunk = lines[after:]
    return {"lines": chunk, "next": after + len(chunk), "total": len(lines)}


@app.get("/api/logs/{name}/file")
async def download_logs(name: str):
    state = SERVICES.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"未知服务: {name}")
    _flush_log_file(state)
    path = LOGS_DIR / f"{name}.log"
    if not path.exists():
        raise HTTPException(status_code=404, detail="暂无日志文件")
    return JSONResponse({"path": str(path)})


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>智能测试平台 · 服务控制台</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background:#0f1115; color:#e6e8ee; }
  header { display:flex; align-items:center; gap:14px; padding:14px 20px; background:#161a22; border-bottom:1px solid #232936; }
  header h1 { font-size:16px; font-weight:600; }
  header .sub { color:#8b93a7; font-size:12px; }
  header .spacer { flex:1; }
  button { border:1px solid #2a3140; background:#1c2230; color:#e6e8ee; border-radius:6px; padding:6px 12px; font-size:12px; cursor:pointer; }
  button:hover { background:#252d3d; }
  button.primary { background:#2563eb; border-color:#2563eb; }
  button.primary:hover { background:#1d4ed8; }
  button.danger { color:#f87171; border-color:#7f1d1d; }
  button:disabled { opacity:.45; cursor:not-allowed; }
  main { display:grid; grid-template-columns: 380px 1fr; gap:14px; padding:14px 20px; height:calc(100vh - 59px); }
  .cards { display:flex; flex-direction:column; gap:10px; overflow-y:auto; }
  .card { background:#161a22; border:1px solid #232936; border-radius:10px; padding:12px 14px; cursor:pointer; }
  .card.selected { border-color:#2563eb; }
  .card .row1 { display:flex; align-items:center; gap:8px; }
  .dot { width:9px; height:9px; border-radius:50%; }
  .dot.running { background:#22c55e; box-shadow:0 0 6px #22c55e; }
  .dot.external { background:#eab308; }
  .dot.stopped { background:#4b5563; }
  .card .name { font-size:13px; font-weight:600; }
  .card .meta { color:#8b93a7; font-size:11px; margin-top:4px; }
  .card .btns { display:flex; gap:6px; margin-top:8px; }
  .logpanel { background:#0b0d12; border:1px solid #232936; border-radius:10px; display:flex; flex-direction:column; overflow:hidden; }
  .logpanel .bar { display:flex; align-items:center; gap:10px; padding:10px 14px; border-bottom:1px solid #232936; font-size:12px; color:#8b93a7; }
  .logpanel pre { flex:1; overflow:auto; padding:12px 14px; font:12px/1.55 Consolas, monospace; white-space:pre-wrap; word-break:break-all; }
  .badge { font-size:10px; padding:2px 8px; border-radius:99px; border:1px solid #2a3140; }
  label.chk { display:flex; gap:6px; align-items:center; font-size:12px; color:#8b93a7; cursor:pointer; }
</style>
</head>
<body>
<header>
  <h1>智能测试平台 · 服务控制台</h1>
  <span class="sub" id="summary"></span>
  <div class="spacer"></div>
  <button class="primary" onclick="allAction('start')">全部启动</button>
  <button class="danger" onclick="allAction('stop')">全部停止</button>
  <button onclick="openPlatform()">打开平台</button>
</header>
<main>
  <div class="cards" id="cards"></div>
  <div class="logpanel">
    <div class="bar">
      <span id="logTitle">选择左侧服务查看日志</span>
      <div class="spacer" style="flex:1"></div>
      <label class="chk"><input type="checkbox" id="autoscroll" checked>自动滚动</label>
      <button onclick="clearView()">清屏</button>
    </div>
    <pre id="logview"></pre>
  </div>
</main>
<script>
let services = [], selected = null, logOffset = 0;

async function refresh() {
  const r = await fetch('/api/services'); const d = await r.json();
  services = d.services;
  const running = services.filter(s=>s.status==='running').length;
  const ext = services.filter(s=>s.status==='external').length;
  document.getElementById('summary').textContent =
    `${running} 运行中 · ${ext} 外部实例 · ${services.length} 服务`;
  renderCards();
}

function statusText(s) {
  if (s.status==='running') return '运行中 · PID ' + s.pid + (s.uptime_sec!=null ? ' · ' + fmt(s.uptime_sec) : '');
  if (s.status==='external') return '外部实例占用 :' + s.port;
  return '已停止';
}

function renderCards() {
  const el = document.getElementById('cards');
  el.innerHTML = '';
  for (const s of services) {
    const c = document.createElement('div');
    c.className = 'card' + (selected===s.name ? ' selected' : '');
    c.innerHTML = `
      <div class="row1">
        <span class="dot ${s.status}"></span>
        <span class="name">${s.label}</span>
        ${s.port ? `<span class="badge">:${s.port}</span>` : ''}
      </div>
      <div class="meta">${statusText(s)}<br>${s.note||''}</div>
      <div class="btns">
        <button onclick="event.stopPropagation();act('${s.name}','start')">启动</button>
        <button onclick="event.stopPropagation();act('${s.name}','restart')">重启</button>
        <button class="danger" onclick="event.stopPropagation();act('${s.name}','stop')">停止</button>
      </div>`;
    c.onclick = () => selectService(s.name);
    el.appendChild(c);
  }
}

function selectService(name) {
  selected = name; logOffset = 0;
  document.getElementById('logview').textContent = '';
  document.getElementById('logTitle').textContent = name + ' 日志';
  renderCards(); pollLogs();
}

async function pollLogs() {
  if (!selected) return;
  const r = await fetch(`/api/logs/${selected}?after=${logOffset}`);
  const d = await r.json();
  if (d.lines.length) {
    const v = document.getElementById('logview');
    v.textContent += d.lines.join('\n') + '\n';
    if (document.getElementById('autoscroll').checked) v.scrollTop = v.scrollHeight;
  }
  logOffset = d.next;
}

async function act(name, action) {
  const btns = event.target; btns.disabled = true;
  try {
    const r = await fetch(`/api/services/${name}/${action}`, {method:'POST'});
    if (!r.ok) { const e = await r.json(); alert(e.detail || '操作失败'); }
  } finally { setTimeout(()=>btns.disabled=false, 1500); refresh(); }
}

async function allAction(action) {
  if (!confirm(action==='start' ? '启动全部服务？' : '停止全部服务？')) return;
  await fetch(`/api/all/${action}`, {method:'POST'});
  setTimeout(refresh, 1000);
}

function openPlatform() { window.open('http://localhost:5013', '_blank'); }
function clearView() { document.getElementById('logview').textContent=''; }
function fmt(sec) {
  if (sec < 60) return sec + 's';
  if (sec < 3600) return Math.floor(sec/60) + 'm' + (sec%60) + 's';
  return Math.floor(sec/3600) + 'h' + Math.floor(sec%3600/60) + 'm';
}

refresh();
setInterval(refresh, 3000);
setInterval(pollLogs, 1500);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(PAGE)


async def _autostart() -> None:
    for state in SERVICES.values():
        if state.spec.autostart:
            try:
                await start_service(state.spec.name)
                await asyncio.sleep(2)
            except HTTPException:
                pass


@app.on_event("startup")
async def on_start():
    for spec in _default_services():
        SERVICES[spec.name] = ServiceState(spec=spec)
    asyncio.create_task(_autostart())


if __name__ == "__main__":
    if os.environ.get("LAUNCHER_NO_BROWSER") != "1":
        webbrowser.open(f"http://localhost:{LAUNCHER_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=LAUNCHER_PORT, log_config=None)
