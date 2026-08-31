"""Per-run dynamic repository mount backend.

Mounted as the static ``/repo/`` route inside the agent's CompositeBackend.
The actual repository directory is resolved **per tool call** from the
LangGraph configurable value ``repo_path`` (set by the chat frontend for
each conversation), so one agent instance can serve different repos per
thread without rebuilding the graph.

Read-only by design: write/edit/upload on ``/repo/`` are rejected — the
agent's deliverables belong in its workspace, never in the game repo.

``agrep`` is deliberately overridden (NOT inherited): the BackendProtocol
default wraps ``grep`` in a fixed 35s ``wait_for`` that does not stop the
worker thread — it both cut the ripgrep budget short and leaked rg.exe
processes on timeout (orphaned scans stack up on the mechanical HDD).
The override follows the dsh harness model: cooperative cancellation,
process-tree kill, output caps, fail-fast errors.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from deepagents.backends import BackendProtocol, FilesystemBackend, LocalShellBackend
from deepagents.backends.protocol import (
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

_MAX_BACKENDS = 32

# Project-local ripgrep: FilesystemBackend's own rg lookup fails when the
# service process PATH lacks rg, silently falling back to a pure-Python scan
# that takes minutes on the multi-GB game repo.
_RG_EXE = Path(__file__).resolve().parents[4] / "tools" / "rg.exe"
# rg 单次运行的硬截止（E盘机械 I/O：2.4万文本文件全搜约 1-2 分钟）。
# 冷盘无输出时读循环会阻塞在 readline，因此由看门狗线程强制执行：
# 到期杀进程树 → 管道 EOF → 读循环退出。
_RG_TIMEOUT = 180
_RG_MAX_TOTAL = 250                  # 内联匹配上限（对齐 dsh / Claude Code head_limit），满额即提前终止 rg
_RG_LINE_CAP = 2000                  # 单行预览截断（dsh GREP_MAX_LINE_BYTES）
_RG_RAW_CAP = 20 * 1024 * 1024       # rg 原始 stdout 上限，超出即快速失败（dsh RAW_OUTPUT_MAX_BYTES）
_RG_STDERR_CAP = 64 * 1024           # 保留的 stderr 诊断尾部（dsh SEARCH_STDERR_MAX_BYTES）
_RG_KILL_GRACE = 3.0                 # terminate → 宽限 → 进程树硬杀（dsh SEARCH_GRACE_MS）
# agrep 层兜底预算：略高于 _RG_TIMEOUT，正常永远由 rg 层先到点；它取代
# 协议默认的 35s（ASYNC_GREP_TIMEOUT）。
_RG_ASYNC_BUDGET = _RG_TIMEOUT + 15
# Unity/工具链生成物与纯资源目录、资源扩展名：体量巨大且不含业务代码，
# 排除后 rg 只打开文本文件，避免 E 盘 30 万文件枚举的 I/O 瓶颈
_RG_EXCLUDES: list[str] = sum(
    ([ "-g", f"!{pat}"] for pat in [
        "Library/**", "Temp/**", "Logs/**", "obj/**", "bin/**",
        "build/**", "VP/**", "HybridCLRData/**", "FBX/**", "client_clone_0/**",
        "*.meta",
        "*.png", "*.jpg", "*.jpeg", "*.tga", "*.exr", "*.psd", "*.dds",
        "*.gif", "*.bmp", "*.ico", "*.icns",
        "*.wav", "*.ogg", "*.mp3", "*.mp4", "*.wem", "*.bnk",
        "*.fbx", "*.obj", "*.blend", "*.prefab", "*.unity", "*.asset",
        "*.anim", "*.controller", "*.mat", "*.shader", "*.spriteatlas",
        "*.exe", "*.dll", "*.so", "*.zip", "*.7z", "*.rar", "*.pak",
        "*.bundle", "*.unity3d", "*.pdf",
    ]),
    [],
)

_READONLY_ERROR = (
    "/repo/ 是只读的代码仓库挂载，禁止写入或修改；"
    "请把生成产物（用例、报告等）用 write_file 保存到工作区根目录下。"
)


def _mounted_repo_path() -> str:
    """Read repo_path from LangGraph configurable; empty when not set.

    Same pattern as the retired git_tools._get_repo_path(): get_config()
    raises RuntimeError outside a runnable context — degrade to "".
    """
    try:
        from langgraph.config import get_config

        config = get_config()
    except RuntimeError:
        return ""
    return (config.get("configurable") or {}).get("repo_path", "") or ""


def _kill_tree(proc: subprocess.Popen | None) -> None:
    """dsh-style termination: terminate → grace → process-tree hard kill.

    No-op for an already-exited process, so callers can invoke it
    unconditionally on every early-exit path.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=_RG_KILL_GRACE)
        return
    except subprocess.TimeoutExpired:
        pass
    if sys.platform == "win32":
        # rg 自身不派生子进程；/T 仅为与 dsh 的进程树硬杀语义对齐兜底
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=_RG_KILL_GRACE, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=_RG_KILL_GRACE)
    except subprocess.TimeoutExpired:
        pass


