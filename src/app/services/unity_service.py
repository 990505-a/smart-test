"""Unity UI automation service (UI 自动化模块).

Wraps the vendored unity-auto-test python layer
(``src/app/skills/unity-ui-test/python``) which talks to the in-game
LuaRemoteServer over HTTP (default 127.0.0.1:16666). All calls are
synchronous in the skill layer, so they run in a thread here.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from src.app.core.config import settings
from src.app.core.async_subprocess import run_subprocess

_SKILL_DIR = Path(__file__).parent.parent / "skills" / "unity-ui-test"
_SKILL_PYTHON = _SKILL_DIR / "python"

_import_error: str | None = None


def _load():
    """Import the vendored unity skill modules (idempotent)."""
    global _import_error
    if str(_SKILL_PYTHON) not in sys.path:
        sys.path.insert(0, str(_SKILL_PYTHON))
    try:
        import gm as gm_mod  # type: ignore
        import inspector as inspector_mod  # type: ignore
        import text_reader as tr_mod  # type: ignore
        import ui as ui_mod  # type: ignore
        import unity_api  # type: ignore
    except ImportError as exc:  # e.g. requests missing
        _import_error = str(exc)
        return None
    _import_error = None
    return unity_api, ui_mod, tr_mod, inspector_mod, gm_mod


def _make_clients():
    mods = _load()
    if mods is None:
        return None
    unity_api, ui_mod, tr_mod, inspector_mod, gm_mod = mods
    client = unity_api.UnityClient(host=settings.unity_host, port=settings.unity_port)
    return {
        "client": client,
        "ui": ui_mod.UI(client),
        "text": tr_mod.TextReader(client),
        "inspector": inspector_mod.Inspector(client),
        "gm": gm_mod.GM(client),
    }


def skill_dir() -> Path:
    return _SKILL_DIR


async def status() -> dict:
    """Unity editor / LuaRemoteServer connectivity status."""
    def _check() -> dict:
        clients = _make_clients()
        if clients is None:
            return {"available": False, "error": f"skill 导入失败: {_import_error}",
                    "hint": "缺少 requests 依赖"}
        client = clients["client"]
        if not client.is_available():
            return {
                "available": False,
                "error": f"无法连接 LuaRemoteServer ({settings.unity_host}:{settings.unity_port})",
                "hint": "请在 Unity Editor 中通过 Tools > LuaTestTool 启动 Server",
            }
        state = client.editor.get_state()
        return {
            "available": True,
            "server": client.status(),
            "editor": state,
            "is_playing": state.get("isPlaying", False),
        }
    return await asyncio.to_thread(_check)


async def screenshot(save_path: str | None = None) -> dict:
    """Capture a Game-view screenshot; returns the saved path."""
    def _shot() -> dict:
        clients = _make_clients()
        if clients is None:
            return {"success": False, "error": f"skill 导入失败: {_import_error}"}
        target = save_path or str(
            settings.workspace_dir / "default" / "ui-auto" / "screenshots"
            / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png")
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        try:
            path = clients["ui"].screenshot(target)
            return {"success": True, "path": path}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}
    return await asyncio.to_thread(_shot)


async def exec_lua(code: str, *, sync: bool = False) -> dict:
    """Execute Lua in the game runtime (Play Mode required)."""
    def _exec() -> dict:
        clients = _make_clients()
        if clients is None:
            return {"success": False, "error": f"skill 导入失败: {_import_error}"}
        try:
            lua = clients["client"].lua
            out = lua.exec_sync(code) if sync else lua.exec(code)
            return {"success": True, "output": out}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}
    return await asyncio.to_thread(_exec)


async def shown_windows() -> dict:
    def _q() -> dict:
        clients = _make_clients()
        if clients is None:
            return {"success": False, "error": f"skill 导入失败: {_import_error}"}
        try:
            return {"success": True,
                    "shown": clients["inspector"].get_shown_windows(),
                    "all": clients["inspector"].get_all_windows()}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}
    return await asyncio.to_thread(_q)


async def run_ui_script(script_id: str, name: str, content: str) -> dict:
    """Run a saved UI automation python script in a subprocess.

    The script has the vendored skill on sys.path via UNITY_SKILL_DIR
    env var and a standard prelude (client/ui/text/inspector/gm objects).
    """
    started = time.monotonic()
    workdir = settings.workspace_dir / "default" / "ui-auto" / script_id
    workdir.mkdir(parents=True, exist_ok=True)
    script_file = workdir / f"{name or 'ui_test'}.py"

    prelude = f'''"""Auto-generated prelude: unity skill bootstrap."""
import os
import sys
sys.path.insert(0, r"{_SKILL_PYTHON}")
from unity_api import UnityClient, UnityAPIError  # noqa: E402
from ui import UI  # noqa: E402
from text_reader import TextReader  # noqa: E402
from inspector import Inspector  # noqa: E402
from gm import GM  # noqa: E402

client = UnityClient(host="{settings.unity_host}", port={settings.unity_port})
ui = UI(client)
text = TextReader(client)
inspector = Inspector(client)
gm = GM(client)

if not client.is_available():
    print("ERROR: 无法连接 LuaRemoteServer，请在 Unity Editor 启动 Tools > LuaTestTool")
    sys.exit(2)

'''
    script_file.write_text(prelude + "\n" + content, encoding="utf-8")
    try:
        out_bytes, _err_bytes, exit_code = await run_subprocess(
            sys.executable, str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir),
            timeout=300.0,
        )
        output = out_bytes.decode("utf-8", errors="replace")
    except TimeoutError:
        output, exit_code = "执行超时(300s)", -1
    except OSError as exc:
        output, exit_code = str(exc), -2

    return {
        "exit_code": exit_code,
        "status": "passed" if exit_code == 0 else ("failed" if exit_code == 1 else "error"),
        "output": output[-30_000:],
        "duration_ms": int((time.monotonic() - started) * 1000),
        "script_file": str(script_file),
    }
