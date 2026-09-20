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

import logging
from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.backends.local_shell import LocalShellBackend

from src.app.core.config import settings

logger = logging.getLogger(__name__)

#: 对话页传来的挂载字段（``repo_path`` 是 2026-09 之前的旧名，保留兼容）
_WORKSPACE_KEYS = ("workspace_path", "repo_path")

#: 平台产物的路由前缀。必须与 ``CompositeBackend(artifacts_root=...)`` 一致。
ARTIFACTS_ROUTE = "/artifacts/"


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
