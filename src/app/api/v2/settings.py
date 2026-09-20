"""Settings routes (设置模块): model provider + platform integration settings."""

import time

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.services.settings_service import (
    JUDGE_KEYS,
    LANGFUSE_KEYS,
    LANGFUSE_MONITOR_KEYS,
    MODEL_KEYS,
    PLATFORM_KEYS,
    SettingsService,
    mask_secrets,
)

router = APIRouter(prefix="/settings")


class SettingsUpdate(BaseModel):
    values: dict[str, str]


class PresetSave(BaseModel):
    name: str
    values: dict[str, str]


@router.get("/model", response_model=SuccessResponse, summary="Get model settings")
async def get_model_settings(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = await svc.get_namespace("model", MODEL_KEYS)
    return SuccessResponse(success=True, data=mask_secrets(values))


@router.put("/model", response_model=SuccessResponse, summary="Update model settings")
async def update_model_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    unknown = set(data.values) - set(MODEL_KEYS)
    values = {k: v for k, v in data.values.items() if k in MODEL_KEYS}
    await svc.set_many("model", values)
    written = svc.sync_env_file(values, MODEL_KEYS)
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "ignored": sorted(unknown),
        "env_written": written,
        "note": "模型设置已保存，下一轮对话起即时生效（无需重启服务）",
    })


# -- Langfuse (测评追踪) -------------------------------------------------------

@router.get("/langfuse", response_model=SuccessResponse, summary="Get Langfuse settings")
async def get_langfuse_settings(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = await svc.langfuse_values()
    return SuccessResponse(success=True, data=mask_secrets(values))


@router.put("/langfuse", response_model=SuccessResponse, summary="Update Langfuse settings")
async def update_langfuse_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    unknown = set(data.values) - set(LANGFUSE_KEYS)
    values = {k: v for k, v in data.values.items() if k in LANGFUSE_KEYS}
    await svc.set_many("langfuse", values)
    written = svc.sync_env_file(values, LANGFUSE_KEYS)
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "ignored": sorted(unknown), "env_written": written,
        "note": "已保存。网页触发的测评立刻生效；CLI / 容器内进程读的是 .env，"
                "重启后生效（容器会随 .env 重建）。",
    })