class RepoProxyBackend(BackendProtocol):
    """Delegates /repo/ file operations to the repo mounted for this run."""

    def __init__(self) -> None:
        self._cache: dict[str, FilesystemBackend] = {}

    def _resolve(self) -> tuple[FilesystemBackend | None, str | None]:
        repo = _mounted_repo_path()
        if not repo:
            return None, (
                "未挂载代码仓库：本次会话没有配置仓库路径，/repo/ 不可用。"
                "请提示用户在聊天页选择要分析的仓库后重新发送。"
            )
        backend = self._cache.get(repo)
        if backend is None:
            if not Path(repo).is_dir():
                return None, f"挂载的仓库目录不存在: {repo}"
            if len(self._cache) >= _MAX_BACKENDS:
                self._cache.clear()
            backend = FilesystemBackend(root_dir=repo, virtual_mode=True)
            self._cache[repo] = backend
        return backend, None

    # ---- read operations ----------------------------------------------------

    def ls(self, path: str) -> LsResult:
        backend, err = self._resolve()
        if err:
            return LsResult(error=err)
        try:
            return backend.ls(path)
        except Exception as exc:  # noqa: BLE001 — surface to LLM, never crash the run
            return LsResult(error=f"/repo/ ls 失败: {exc}")

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        backend, err = self._resolve()
        if err:
            return ReadResult(error=err)
        try:
            return backend.read(file_path, offset=offset, limit=limit)
        except Exception as exc:  # noqa: BLE001
            return ReadResult(error=f"/repo/ read 失败: {exc}")

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return self._grep_with_cancel(pattern, path, glob, max_count, None, None)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        """Async grep with a real budget and real cancellation (dsh model).

        Unlike the protocol default (35s wait_for that leaks the worker
        thread and the rg.exe process), hitting the budget here kills the rg
        process tree — the blocked readline unblocks via pipe EOF and the
        worker thread exits promptly. No orphaned scans stacking I/O.
        """
        cancel = threading.Event()
        proc_box: list[subprocess.Popen | None] = []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._grep_with_cancel,
                    pattern, path, glob, max_count, cancel, proc_box,
                ),
                timeout=_RG_ASYNC_BUDGET,
            )
        except TimeoutError:
            cancel.set()
            _kill_tree(proc_box[0] if proc_box else None)
            return GrepResult(
                error=f"grep 超时（{_RG_ASYNC_BUDGET}s），"
                      "请缩小检索范围（path/glob）或更换更具体的关键词后重试",
            )
        except asyncio.CancelledError:
            cancel.set()
            _kill_tree(proc_box[0] if proc_box else None)
            raise

    def _grep_with_cancel(
        self,
        pattern: str,
        path: str | None,
        glob: str | None,
        max_count: int | None,
        cancel: threading.Event | None,
        proc_box: list[subprocess.Popen | None] | None,
    ) -> GrepResult:
        backend, err = self._resolve()
        if err:
            return GrepResult(error=err)
        result = self._rg_grep(
            pattern, path, glob,
            max_count=max_count, cancel=cancel, proc_box=proc_box,
        )
        if result is not None:
            return result
        # rg unavailable or errored — fall back to the stock (slow) backend,
        # which carries its own 15s budget (deepagents DEFAULT_GREP_TIMEOUT).
        try:
            return backend.grep(pattern, path=path, glob=glob, max_count=max_count)
        except Exception as exc:  # noqa: BLE001
            return GrepResult(error=f"/repo/ grep 失败: {exc}")

    def _rg_grep(
        self,
        pattern: str,
        path: str | None,
        glob: str | None,
        *,
        max_count: int | None = None,
        cancel: threading.Event | None = None,
        proc_box: list[subprocess.Popen | None] | None = None,
    ) -> GrepResult | None:
        """Streaming ripgrep search with dsh-style guards.

        - deadline watchdog: kills the process tree at ``_RG_TIMEOUT`` (a
          cold-HDD scan emits no output, so readline can block forever)
        - raw-stdout byte cap: overflow fails fast instead of limping on
        - inline match cap: terminate rg as soon as it is reached
        - per-line preview truncation
        - ``--no-config``: never honor host RIPGREP_CONFIG_PATH injection

        ``None`` means ripgrep cannot serve this call (exe missing / spawn
        error) and the caller should fall back to the stock backend.
        """
        if not _RG_EXE.exists():
            return None
        repo = _mounted_repo_path()
        if not repo:
            return None
        if cancel is not None and cancel.is_set():
            return GrepResult(error="grep 已取消")
        # Virtual path ("/repo/server") -> path relative to the repo root
        rel = (path or "/repo").replace("\\", "/")
        for prefix in ("/repo/", "/repo"):
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break
        rel = rel.strip("/")
        root = Path(repo)
        target = root / rel if rel else root
        if not target.exists():
            return GrepResult(matches=[])
        cap = _RG_MAX_TOTAL if max_count is None else min(max_count, _RG_MAX_TOTAL)

        cmd = [
            str(_RG_EXE), "--json", "-F", "--no-config",
            "--max-filesize", "10M",
            *_RG_EXCLUDES,
        ]
        if glob:
            cmd.extend(["-g", glob])
        cmd.extend(["--", pattern, rel or "."])

        timed_out = False

        def _on_deadline() -> None:
            nonlocal timed_out
            timed_out = True
            _kill_tree(proc_box[0] if proc_box else None)

        stderr_tail = bytearray()
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError:
            return None
        if proc_box is not None:
            proc_box.clear()
            proc_box.append(proc)
        timer = threading.Timer(_RG_TIMEOUT, _on_deadline)
        timer.start()

        def _drain_stderr() -> None:
            # Concurrent drain so a chatty rg cannot deadlock on a full pipe.
            try:
                stream = proc.stderr
                while stream is not None:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    stderr_tail.extend(chunk)
            except OSError:
                pass
            if len(stderr_tail) > _RG_STDERR_CAP:
                del stderr_tail[:-_RG_STDERR_CAP]

        drain = threading.Thread(target=_drain_stderr, daemon=True)
        drain.start()

        matches: list[GrepMatch] = []
        truncated = False
        overflow = False
        bytes_read = 0
        try:
            for raw in proc.stdout:  # type: ignore[union-attr]
                bytes_read += len(raw)
                if cancel is not None and cancel.is_set():
                    return GrepResult(error="grep 已取消")
                if bytes_read > _RG_RAW_CAP:
                    overflow = True
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") != "match":
                    continue
                data = event.get("data") or {}
                # rg 以 "." 为搜索根时输出 "./client/..."，剥掉以免路径带 /./ 前缀
                file_part = ((data.get("path") or {}).get("text") or "").replace("\\", "/").removeprefix("./")
                if not file_part:
                    continue
                text = ((data.get("lines") or {}).get("text") or "").rstrip("\r\n")
                if len(text) > _RG_LINE_CAP:
                    text = text[:_RG_LINE_CAP] + " …(行已截断)"
                matches.append({
                    # CompositeBackend re-prefixes sub-backend paths with the
                    # "/repo" mount point, so return repo-relative paths here.
                    "path": "/" + file_part,
                    "line": int(data.get("line_number") or 0),
                    "text": text,
                })
                if len(matches) >= cap:
                    truncated = True
                    break
        finally:
            timer.cancel()
            # No-op when rg already exited; every early-exit path needs the kill.
            _kill_tree(proc)
            try:
                proc.wait(timeout=_RG_KILL_GRACE)
            except subprocess.TimeoutExpired:
                pass
            drain.join(timeout=_RG_KILL_GRACE)

        if timed_out:
            return GrepResult(
                error=f"grep 超时（{_RG_TIMEOUT}s），"
                      "请缩小检索范围（path/glob）或更换更具体的关键词后重试",
            )
        if overflow:
            return GrepResult(
                error=f"rg 原始输出超过 {_RG_RAW_CAP} 字节上限，"
                      "请收窄 pattern / path / glob 后重试",
            )
        # rc 0 = matches found, rc 1 = none — both fine; rc 2 = hard error.
        if proc.returncode == 2:
            detail = stderr_tail.decode("utf-8", errors="replace").strip()[:800]
            return GrepResult(error=f"rg 执行失败: {detail or '未知错误'}")
        return GrepResult(matches=matches, truncated=truncated)

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        backend, err = self._resolve()
        if err:
            return GlobResult(error=err)
        try:
            return backend.glob(pattern, path=path)
        except Exception as exc:  # noqa: BLE001
            return GlobResult(error=f"/repo/ glob 失败: {exc}")

    # ---- write operations: rejected (read-only mount) -----------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READONLY_ERROR)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=_READONLY_ERROR)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        backend, err = self._resolve()
        if err:
            return [FileDownloadResponse(path=p, error="invalid_path") for p in paths]
        try:
            return backend.download_files(paths)
        except Exception as exc:  # noqa: BLE001
            return [FileDownloadResponse(path=p, error=str(exc)) for p in paths]


