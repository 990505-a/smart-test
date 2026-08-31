"""Settings routes (设置模块): model provider + platform integration settings."""

import time

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from src.app.api.deps import DbSessionDep
from src.app.api.v2.auth import CurrentUserDep
from src.app.db.schemas.common import SuccessResponse
from src.app.services.settings_service import (
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
    from src.app.agents.testcase.model_factory import build_test_models

    svc = SettingsService(db)
    values = {k: v for k, v in data.values.items() if k in MODEL_KEYS}
    values = await svc.resolve_masked("model", values)
    try:
        models = build_test_models(values, timeout=30)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — provider init errors must be readable
        raise HTTPException(status_code=500, detail=f"构建测试模型失败: {exc}") from exc

    async def _ping(model, label: str) -> dict:
        t0 = time.monotonic()
        try:
            await model.ainvoke([HumanMessage(content="连通性测试，请只回复：pong")])
            return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000)}
        except Exception as exc:  # noqa: BLE001 — surface any provider error to the form
            return {"ok": False, "error": str(exc)[:500]}

    results = {"text": {**await _ping(models["text"], "text"),
                        "model": values.get("llm_model") or values.get("deepseek_model") or "deepseek-chat"}}
    if models["vision"] is not None:
        results["vision"] = {**await _ping(models["vision"], "vision"),
                             "model": values.get("vision_model")}
    else:
        results["vision"] = {"ok": True, "skipped": True,
                             "model": "复用文本模型"}
    ok = all(r.get("ok") for r in results.values())
    return SuccessResponse(success=ok, data=results)


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
