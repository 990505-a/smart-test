"""Local file storage utility.

Provides file storage under the workspace directory structure.
Attachments: workspace/{space_id}/attachments/
Scripts: workspace/{space_id}/scripts/

Per D-07: local filesystem storage, no external object storage service.

**边界**：``space_id`` 是一层目录名、``relative_path`` 必须在 ``workspace/{space}``
之内——两个都来自请求，过去是裸拼的（``base / relative_path``，含 ``..`` 就出去
了）。这里统一收口：``space_id`` 走 ``safe_segment``，``relative_path`` 解析后
校验是否仍在 base 之下（含解析软链）。
"""

from pathlib import Path

from src.app.core.config import settings
from src.app.core.workspace import safe_segment


def _space_base(space_id: str) -> Path:
    """``workspace/{space_id}`` 的解析后路径（space_id 经白名单校验）。"""
    return (settings.workspace_dir / safe_segment(space_id, field="space_id")).resolve()


def _resolve_within(base: Path, relative_path: str) -> Path:
    """把 ``relative_path`` 解析到 ``base`` 之下；越界即拒绝。

    用 ``resolve()`` 而不是字符串规范化：``resolve()`` 会展开 ``..`` **和软链**，
    所以"看起来在 base 里、实际指向外面"的链接也会被识破。
    """
    full = (base / relative_path).resolve()
    if not full.is_relative_to(base):
        raise ValueError("relative_path 越出了 workspace 目录")
    return full


def get_attachment_dir(space_id: str = "default") -> Path:
    """Resolve attachment directory: workspace/{space_id}/attachments/.

    Creates the directory if it does not exist.

    Args:
        space_id: Workspace ID.

    Returns:
        Path to attachment directory.
    """
    path = _space_base(space_id) / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_script_dir(space_id: str = "default") -> Path:
    """Resolve script directory: workspace/{space_id}/scripts/.

    Creates the directory if it does not exist.

    Args:
        space_id: Workspace ID.

    Returns:
        Path to script directory.
    """
    path = _space_base(space_id) / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_file(file_content: bytes, relative_path: str, space_id: str = "default") -> Path:
    """Save file content to local filesystem under workspace/{space_id}/.

    Args:
        file_content: Raw file bytes.
        relative_path: Relative path within workspace/{space_id}/.
        space_id: Workspace ID.

    Returns:
        Full path to saved file.

    Raises:
        ValueError: relative_path 解析后落在 workspace 之外。
    """
    full_path = _resolve_within(_space_base(space_id), relative_path)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(file_content)
    return full_path


def get_file_path(relative_path: str, space_id: str = "default") -> Path:
    """Resolve full file path from relative path.

    Args:
        relative_path: Relative path within workspace/{space_id}/.
        space_id: Workspace ID.

    Returns:
        Full path to the file.

    Raises:
        ValueError: relative_path 解析后落在 workspace 之外。
    """
    return _resolve_within(_space_base(space_id), relative_path)
