"""Skill library routes (Skill 模块): upload / browse / delete user-managed skills.

Skills live in ``src/app/skills/`` and are injected into the agents'
system prompts by deepagents SkillsMiddleware. Users curate the library
by uploading SKILL.md files or zipped skill folders — the platform no
longer auto-distills skills (removed 2026-08).
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse

router = APIRouter(prefix="/skills")

_SKILLS_ROOT = Path(__file__).parent.parent.parent / "skills"

# Extensions allowed inside uploaded skills (text-centric; block executables)
_ALLOWED_EXT = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg",
    ".ini", ".sh", ".bat", ".ps1", ".lua", ".cs", ".js", ".ts", ".xml",
    ".html", ".css", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg",
}
_SAFE_NAME = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.") | {
    chr(c) for c in range(0x4E00, 0x9FFF + 1)  # 中文
}


def _safe_rel_path(rel: str) -> Path:
    """Validate a relative path stays inside the skills root."""
    target = (_SKILLS_ROOT / rel).resolve()
    if not str(target).startswith(str(_SKILLS_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="非法路径")
    return target


def _validate_member_path(member: str) -> Path:
    """Validate a zip member path (zip-slip protection + extension check)."""
    member = member.replace("\\", "/")
    if member.startswith("/") or ".." in member.split("/"):
        raise HTTPException(status_code=400, detail=f"非法压缩包条目: {member}")
    parts = member.split("/")
    for part in parts:
        if not part or part in {".", ".."}:
            raise HTTPException(status_code=400, detail=f"非法压缩包条目: {member}")
    p = Path(member)
    if p.suffix and p.suffix.lower() not in _ALLOWED_EXT:
        raise HTTPException(status_code=400,
                            detail=f"不支持的文件类型: {p.name}（仅允许文本/脚本/图片类文件）")
    return p


@router.get("/tree", response_model=SuccessResponse, summary="技能文件树")
async def skill_tree(user: CurrentUserDep):
    def walk(root: Path) -> list[dict]:
        items = []
        if not root.exists():
            return items
        for path in sorted(root.iterdir()):
            if path.name.startswith(".") or path.name == "__pycache__":
                continue
            if path.is_dir():
                items.append({"name": path.name, "type": "dir", "children": walk(path)})
            elif path.suffix.lower() in (".md", ".py", ".txt", ".json", ".yaml"):
                items.append({"name": path.name, "type": "file",
                              "path": str(path.relative_to(_SKILLS_ROOT))})
        return items

    return SuccessResponse(success=True, data=walk(_SKILLS_ROOT))


@router.get("/content", response_model=SuccessResponse, summary="读取技能文件内容")
async def skill_content(user: CurrentUserDep, path: str):
    target = _safe_rel_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return SuccessResponse(success=True, data={
        "path": path, "content": target.read_text(encoding="utf-8", errors="replace"),
    })


@router.post("/upload", response_model=SuccessResponse, summary="上传技能文件/技能包(zip)")
async def upload_skill(
    user: CurrentUserDep,
    file: UploadFile = File(...),
    dest: str = "",
):
    """Upload a skill.

    - Single text file (.md/.py/...): saved as ``<dest>/<filename>`` (dest default: root)
    - .zip: extracted into the skills root; if entries share one top-level dir
      it is preserved (zip should contain ``<skill-name>/SKILL.md``),
      otherwise entries are wrapped in a folder named after the zip.
    """
    base_dir = _safe_rel_path(dest) if dest else _SKILLS_ROOT
    base_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "skill.md"
    suffix = Path(filename).suffix.lower()

    if suffix == ".zip":
        with tempfile.TemporaryDirectory() as tmp:
            tmp_zip = Path(tmp) / "upload.zip"
            tmp_zip.write_bytes(await file.read())
            try:
                with zipfile.ZipFile(tmp_zip) as zf:
                    members = [m for m in zf.namelist() if not m.endswith("/")]
                    if not members:
                        raise HTTPException(status_code=400, detail="压缩包为空")
                    validated = {m: _validate_member_path(m) for m in members}
                    top_dirs = {v.parts[0] for v in validated.values() if len(v.parts) > 1}
                    if len(top_dirs) == 1:
                        extract_root = _SKILLS_ROOT
                    else:
                        stem = Path(filename).stem
                        extract_root = _SKILLS_ROOT / stem
                        extract_root.mkdir(parents=True, exist_ok=True)
                    for member, rel in validated.items():
                        out = extract_root / rel
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(zf.read(member))
            except zipfile.BadZipFile:
                raise HTTPException(status_code=400, detail="无效的 zip 文件")
        return SuccessResponse(success=True, data={
            "uploaded": filename, "kind": "zip", "note": "已解压到技能库，Agent 下次运行自动加载"})

    # Single file upload
    check = Path(filename)
    if check.suffix and check.suffix.lower() not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {filename}")
    if not all(c in _SAFE_NAME for c in check.name):
        raise HTTPException(status_code=400, detail=f"非法文件名: {check.name}")
    target = base_dir / check.name
    if target.exists():
        raise HTTPException(status_code=409, detail=f"文件已存在: {check.name}（先删除再上传）")
    target.write_bytes(await file.read())
    return SuccessResponse(success=True, data={
        "uploaded": filename, "kind": "file", "path": str(target.relative_to(_SKILLS_ROOT)),
        "note": "已保存到技能库，Agent 下次运行自动加载"})


@router.delete("", response_model=SuccessResponse, summary="删除技能文件/目录")
async def delete_skill(user: CurrentUserDep, path: str):
    if not path or path.strip("/") == "":
        raise HTTPException(status_code=400, detail="禁止删除技能库根目录")
    target = _safe_rel_path(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="路径不存在")
    if target.resolve() == _SKILLS_ROOT.resolve():
        raise HTTPException(status_code=400, detail="禁止删除技能库根目录")
    if target.is_dir():
        shutil.rmtree(target)
        deleted = f"{path}/ (目录)"
    else:
        target.unlink()
        deleted = path
    return SuccessResponse(success=True, data={"deleted": deleted})
