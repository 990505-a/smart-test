"""EverOS memory service (记忆模块).

平台记忆系统的唯一后端：本地 EverOS server（Markdown 单一事实源 + SQLite +
LanceDB 索引 + 离线进化 OME）。本模块负责：

1. **进程管理** —— ensure_everos_server() 先探活 /health，不通则应用
   everalgo 补丁（tools/patch_everos.py，修复 1.2.3 上游 DetectionResult
   失配）、必要时 `everos init`、再以 DETACHED 方式拉起 server（脱离
   FastAPI/LangGraph 生命周期常驻）。启动器也会管理同一实例——探活优先，
   端口被占时第二个拉起方自然退出，不会冲突。
2. **HTTP 客户端** —— add/flush/search 的 httpx 封装，search 自动按
   capabilities 选择 hybrid/keyword（无 embedding key 时降级关键词）。
3. **文件操作** —— 记忆根目录下 *.md 的列表/读/写/删。EverOS 的级联
   watcher 会把人工编辑同步回索引，这是"记忆可被人审查修正"的关键路径。

Windows 依赖两个垫片（见 config.everos_enabled 注释）：
- src/app/everos_compat/fcntl.py：fcntl.flock → msvcrt.locking
- tools/patch_everos.py：everalgo agent_memory DetectionResult 构造补丁
两者都通过 EVEROS 子进程的 env（PYTHONPATH）与启动前 subprocess 生效。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

from src.app.core.config import settings

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
_BOOT_TIMEOUT = 60.0  # 首次启动含 LanceDB 建索引，给足余量
_HTTP_TIMEOUT = 120.0  # add/flush 触发 LLM 边界检测与蒸馏
_ensure_lock = asyncio.Lock()


class EverosError(RuntimeError):
    """EverOS 调用失败（服务未启动且拉起失败，或 HTTP/响应异常）。"""


def memory_root() -> Path:
    return (ROOT / settings.everos_root).resolve()


def _base_url() -> str:
    return f"http://{settings.everos_host}:{settings.everos_port}"


def _everos_exe() -> str:
    # Windows: venv Scripts/everos.exe；POSIX: 同目录的无后缀脚本
    candidate = Path(sys.executable).parent / ("everos.exe" if os.name == "nt" else "everos")
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("everos")
    if found:
        return found
    raise EverosError("找不到 everos 可执行文件（虚拟环境未安装 everos？）")


def _shim_env_path() -> str:
    """Windows fcntl 垫片目录（仅 win32 需要注入 PYTHONPATH）。"""
    return str(ROOT / "src" / "app" / "everos_compat")


def _server_env() -> dict[str, str]:
    """构建 EverOS 子进程 env 覆盖层（密钥只走环境变量，不落盘）。"""
    env = {k: v for k, v in os.environ.items()}
    env["EVEROS_ROOT"] = str(memory_root())
    env["EVEROS_MEMORY__TIMEZONE"] = "Asia/Shanghai"

    llm_model = settings.everos_llm_model or settings.llm_model or settings.deepseek_model
    llm_base = settings.everos_llm_base_url or settings.llm_base_url
    llm_key = settings.everos_llm_api_key or settings.llm_api_key or settings.deepseek_api_key
    if llm_base:
        env["EVEROS_LLM__BASE_URL"] = llm_base
        env["EVEROS_LLM__MODEL"] = llm_model
        env["EVEROS_LLM__API_KEY"] = llm_key

    embedding_key = settings.everos_embedding_api_key or settings.lightrag_embedding_api_key
    if embedding_key:
        env["EVEROS_EMBEDDING__API_KEY"] = embedding_key
        env["EVEROS_EMBEDDING__BASE_URL"] = (
            settings.everos_embedding_base_url or settings.lightrag_embedding_base_url)
        env["EVEROS_EMBEDDING__MODEL"] = (
            settings.everos_embedding_model or settings.lightrag_embedding_model)

    if sys.platform == "win32":
        env["PYTHONPATH"] = os.pathsep.join(
            p for p in (_shim_env_path(), env.get("PYTHONPATH", "")) if p
        )
    return env


async def _server_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{_base_url()}/health")
            return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _apply_compat_patches(env: dict[str, str]) -> None:
    """幂等应用 everalgo site-packages 补丁；失败只告警不阻断。"""
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "patch_everos.py")],
            capture_output=True, text=True, timeout=60, env=env,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[everos] everalgo 补丁应用失败（可能已由上游修复）: %s", exc)


async def ensure_everos_server() -> dict:
    """确保 EverOS server 在跑：探活 → 补丁/初始化 → 拉起 → 等就绪。"""
    if not settings.everos_enabled:
        return {"success": False, "error": "记忆模块已禁用 (everos_enabled=False)"}
    if await _server_up():
        return {"success": True, "up": True, "spawned": False}

    async with _ensure_lock:
        if await _server_up():  # 双重检查：并发调用只允许一个拉起
            return {"success": True, "up": True, "spawned": False}

        env = _server_env()
        root = memory_root()
        root.mkdir(parents=True, exist_ok=True)
        _apply_compat_patches(env)
        if not (root / "everos.toml").exists():
            subprocess.run(
                [_everos_exe(), "init", "--root", str(root)],
                capture_output=True, text=True, timeout=60, env=env, check=True,
            )

        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        log_path = ROOT / "logs" / "everos.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log_fh:
            subprocess.Popen(  # noqa: S603 - 参数全部来自本地配置
                [_everos_exe(), "server", "start",
                 "--host", settings.everos_host,
                 "--port", str(settings.everos_port),
                 "--root", str(root)],
                stdout=log_fh, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=flags, close_fds=True, env=env, cwd=str(ROOT),
            )

        deadline = time.monotonic() + _BOOT_TIMEOUT
        while time.monotonic() < deadline:
            if await _server_up():
                logger.info("[everos] server 已就绪 :%s", settings.everos_port)
                return {"success": True, "up": True, "spawned": True}
            await asyncio.sleep(1.5)
        return {"success": False,
                "error": f"EverOS server 启动后未就绪，详见 {log_path}"}


async def _client() -> httpx.AsyncClient:
    """ensure server 后返回可用的 AsyncClient（调用方负责关闭）。"""
    ensured = await ensure_everos_server()
    if not ensured.get("success"):
        raise EverosError(ensured.get("error", "EverOS server 不可用"))
    return httpx.AsyncClient(timeout=_HTTP_TIMEOUT, base_url=_base_url())


async def everos_health() -> dict:
    """健康与能力（llm/embed 等）；服务未启动时也会尝试拉起。"""
    ensured = await ensure_everos_server()
    if not ensured.get("success"):
        return {"up": False, "error": ensured.get("error")}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_base_url()}/health")
        resp.raise_for_status()
        data = resp.json()
    return {
        "up": True,
        "version": data.get("version"),
        "capabilities": data.get("capabilities", {}),
        "disabled_features": data.get("disabled_features", []),
        "root": str(memory_root()),
    }


def _dims() -> dict:
    return {
        "app_id": settings.everos_app_id,
        "project_id": settings.everos_project_id,
    }


async def add_messages(session_id: str, messages: list[dict], *,
                       agent_id: str | None = None) -> dict:
    """把一批消息写入 EverOS 记忆（边界检测即触发，未必蒸馏）。"""
    payload = {
        "session_id": session_id,
        "sender_id": settings.everos_user_id,
        "messages": messages,
        **_dims(),
    }
    if agent_id:
        payload["agent_id"] = agent_id
    async with await _client() as client:
        resp = await client.post("/api/v2/memory/add", json=payload)
        if resp.status_code >= 400:
            raise EverosError(f"add 失败 [{resp.status_code}]: {resp.text[:300]}")
        return resp.json().get("data", {})


async def flush_session(session_id: str) -> dict:
    """会话结束：蒸馏为持久 Markdown 记忆（episode/atomic facts）。"""
    payload = {"session_id": session_id,
               "user_id": settings.everos_user_id, **_dims()}
    async with await _client() as client:
        resp = await client.post("/api/v2/memory/flush", json=payload)
        if resp.status_code >= 400:
            raise EverosError(f"flush 失败 [{resp.status_code}]: {resp.text[:300]}")
        return resp.json().get("data", {})


async def save_fact(key: str, content: str, category: str | None = None) -> dict:
    """save_memory 工具的后端：单条显式记忆 → add + flush（立即固化）。"""
    text = content.strip()
    header = []
    if category:
        header.append(f"分类：{category}")
    header.append(f"标识：{key}")
    message = {
        "sender_id": settings.everos_user_id,
        "role": "user",
        "timestamp": int(time.time() * 1000),
        "content": f"【长期记忆】{'；'.join(header)}。内容：{text}",
    }
    session_id = f"agent-save-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
    added = await add_messages(session_id, [message])
    flushed = await flush_session(session_id)
    return {"added": added, "flush": flushed, "session_id": session_id}


async def search_memory(query: str, *, top_k: int = 8) -> list[dict]:
    """检索记忆；有 embedding 用 hybrid，否则 keyword（jieba 中文分词）。"""
    async with await _client() as client:
        health = await client.get("/health")
        caps = health.json().get("capabilities", {}) if health.status_code == 200 else {}
        method = "hybrid" if caps.get("embed") else "keyword"
        payload = {
            "user_id": settings.everos_user_id,
            "query": query, "method": method, "top_k": top_k,
            **_dims(),
        }
        resp = await client.post("/api/v2/memory/search", json=payload)
        if resp.status_code >= 400:
            raise EverosError(f"search 失败 [{resp.status_code}]: {resp.text[:300]}")
        data = resp.json().get("data", {})
    episodes = data.get("episodes", [])
    return [
        {
            "id": ep.get("id"),
            "subject": ep.get("subject") or ep.get("summary", "")[:80],
            "summary": ep.get("summary"),
            "timestamp": ep.get("timestamp"),
            "score": ep.get("score"),
        }
        for ep in episodes
    ]


# ---------------------------------------------------------------------------
# 记忆文件操作（MD 单一事实源；人工编辑由 EverOS watcher 自动回灌索引）
# ---------------------------------------------------------------------------

_EXCLUDED_DIRS = {".index", ".tmp", "__pycache__"}


def _safe_resolve(rel_path: str) -> Path:
    root = memory_root()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root) or not target.suffix == ".md":
        raise EverosError(f"非法记忆文件路径: {rel_path}")
    return target


def list_memory_files() -> list[dict]:
    """列出记忆根目录下全部 *.md（episodes / 原子事实 / 用户画像 / 技能）。"""
    root = memory_root()
    if not root.is_dir():
        return []
    files = []
    for path in sorted(root.rglob("*.md")):
        if any(part in _EXCLUDED_DIRS or part.startswith(".lance")
               for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        files.append({
            "path": rel,
            "size": stat.st_size,
            "modified_at": time.strftime("%Y-%m-%d %H:%M:%S",
                                         time.localtime(stat.st_mtime)),
            "track": "agent" if "/agents/" in f"/{rel}" else "user",
        })
    return files


def read_memory_file(rel_path: str) -> str:
    target = _safe_resolve(rel_path)
    if not target.is_file():
        raise EverosError(f"记忆文件不存在: {rel_path}")
    return target.read_text(encoding="utf-8")


def write_memory_file(rel_path: str, content: str) -> None:
    target = _safe_resolve(rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # 原子写：EverOS watcher 按 mtime 触发重索引，半写状态会被误索引
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


def delete_memory_file(rel_path: str) -> None:
    target = _safe_resolve(rel_path)
    if target.is_file():
        target.unlink()
