"""工作区挂载（dsh 风格）：一次对话 = 一个真实目录 + 真实路径语义。

平台过去挂的是「代码仓库」，只读、只在 `/repo/` 路由下可见，且每次对话都强制
选择。现在改成 harness（dsh / Claude Code / Codex）的**工作区**模型：

* 用户在对话页选一个目录作为本次对话的工作区，它同时是 agent 的 ``cwd``——
  ``ls`` / ``glob`` / ``grep`` 不带路径时就在工作区里找；
* 路径语义是**真实路径**（``virtual_mode=False``）：``read_file`` 收绝对路径，
  相对路径按工作区解析，``execute`` 直接跑 shell。完全权限档下 agent 可以访问
  工作区之外的任何位置（这是"给完全权限"的本意，不再有隐藏的沙箱）；
* 没选工作区就用平台默认目录 ``workspace/{space}/{agent}/``，行为与过去一致；
* `/repo/` 这个只读挂载点连同 RepoProxyBackend 一并删除——工作区不是仓库，
  agent 也不需要先"读仓库"才能干活。

实现方式：继承 ``LocalShellBackend``，把 ``cwd`` 换成**每次调用时解析**的属性
（``configurable.workspace_path``，兼容旧字段 ``repo_path``）。这样一份编译好的
graph 能服务不同工作区的会话，与权限档位一样按 run 生效。
"""

from __future__ import annotations

import dataclasses
import logging
import re
from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.backends.local_shell import LocalShellBackend

from src.app.core.config import settings

logger = logging.getLogger(__name__)

#: 对话页传来的挂载字段（``repo_path`` 是 2026-09 之前的旧名，保留兼容）
_WORKSPACE_KEYS = ("workspace_path", "repo_path")

#: 平台产物的路由前缀。必须与 ``CompositeBackend(artifacts_root=...)`` 一致。
ARTIFACTS_ROUTE = "/artifacts/"

#: 文件工具 not-found 报错的路径提示。真实路径语义（``virtual_mode=False``）
#: 一直支持绝对路径，但模型常犯两个错：拿 ``/logs/...``（POSIX 风格，Windows
#: 上解析到盘根）或仓库相对路径（按工作区解析）去读工作区之外的文件，失败后
#: 又看到 /skills/、/artifacts/ 两个虚拟路由，就推断"文件工具只支持映射过的
#: 虚拟路径"并绕道 execute——报错里直接把正确写法说出来，堵住这条歧路。
_PATH_HINT = (
    "。路径提示：'/' 开头是虚拟路由（/skills/、/artifacts/）或文件系统根，"
    "不是项目相对路径；读其他位置的文件请用操作系统绝对路径"
    "（Windows 用 'E:/...' 正斜杠形式）；相对路径按当前工作区解析：{cwd}"
)

#: read_file 读到图片时的压缩参数。为什么必须压：read_file 返回二进制图片是
#: **整个 base64 进对话**——Unity 的 1080p 截图 PNG 约 3MB，几条就把消息/数据库
#: 撑到几 MB，前端渲染 3MB 的 JSON 直接卡死页面（2026-09-21 实测）。
#: 输出仍存成 PNG（工具链路按**文件后缀**推断 mime_type，换成 JPEG 会 mime
#: 与数据不符）。1280 边 + 调色板量化对 UI 截图几乎无损，体积缩 5-10 倍。
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_IMAGE_COMPRESS_MIN_B64 = 300_000  # base64 长度阈值（约 220KB 原始数据）
_IMAGE_MAX_EDGE = 1280


def _compress_image_b64(b64: str) -> str | None:
    """压缩大图（保持 PNG）。压不动/失败返回 None，调用方回退原图。"""
    try:
        import base64
        import io

        from PIL import Image

        raw = base64.b64decode(b64)
        image = Image.open(io.BytesIO(raw))
        image.thumbnail((_IMAGE_MAX_EDGE, _IMAGE_MAX_EDGE))
        if image.mode not in ("P", "L"):
            image = image.convert("RGBA").convert(
                "P", palette=Image.ADAPTIVE, colors=256)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        packed = buffer.getvalue()
        if len(packed) >= len(raw) * 0.7:  # 省不到三成就不折腾
            return None
        return base64.b64encode(packed).decode()
    except Exception:  # noqa: BLE001 — 压缩失败不该拦住读文件
        return None


def artifacts_backend() -> FilesystemBackend:
    """承载 deepagents 内部产物的 backend（摘要 offload / 超大工具结果）。

    为什么需要它：``CompositeBackend.artifacts_root`` 默认是 ``"/"``，而我们的
    默认 backend 是 ``virtual_mode=False`` 的**真实路径**语义——两者一叠加，
    摘要 offload 与工具结果淘汰就会往 ``/conversation_history``、
    ``/large_tool_results`` 写，也就是**文件系统根目录**：本机普通用户权限失败；
    容器里（root）写进容器根目录，**重建即丢**（既不进卷，也不在 workspace 里，
    排查时根本想不到去看那里）。

    把它挂成一个路由前缀 + 显式 ``artifacts_root="/artifacts"``：产物落在
    ``<repo>/workspace/.artifacts/`` 下，跟 workspace 卷一起持久化，可查可清。
    """
    root = settings.workspace_dir / ".artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return FilesystemBackend(root_dir=root, virtual_mode=True)


def _run_configurable() -> dict:
    """当前 run 的 configurable（不在 run 里时返回空字典）。"""
    try:
        from langgraph.config import get_config

        config = get_config()
    except Exception:  # noqa: BLE001 — RuntimeError 之外也可能是别的东西在裸调
        return {}
    return config.get("configurable") or {}


