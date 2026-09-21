"""Install/upgrade the official codebase-memory-mcp binary (代码图谱模块).

Why this exists: the platform used to require the user to obtain a prebuilt
``.exe`` by hand (and only a Windows build was ever produced for this repo),
which made the whole 代码图谱 feature unusable anywhere else. Upstream now
publishes per-platform releases, so the platform installs it itself — same
deal as the launcher-managed LightRAG: platform owns the lifecycle, the user
clicks a button.

Install layout::

    tools/codebase-memory/codebase-memory-mcp[.exe]     the binary
    tools/codebase-memory/.installed.json               {version, asset, sha256, installed_at}

Contract notes (verified against the v0.11.0 release, not inferred):
* the plain and ``-ui-`` archives of a given platform are byte-identical
  (same sha256 in the release's ``checksums.txt``) — the UI is built into
  every build, so only one asset is ever fetched here;
* ``checksums.txt`` from the same release is the integrity source; the
  download is rejected if the digest does not match;
* macOS needs the quarantine bit stripped + an ad-hoc signature, otherwise
  the kernel kills the binary on first exec. Upstream's own ``install.sh``
  does this; we do the same two commands rather than shelling out to it,
  because ``install.sh`` also rewrites MCP client configs for ~45 agents on
  this machine, which is not ours to touch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.app.core.config import CBM_MANAGED_DIR, settings

logger = logging.getLogger(__name__)

_REPO = "DeusData/codebase-memory-mcp"
_RELEASE_BASE = f"https://github.com/{_REPO}/releases/download"
_TIMEOUT = 300.0
#: release asset naming for the current platform, e.g. "darwin-arm64" —
#: Windows assets are named "-windows-amd64" while macOS/Linux use "-darwin-arm64".
_OS_ALIAS = {"darwin": "darwin", "linux": "linux", "win32": "windows"}
_ARCH_ALIAS = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}


class InstallError(RuntimeError):
    """Anything that stops the install; message is user-facing (Chinese)."""


def asset_tag() -> str:
    """``codebase-memory-mcp-<os>-<arch>.tar.gz|zip`` for this machine."""
    os_key = _OS_ALIAS.get(sys.platform)
    arch_key = _ARCH_ALIAS.get(platform.machine().lower())
    if os_key is None or arch_key is None:
        raise InstallError(
            f"官方未提供当前平台的构建（{__import__('sys').platform}/{platform.machine()}）")
    return f"{os_key}-{arch_key}"


def managed_exe() -> Path:
    return Path(settings.codebase_memory_exe)


def installed_version() -> str | None:
    """Version recorded at install time, or None when not installed."""
    meta = CBM_MANAGED_DIR / ".installed.json"
    if not meta.is_file():
        return None
    try:
        return (json.loads(meta.read_text("utf-8")) or {}).get("version")
    except (OSError, json.JSONDecodeError):
        return None


def binary_version() -> str | None:
    """``<exe> --version`` of the configured binary; None when missing/broken."""
    exe = managed_exe()
    if not exe.is_file():
        return None
    try:
        out = subprocess.run([str(exe), "--version"], capture_output=True,
                             timeout=30, check=False)
        text = (out.stdout or b"").decode("utf-8", errors="replace").strip()
        # "codebase-memory-mcp 0.11.0"
        return text.rsplit(" ", 1)[-1].lstrip("v") or None
    except (OSError, subprocess.SubprocessError):
        return None


def _fetch(url: str, dest: Path) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_bytes(1 << 20):
                fh.write(chunk)


def _expected_sha(version: str, asset: str) -> str:
    """Digest for one asset out of the release's own checksums.txt."""
    url = f"{_RELEASE_BASE}/{version}/checksums.txt"
    resp = httpx.get(url, follow_redirects=True, timeout=60.0)
    resp.raise_for_status()
    for line in resp.text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset:
            return parts[0].lower()
    raise InstallError(f"{version} 的 checksums.txt 里没有 {asset}（release 资产名可能变了）")


