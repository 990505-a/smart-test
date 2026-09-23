"""显卡设备丢失（DXGI_ERROR_DEVICE_REMOVED）熔断。

现场（2026-09-23 10:26，整机卡死到只能长按电源）：Unity 日志里 85 条
``D3D11: Failed to create RenderTexture … error 0x887a0005`` 之后是
``Failed to present D3D11 swapchain due to device reset/removed. … the editor will
shut down``。显卡没了这件事软件修不了，能修的只有"平台别继续往上叠负载"：
识别签名 → 一律拒绝工具调用 → 开局与录像直接拦下 → 等 Unity 换成新实例自动解除。

这里钉住的就是这条链。**没有一条用例要求"继续把调用发出去"** —— 那正是当时
把机器推到资源耗尽的行为。
"""

from __future__ import annotations

import asyncio

import pytest

from src.app.services import unity_bridge, unity_service


@pytest.fixture(autouse=True)
def _clean_latch():
    unity_bridge.clear_gpu_loss("测试前置")
    yield
    unity_bridge.clear_gpu_loss("测试收尾")


#: Unity 真日志里的原话（截断成一段）
_LIVE_EVIDENCE = (
    "D3D11: Failed to create RenderTexture (828 x 1472 fmt 26 aa 1), error 0x887a0005\n"
    "Failed to present D3D11 swapchain due to device reset/removed.This error can happen "
    "if you draw or dispatch very expensive workloads to the GPU. This is an unrecoverable "
    "error and the editor will shut down."
)


def test_detects_device_removed_signature():
    assert "887a0005" in unity_bridge._gpu_evidence_in(_LIVE_EVIDENCE)
    # 单独一条也算：显卡开始拒绝创建资源，就是这条路的起点
    assert unity_bridge._gpu_evidence_in("D3D11: Failed to create RenderTexture (16 x 29)") != ""
    assert unity_bridge._gpu_evidence_in("Failed to present D3D11 swapchain due to device reset/removed") != ""


def test_ignores_unrelated_errors():
    assert unity_bridge._gpu_evidence_in("NullReferenceException: Object reference not set") == ""
    assert unity_bridge._gpu_evidence_in({"success": False, "error": "找不到对象 UI/Bag"}) == ""


def test_mark_found_even_next_to_huge_image_blob():
    """截图结果里带着几十万字符的 base64 —— 签名还是得找到（但别整个遍历）。"""
    payload = {"data": {"image": "data:image/png;base64," + "A" * 300_000},
               "text": "error 0x887a0005 while presenting"}
    assert "887a0005" in unity_bridge._gpu_evidence_in(payload)


def test_latch_then_clear():
    assert unity_bridge.gpu_device_lost() == ""
    assert unity_bridge.note_gpu_loss({"error": "D3D11: failed to create RenderTexture"}) is True
    assert "failed to create" in unity_bridge.gpu_device_lost().lower()
    unity_bridge.clear_gpu_loss("测试")
    assert unity_bridge.gpu_device_lost() == ""


def test_guard_call_refuses_and_does_not_touch_unity(monkeypatch):
    """熔断后底层函数**一次都不能被调用** —— 那才是"平台停手"。"""
    called: list[str] = []

    def _boom():
        called.append("called")
        return {"success": True}

    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "")   # 探活：读不到 → 保持熔断
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)

    out = asyncio.run(unity_bridge._guard_call(_boom))

    assert called == []
    assert out["success"] is False and out["gpu_device_lost"] is True
    assert "显卡设备丢失" in out["error"]
    assert "Editor.log" in out["error"]


def test_guard_call_latches_from_result():
    async def _run():
        return await unity_bridge._guard_call(lambda: {"success": False, "error": _LIVE_EVIDENCE})

    out = asyncio.run(_run())

    assert out["success"] is False                     # 这一次照样把真结果给出去
    assert unity_bridge.gpu_device_lost() != ""         # 但状态已经变成熔断


def test_guard_call_latches_from_exception():
    async def _run():
        def _raise():
            raise unity_bridge.UnityBridgeError("Unity said: Failed to present D3D11 swapchain")

        return await unity_bridge._guard_call(_raise)

    out = asyncio.run(_run())

    assert unity_bridge.gpu_device_lost() != ""
    assert "D3D11" in out["error"]