def mounted_workspace_path() -> str:
    """本次对话挂载的工作区路径（未挂载时为空串）。"""
    conf = _run_configurable()
    for key in _WORKSPACE_KEYS:
        value = str(conf.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_workspace_dir(default: Path | str) -> Path:
    """挂载目录存在则用它，否则退回默认目录（挂载了一个不存在的路径时给出日志）。"""
    mounted = mounted_workspace_path()
    if not mounted:
        return Path(default).expanduser().resolve()
    candidate = Path(mounted).expanduser()
    if candidate.is_dir():
        return candidate.resolve()
    logger.warning("挂载的工作区不存在，回退默认目录: %s -> %s", mounted, default)
    return Path(default).expanduser().resolve()


class WorkspaceShellBackend(LocalShellBackend):
    """以「本次对话的工作区」为 cwd 的 shell 后端（真实路径语义）。

    ``cwd`` 是动态属性：``LocalShellBackend`` 里所有用到 cwd 的地方（相对路径解析、
    显示路径、shell 的 cwd）都会在**调用时**读到当前挂载，所以同一份 graph 能同时
    服务多个工作区不同的会话。
    """

    def __init__(self, default_dir: Path | str, *, timeout: int = 180) -> None:
        super().__init__(
            root_dir=default_dir,
            virtual_mode=False,   # 真实路径：绝对路径直接用，允许访问工作区之外
            inherit_env=True,     # Windows 上缺 SystemRoot/APPDATA，lark-cli/node 会崩
            timeout=timeout,
        )
        # 兜底目录（未挂载/挂载失效时）。注意：设置 setter 之外不要再赋值，
        # 属性读写都走下面的 property。
        self.cwd = Path(default_dir)

    @property
    def cwd(self) -> Path:  # type: ignore[override]
        return resolve_workspace_dir(self.__dict__.get("_fallback_dir", Path.cwd()))

    @cwd.setter
    def cwd(self, value: Path | str) -> None:
        self.__dict__["_fallback_dir"] = Path(value)

    # -- not-found 报错附路径提示（见 _PATH_HINT） ---------------------------

    def _with_path_hint(self, result, path: str):
        error = getattr(result, "error", None)
        # read 报 "File 'x' not found"，ls 报 "Path 'x': path_not_found"，两种都接；
        # 路径本身已是盘符绝对路径（正确形式）时不附提示——那时文件是真不存在，
        # 再说"请用绝对路径"反而会把模型带偏。
        if (
            not error
            or _WIN_DRIVE.match(path)
            or not any(token in str(error).lower() for token in ("not found", "not_found"))
        ):
            return result
        try:
            return dataclasses.replace(
                result, error=f"{error}{_PATH_HINT.format(cwd=self.cwd)}")
        except TypeError:  # 非 dataclass 的结果类型：原样返回，别为提示拦住正路
            return result

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        result = super().read(file_path, offset=offset, limit=limit)
        result = self._with_path_hint(result, file_path)
        return self._with_compressed_image(result, file_path)

    def _with_compressed_image(self, result, file_path: str):
        """大图压缩后再交给模型/落库（见 _IMAGE_* 处的说明）。"""
        data = getattr(result, "file_data", None)
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            return result
        suffix = Path(file_path).suffix.lower()
        content = data.get("content") or ""
        if suffix not in _IMAGE_SUFFIXES or len(content) <= _IMAGE_COMPRESS_MIN_B64:
            return result
        packed = _compress_image_b64(content)
        if not packed:
            return result
        try:
            return dataclasses.replace(result, file_data={**data, "content": packed})
        except TypeError:
            return result

    def ls(self, path: str):
        result = super().ls(path)
        return self._with_path_hint(result, path)


# ---------------------------------------------------------------------------
# deepagents 工具层的 Windows 路径补丁
#
# 上游 ``validate_path``（backends/utils.py）是虚拟路径世界的设计：一律拒绝
# 盘符绝对路径（``E:/...``、``E:\\...``）。而 FilesystemMiddleware 的每个文件
# 工具在调 backend 前都先过它，于是真实路径语义（``virtual_mode=False``）下
# 模型按系统提示给的绝对路径调用 read_file/write_file 会被整批拒绝——agent
# 只能得出"文件工具不支持真实路径"的结论并绕道 execute。
#
# 补丁：盘符开头的绝对路径原样放行（backend 本来就按原样使用）。安全性不
# 降级：读本来就不设沙箱（真实路径语义的设计意图），写/删的越界审批由平台
# permission_gate 负责（``_resolve_write_target`` 能正确解析盘符路径并按
# ``_allowed_write_roots`` 判界），不依赖这层校验。
# ---------------------------------------------------------------------------

_WIN_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")


def _patch_deepagents_validate_path() -> None:
    """让 validate_path 放行 Windows 盘符绝对路径（幂等，import 时执行）。"""
    import deepagents.backends.utils as _da_utils
    import deepagents.middleware._fs_interrupt as _fs_interrupt
    import deepagents.middleware.filesystem as _fs_mw

    original = _da_utils.validate_path
    if getattr(original, "_platform_realpath_patch", False):
        return

    def validate_path(path: str, *, allowed_prefixes=None):  # noqa: ANN001
        if _WIN_DRIVE.match(path):
            return path  # 真实路径语义：backend 原样使用
        return original(path, allowed_prefixes=allowed_prefixes)

    validate_path._platform_realpath_patch = True  # type: ignore[attr-defined]
    # 三个引用点都要换：定义处 + 两个 from-import 的工具/审批模块
    _da_utils.validate_path = validate_path
    _fs_mw.validate_path = validate_path
    _fs_interrupt.validate_path = validate_path
    logger.debug("deepagents validate_path 已打真实路径补丁（Windows 盘符路径放行）")


_patch_deepagents_validate_path()