# ============================================================================
# RepoAwareShellBackend — full_access 档的 /repo/ shell 路径翻译
# ============================================================================

# 匹配命令中的 /repo 虚拟前缀：后随路径分隔符/空白/引号/行尾（不误伤
# /repository 等普通词），前邻不是 . 或字母数字（不误伤 ./repo、x/repo）。
_REPO_TOKEN_RE = re.compile(r"(?<![.\w])/repo(?=[/\\\s\"']|$)")


def _full_access_mode() -> bool:
    """会话权限档是否为 full_access（与 permission_gate._permission_mode 同源）。

    get_config() 在 runnable 上下文之外抛 RuntimeError —— 此时按非
    full_access 处理（保持透传，不翻译）。
    """
    try:
        from langgraph.config import get_config

        configurable = (get_config() or {}).get("configurable") or {}
    except Exception:  # noqa: BLE001
        return False
    mode = str(configurable.get("permission_mode", "")).strip().lower()
    if mode == "full_access":
        return True
    # 兼容旧开关（与 permission_gate 一致）：execute_approval=off → full_access
    return str(configurable.get("execute_approval", "")).strip().lower() == "off"


class RepoAwareShellBackend(LocalShellBackend):
    """LocalShellBackend + full_access 档下把命令里的 /repo/ 翻译为真实仓库路径。

    /repo/ 只存在于 CompositeBackend 的 Python 路由层，shell 子进程
    （subprocess.run(shell=True, cwd=root_dir)）看不到它。本类在命令真正
    执行前做虚拟路径→真实路径翻译，让 full_access 会话能用 git log /
    rg 管道等 shell 能力直接操作挂载仓库：

    - 仅当 permission_mode == full_access 且 repo_path 已挂载时翻译；
    - 其余档位原样透传（/repo/ 仍只能由文件工具访问，行为不变）；
    - 真实路径统一正斜杠（cmd/bash 下均可读）。

    权限门（HumanInTheLoopMiddleware 拦 execute）不受影响：翻译发生在
    审批放行之后、subprocess 之前。full_access 本就是危险档（前端二次
    确认），翻译后仓库对 shell 完全可写是该档的应有语义。
    """

    def execute(self, command: str, *, timeout: int | None = None):
        repo_path = _mounted_repo_path()
        if repo_path and _full_access_mode() and "/repo" in command:
            real = Path(repo_path).resolve().as_posix()
            # lambda 替换避免 replacement 中的反斜杠被 re 解释
            command = _REPO_TOKEN_RE.sub(lambda _m: real, command)
        return super().execute(command, timeout=timeout)