def test_auto_clear_when_unity_restarts(monkeypatch):
    """换实例（Unity 重启过）就自动解除 —— 否则一次现象把平台焊死到进程结束。"""
    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "unity-old@1")
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)
    assert unity_bridge.gpu_device_lost() != ""

    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "unity-new@2")
    unity_bridge._gpu_state["probed"] = 0.0             # 跳过节流，模拟"20 秒后再探"
    assert unity_bridge._gpu_recheck_sync() is False
    assert unity_bridge.gpu_device_lost() == ""


def test_recheck_keeps_latch_when_instance_unreadable(monkeypatch):
    """读不到实例（编辑器还没起来）→ **保持熔断**：宁可多拦一次，别赌。"""
    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "unity-old@1")
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)
    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "")
    unity_bridge._gpu_state["probed"] = 0.0

    assert unity_bridge._gpu_recheck_sync() is True
    assert unity_bridge.gpu_device_lost() != ""


def test_record_start_refuses_while_gpu_lost():
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)
    with pytest.raises(unity_bridge.UnityBridgeError) as exc:
        unity_bridge.unity_on_cached_client().record_start()
    assert "显卡设备已丢失" in str(exc.value)


def test_run_unity_script_does_not_start_while_gpu_lost(tmp_path):
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)

    out = asyncio.run(unity_service.run_unity_script("case-x", "冒烟", "print(1)",
                                                     workdir=tmp_path))

    assert out["status"] == "error" and out["exit_code"] == -3
    assert out["failure"]["kind"] == "environment"
    assert "显卡" in out["failure"]["summary"]
    assert not (tmp_path / "case.py").exists()      # 连脚本都没落盘：根本没开局


def test_status_reports_alarm_and_advice(monkeypatch):
    """状态页要能直接说出"是显卡" —— 不然用户看到的就是"平台莫名其妙不动了"。"""
    monkeypatch.setattr(unity_bridge, "_instance_key", lambda: "")
    monkeypatch.setattr(unity_bridge, "_rpc", lambda *_a, **_k: [])
    monkeypatch.setattr(unity_bridge, "_instances_sync", lambda _c: [])
    monkeypatch.setattr(unity_bridge, "_editor_state_sync", lambda _c: None)
    monkeypatch.setattr(unity_bridge, "_project_external_changes_dirty", lambda _c: False)
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)

    st = asyncio.run(unity_bridge.status())

    assert st["gpu_device_lost"] is True
    assert "0x887a0005" in st["gpu_evidence"]
    assert any("显卡设备丢失" in line for line in st["advice"])


def test_clear_gpu_alarm_service_wrapper():
    unity_bridge.note_gpu_loss(_LIVE_EVIDENCE)

    out = unity_service.clear_gpu_alarm()

    assert out["cleared"] is True
    assert unity_bridge.gpu_device_lost() == ""
    assert unity_service.clear_gpu_alarm()["cleared"] is False   # 本来就没熔断


# --- 截图主路径不能带"被插件安检拦下"的代码 -------------------------------
#
# 2026-09-23 11:29 实测：`execute_code` 的安检有一条 `Blocked pattern`，命中的整段
# 代码会被原样拒绝 —— 文件版截图里那句"先删同名文件"（System.IO.File.Delete）正好
# 撞上它。表现极具欺骗性：三条路都回 success，其实每次都退到**相机截图**（看不见
# Screen Space - Overlay 的 UI，整个平台存在的理由就是那层 UI），而 note 里只看得到
# texture 版那句"返回 null"，真凶被盖住。这里把两条都钉住。

def test_screenshot_primary_path_avoids_blocked_patterns():
    code = unity_bridge._CS_SCREENSHOT_FILE
    assert "System.IO.File.Delete" not in code
    assert "CaptureScreenshot(" in code
    # 文件名要够独特（不靠"先删"来保证干净）：毫秒 + Guid
    assert "yyyyMMdd_HHmmss_fff" in code and "Guid.NewGuid" in code


def test_capture_overlay_reports_every_failed_path(monkeypatch):
    """两条路的错误都要报出来，别只留最后一条。"""
    monkeypatch.setattr(unity_bridge, "_overlay_state",
                        {"fails": 0, "why": "", "last_error": ""})

    def _fake_exec(_snippet, client=None, call=None):
        return {"success": False, "error": "Blocked pattern detected: System.IO.File.Delete"}

    monkeypatch.setattr(unity_bridge, "_exec_csharp_sync", _fake_exec)

    assert unity_bridge._capture_overlay(None) is None
    why = unity_bridge._overlay_state["why"]
    assert "文件版" in why and "texture 版" in why
    assert "Blocked pattern" in why