def _unpack(archive: Path, dest_dir: Path) -> Path:
    """Extract and return the binary inside; only the binary is taken out."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            names = [n for n in zf.namelist() if Path(n).name == "codebase-memory-mcp.exe"]
            if not names:
                raise InstallError("压缩包里没有 codebase-memory-mcp.exe")
            zf.extract(names[0], dest_dir)
            return dest_dir / names[0]
    with tarfile.open(archive) as tf:
        member = next((m for m in tf.getmembers()
                       if Path(m.name).name == "codebase-memory-mcp"), None)
        if member is None:
            raise InstallError("压缩包里没有 codebase-memory-mcp")
        tf.extract(member, dest_dir, filter="data")  # requires-python >=3.12
        return dest_dir / member.name


def _macos_prepare(binary: Path) -> None:
    """Strip quarantine + ad-hoc sign — without this macOS kills the binary."""
    for cmd in (["xattr", "-d", "com.apple.quarantine", str(binary)],
                ["codesign", "--force", "--sign", "-", str(binary)]):
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):  # 工具缺失不该让安装失败
            logger.warning("macOS 预处理失败（忽略）: %s", cmd[0])


def _stop_own_processes(dest: Path) -> int:
    """停掉正在运行的 dest 本体（返回停掉的进程数）。

    Windows 不允许覆盖正在执行的文件：平台的探活/查询每次都会经这个 exe
    拉起常驻 daemon，CLI 退出后它还活着，换版覆盖时正是它锁着目标文件
    （WinError 5 拒绝访问）。只按「可执行文件路径等于 dest」精确匹配，
    机器上其他 codebase 安装（别的路径/别的版本）不受影响。"""
    pids: list[str] = []
    try:
        if os.name == "nt":
            query = ("Get-CimInstance Win32_Process | Where-Object "
                     "{ $_.ExecutablePath -eq '%s' } | ForEach-Object { $_.ProcessId }"
                     % str(dest))
            out = subprocess.run(["powershell", "-NoProfile", "-Command", query],
                                 capture_output=True, text=True, timeout=30)
            pids = out.stdout.split()
        else:
            out = subprocess.run(["pgrep", "-f", str(dest)],
                                 capture_output=True, text=True, timeout=30)
            pids = out.stdout.split()
    except (OSError, subprocess.SubprocessError) as exc:
        # 查不到就当没有：替换失败会走 _replace_binary 的报错路径，不至于装一半
        logger.warning("查找 %s 的运行进程失败（忽略，继续尝试覆盖）：%s", dest, exc)
        return 0
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", pid, "/F", "/T"],
                               capture_output=True, timeout=15)
            else:
                subprocess.run(["kill", "-9", pid], capture_output=True, timeout=15)
            logger.info("已停止占用 %s 的进程 PID %s", dest.name, pid)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("停止 PID %s 失败（继续）：%s", pid, exc)
    return len(pids)


def _replace_binary(staged: Path, dest: Path) -> None:
    """把 staged 换名到 dest；被占用则先停进程再重试，仍失败给人话。

    daemon 收到 taskkill 后退出有零点几秒延迟，所以停完等一下再试；
    三轮（立即 / 1.5s / 3s）都失败才放弃——此时报 WinError 5 裸错误
    用户只会一头雾水，告诉他「daemon 还没退干净，稍等重试」才有用。"""
    last: PermissionError | None = None
    for delay in (0.0, 1.5, 3.0):
        if delay:
            time.sleep(delay)
        _stop_own_processes(dest)
        try:
            staged.replace(dest)
            return
        except PermissionError as exc:
            last = exc
    raise InstallError(
        f"覆盖 {dest.name} 失败：文件仍被占用（平台的图谱 daemon 退出有延迟）。"
        f"稍等几秒再点一次安装即可；仍失败就到启动器重启 fastapi 后再装。"
        f"原始错误：{last}") from last


def install(version: str | None = None, *, force: bool = False) -> dict:
    """Download + verify + install the official binary. Raises InstallError.

    Idempotent: when the recorded version already matches and the binary is
    present, this returns immediately (``{"skipped": True}``) unless ``force``.
    """
    version = version or settings.codebase_version
    if not version.startswith("v"):
        version = f"v{version}"
    tag = asset_tag()
    ext = ".zip" if tag.startswith("windows") else ".tar.gz"
    asset = f"codebase-memory-mcp-{tag}{ext}"
    dest = CBM_MANAGED_DIR / ("codebase-memory-mcp.exe" if tag.startswith("windows")
                              else "codebase-memory-mcp")

    if not force and dest.is_file() and installed_version() == version:
        return {"skipped": True, "version": version, "exe": str(dest),
                "message": f"{version} 已安装"}

    try:
        expect = _expected_sha(version, asset)
    except httpx.HTTPError as exc:
        raise InstallError(f"取 checksums.txt 失败（网络？）：{exc}") from exc

    CBM_MANAGED_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CBM_MANAGED_DIR) as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / asset
        try:
            _fetch(f"{_RELEASE_BASE}/{version}/{asset}", archive)
        except httpx.HTTPError as exc:
            raise InstallError(f"下载 {asset} 失败（网络？）：{exc}") from exc

        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != expect:
            raise InstallError(f"校验和不匹配：期望 {expect[:12]}… 实际 {digest[:12]}…")

        try:
            extracted = _unpack(archive, tmp_dir / "x")
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
            raise InstallError(f"解包失败：{exc}") from exc

        # 先落到同目录再原子换名：换版时不会留下半个文件
        staged = dest.with_suffix(dest.suffix + ".new")
        shutil.move(str(extracted), staged)
        if os.name != "nt":
            staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            if sys.platform == "darwin":
                _macos_prepare(staged)
        _replace_binary(staged, dest)

    (CBM_MANAGED_DIR / ".installed.json").write_text(json.dumps({
        "version": version, "asset": asset, "sha256": expect,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), "utf-8")

    logger.info("codebase-memory %s 安装完成 → %s", version, dest)
    return {"skipped": False, "version": version, "exe": str(dest), "sha256": expect,
            "message": f"{version} 安装完成"}


async def install_async(version: str | None = None, *, force: bool = False) -> dict:
    """``install`` off the event loop (it is a 40MB download + sha256)."""
    import asyncio

    try:
        return await asyncio.to_thread(install, version, force=force)
    except InstallError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 安装失败不该 500
        return {"success": False, "error": f"安装失败：{exc}"}
