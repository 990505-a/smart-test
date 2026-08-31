"""
Unity Remote API Python Wrapper
Thin wrapper around LuaRemoteServer HTTP API (port 16666).
"""
import requests


class UnityAPIError(Exception):
    """Raised when the Unity API returns an error response."""
    pass


class EditorControl:
    """Control Unity Editor play state."""

    def __init__(self, base_url: str, timeout: float):
        self._base = base_url
        self._timeout = timeout

    def get_state(self) -> dict:
        """Get current editor state. Returns {"isPlaying": bool, "isPaused": bool}."""
        resp = requests.get(f"{self._base}/editor/state", timeout=self._timeout)
        return _parse_data(resp)

    def play(self) -> str:
        """Start Play Mode. Returns 'playing'."""
        resp = requests.post(f"{self._base}/editor/play", timeout=self._timeout)
        return _parse_output(resp)

    def stop(self) -> str:
        """Stop Play Mode. Returns 'stopped'."""
        resp = requests.post(f"{self._base}/editor/stop", timeout=self._timeout)
        return _parse_output(resp)

    def pause(self) -> str:
        """Toggle pause/resume. Returns 'paused' or 'resumed'."""
        resp = requests.post(f"{self._base}/editor/pause", timeout=self._timeout)
        return _parse_output(resp)


class LuaExecutor:
    """Execute Lua code in Unity runtime."""

    def __init__(self, base_url: str, timeout: float):
        self._base = base_url
        self._timeout = timeout

    def exec(self, code: str) -> str:
        """Async execute Lua code (wrapped in coroutine). Requires Play Mode."""
        resp = requests.post(
            f"{self._base}/exec",
            json={"code": code},
            timeout=self._timeout,
        )
        return _parse_output(resp)

    def exec_sync(self, code: str) -> str:
        """Sync execute Lua code. Requires Play Mode."""
        resp = requests.post(
            f"{self._base}/exec_sync",
            json={"code": code},
            timeout=self._timeout,
        )
        return _parse_output(resp)

    def eval(self, expression: str) -> str:
        """Evaluate Lua expression and return serialized result. Requires Play Mode."""
        resp = requests.post(
            f"{self._base}/eval",
            json={"code": expression},
            timeout=self._timeout,
        )
        return _parse_output(resp)


class HierarchyExplorer:
    """Query and interact with Unity scene hierarchy."""

    def __init__(self, base_url: str, timeout: float):
        self._base = base_url
        self._timeout = timeout

    def roots(self) -> list:
        """Get all root GameObjects across loaded scenes."""
        resp = requests.get(f"{self._base}/hierarchy", timeout=self._timeout)
        return _parse_data(resp)

    def children(self, instance_id: int) -> list:
        """Get direct children of a GameObject."""
        resp = requests.get(
            f"{self._base}/hierarchy/children",
            params={"id": instance_id},
            timeout=self._timeout,
        )
        return _parse_data(resp)

    def components(self, instance_id: int) -> list:
        """Get all components on a GameObject."""
        resp = requests.get(
            f"{self._base}/hierarchy/components",
            params={"id": instance_id},
            timeout=self._timeout,
        )
        return _parse_data(resp)

    def click(self, instance_id: int) -> str:
        """Simulate click on a Button component attached to this GameObject."""
        resp = requests.post(
            f"{self._base}/hierarchy/click",
            params={"id": instance_id},
            timeout=self._timeout,
        )
        return _parse_output(resp)

    def search(self, name: str = None, type: str = None, parent: int = None) -> list:
        """Search GameObjects by name and/or component type.

        At least one of name or type must be provided.
        parent limits search to that GameObject's subtree.
        """
        params = {}
        if name is not None:
            params["name"] = name
        if type is not None:
            params["type"] = type
        if parent is not None:
            params["parent"] = parent
        resp = requests.get(
            f"{self._base}/hierarchy/search",
            params=params,
            timeout=self._timeout,
        )
        return _parse_data(resp)


class Screenshot:
    """Capture Game window screenshots."""

    def __init__(self, base_url: str, timeout: float):
        self._base = base_url
        self._timeout = timeout

    def capture(self, save_path: str) -> str:
        """Capture Game window and save as PNG. Returns the save_path."""
        resp = requests.get(
            f"{self._base}/editor/screenshot",
            timeout=self._timeout,
        )
        if resp.headers.get("Content-Type", "").startswith("image/"):
            with open(save_path, "wb") as f:
                f.write(resp.content)
            return save_path
        # Error response (JSON)
        data = resp.json()
        raise UnityAPIError(data.get("error", "screenshot failed"))


class UnityClient:
    """Entry point for Unity Remote API.

    Usage:
        client = UnityClient()          # default localhost:16666
        client.editor.play()
        result = client.lua.eval("HeroD.data.level")
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 16666, timeout: float = 10.0):
        self._base = f"http://{host}:{port}"
        self._timeout = timeout
        self.editor = EditorControl(self._base, timeout)
        self.lua = LuaExecutor(self._base, timeout)
        self.hierarchy = HierarchyExplorer(self._base, timeout)
        self.screenshot = Screenshot(self._base, timeout)

    def status(self) -> dict:
        """Check if the server is running. Returns {"running": bool, "port": int}."""
        resp = requests.get(f"{self._base}/status", timeout=self._timeout)
        return resp.json()

    def is_available(self) -> bool:
        """Return True if the Unity server is reachable."""
        try:
            return self.status().get("running", False)
        except requests.ConnectionError:
            return False


def _parse_output(resp: requests.Response) -> str:
    """Parse a response that returns {success, output, error}."""
    data = resp.json()
    if not data.get("success", False):
        raise UnityAPIError(data.get("error", "unknown error"))
    return data.get("output", "")


def _parse_data(resp: requests.Response):
    """Parse a response that returns {success, data}."""
    data = resp.json()
    if not data.get("success", False):
        raise UnityAPIError(data.get("error", "unknown error"))
    return data.get("data")