def test_overlay_note_not_shown_after_a_single_failure(monkeypatch):
    """一次失败不该改道：下一次照样从文件版开始（用户口径：Play 下截图一直可用）。"""
    monkeypatch.setattr(unity_bridge, "_overlay_state",
                        {"fails": 0, "why": "", "last_error": ""})
    unity_bridge._overlay_state["fails"] = 1

    assert unity_bridge._overlay_disabled_reason() == ""
    unity_bridge._overlay_state["fails"] = 5
    unity_bridge._overlay_state["why"] = "文件版：xxx"

    assert "文件版" in unity_bridge._overlay_disabled_reason()


# --- Editor.log 巡检：插件掉线后唯一还能读到的现场 -----------------------------
#
# 2026-09-23 12:25 那次：插件 WS 掉线（1005）、熔断没响，页面上只显示"未连接"，
# 因为**证据只写在 Unity 自己的 Editor.log 里**，而平台从不读它。这批用例钉住这条通路。

def test_scan_editor_log_finds_device_loss(tmp_path, monkeypatch):
    log = tmp_path / "Editor.log"
    log.write_text("初始化完成\n"
                   "d3d11: failed to create buffer (target 0x1 mode 0 size 480) [0x887A0005]\n"
                   "d3d11: failed to create buffer (target 0x2 mode 0 size 60) [0x887A0005]\n",
                   encoding="utf-8")
    monkeypatch.setattr(unity_bridge, "editor_log_path", lambda: log)

    evidence = unity_bridge.scan_editor_log(force=True)

    assert "0x887A0005" in evidence
    assert "failed to create buffer" in evidence
    assert unity_bridge.gpu_device_lost() != ""       # 顺手置熔断


def test_scan_editor_log_clean_log_does_not_latch(tmp_path, monkeypatch):
    log = tmp_path / "Editor.log"
    log.write_text("Compile finished\nAsset Pipeline Refresh: 0.02 seconds\n", encoding="utf-8")
    monkeypatch.setattr(unity_bridge, "editor_log_path", lambda: log)

    assert unity_bridge.scan_editor_log(force=True) == ""
    assert unity_bridge.gpu_device_lost() == ""


def test_scan_editor_log_missing_file_is_not_an_error(monkeypatch):
    monkeypatch.setattr(unity_bridge, "editor_log_path", lambda: None)

    assert unity_bridge.scan_editor_log(force=True) == ""
    assert unity_bridge.gpu_device_lost() == ""
    assert unity_bridge.editor_log_age_s() is None


def test_scan_editor_log_caches_by_mtime(tmp_path, monkeypatch):
    """日志一直在长，纯按 mtime 缓存等于每次都读 —— 同一个 mtime + 5 秒内只读一次。"""
    log = tmp_path / "Editor.log"
    log.write_text("d3d11: failed to create buffer [0x887A0005]\n", encoding="utf-8")
    monkeypatch.setattr(unity_bridge, "editor_log_path", lambda: log)

    reads = {"n": 0}
    real_open = type(log).open

    def _counting_open(self, *a, **k):
        if self == log:
            reads["n"] += 1
        return real_open(self, *a, **k)

    monkeypatch.setattr(type(log), "open", _counting_open)
    unity_bridge.scan_editor_log(force=True)
    first = reads["n"]
    unity_bridge.scan_editor_log()          # 同一个 mtime、TTL 内
    assert reads["n"] == first


def test_guard_call_scans_editor_log_when_call_fails(tmp_path, monkeypatch):
    """调用失败时顺手看一眼日志：显卡丢失要当场认出来，而不是只报"未连接"。"""
    log = tmp_path / "Editor.log"
    log.write_text("d3d11: failed to create buffer [0x887A0005]\n", encoding="utf-8")
    monkeypatch.setattr(unity_bridge, "editor_log_path", lambda: log)

    async def _run():
        def _fail():
            raise unity_bridge.UnityBridgeError("无法连接 Unity（插件已掉线）")

        return await unity_bridge._guard_call(_fail)

    out = asyncio.run(_run())

    assert out["gpu_device_lost"] is True and out["stop"] is True
    assert "显卡设备丢失" in out["error"]
