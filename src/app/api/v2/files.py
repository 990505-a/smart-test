"""工作区静态文件服务（只读）。

为什么需要：智能体/工具会把产物（飞书授权二维码、Unity / Web-UI 截图、
导出的图片等）落在 workspace 下，并在回复里以**本地绝对路径**引用
（如 ``![飞书授权二维码](E:\\...\\workspace\\default\\agent\\qr.png)``）。
浏览器无法加载本地路径，前端 Markdown 渲染只能是裂图——这个端点把
workspace 内的文件以 HTTP 形式暴露，前端把本地路径改写成本端点 URL。

安全边界：**只服务 workspace 根目录内的文件**。越界路径（盘上任意文件、
``..`` 穿越、指向外部的符号链接——``resolve()`` 会展开）一律 404，
不区分"不存在"与"不许读"，避免探测。
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from src.app.core.config import settings

router = APIRouter(prefix="/files", tags=["Files (工作区文件服务)"])


def _resolve_inside_workspace(raw: str) -> Path | None:
    """把请求路径解析到 workspace 内的绝对路径；越界/畸形返回 None。"""
    if not raw or "\x00" in raw:
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            # 两种相对形态都认：相对 workspace 根（"default/agent/qr.png"），
            # 或相对仓库根（"workspace/default/agent/qr.png"——智能体最爱写这种）
            if candidate.parts and candidate.parts[0] == settings.workspace_dir.name:
                candidate = settings.workspace_dir.parent / candidate
            else:
                candidate = settings.workspace_dir / candidate
        candidate = candidate.resolve()
        root = settings.workspace_dir.resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    if root not in candidate.parents:
        return None
    return candidate


@router.get(
    "",
    summary="Read a file inside the workspace",
    description=(
        "Serve a workspace file over HTTP (read-only). Accepts an absolute path "
        "or a path relative to the workspace root; anything resolving outside "
        "the workspace is rejected with 404."
    ),
)
async def read_workspace_file(
    path: str = Query(description="绝对路径，或相对 workspace 根 / 仓库根（workspace/…）的路径"),
) -> FileResponse:
    target = _resolve_inside_workspace(path)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)