@router.post("/langfuse/test", response_model=SuccessResponse, summary="Test Langfuse connectivity")
async def test_langfuse_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    """按表单里的值探活：能不能连上、key 属于哪个项目、里面有多少条 trace。

    和模型设置的「测试连接」同一套路：先验后存，避免把错 key 存进去之后
    测评静默不上报（那种故障最难查）。
    """
    from src.app.eval.langfuse_client import LangfuseClient

    svc = SettingsService(db)
    values = await svc.resolve_masked("langfuse", data.values or {})
    merged = await svc.langfuse_values()
    merged.update({k: str(v) for k, v in values.items() if v is not None})

    enabled = str(merged.get("langfuse_enabled", "")).strip().lower() not in ("", "0", "false", "no")
    host = merged.get("langfuse_base_url") or ""
    public_key = merged.get("langfuse_public_key") or ""
    secret_key = merged.get("langfuse_secret_key") or ""

    missing = [name for name, value in (
        ("地址", host), ("Public Key", public_key), ("Secret Key", secret_key)) if not value]
    if missing:
        return SuccessResponse(success=True, data={
            "ok": False, "error": f"缺少配置：{'、'.join(missing)}"})
    if not enabled:
        return SuccessResponse(success=True, data={
            "ok": False, "error": "Langfuse 已关闭（enabled = false），测评不会上报"})

    started = time.monotonic()
    client = LangfuseClient(host=host, public_key=public_key, secret_key=secret_key,
                            enabled=True)
    try:
        projects = client._get("/api/public/projects")  # noqa: SLF001 — probe only
        latency = int((time.monotonic() - started) * 1000)
        if projects is None:
            return SuccessResponse(success=True, data={
                "ok": False, "latency_ms": latency,
                "error": f"连不上或认证失败：{client.host}（检查地址是否可达、key 是否属于该项目）"})
        items = projects.get("data") or []
        project = items[0] if items else {}
        # 项目 id 是拼 trace 链接用的（/project/<id>/traces/<traceId>）
        client._project_id = project.get("id")  # noqa: SLF001
        return SuccessResponse(success=True, data={
            "ok": True, "latency_ms": latency, "host": client.host,
            "project_id": project.get("id"), "project_name": project.get("name"),
            "organization": (project.get("organization") or {}).get("name"),
            "projects": len(items),
        })
    except Exception as exc:  # noqa: BLE001
        return SuccessResponse(success=True, data={
            "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        client.close()


# -- Langfuse 监控（日常智能体使用链路）---------------------------------------

@router.get("/langfuse-monitor", response_model=SuccessResponse,
            summary="Get monitoring Langfuse settings")
async def get_monitor_langfuse_settings(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = await svc.monitor_langfuse_values()
    return SuccessResponse(success=True, data=mask_secrets(values))


@router.put("/langfuse-monitor", response_model=SuccessResponse,
            summary="Update monitoring Langfuse settings")
async def update_monitor_langfuse_settings(data: SettingsUpdate, user: CurrentUserDep,
                                           db: DbSessionDep):
    svc = SettingsService(db)
    unknown = set(data.values) - set(LANGFUSE_MONITOR_KEYS)
    values = {k: v for k, v in data.values.items() if k in LANGFUSE_MONITOR_KEYS}
    await svc.set_many("langfuse_monitor", values)
    written = svc.sync_env_file(values, LANGFUSE_MONITOR_KEYS)
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "ignored": sorted(unknown), "env_written": written,
        "note": "已保存。日常对话的 trace 从**下一轮**开始上报到监控 Langfuse"
                "（agent 进程每 15 秒重读一次 .env，不需要重启容器）。",
    })


@router.post("/langfuse-monitor/test", response_model=SuccessResponse,
             summary="Test monitoring Langfuse connectivity")
async def test_monitor_langfuse_settings(data: SettingsUpdate, user: CurrentUserDep,
                                         db: DbSessionDep):
    """按表单里的值探活：连不上就当场报，别等到想看 trace 时才发现没有。"""
    from src.app.eval.langfuse_client import LangfuseClient

    svc = SettingsService(db)
    values = await svc.resolve_masked("langfuse_monitor", data.values or {})
    merged = await svc.monitor_langfuse_values()
    merged.update({k: str(v) for k, v in values.items() if v is not None})

    enabled = str(merged.get("langfuse_monitor_enabled", "")).strip().lower() \
        not in ("", "0", "false", "no", "off")
    host = (merged.get("langfuse_monitor_base_url") or "").strip()
    public_key = (merged.get("langfuse_monitor_public_key") or "").strip()
    secret_key = (merged.get("langfuse_monitor_secret_key") or "").strip()
    missing = [name for name, value in (
        ("LANGFUSE_MONITOR_BASE_URL", host),
        ("LANGFUSE_MONITOR_PUBLIC_KEY", public_key),
        ("LANGFUSE_MONITOR_SECRET_KEY", secret_key),
    ) if not value]
    if missing:
        return SuccessResponse(success=True, data={
            "ok": False, "error": f"缺少配置：{'、'.join(missing)}"})
    if not enabled:
        return SuccessResponse(success=True, data={
            "ok": False, "error": "监控已关闭（enabled = false），日常对话不会上报"})

    started = time.monotonic()
    client = LangfuseClient(host=host, public_key=public_key, secret_key=secret_key,
                            enabled=True)
    try:
        projects = client._get("/api/public/projects")  # noqa: SLF001 — 只做探活
        latency = int((time.monotonic() - started) * 1000)
        if projects is None:
            return SuccessResponse(success=True, data={
                "ok": False, "latency_ms": latency,
                "error": f"连不上或认证失败：{client.host}（检查地址是否可达、key 是否属于该项目）"})
        items = projects.get("data") or []
        project = items[0] if items else {}
        client._project_id = project.get("id")  # noqa: SLF001
        return SuccessResponse(success=True, data={
            "ok": True, "latency_ms": latency, "host": client.host,
            "project_id": project.get("id"), "project_name": project.get("name"),
            "organization": (project.get("organization") or {}).get("name"),
            "projects": len(items),
        })
    except Exception as exc:  # noqa: BLE001
        return SuccessResponse(success=True, data={
            "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        client.close()


# -- LLM 裁判 (测评打分) -------------------------------------------------------

@router.get("/judge", response_model=SuccessResponse, summary="Get judge settings")
async def get_judge_settings(user: CurrentUserDep, db: DbSessionDep):
    """裁判配置 + **实际生效的端点**。

    留空的项会回退到主 LLM——界面必须把"实际用的是谁"一起显示，否则用户看到
    卡片上有个模型名会以为自己配过（这正是之前"judge：glm-4.7 找不到在哪配"的成因）。
    """
    from src.app.eval.scorers import judge_endpoint_from_values

    svc = SettingsService(db)
    values = await svc.judge_values()
    endpoint = judge_endpoint_from_values(values, await svc.model_values())
    return SuccessResponse(success=True, data={
        "values": mask_secrets(values),
        "effective": {"model": endpoint.model, "base_url": endpoint.base_url,
                      "source": endpoint.source, "configured": bool(endpoint.api_key)},
    })


@router.put("/judge", response_model=SuccessResponse, summary="Update judge settings")
async def update_judge_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    unknown = set(data.values) - set(JUDGE_KEYS)
    values = {k: v for k, v in data.values.items() if k in JUDGE_KEYS}
    await svc.set_many("judge", values)
    written = svc.sync_env_file(values, JUDGE_KEYS)
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "ignored": sorted(unknown), "env_written": written,
        "note": "已保存。网页触发的测评**下一批次立刻生效**（裁判端点是每批解析一次）；"
                "CLI / 容器内其他进程读 .env，重启后生效。",
    })


@router.post("/judge/test", response_model=SuccessResponse, summary="Test judge connectivity")
async def test_judge_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    """按表单里的值真跑一次裁判自检：能不能连、认不认这个模型、会不会按 JSON 回话。

    先验后存：裁判端点配错时，测评会**每条用例都变成执行异常**（不是静默低分），
    那种批次跑到一半才发现就白等了。自检走的是和真实打分同一条通道
    （见 ``LlmJudge.probe``），所以"连通"就等于"能判分"。
    """
    from src.app.eval.scorers import LlmJudge, judge_endpoint_from_values

    svc = SettingsService(db)
    values = await svc.resolve_masked("judge", data.values or {})
    merged = await svc.judge_values()
    merged.update({k: str(v) for k, v in values.items() if v is not None})
    endpoint = judge_endpoint_from_values(merged, await svc.model_values())

    if not endpoint.api_key:
        return SuccessResponse(success=True, data={
            "ok": False, "error": "缺少 API Key（JUDGE_API_KEY / LLM_API_KEY / DEEPSEEK_API_KEY 都为空）"})

    started = time.monotonic()
    try:
        verdict = await LlmJudge(endpoint).probe()
        return SuccessResponse(success=True, data={
            "ok": True, "latency_ms": int((time.monotonic() - started) * 1000),
            "model": endpoint.model, "base_url": endpoint.base_url,
            "source": endpoint.source, "verdict": verdict,
        })
    except Exception as exc:  # noqa: BLE001
        return SuccessResponse(success=True, data={
            "ok": False, "latency_ms": int((time.monotonic() - started) * 1000),
            "model": endpoint.model, "source": endpoint.source,
            "error": f"{type(exc).__name__}: {exc}"})


# -- Model presets (模型预设) -------------------------------------------------

@router.get("/model/presets", response_model=SuccessResponse, summary="List model presets")
async def list_model_presets(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    presets = [
        {"name": p["name"], "saved_at": p.get("saved_at"), "values": mask_secrets(p.get("values", {}))}
        for p in await svc.list_presets()
    ]
    return SuccessResponse(success=True, data=presets)


@router.post("/model/presets", response_model=SuccessResponse, summary="Save current form as a preset")
async def save_model_preset(data: PresetSave, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = {k: v for k, v in data.values.items() if k in MODEL_KEYS}
    # masked secrets in the form -> real stored values, so presets are self-contained
    values = await svc.resolve_masked("model", values)
    try:
        entry = await svc.save_preset(data.name, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return SuccessResponse(success=True, data={"name": entry["name"], "saved_at": entry["saved_at"]})


@router.post("/model/presets/{name}/apply", response_model=SuccessResponse, summary="Apply a preset")
async def apply_model_preset(name: str, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    preset = await svc.get_preset(name)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"预设不存在: {name}")
    values = {k: v for k, v in preset.get("values", {}).items() if k in MODEL_KEYS}
    await svc.set_many("model", values)
    written = svc.sync_env_file(values, MODEL_KEYS)
    await db.commit()
    current = await svc.get_namespace("model", MODEL_KEYS)
    return SuccessResponse(success=True, data={
        "applied": name, "env_written": written, "values": mask_secrets(current),
    })


@router.delete("/model/presets/{name}", response_model=SuccessResponse, summary="Delete a preset")
async def delete_model_preset(name: str, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    if not await svc.delete_preset(name):
        raise HTTPException(status_code=404, detail=f"预设不存在: {name}")
    await db.commit()
    return SuccessResponse(success=True, data={"deleted": name})


# -- Connectivity test (连通性校验) -------------------------------------------

@router.post("/model/test", response_model=SuccessResponse, summary="Test model connectivity")
async def test_model_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    from src.app.agents.testcase.model_factory import build_test_model

    svc = SettingsService(db)
    values = {k: v for k, v in data.values.items() if k in MODEL_KEYS}
    values = await svc.resolve_masked("model", values)
    try:
        model = build_test_model(values, timeout=30)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — provider init errors must be readable
        raise HTTPException(status_code=500, detail=f"构建测试模型失败: {exc}") from exc

    t0 = time.monotonic()
    try:
        await model.ainvoke([HumanMessage(content="连通性测试，请只回复：pong")])
        result = {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000)}
    except Exception as exc:  # noqa: BLE001 — surface any provider error to the form
        result = {"ok": False, "error": str(exc)[:500]}
    result["model"] = values.get("llm_model") or values.get("deepseek_model") or "deepseek-chat"
    return SuccessResponse(success=result["ok"], data=result)


@router.get("/platform", response_model=SuccessResponse, summary="Get platform integration settings")
async def get_platform_settings(user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    values = await svc.get_namespace("platform", PLATFORM_KEYS)
    return SuccessResponse(success=True, data=mask_secrets(values))


@router.put("/platform", response_model=SuccessResponse, summary="Update platform settings")
async def update_platform_settings(data: SettingsUpdate, user: CurrentUserDep, db: DbSessionDep):
    svc = SettingsService(db)
    unknown = set(data.values) - set(PLATFORM_KEYS)
    values = {k: v for k, v in data.values.items() if k in PLATFORM_KEYS}
    await svc.set_many("platform", values)
    written = svc.sync_env_file(values, PLATFORM_KEYS)
    await db.commit()
    return SuccessResponse(success=True, data={
        "saved": sorted(values), "ignored": sorted(unknown), "env_written": written,
    })
