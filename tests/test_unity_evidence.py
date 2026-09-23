"""Unity 执行存证（产物回取 + 步骤轨迹 + 失败现场）的接口测试。

锁住的性质：**页面上能不能看见证据**全靠这几个接口。
- 执行记录里要能读出产物清单（类型/大小/带签名的直链）与步骤轨迹；
- 产物走签名 URL —— `<img>`/`<video>` 是浏览器自己发的请求，带不上自定义头；
- 文件被清理时说清 410，而不是让前端画一排破图；
- 用例一入队就有 run_id（前端才能立刻打开详情看轨迹）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.app.db.database as db_module
from src.app.api.v2 import unity_auto as unity_api
from src.app.core import share_link
from src.app.db.database import Base
from src.app.db.models.unity_script import UnityScript, UnityScriptRun


@pytest_asyncio.fixture
async def db_factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    yield factory
    await engine.dispose()


async def _make_run(factory, tmp_path: Path, *, artifacts: dict[str, str] | None = None,
                    steps: list[dict] | None = None) -> UnityScriptRun:
    """建一条执行记录 + 落几个产物文件（默认：截图 / 录像 / 轨迹 / 失败现场）。"""
    steps_blob = ("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in steps)
                  if steps else '{"i":1,"t":0.1,"action":"click","ms":5,"ok":true}\n')
    files = artifacts if artifacts is not None else {
        "01_hud.png": b"\x89PNG\r\n\x1a\n hud",
        "run.mp4": b"\x00\x00\x00 ftypmp42 video",
        "steps.jsonl": steps_blob.encode("utf-8"),
        "failure.txt": "挂在第 2 步".encode("utf-8"),
    }
    folder = tmp_path / "20260919_120000_用例"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, blob in files.items():
        (folder / name).write_bytes(blob)
        paths.append(str(folder / name))
    async with factory() as db:
        script = UnityScript(name="用例", content="print('PASS')\n")
        db.add(script)
        await db.flush()
        run = UnityScriptRun(script_id=script.id, status="failed", exit_code=1,
                             screenshots=json.dumps(paths, ensure_ascii=False),
                             duration_ms=1234, output="boom")
        db.add(run)
        await db.commit()
        await db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# 执行记录 -> 产物清单 / 步骤轨迹
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_dict_lists_artifacts_with_signed_urls(db_factory, tmp_path):
    steps = [{"i": 1, "t": 0.1, "action": "click", "target": "UI/Bag", "ms": 30, "ok": True},
             {"i": 2, "t": 0.9, "action": "expect_text", "target": "Bag/Title", "ms": 8,
              "ok": False, "error": "AssertionError: 文本里没有 '背包'"}]
    run = await _make_run(db_factory, tmp_path, steps=steps)

    data = unity_api._run_dict(run)
    by_name = {a["name"]: a for a in data["artifacts"]}

    assert set(by_name) == {"01_hud.png", "run.mp4", "steps.jsonl", "failure.txt"}
    assert by_name["01_hud.png"]["kind"] == "image"
    assert by_name["run.mp4"]["kind"] == "video"
    assert by_name["failure.txt"]["kind"] == "text"
    assert by_name["01_hud.png"]["size"] > 0 and by_name["01_hud.png"]["pruned"] is False
    # 直链带签名，且签名对得上这条记录（浏览器直接 GET 就能取）
    url = by_name["01_hud.png"]["url"]
    assert url.startswith(f"/unity-auto/artifact/{run.id}/") and "sig=" in url
    assert share_link.verify(url.split("sig=")[1], str(run.id))
    assert data["artifacts_pruned"] is False
    assert [s["action"] for s in data["steps"]] == ["click", "expect_text"]
    assert data["steps"][1]["ok"] is False


@pytest.mark.asyncio
async def test_pruned_artifacts_are_flagged_not_silently_missing(db_factory, tmp_path):
    """产物文件被清理：清单还认得出来，但每一条都标成 pruned（前端据此不画破图）。"""
    run = await _make_run(db_factory, tmp_path)
    for path in json.loads(run.screenshots):
        Path(path).unlink()

    data = unity_api._run_dict(run)

    assert data["artifacts"] and all(a["pruned"] for a in data["artifacts"])
    assert data["artifacts_pruned"] is True
    assert data["steps"] == []          # 轨迹文件没了就是空，不是报错


@pytest.mark.asyncio
async def test_legacy_screenshots_field_still_readable(db_factory, tmp_path):
    """老记录（screenshots 只是路径数组）也要能读：迁移期两代记录共存。"""
    run = await _make_run(db_factory, tmp_path)
    data = unity_api._run_dict(run)
    assert json.loads(data["screenshots"])
    assert data["artifacts"]


# ---------------------------------------------------------------------------
# 产物回取（签名 URL）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_artifact_route_serves_by_index(db_factory, tmp_path):
    run = await _make_run(db_factory, tmp_path)
    sig = share_link.sign(str(run.id))
    async with db_factory() as db:
        png_index = next(a["index"] for a in unity_api._artifacts(run) if a["kind"] == "image")
        response = await unity_api.get_artifact(str(run.id), png_index, db, sig=sig)
        assert response.media_type == "image/png"
        assert Path(response.path).name == "01_hud.png"

        video_index = next(a["index"] for a in unity_api._artifacts(run) if a["kind"] == "video")
        response = await unity_api.get_artifact(str(run.id), video_index, db, sig=sig)
        # MIME 写死成 video/mp4：猜错浏览器就是一块黑框（静默不播）
        assert response.media_type == "video/mp4"


@pytest.mark.asyncio
async def test_artifact_route_rejects_bad_signature(db_factory, tmp_path):
    run = await _make_run(db_factory, tmp_path)
    async with db_factory() as db:
        with pytest.raises(HTTPException) as err:
            await unity_api.get_artifact(str(run.id), 0, db, sig="123.abc")
        assert err.value.status_code == 403
        # 别的执行记录的签名也换不到这一条
        with pytest.raises(HTTPException):
            await unity_api.get_artifact(str(run.id), 0, db,
                                         sig=share_link.sign("00000000-0000-0000-0000-000000000000"))


@pytest.mark.asyncio
async def test_artifact_route_reports_pruned_and_missing(db_factory, tmp_path):
    run = await _make_run(db_factory, tmp_path)
    sig = share_link.sign(str(run.id))
    paths = json.loads(run.screenshots)
    Path(paths[0]).unlink()
    async with db_factory() as db:
        with pytest.raises(HTTPException) as err:
            await unity_api.get_artifact(str(run.id), 0, db, sig=sig)
        assert err.value.status_code == 410 and "已被清理" in err.value.detail
        with pytest.raises(HTTPException) as err:
            await unity_api.get_artifact(str(run.id), 99, db, sig=sig)
        assert err.value.status_code == 404


# ---------------------------------------------------------------------------
# 入队：先建记录再跑（前端拿得到 run_id）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_endpoint_returns_run_id_and_records_result(db_factory, monkeypatch):
    from src.app.services import unity_service

    seen: dict = {}

    async def fake_run(script_id, name, content, workdir=None):   # 不真起子进程
        seen["workdir"] = workdir
        return {"exit_code": 0, "status": "passed", "output": "PASS: ok\n",
                "duration_ms": 42, "script_file": "/tmp/case.py",
                "screenshots": json.dumps(["/tmp/01.png"])}

    monkeypatch.setattr(unity_service, "run_unity_script", fake_run)
    async with db_factory() as db:
        script = UnityScript(name="冒烟", content="print('PASS')\n")
        db.add(script)
        await db.commit()
        await db.refresh(script)

        class _BG:                       # BackgroundTasks 的最小替身
            def __init__(self): self.tasks = []
            def add_task(self, fn, *a, **kw): self.tasks.append((fn, a, kw))

        bg = _BG()
        out = await unity_api.run_script(str(script.id), user=None, db=db, background=bg)
        run_id = out.data["run_id"]
        assert run_id and bg.tasks, "执行记录先建好、任务后入队"

        # 运行目录入队就定好并落库：执行中读实时产物靠它（否则永远是 0 步 0 图）
        row = await unity_api._require_run(db, run_id)
        assert row.workdir and Path(row.workdir).is_dir()

        fn, args, kwargs = bg.tasks[0]
        await fn(*args, **kwargs)
    assert str(seen["workdir"]) == row.workdir, "执行用的是同一条目录"

    async with db_factory() as db:
        row = await unity_api._require_run(db, run_id)
        assert row.status == "passed" and row.exit_code == 0
        assert row.duration_ms == 42 and json.loads(row.screenshots) == ["/tmp/01.png"]
        script_row = await unity_service.get_script(db, str(script.id))
        assert script_row.status == "active"


# ---------------------------------------------------------------------------
# 删除用例（执行记录 + 磁盘产物一起清）
# ---------------------------------------------------------------------------

async def _make_script_with_files(factory, tmp_path: Path, *, status: str = "passed",
                                  age_s: float = 0.0):
    """建一条用例 + 一次执行 + 它的运行目录（截图/录像/轨迹/起跑线）。"""
    import datetime as dt

    from src.app.core.config import settings

    async with factory() as db:
        script = UnityScript(name="旧用例", content="print('PASS')\n")
        db.add(script)
        await db.flush()
        created = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(seconds=age_s)
        run = UnityScriptRun(script_id=script.id, status=status, exit_code=0,
                             screenshots=json.dumps([]))
        if age_s:
            run.created_at = created
        db.add(run)
        await db.commit()
        await db.refresh(script)

    folder = settings.workspace_dir / "default" / "unity-auto" / str(script.id) / "20260919_120000_旧用例"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "01_hud.png").write_bytes(b"\x89PNG\r\n\x1a\n shot")
    (folder / "run.mp4").write_bytes(b"\x00" * 2048)
    (settings.workspace_dir / "default" / "unity-auto" / str(script.id)
     / "start_state.json").write_text("{}", encoding="utf-8")
    # 共享的截图目录（不属于任何一条用例）：删除不该动它
    shared = settings.workspace_dir / "default" / "unity-auto" / "screenshots"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "07_xiake_retry.png").write_bytes(b"\x89PNG\r\n\x1a\n shared")
    return script


@pytest.mark.asyncio
async def test_delete_script_removes_runs_and_disk_files(db_factory, tmp_path, monkeypatch):
    """删掉一条用例：库里的执行记录与盘上的截图/录像/起跑线一起走。

    只删库不删盘会留下永远没人认领的运行目录（一次执行几十 MB），而人点"删除"想要
    的就是它彻底没了 —— 所以顺带回报"清掉了多少"，让人看得见。
    """
    from src.app.core.config import settings

    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    script = await _make_script_with_files(db_factory, tmp_path)
    home = tmp_path / "default" / "unity-auto" / str(script.id)

    async with db_factory() as db:
        out = await unity_api.delete_script(str(script.id), user=None, db=db)

    assert out.data["deleted"] is True and out.data["runs"] == 1
    assert out.data["files"] == 3 and out.data["bytes"] > 0    # 2 个产物 + 起跑线
    assert not home.exists()
    # 共享截图目录不动（删一条用例不该把别人的图带走）
    assert (tmp_path / "default" / "unity-auto" / "screenshots" / "07_xiake_retry.png").exists()

    async with db_factory() as db:
        from src.app.services import unity_service

        assert await unity_service.list_runs(db, str(script.id)) == []
        assert await unity_service.get_script(db, str(script.id)) is None


@pytest.mark.asyncio
async def test_delete_refuses_while_a_run_is_in_flight(db_factory, tmp_path, monkeypatch):
    """正在执行的用例删不掉（409）：后台任务还要往回写，产物还在生成。

    僵死的 running（进程被杀留下的，超过 `unity_service.run_stale_after_s()`）不拦 ——
    否则一条永远跑不完的记录会让脚本永远删不掉。阈值**从函数取**（= 执行预算 + 180s，
    预算可配），不写死数字：写死的话预算一调，这条测试就会用错的年龄构造"僵死"记录。
    """
    from src.app.core.config import settings
    from src.app.services import unity_service

    monkeypatch.setattr(settings, "workspace_dir", tmp_path)

    fresh = await _make_script_with_files(db_factory, tmp_path, status="running")
    async with db_factory() as db:
        with pytest.raises(HTTPException) as err:
            await unity_api.delete_script(str(fresh.id), user=None, db=db)
        assert err.value.status_code == 409 and "正在执行中" in err.value.detail

    stale = await _make_script_with_files(
        db_factory, tmp_path, status="running",
        age_s=unity_service.run_stale_after_s() + 60)
    async with db_factory() as db:
        out = await unity_api.delete_script(str(stale.id), user=None, db=db)
        assert out.data["deleted"] is True


@pytest.mark.asyncio
async def test_delete_missing_script_is_404(db_factory):
    async with db_factory() as db:
        with pytest.raises(HTTPException) as err:
            await unity_api.delete_script("00000000-0000-0000-0000-000000000000",
                                          user=None, db=db)
        assert err.value.status_code == 404


def test_purge_does_not_follow_symlinks(tmp_path, monkeypatch):
    """软链不跟：删的是链接，不是它指向的东西（一条用例删掉别人的目录就麻烦了）。"""
    from src.app.core.config import settings
    from src.app.services import unity_service as svc

    monkeypatch.setattr(settings, "workspace_dir", tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("别删我", encoding="utf-8")
    home = tmp_path / "default" / "unity-auto" / "sid-1"
    home.mkdir(parents=True)
    (home / "link").symlink_to(outside)
    (home / "shot.png").write_bytes(b"x")

    freed = svc.purge_script_files("sid-1")

    assert freed["files"] == 1 and not home.exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "别删我"


# ---------------------------------------------------------------------------
# 执行中的实时可见性（"轨迹实时刷新"要真能刷出来）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_running_run_reads_live_steps_and_artifacts(db_factory, tmp_path):
    """还在跑的记录：步骤轨迹与截图从**运行目录**现读，不等跑完。

    以前只有跑完才把产物清单写回 `screenshots`，于是执行中的详情页永远是
    "0 步 / 0 图 / 耗时 -"，人只能看着一潭死水猜它是不是卡了（实测：用户就是这么以为的）。
    """
    workdir = tmp_path / "run-now"
    workdir.mkdir()
    (workdir / "steps.jsonl").write_text(
        '{"i":1,"t":0.1,"action":"click","target":"UI/Bag","ms":30,"ok":true}\n',
        encoding="utf-8")
    (workdir / "01_hud.png").write_bytes(b"\x89PNG\r\n\x1a\n shot")
    (workdir / "case.py").write_text("print('x')\n", encoding="utf-8")   # 不是产物

    async with db_factory() as db:
        script = UnityScript(name="跑着的用例", content="print('PASS')\n")
        db.add(script)
        await db.flush()
        run = UnityScriptRun(script_id=script.id, status="running", workdir=str(workdir))
        db.add(run)
        await db.commit()
        await db.refresh(run)

    data = unity_api._run_dict(run)

    assert data["status"] == "running"
    assert [s["action"] for s in data["steps"]] == ["click"]
    names = {a["name"] for a in data["artifacts"]}
    assert names == {"steps.jsonl", "01_hud.png"}          # case.py 不在产物里
    assert data["artifacts_pruned"] is False
    assert data["elapsed_ms"] is not None and data["duration_ms"] is None
    # 跑完/被清理后：还是以 screenshots 那份清单为准
    run.status, run.screenshots = "passed", json.dumps([str(workdir / "01_hud.png")])
    after = unity_api._run_dict(run)
    assert [a["name"] for a in after["artifacts"]] == ["01_hud.png"]
    assert after["elapsed_ms"] is None
