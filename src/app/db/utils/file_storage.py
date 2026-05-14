"""Local file storage utility.

Provides file storage under the workspace directory structure.
Attachments: workspace/{space_id}/attachments/
Scripts: workspace/{space_id}/scripts/

Per D-07: local filesystem storage, no external object storage service.
"""

from pathlib import Path

from src.app.core.config import settings


def get_attachment_dir(space_id: str = "default") -> Path:
    """Resolve attachment directory: workspace/{space_id}/attachments/.

    Creates the directory if it does not exist.

    Args:
        space_id: Workspace ID.

    Returns:
        Path to attachment directory.
    """
    path = settings.workspace_dir / space_id / "attachments"
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
    path = settings.workspace_dir / space_id / "scripts"
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
    """
    base = settings.workspace_dir / space_id
    full_path = base / relative_path
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
    """
    return settings.workspace_dir / space_id / relative_path
