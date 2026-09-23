"""Unity 自动化服务层（Unity 自动化模块）。

这一层做三件事，工具层与 REST 层共用：

1. **操作**：全部转发给 ``services/unity_bridge.py``（标准 MCP）。平台不再自带
   任何游戏侧代码 —— 旧版内嵌的 unity-ui-test python 层（Lua 客户端 / UI 操作 /
   TMP 文本断言 / GM 命令）连同那份游戏专属知识一起删除了。
2. **用例沉淀**：``UnityScript`` 的读/写/列（与 Web-UI 模块同构的入库契约）。
3. **执行**：把脚本落盘 + 注入 prelude（``u = Unity()``）后在子进程里跑，
   退出码 => passed / failed / error，并收集本次运行产出的截图。

生成脚本的模型调用与 Playwright 版同构（``generate_script`` ↔
``playwright_service.generate_spec``），提示词只写**流水线契约**，写法规范在
``skills/unity-ui-test`` 里，避免两处描述漂移。
"""

from __future__ import annotations

import asyncio
import ast
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from src.app.core.async_subprocess import run_subprocess
from src.app.core.config import settings
from src.app.db.models.unity_script import UnityScript
from src.app.services import unity_bridge, unity_recorder

ROOT = Path(__file__).resolve().parents[3]

def run_timeout_s() -> float:
    """单次用例执行的**墙钟预算**（秒，默认 1800 = 30 分钟）。

    读的是**设置**（`settings.unity_run_timeout_s` ← `.env` 的 `UNITY_RUN_TIMEOUT_S`），
    不是导入时从 `os.environ` 取一次的常量 —— 后者有个安静的坑：`.env` 只有 langgraph
    进程会 load_dotenv 进 os.environ（start_server.py），FastAPI 进程读不到，于是
    "对话内执行"和"页面点运行"两条路各自一套上限。设置对象在每个进程都读得到，
    真·环境变量照旧能覆盖，而且改完重启即生效（不需要改代码）。

    这段预算是**为了收尾**留的：跑完用例还要抓失败现场、把上千帧合成录像，都算在里面。
    用例自己的等待上限（`u.wait_for(timeout=…)`）是另一回事。到点平台硬杀子进程，
    并补一次录像收尾（`_salvage_recording`）—— 不留无人值守的钩子。
    """
    try:
        return max(60.0, float(settings.unity_run_timeout_s))
    except (TypeError, ValueError):  # 配置被写坏时不至于让用例跑不起来
        return 1800.0


def run_stale_after_s() -> float:
    """执行记录挂 `running` 多久就当它是僵死的（比预算宽 180s）。

    宽出来的那截是给收尾的：合成录像 + 写失败现场 + 网络往返。比执行预算窄的话，
    一条**正在跑**的记录会被页面上标成"僵死"、还能被删掉。
    """
    return run_timeout_s() + 180.0



# ===========================================================================
# 操作（转发给桥）
# ===========================================================================

async def status() -> dict:
    """桥 / 服务器 / 编辑器状态。

    额外带 ``run_timeout_s``：单次执行的墙钟预算。智能体判断"这条用例能不能一次
    跑完"时必须知道它 —— 否则只能去翻 `.env`（2026-09-23 实测它就是这么干的，
    一次会话为此读了配置文件、平台源码，还 grep 了全仓）。
    """
    out = await unity_bridge.status()
    if isinstance(out, dict):
        out.setdefault("run_timeout_s", settings.unity_run_timeout_s)
    return out


async def editor_action(action: str) -> dict:
    """play / pause / stop / state / refresh。"""
    return await unity_bridge.editor_action(action)


async def start_line(scene: str = "", wait_for: str = "") -> dict:
    """看当前在不在起跑线（**只读**：平台不做复位，见本文件「起跑线」一节）。"""
    return await unity_bridge.check_start_line(scene=scene, wait_for=wait_for)


async def find_objects(**kwargs) -> dict:
    return await unity_bridge.find_objects(**kwargs)


async def hierarchy(root: str = "", depth: int = 3, max_nodes: int = 80) -> dict:
    """场景/子树层级（路径 + 可见性 + 组件 + 文本）—— 探索界面的第一步。"""
    return await unity_bridge.hierarchy(root, depth, max_nodes)


async def find_by_text(text: str, root: str = "", limit: int = 20) -> dict:
    """按界面上的文字反查对象（含往上最近的可点祖先）。"""
    return await unity_bridge.find_by_text(text, root, limit)


async def object_text(target: str) -> dict:
    """读对象及其子孙的文本（"这个面板现在显示什么"）。"""
    return await unity_bridge.subtree_text(target)


async def object_info(target: str, component: str = "") -> dict:
    return await unity_bridge.object_info(target, component)


async def click(target: str) -> dict:
    return await unity_bridge.click(target)


async def set_text(target: str, text: str) -> dict:
    return await unity_bridge.set_text(target, text)


async def wait_for(target: str, timeout_s: float = 10.0, state: str = "present") -> dict:
    return await unity_bridge.wait_for(target, timeout_s, state)


async def console(action: str = "get", filter_text: str = "", limit: int = 50,
                  types: str = "all") -> dict:
    return await unity_bridge.console(action, filter_text, limit, types)


async def screenshot(save_path: str | None = None) -> dict:
    return await unity_bridge.screenshot(save_path)


async def exec_csharp(code: str, timeout: float = 60.0) -> dict:
    return await unity_bridge.exec_csharp(code, timeout)


async def run_tests(mode: str = "PlayMode", filter_text: str = "",
                    timeout_s: float = 300.0) -> dict:
    return await unity_bridge.run_tests(mode, filter_text, timeout_s)


async def mcp_tools(refresh: bool = False) -> dict:
    return await unity_bridge.tools(refresh=refresh)


async def mcp_call(tool: str, args: dict | None = None, timeout: float = 60.0) -> dict:
    return await unity_bridge.call(tool, args, timeout)


# ===========================================================================
# 生成（LLM；与 playwright_service.generate_spec 同构）
# ===========================================================================

SCRIPT_PROMPT = """你是资深 Unity 客户端自动化测试工程师。请把下面的测试意图写成**一份可直接运行的 Python 用例脚本**（驱动平台注入的 `u` 客户端操作 Unity）。

这是一次**草稿生成**调用：你只拿到输出格式契约，看不到平台技能库里的完整规范。
探索手法、等待策略、断言写法以 `skills/unity-ui-test` 的规范为准（生成后由人和
用例智能体按那份规范复核）。所以这里只写**流水线契约**，不重复业务规范。

输出契约：
1. 只输出代码，用 ```python 围栏包裹，不要任何解释文字。
2. **不要 import 任何东西、不要构造客户端**：prelude 已经注入了 `u`（Unity 客户端）
   和 `UnityBridgeError`。脚本从第一行开始直接用 `u`。
3. **开头声明起跑线**（平台每次执行前会自动复位到这里 —— 用例之间互不污染，
   也省掉"先手动打开某场景再进 Play"这类手工前置）：
   ```python
   RESET = {"scene": "Assets/…/起始场景.unity", "wait_for": "起跑线标志物"}
   ```
   不知道确切场景/标志物就写 `RESET = True`（用平台记住的上次跑通现场），
   或干脆不写（平台也会兜底）；`RESET = False` 表示"接着现场跑，不复位"。
4. 顺序永远是：确认状态 → 等对象出现 → 操作 → 断言 → 截图存证。
   例：
   ```python
   u.expect_exists("LoginWindow", timeout=15)
   u.click("LoginWindow/StartButton")
   u.expect_text("MainHud/LevelText", "Lv.")
   u.screenshot("main_hud.png")
   ```
5. 断言必须给出具体期望值（`expect_text/expect_exists/expect_absent` 或 `assert` 表达式），
   禁止 `assert True` 这类空断言。
   **关面板/关窗口用 `u.expect_hidden(...)`**：uGUI 的面板关闭通常是 `SetActive(false)`，
   对象还在场景里，用 `expect_absent` 会超时（报错会提示这一点）。
6. 用**层级路径**定位对象（`Window/Child/Button`），次选名字；不要用只在某次运行里
   成立的临时 id。
7. 每个用例至少 1 处 `u.screenshot(...)` 存证；截图文件名用英文短横线风格。
8. 不写 `time.sleep` 硬等：用 `u.wait_for(...)` / `expect_*` 自带超时。
9. 打印一行 `PASS: <做了什么>` 作为成功标记；失败就让它抛异常（异常 = 用例失败）。

额外要求：
{extra}

测试意图：
{intent}
"""


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    return match.group(1).rstrip() + "\n" if match else text.rstrip() + "\n"


async def generate_script(*, intent: str, extra_requirements: str = "") -> dict:
    """把测试意图变成第一版用例脚本（草稿，需实跑验证后再入库）。"""
    from src.app.core.llms import get_deepseek_model

    prompt = SCRIPT_PROMPT.format(intent=intent,
                                  extra=extra_requirements or "- 无额外要求。")
    try:
        model = get_deepseek_model()
        response = await model.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"LLM 调用失败: {exc}"}
    text = response.content if isinstance(response.content, str) else str(response.content)
    return {"success": True, "content": _extract_code(text)}


# ===========================================================================
# 用例入库（对话页与模块页共用的唯一写入口）
# ===========================================================================

async def save_script(db, *, script_id: str | None = None, name: str | None = None,
                      content: str | None = None, module: str | None = None,
                      description: str | None = None,
                      status: str | None = None) -> UnityScript:
    """新建或更新一条 Unity 用例。

    - 给了 ``script_id`` 就更新（``content`` 真变了才 version+1），否则新建。
    - 与 ``playwright_service.save_script`` 同构：默认值只在这一处定义。
    - 入库前统一**写起跑线标注**（见 ``annotate_start_line``）：平台不复位之后，
      "这条用例要从什么状态开始"必须写在用例里给人看。
    """
    row: UnityScript | None = None
    if script_id:
        row = (await db.execute(
            select(UnityScript).where(UnityScript.id == UUID(str(script_id)))
        )).scalars().first()
        if row is None:
            raise LookupError(f"脚本不存在: {script_id}")

    if content is not None:
        content = annotate_start_line(content, start_line(content, str(script_id or "")))
        status = effective_status(status, content)

    if row is None:
        if not content:
            raise ValueError("新建脚本必须提供 content")
        row = UnityScript(name=name or "未命名用例", module=module or None,
                          description=description or None, content=content,
                          status=status or "draft")
        db.add(row)
    else:
        if name is not None:
            row.name = name
        if module is not None:
            row.module = module
        if description is not None:
            row.description = description
        if content is not None and content != row.content:
            row.content = content
            row.version += 1
        if status is not None:
            row.status = status
    await db.commit()
    await db.refresh(row)
    return row


async def get_script(db, script_id: str) -> UnityScript | None:
    return (await db.execute(
        select(UnityScript).where(UnityScript.id == UUID(str(script_id)))
    )).scalars().first()


async def list_scripts(db, limit: int = 50) -> list[UnityScript]:
    return list((await db.execute(
        select(UnityScript).order_by(UnityScript.updated_at.desc()).limit(limit)
    )).scalars().all())


# ===========================================================================
# 跑挂了怎么办：失败摘要（供智能体**改用例**，而不是直接放弃）
# ===========================================================================
#
# 一次执行失败可能是三件事，处理方式完全不同（用户 2026-09-22 的要求：走不通就先
# **优化用例**再跑，而不是直接说"执行不了"）：
#
#   * ``case``        —— 用例自己的问题（断言挂了 / 对象改名了 / 等待不够）：改用例；
#   * ``environment`` —— 桥/编辑器/工程的问题（掉线、工程脏被门禁挡住、不在 Play）：
#                        **不要动用例**，先解决环境，并把结论告诉用户；
#   * ``timeout``     —— 超时：看最后一步在等什么，判断是"等待上限太短"还是"环境卡住"。
#
# 判断依据全部来自**现场**（steps.jsonl 的最后一步 + failure.txt + 控制台报错），不猜。

#: 环境类失败的指纹：命中任意一条就不是用例的错
_ENV_FAILURE_MARKERS = (
    "连不上 Unity MCP 桥", "Unity 编辑器未连接", "编辑器未连接",
    "拒绝调用", "no_unity_session", "session disconnected",
    "不在 Play Mode", "设备丢失", "ECONNREFUSED", "Connection refused",
    # 被测程序**自己那一侧**的环境失败：客户端拉不到远端配置、连不上它自己的本地
    # 服务。2026-09-23 实测：这类失败是当天三次运行的全部原因，却因为不在上面那批
    # 指纹里被算成 `case` —— 脚本被标 broken，智能体被指去"改一份本来正确的用例"。
    # 它们和桥的问题同类：**改用例是白改**。
    "尝试获远端配置失败", "获取服务器时间失败", "Fail to get remote text",
    "ConnectionError",
)


def env_failure_hint(output: str) -> str:
    """输出里命中的环境指纹（没有则空串）。

    两处用它：``failure_digest`` 判 kind；``unity_list_scripts`` 回答"上次那次
    失败像不像环境问题"（用户说"接着上次跑"时，先看这个，别去观测游戏界面）。
    """
    for mark in _ENV_FAILURE_MARKERS:
        if mark in (output or ""):
            return mark
    return ""


def _content_key(content: str) -> str:
    """用例**主体**的指纹（入库标注不算差异 —— 那两行是平台自己写的）。"""
    body = "\n".join(
        ln for ln in (content or "").splitlines()
        if not ln.strip().startswith(_START_LINE_MARK)
        and not ln.strip().startswith("#   平台不复位"))
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


#: 跑通过的内容台账（hash → 时间/名字）。保存时据此决定 active 还是 draft ——
#: 工具的契约是"已验证才入库"，但过去只是这么写、并没有真的验过。
_PASSED_LEDGER_NAME = ".passed.json"
_PASSED_LEDGER_MAX = 200


def _passed_ledger_path() -> Path:
    return settings.workspace_dir / "default" / "unity-auto" / _PASSED_LEDGER_NAME


def _load_passed() -> dict:
    try:
        data = json.loads(_passed_ledger_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _record_passed(content: str, name: str = "") -> None:
    """记一笔"这份内容跑通过"（保存时用来判 active / draft）。"""
    ledger = _load_passed()
    ledger[_content_key(content)] = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "name": name}
    # 只留最近的若干条：台账是"最近验证过什么"，不是审计日志
    if len(ledger) > _PASSED_LEDGER_MAX:
        for key, _ in sorted(ledger.items(), key=lambda kv: str(kv[1].get("at") or ""))[
                :len(ledger) - _PASSED_LEDGER_MAX]:
            ledger.pop(key, None)
    try:
        path = _passed_ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass        # 台账写不进去不该拦住用例链路：大不了退回 draft


def passed_before(content: str) -> bool:
    """这份内容（忽略入库标注）有没有跑通过。"""
    return _content_key(content) in _load_passed()


def effective_status(status: str | None, content: str) -> str | None:
    """入库状态判定：**没跑通过的内容不给 active**（"已验证才入库"）。

    工具的契约一直是这句话，但过去只是写在 docstring 里；现在有台账兜着 ——
    想标 active 就得先有一轮 exit 0 把这份内容的指纹记下来。
    """
    if status == "active" and not passed_before(content):
        return "draft"
    return status


def _failed_step(trace: Path) -> dict | None:
    """轨迹里**最后一个失败的步骤** —— "走到哪儿挂的"就是它。"""
    try:
        lines = trace.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    last = None
    for line in lines:
        try:
            step = json.loads(line)
        except ValueError:
            continue
        if not step.get("ok", True):
            last = step
    return last


def failure_digest(workdir: Path, exit_code: int, output: str) -> dict | None:
    """把"为什么没走通"压成一小块，交给智能体判断该改用例还是修环境。

    ``None`` = 没有失败。有失败时给：``kind`` / 挂在哪一步 / 证据文件路径 /
    环境类失败的原文（控制台报错那几行）。
    """
    if exit_code == 0:
        return None
    kind = "timeout" if exit_code == -1 else ("case" if exit_code == 1 else "environment")
    if kind == "case" and any(m in output for m in _ENV_FAILURE_MARKERS):
        # exit 1 也可能是"桥在用例跑到一半断了"：报错里出现环境指纹就按环境算
        kind = "environment"
    step = _failed_step(workdir / "steps.jsonl") or {}
    artifacts = {}
    for name in ("failure.png", "failure.txt", "steps.jsonl", "case.py"):
        path = workdir / name
        if path.is_file():
            artifacts[name] = str(path)
    digest: dict = {
        "kind": kind,
        "exit_code": exit_code,
        "step": {"action": step.get("action"), "target": step.get("target"),
                 "error": step.get("error")} if step else None,
        "artifacts": artifacts,
    }
    if kind == "environment":
        digest["errors"] = [ln.strip() for ln in output.splitlines()
                            if ln.strip().startswith(("ERROR:", "WARN:"))][-5:]
    elif kind == "case":
        digest["errors"] = [str(step.get("error"))[:400]] if step.get("error") else []
    return digest


# ===========================================================================
# 执行
# ===========================================================================

_PRELUDE = '''"""Auto-generated prelude: Unity MCP bridge bootstrap (平台注入，勿改)."""
import atexit
import json
import os
import sys
import traceback

sys.path.insert(0, r"{root}")
os.environ.setdefault("UNITY_MCP_URL", r"{url}")
os.environ.setdefault("UNITY_MCP_TRANSPORT", "{transport}")
os.environ.setdefault("UNITY_MCP_COMMAND", r"{command}")
os.environ.setdefault("UNITY_MCP_SERVER", "{flavor}")

from src.app.services.unity_bridge import Unity, UnityBridgeError  # noqa: E402

u = Unity()

try:
    _st = u.status()
except UnityBridgeError as exc:
    print("ERROR: 连不上 Unity MCP 桥 ——", exc)
    sys.exit(2)

print("Unity MCP:", _st.get("server"), "| editor:", _st.get("editor"))

if not _st.get("unity_connected"):
    # 桥在、Unity 编辑器没连上 —— 这是环境问题（exit 2），不是用例失败（exit 1）。
    # 分开的意义：平台按退出码把脚本标成 error 还是 broken，人看到的是两件事。
    print("ERROR: Unity MCP 桥在线，但 Unity 编辑器未连接（工程里没装/没连 MCP for Unity 包）")
    sys.exit(2)

#: 现在是不是 Play Mode（用上面这次 status 的结果，不再多打一次桥）。
#: 起跑线快照只在 Play 中才记 —— 编辑模式下的场景不算"游戏跑到了哪儿"。
_ST_PLAYING = bool((_st.get("editor") or {{}}).get("isPlaying"))

# --- 存证：步骤轨迹 / 录像 / 失败现场 -----------------------------------------
# 用例脚本一行都不用写：轨迹与录像由这里统一开关（Playwright 那边同理 ——
# trace/video 是 runner 的事，不是 spec 的事）。任何一步失败都不影响用例判定。
if os.environ.get("UNITY_TRACE_FILE"):
    u.trace_to(os.environ["UNITY_TRACE_FILE"])

# --- 跑用例期间不许系统睡觉 ---------------------------------------------------
# 2026-09-22 实测：机器在跑用例途中进了「新型待机」（Idle Timeout），唤醒时
# D3D11 设备丢失、Unity 直接自杀（编辑器日志最后一句是 device reset/removed）。
# 屏幕一灭，Play Mode 里的移动端工程就是雷 —— 从 runner 起来到收尾，全程把
# 系统钉在醒着状态；线程结束时 ES_CONTINUOUS 自动失效，不需要额外的兜底。
_AWAKE = None
if os.name == "nt":
    try:
        import ctypes

        _ES_CONTINUOUS, _ES_SYSTEM_REQUIRED, _ES_DISPLAY_REQUIRED = (
            0x80000000, 0x00000001, 0x00000002)
        _AWAKE = ctypes.windll.kernel32
        _AWAKE.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED)
    except Exception as exc:  # noqa: BLE001 —— 钉不住也别拦着用例
        _AWAKE = None
        print("WARN: 没能禁止系统睡眠（不影响用例判定）：", exc)


def _allow_sleep():
    if _AWAKE is not None:
        try:
            _AWAKE.SetThreadExecutionState(_ES_CONTINUOUS)
        except Exception:  # noqa: BLE001
            pass


_FAILED = {{"flag": False}}
_RECORD = os.environ.get("UNITY_RECORD", "1").strip().lower() not in ("0", "off", "false")

#: 录像进行中的标记。runner 被平台超时**硬杀**时 atexit 不会执行 —— 父进程靠
#: 这个文件知道"这一轮的钩子还在编辑器里挂着"，好补发一次收尾（见 unity_service
#: 里的 _salvage_recording）：不补的话，钩子会留在编辑器里以 fps 频率一直截图。
_REC_MARKER = ".recording"


def _excepthook(exc_type, exc, tb):
    """用例挂在异常上就是失败：记下这一笔，堆栈照原样打印（人还要看）。"""
    _FAILED["flag"] = True
    traceback.print_exception(exc_type, exc, tb)


sys.excepthook = _excepthook


def _finalize():
    """收尾：失败抓现场 + 录像合成。**任何异常都吞掉** —— 存证坏了不该改判结果。"""
    if _FAILED["flag"]:
        try:
            info = u.capture_failure("failure.png")
            print("失败现场 ->", info.get("image"), info.get("context"))
            for line in (info.get("errors") or [])[-5:]:
                print("  报错:", str(line)[:300])
        except Exception as exc:
            print("WARN: 失败现场没抓到（不影响判定）：", exc)
    if u.recording:
        try:
            out = u.record_stop()
            if out.get("ok"):
                print("录像 ->", out.get("path"),
                      "(%s 帧 / %ss)" % (out.get("frames"), out.get("duration_s")))
                if out.get("note"):
                    print("WARN: 录像提前结束 ——", out.get("note"))
            else:
                print("WARN: 录像没有合成：", out.get("error"))
        except Exception as exc:
            print("WARN: 录像收尾异常（不影响判定）：", exc)
    try:
        os.remove(_REC_MARKER)
    except OSError:
        pass
    _allow_sleep()


atexit.register(_finalize)

# --- 起跑线：平台**不再自动复位** ---------------------------------------------
# 2026-09-22 起：复位（Lua 注入 / 重载场景）是**改被测对象状态**的动作 —— 出问题时
# 没人分得清"游戏本来就这样"还是"平台把它点成这样"，排查成本极高；自动复位还让
# 用例失败的理由多出一类（是断言挂了，还是没回起点？）。所以平台既不复位、**也不
# 强制检查**起点：起跑线只**通知**（跑之前把"这条用例要求从哪儿开始"打出来），
# 在不在由人自己说了算 —— 不再打断执行、不再有"待复位"这种状态。
#
# 起跑线从哪儿来：用例里写的模块级 ``RESET = {{...}}`` 优先（``scene`` / ``wait_for``），
# 没写就用平台记住的（上次跑通时的现场，start_state.json，read-only）。
_RESET_KEYS = ("scene", "wait_for", "timeout", "mode", "play", "lua")
_START = {{}}
try:
    _raw = json.loads(os.environ.get("UNITY_START_LINE_JSON") or "{{}}")
    if isinstance(_raw, dict):
        _START = {{k: v for k, v in _raw.items() if k in _RESET_KEYS}}
except ValueError as exc:
    print("WARN: 起跑线声明解析不了，跳过提示：", exc)


def _start_line_notice(cfg):
    """起跑线提示（一行，给人看）：要求从哪儿开始 —— 不做任何检查。"""
    _scene = str(cfg.get("scene") or "").strip()
    _anchor = str(cfg.get("wait_for") or "").strip()
    _bits = []
    if _scene:
        _bits.append("场景=%s" % _scene)
    if _anchor:
        _bits.append("标志物=%s" % _anchor)
    if not _bits:
        return ""
    return ("起跑线（平台不复位、不检查，请自行确认）：" + "；".join(_bits)
            + "　—— 不在这个状态就先手动回过去，否则后面的断言多半会从「找不到对象」开始")


if _START:
    print(_start_line_notice(_START))

# --- 起跑线快照：跑通一次就记住这条用例从哪儿起跑 ------------------------------
# 记的是**用例动作之前**那一瞬：下一轮就有一份"该复位到哪儿"的说明可讲给用户，
# 作者不用手写。平台不据此复位，只是把起跑线**记下来**（读得越多，提示越准）。
#
# **只读路径不许有写风险**：这里读场景走 u.active_scene_path()（execute_code），
# 不用 u.active_scene() —— 后者打的是 manage_scene，那批工具在桥内部带 preflight，
# 工程被判"有未导入的外部改动"时，**桥会自己**发 refresh_unity(compile="request")，
# 也就是一次域重载。2026-09-23 01:37 就是这么把 Play 中的编辑器卡死在 Reloading
# Domain 的（随后 D3D11 设备丢失、整机断电）。要读路径，不要拿读去换一次重载。
if os.environ.get("UNITY_START_STATE_FILE") and _ST_PLAYING:
    try:
        _snap_scene = u.active_scene_path()
        if _snap_scene:
            with open(os.environ["UNITY_START_STATE_FILE"], "w", encoding="utf-8") as _fh:
                json.dump({{"scene": _snap_scene, "play": True,
                            "wait_for": _START.get("wait_for") or ""}}, _fh,
                          ensure_ascii=False)
    except Exception as exc:
        print("WARN: 起跑线没记下来（不影响判定）：", exc)

if _RECORD:
    try:
        # 固定 5fps（2026-09-23 起）：够看清"点了哪个按钮、面板怎么出现"，写盘量与
        # GPU 回读次数只有 10fps 的一半 —— 配 30 分钟的执行预算约 9000 帧。
        # 帧数/秒数上限不用在这里给：record_start 会按同一个执行预算推导
        # （unity_bridge.record_budget），两处常量不会再各写一套。
        _rec = u.record_start(fps=float(os.environ.get("UNITY_RECORD_FPS", "5")))
        print("录像已开始 ->", _rec.get("dir"))
        try:
            with open(_REC_MARKER, "w", encoding="utf-8") as _fh:
                _fh.write(str(_rec.get("dir") or ""))
        except OSError:
            pass
    except UnityBridgeError as exc:
        print("WARN: 录像没有开始（不影响用例判定）：", exc)
'''


def _prelude() -> str:
    return _PRELUDE.format(
        root=ROOT,
        url=settings.unity_mcp_url,
        transport=(settings.unity_mcp_transport or "http").strip().lower(),
        command=settings.unity_mcp_command or "",
        flavor=(settings.unity_mcp_server or "auto").strip().lower(),
    )


#: 一次运行里要收进产物的文件类型 —— 和 Web-UI 那边的产物口径对齐（截图/录像/
#: 文本/trace），前端一套渲染逻辑吃两种模块的产物。
_ARTIFACT_GLOBS = ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif",
                   "*.mp4", "*.webm", "*.mov",
                   "*.txt", "*.md", "*.json", "*.jsonl", "*.html", "*.zip")
#: 上限：一次运行最多留这么多产物（截图帧序列全收会把执行记录撑爆）。
_ARTIFACT_LIMIT = 40


def live_artifacts(workdir: Path) -> list[Path]:
    """运行目录里现存的产物文件（**执行中**也读得出来：文件是边跑边落盘的）。

    "跑完才写回产物清单"是执行记录的存储方式，不是产物的时间线 —— 执行期间
    前端要看到步骤一条条冒出来，就得能直接读这个目录。
    """
    found: set[Path] = set()
    try:
        for pattern in _ARTIFACT_GLOBS:
            found.update(p for p in workdir.rglob(pattern) if p.is_file())
    except OSError:
        pass
    # 按文件名排：用例脚本本来就用 01_xx / 02_xx 的命名给出顺序，名字排=操作顺序。
    return sorted(found, key=lambda p: p.name)[:_ARTIFACT_LIMIT]


def _collect_artifacts(workdir: Path) -> list[str]:
    return [str(p) for p in live_artifacts(workdir)]


def _run_dir(script_id: str, name: str) -> Path:
    """每次执行一个独立目录：脚本与产物（截图）都留在里面，不覆盖上一次。"""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r"[^\w.\-]+", "_", name or "case")[:60]
    d = settings.workspace_dir / "default" / "unity-auto" / str(script_id) / f"{stamp}_{safe}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===========================================================================
# 起跑线（用例从什么状态开始跑）—— 平台不复位、也不检查，只提示
# ===========================================================================
#
# 用例与用例之间必须"各跑各的"：上一轮把游戏停在背包里/打到一半，这一轮不能接着
# 那个状态往下跑。过去平台的答案是**自动复位**（Lua 注入 / 退 Play 重进）；2026-09-22
# 起改成**只检查、不动作**：复位是改被测对象状态的动作，做多了没人分得清"游戏本来
# 就这样"还是"平台点成这样"，而且自动复位会让失败多出一类说不清的理由。
#
# 现在：跑之前只**打印一行提示**（"这条用例要求从哪个场景/界面开始"），检查与判断
# 全交给用户 —— 目的是"别让平台的状态动作混进被测对象"，不是再造一道闸门。
#
# 起跑线从哪儿来，两条路（都只用来**写说明**，不再驱动任何动作）：
#   1. 用例里显式写 ``RESET = {"scene": …, "wait_for": …}`` —— 作者说了算；
#   2. **跑通一次就记住**（``start_state.json``）：记的是上次跑通时开头那一瞬的
#      场景与标志物，给没写 RESET 的用例兜一份说明。

_START_STATE_NAME = "start_state.json"
#: 子进程写的"候选起跑线"：跑通才提升成正式的 start_state.json（跑挂的那次的
#: 开场状态可能是半路状态，记下来只会把下一轮带偏）。
_CANDIDATE_NAME = "start_state.candidate.json"
#: 老的 RESET 里可能有 mode / lua / play / timeout（当年驱动自动复位的）；现在
#: 只认 scene / wait_for，多出来的键照旧丢掉（老用例不用改也能跑）。
_RESET_KEYS = ("scene", "wait_for", "timeout", "mode", "play", "lua")


def script_dir(script_id: str) -> Path:
    """一份用例的常驻目录（跨执行保留的东西放这儿 —— 起跑线就是其中之一）。"""
    d = settings.workspace_dir / "default" / "unity-auto" / str(script_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def declared_reset(content: str) -> tuple[bool, dict]:
    """读用例里模块级的 ``RESET``，返回 ``(声明了没有, 参数)``。

    名字保留（存量用例、文档都这么叫）；语义已变成"起跑线声明"：``RESET = {...}``
    是显式起跑线，``RESET = True`` 用平台记住的，``RESET = False`` 表示这条用例
    不关心起跑线（平台的检查也跳过）。解析不了就当作没声明。
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False, {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "RESET" for t in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return False, {}
        if isinstance(value, dict):
            return True, {k: v for k, v in value.items() if k in _RESET_KEYS}
        if value is False:
            return True, {}          # 明确"不管起跑线"
        return True, {}              # True / 其他真值：用记住的那条
    return False, {}


def learned_start_state(script_id: str) -> dict:
    """上次跑通时记下的起跑线（没有就给空 dict）。"""
    path = script_dir(script_id) / _START_STATE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k in ("scene", "wait_for") and v}


def start_line(content: str, script_id: str = "") -> dict:
    """这条用例的起跑线说明：``{"scene": …, "wait_for": …}``（空 dict = 没得说）。

    显式声明优先；没写就用记住的。**它只用来生成"该复位到什么状态"的提示**，
    平台不会照着它去动游戏（见本节顶部）。
    """
    declared, cfg = declared_reset(content)
    if declared:
        # ``RESET = False`` 与"解析失败"都是空 dict：都没得说。区别在下面：
        # 显式写了 False 就是"这条用例不关心起跑线"，不能又拿记住的那条顶上。
        plan = {**learned_start_state(script_id), **cfg} if cfg else {}
    else:
        plan = learned_start_state(script_id)
    return {k: v for k, v in plan.items() if k in ("scene", "wait_for") and v}


#: 用例文件里的起跑线标注行（幂等：已有就更新，不重复加）。
_START_LINE_MARK = "# 起跑线（人工复位）："


def start_line_note(plan: dict) -> str:
    """起跑线 → 一行给人看的标注（没有起跑线就返回空串）。

    不带注释记号 —— 界面直接显示它；写进用例文件时由 ``annotate_start_line``
    补上 ``# 起跑线（人工复位）：`` 前缀。
    """
    scene = str(plan.get("scene") or "").strip()
    anchor = str(plan.get("wait_for") or "").strip()
    if not scene and not anchor:
        return ""
    parts = (["场景=" + scene] if scene else []) + (["标志物=" + anchor] if anchor else [])
    return "；".join(parts)


def annotate_start_line(content: str, plan: dict) -> str:
    """把「起跑线（人工复位）」标注写进用例开头（幂等）。

    为什么写进文件：平台不再自动复位（2026-09-22 起），起跑线从"平台会做的事"变成了
    "人要照着做的事" —— 那它就得在**用例本身**里看得见，而不是藏在运行日志里。已有
    标注就更新它（起跑线改了要跟着改），没有就插在文件最上面。
    """
    body = start_line_note(plan)
    if not body:
        return content
    note = _START_LINE_MARK + body
    lines = content.splitlines()
    for index, line in enumerate(lines[:20]):     # 只在开头这一小段里找标注
        if line.strip().startswith(_START_LINE_MARK):
            if line.strip() == note:
                return content
            lines[index] = note
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    head = [note,
            "#   平台不复位、也不检查起跑线：跑之前请自行把游戏恢复成上面这个状态"]
    return "\n".join(head + lines) + ("\n" if content.endswith("\n") else "")


def _first_anchor(trace_path: Path) -> str:
    """轨迹里第一个成功的 ``wait_for`` —— 这条用例真正等的第一个标志物，就是起跑线。"""
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            step = json.loads(line)
        except ValueError:
            continue
        if step.get("action") == "wait_for" and step.get("ok") and step.get("target"):
            return str(step["target"])
    return ""


async def _salvage_recording(workdir: Path) -> str:
    """runner 被硬杀（超时）时兜底收尾录像：解除编辑器侧钩子 + 合成已采到的帧。

    为什么必须由父进程兜：runner 的收尾挂在 ``atexit`` 上，被 kill 时不会执行，
    而帧钩子是挂在**编辑器**上的（``EditorApplication.update``）—— 不解除就会
    留在编辑器里以 fps 频率一直截图。2026-09-22 那两次 Unity 崩溃（D3D11
    device removed）前的日志里刷的就是它：一次会话 11532 次失败截图。

    判据是 runner 留的 ``.recording`` 标记（正常收尾时它自己会删）—— 只有
    "这一轮挂了钩子、却没来得及收尾"才动手，不会误伤同时跑的其它轮。
    """
    marker = workdir / ".recording"
    if not marker.is_file():
        return ""
    try:
        from src.app.services import unity_bridge

        out = await asyncio.to_thread(
            lambda: unity_bridge.unity_on_cached_client().record_stop(
                str(workdir / "run.mp4")))
    except Exception as exc:  # noqa: BLE001 —— 存证坏了不该改判用例结果
        return f"WARN: 录像兜底收尾失败（不影响判定）：{exc}"
    finally:
        try:
            marker.unlink()
        except OSError:
            pass
    if out.get("ok") and out.get("frames"):
        return (f"录像（超时兜底）-> {out.get('path')}"
                f"（{out.get('frames')} 帧 / {out.get('duration_s')}s）")
    if out.get("note"):
        return f"WARN: 录像兜底收尾 —— {out.get('note')}"
    return ""


def _promote_start_state(script_id: str, workdir: Path, content: str) -> dict | None:
    """跑通之后：把这次的候选起跑线提成正式的（顺带补上轨迹里的第一个标志物）。"""
    candidate = workdir / _CANDIDATE_NAME
    if not candidate.is_file():
        return None
    try:
        state = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(state, dict) or not state.get("scene"):
        return None
    anchor = _first_anchor(workdir / "steps.jsonl")
    if anchor:
        state["wait_for"] = anchor
    try:
        (script_dir(script_id) / _START_STATE_NAME).write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return None
    return state


#: 正在跑的用例（workdir -> Task）。急停用的：取消这些任务，取消路径会去补收尾
#: （卸掉编辑器侧的录像钩子）——否则钩子留在编辑器里按 fps 一直截图。
_ACTIVE_RUNS: dict[str, "asyncio.Task"] = {}


def _remember_active_run(workdir: Path) -> None:
    task = asyncio.current_task()
    if task is not None:
        _ACTIVE_RUNS[str(workdir)] = task


def _forget_active_run(workdir: Path) -> None:
    _ACTIVE_RUNS.pop(str(workdir), None)


async def stop_all_runs(reason: str = "用户急停") -> dict:
    """急停：取消所有正在跑的用例 + 卸掉编辑器上的录制钩子。

    停止按钮只能停"那一轮对话"，而用例跑在独立子进程里、录像钩子挂在编辑器上 ——
    用户看到的是"我明明中断了，Unity 还在被驱动"。这条是那个缺口的兜底，任何一条路
    （中断、超时、急停、进程崩溃后的下次启动）都能把编辑器拉回干净状态。
    """
    running = list(_ACTIVE_RUNS.items())
    for _key, task in running:
        task.cancel(reason)
    if running:
        # 让取消落地（每个任务自己会 salvage 收尾），但不无限等 —— 编辑器可能已经不在。
        await asyncio.gather(*(t for _k, t in running), return_exceptions=True)
    cancelled = [k for k, _t in running]
    # 登记自己也要清干净：被取消的任务不一定走到 run_unity_script 的收尾那几行
    # （比如刚起、还没真正开始跑就被取消），留着会让按钮越按越"有东西在跑"。
    for key in cancelled:
        _ACTIVE_RUNS.pop(key, None)
    disarmed = await unity_bridge.disarm_all_recorders()
    return {"cancelled_runs": cancelled, "disarmed": disarmed}


async def sync_assets() -> dict:
    """清掉"工程里有未导入的外部改动"标记（安全：只刷新、不重编译、不在 Play 做）。"""
    return await unity_bridge.sync_assets()


def clear_gpu_alarm() -> dict:
    """解除「显卡设备丢失」熔断（手动兜底；正常路径是由"换了 Unity 实例"自动解除）。"""
    was = unity_bridge.gpu_device_lost()
    unity_bridge.clear_gpu_loss("用户在平台上手动解除")
    return {"cleared": bool(was), "evidence": was[:400]}


async def run_unity_script(script_id: str, name: str, content: str,
                           workdir: Path | None = None) -> dict:
    """在子进程里跑一份用例脚本（prelude 注入 ``u``）。

    执行前按起跑线复位（见上面那节）：声明式优先、自动记住的兜底。

    ``workdir`` 可以由调用方**先定好**（REST 入队那条路就是）：执行记录里存下这个目录，
    执行中就能读实时产物与步骤轨迹 —— 否则"运行中"的执行记录在页面上永远是 0 步 0 图。
    """
    started = time.monotonic()
    workdir = Path(workdir) if workdir else _run_dir(script_id, name)
    workdir.mkdir(parents=True, exist_ok=True)
    # 显卡设备已经丢失（DXGI_ERROR_DEVICE_REMOVED）：编辑器随后一定会关，这时候开局
    # 只会往坏掉的 GPU 上继续叠负载（2026-09-23 的现场就是整机卡死到长按电源）。
    if (gpu := unity_bridge.gpu_device_lost()):
        return {
            "exit_code": -3, "status": "error",
            "output": "", "duration_ms": int((time.monotonic() - started) * 1000),
            "failure": {"kind": "environment",
                        "summary": "Unity 编辑器已报「显卡设备丢失」，平台停手没有开局",
                        "evidence": gpu[:400],
                        "next": "请用户更新显卡驱动 / 检查供电线与 PCIe 插槽 / 关掉超频降压，"
                                "重启 Unity；平台检测到新实例后自动解除熔断。"},
            "script_file": "", "workdir": str(workdir),
        }
    _remember_active_run(workdir)
    script_file = workdir / "case.py"
    script_file.write_text(_prelude() + "\n" + content, encoding="utf-8")
    # 存证落盘位置一并交给脚本：轨迹写这一步的目录、不带文件名的截图也落这里，
    # 这样"这次执行有哪些产物"只有一个答案（运行目录里有什么就是什么）。
    # 起跑线只作为**检查依据**交给脚本（平台不复位，见上面那节）。
    plan = start_line(content, script_id)
    env = {
        **os.environ,
        "UNITY_TRACE_FILE": str(workdir / "steps.jsonl"),
        "UNITY_SHOT_DIR": str(workdir),
        "UNITY_START_LINE_JSON": json.dumps(plan, ensure_ascii=False) if plan else "",
        "UNITY_START_STATE_FILE": str(workdir / _CANDIDATE_NAME),
    }
    try:
        out_bytes, _err_bytes, exit_code = await run_subprocess(
            sys.executable, str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir),
            env=env,
            timeout=run_timeout_s(),
        )
        output = out_bytes.decode("utf-8", errors="replace")
    except TimeoutError:
        output, exit_code = f"执行超时({int(run_timeout_s())}s)", -1
    except OSError as exc:
        output, exit_code = str(exc), -2
    except asyncio.CancelledError:
        # **用户中断**（停止按钮 / 关掉那一轮对话）走的是这条：run_subprocess 会把
        # 子进程硬杀掉，子进程的 atexit 于是不执行 —— 但录像钩子挂在**编辑器**上，
        # 不补收尾它就会以 fps 频率一直截图（2026-09-22 的 D3D11 崩溃正是如此）。
        # 超时分支原本就有 salvage，取消分支以前漏了：这里补上，再原样抛出去。
        # shield：收尾要**跑完**，不能被第二次取消打断（子进程已经死了，这是最后一次机会）。
        try:
            await asyncio.shield(_salvage_recording(workdir))
        except Exception:  # noqa: BLE001 —— 收尾失败不能盖掉"用户中断"这件事
            pass
        _forget_active_run(workdir)
        raise

    if (salvage := await _salvage_recording(workdir)):
        output = f"{output}\n{salvage}"
    # 用例输出里带显卡丢失签名（Unity 自己的报错会打到运行输出里）→ 置熔断，
    # 后面所有工具调用一律拒绝，并让页面/agent 直接说出"是显卡"。
    if unity_bridge.note_gpu_loss(output):
        print("[unity]", unity_bridge.gpu_device_lost()[:200])
    _forget_active_run(workdir)

    # 跑通才认这条起跑线：挂掉的那次开场状态可能只是"半路"，记下来会把下一轮带偏。
    learned = _promote_start_state(script_id, workdir, content) if exit_code == 0 else None
    if learned and not declared_reset(content)[0]:
        print("起跑线已记住 ->", learned.get("scene"),
              "标志物", learned.get("wait_for") or "(无)")

    failure = failure_digest(workdir, exit_code, output)
    if failure is None:
        # 跑通了：记一笔"这份内容验证过"（保存时据此定 active 还是 draft）
        _record_passed(content, name=script_id)

    return {
        "exit_code": exit_code,
        "status": "passed" if exit_code == 0 else ("failed" if exit_code == 1 else "error"),
        "output": output[-30_000:],
        # 没走通时给一小块结构化摘要：是**用例**的问题（改用例）还是**环境**的问题
        # （别改用例，先修环境）—— 智能体照这个决定下一步，不用啃 30k 输出。
        "failure": failure,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "script_file": str(script_file),
        "screenshots": json.dumps(_collect_artifacts(workdir), ensure_ascii=False),
    }


async def list_runs(db, script_id: str, limit: int = 30) -> list:
    from src.app.db.models.unity_script import UnityScriptRun

    return list((await db.execute(
        select(UnityScriptRun).where(UnityScriptRun.script_id == UUID(str(script_id)))
        .order_by(UnityScriptRun.created_at.desc()).limit(limit)
    )).scalars().all())


# ===========================================================================
# 删除
# ===========================================================================

#: 僵死阈值 = 执行预算 + 180s，见上面的 run_stale_after_s()（**函数**，不是常量：
#: 预算可配，写死一个数就会在"预算被调大"之后把正在跑的记录标成僵死）。
#: 超过这个时长就不再拦删除 —— 否则一条永远跑不完的记录会让脚本永远删不掉。


def run_age_s(run) -> float:
    created = getattr(run, "created_at", None)
    if created is None:
        return 0.0
    if created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    return (datetime.now(timezone.utc).replace(tzinfo=None) - created).total_seconds()


def purge_script_files(script_id: str) -> dict:
    """删掉这条用例在磁盘上的"家"：各次运行目录（截图/录像/轨迹）+ 起跑线。

    只动 ``unity-auto/<script_id>/`` 这一层，**不碰共享的 ``unity-auto/screenshots/``**
    —— 那是探索时截图落的地方，不属于任何一条用例（删一条用例把别人的图带走，
    是最容易悄悄发生的那种损失）。软链也不跟：删链接，不删它指向的东西。
    """
    root = settings.workspace_dir / "default" / "unity-auto" / str(script_id)
    if not root.is_dir() or root.is_symlink():
        return {"files": 0, "bytes": 0}
    files = 0
    size = 0
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            files += 1
            try:
                size += path.stat().st_size
            except OSError:
                pass
    try:
        shutil.rmtree(root)
    except OSError as exc:
        return {"files": files, "bytes": size, "error": str(exc)}
    return {"files": files, "bytes": size}


async def delete_script(db, script_id: str) -> dict:
    """删掉一条用例：**执行记录 + 磁盘产物 + 起跑线**一起清掉。

    只删库不删盘会留下永远没人认领的运行目录 —— 一次执行就是几张截图加一段录像
    （大型游戏一次几十 MB，见 jynew），而"删掉这条旧脚本"想要的就是它彻底没了。
    正在执行的用例不让删（后台任务还要往回写、产物还在生成）：报清楚，让人等它跑完。
    """
    from src.app.db.models.unity_script import UnityScriptRun

    row = await get_script(db, script_id)
    if row is None:
        raise LookupError(f"脚本不存在: {script_id}")

    runs = list((await db.execute(
        select(UnityScriptRun).where(UnityScriptRun.script_id == UUID(str(script_id)))
    )).scalars().all())
    inflight = [r for r in runs
                if r.status == "running" and run_age_s(r) < run_stale_after_s()]
    if inflight:
        raise RuntimeError(
            f"这条用例正在执行中（{len(inflight)} 条运行记录还没结束），等它跑完再删")

    for run in runs:
        await db.delete(run)
    # 先把执行记录**落库删掉**，再删用例：工作单元会自己排序，若先删父行，外键级联
    # 已经把记录带走了，ORM 那条 DELETE 就成了"期望删 N 行、实际 0 行" —— 每删一条
    # 用例都往日志里留一条警告（实测踩到）。显式 flush 把顺序钉死。
    await db.flush()
    await db.delete(row)
    await db.commit()

    freed = purge_script_files(script_id)
    return {"deleted": True, "runs": len(runs), **freed}


# ===========================================================================
# 手动录制（玩家自己点，平台录成用例）
# ===========================================================================
#
# 链路：前端「开始录制」-> 桥把录制器注入 Unity 编辑器（帧回调，见
# services/unity_recorder.py）-> 用户在 Play 里正常玩 -> 「停止」把事件取回、
# 落盘到 workspace/default/unity-auto/recordings/<rec_id>/ -> 转换器生成
# 平台风格的用例脚本（draft），跑通一次才算 active（与既有契约一致）。
#
# 域重载（进 Play Mode 默认会重载域）会清掉 Unity 侧的动态钩子：钩子带心跳，
# 平台每次查状态发现心跳停了就用同一个 subdir 重挂 —— 事件文件与计数都保留。

_RECORDINGS_DIRNAME = "recordings"
#: 录制 id 会被拼进 Unity 侧目录名与磁盘路径：只允许安全字符（防路径穿越）
_REC_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

#: 进程内记住当前录制的 id（重启后由 meta 扫描兜底）
_ACTIVE_REC_ID: str | None = None


def _recordings_root() -> Path:
    return settings.workspace_dir / "default" / "unity-auto" / _RECORDINGS_DIRNAME


def _recording_dir(rec_id: str) -> Path:
    if not _REC_ID_RE.match(rec_id or ""):
        raise ValueError(f"非法录制 id: {rec_id!r}")
    return _recordings_root() / rec_id


def _read_meta(rec_dir: Path) -> dict:
    try:
        data = json.loads((rec_dir / "meta.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_meta(rec_dir: Path, meta: dict) -> None:
    rec_dir.mkdir(parents=True, exist_ok=True)
    (rec_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _active_recording_id() -> str | None:
    """当前在录的录制 id：先看进程内记录，再看磁盘 meta（重启后仍认）。"""
    global _ACTIVE_REC_ID
    if _ACTIVE_REC_ID and (_recording_dir(_ACTIVE_REC_ID) / "meta.json").exists():
        if _read_meta(_recording_dir(_ACTIVE_REC_ID)).get("status") == "recording":
            return _ACTIVE_REC_ID
    root = _recordings_root()
    if not root.is_dir():
        _ACTIVE_REC_ID = None
        return None
    for child in sorted(root.iterdir(), reverse=True):
        if not child.is_dir():
            continue
        meta = _read_meta(child)
        if meta.get("status") == "recording":
            _ACTIVE_REC_ID = child.name
            return _ACTIVE_REC_ID
    _ACTIVE_REC_ID = None
    return None


def _bridge_payload(out: dict) -> dict:
    """把桥的返回拆成它自己那段 dict（``{"success":…,"result":{…}}``）。"""
    result = out.get("result") if isinstance(out, dict) else None
    return result if isinstance(result, dict) else {}


def list_recordings() -> list[dict]:
    """录制记录列表（磁盘是事实源；按创建时间倒序）。"""
    root = _recordings_root()
    if not root.is_dir():
        return []
    items: list[dict] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        meta = _read_meta(child)
        if not meta:
            continue
        items.append({
            "id": child.name,
            "name": meta.get("name") or "未命名录制",
            "status": meta.get("status") or "recorded",
            "events": int(meta.get("events") or 0),
            "steps": int(meta.get("steps") or 0),
            "scene": meta.get("scene") or "",
            "created_at": meta.get("created_at") or "",
            "duration_s": meta.get("duration_s"),
            "script_file": meta.get("script_file") or None,
            "stopped_reason": meta.get("stopped_reason") or "",
        })
    items.sort(key=lambda m: m["created_at"], reverse=True)
    return items


def get_recording(rec_id: str) -> dict:
    """单条录制：meta + 原始事件 + （生成过的）脚本内容。"""
    rec_dir = _recording_dir(rec_id)
    meta = _read_meta(rec_dir)
    if not meta:
        raise LookupError(f"录制不存在: {rec_id}")
    events_text = ""
    try:
        events_text = (rec_dir / "events.jsonl").read_text(encoding="utf-8")
    except OSError:
        pass
    script_text = ""
    try:
        script_text = (rec_dir / "script.py").read_text(encoding="utf-8")
    except OSError:
        pass
    return {
        "id": rec_id,
        "meta": meta,
        "events": unity_recorder.parse_events_jsonl(events_text),
        "script": script_text,
    }


def delete_recording(rec_id: str) -> dict:
    """删掉一条录制（含事件与生成的脚本）。正在录的那条不让删。"""
    global _ACTIVE_REC_ID
    rec_dir = _recording_dir(rec_id)
    meta = _read_meta(rec_dir)
    if not meta:
        raise LookupError(f"录制不存在: {rec_id}")
    if meta.get("status") == "recording":
        raise RuntimeError("这条录制正在进行中：先「停止录制」再删")
    shutil.rmtree(rec_dir, ignore_errors=True)
    if _ACTIVE_REC_ID == rec_id:
        _ACTIVE_REC_ID = None
    return {"deleted": True, "id": rec_id}


async def record_ui_start(name: str = "") -> dict:
    """开始录制：先查环境（桥 + Unity + 在 Play），再让 Unity 装帧回调录制器。

    为什么要求**先 Play 再录**：进 Play Mode 默认触发域重载，会把刚挂上的钩子
    清掉（平台会自动重挂，但那一段的事件就丢了）。所以顺序必须是
    "Unity 里点 Play -> 平台上点开始录制"。
    """
    global _ACTIVE_REC_ID
    existing = _active_recording_id()
    if existing:
        return {"success": False, "error": f"已有一条录制在进行（{existing}）：先停止它"}

    st = await unity_bridge.status()
    if not st.get("available"):
        return {"success": False, "error": "Unity MCP 桥不可用：" + str(st.get("error") or "")}
    if not st.get("unity_connected"):
        return {"success": False,
                "error": "Unity 编辑器未连接：请在 Unity 里打开工程并让 MCP 桥连上"}
    if not st.get("is_playing"):
        return {"success": False,
                "error": "Unity 不在 Play Mode",
                "hint": "请先在 Unity 里点 Play（平台不代管 Play），再回来点「开始录制」"}

    stamp = time.strftime("rec_%Y%m%d_%H%M%S")
    rec_id = f"{stamp}_{os.urandom(2).hex()}"
    rec_dir = _recording_dir(rec_id)
    rec_dir.mkdir(parents=True, exist_ok=True)

    try:
        out = await unity_bridge.record_ui_start(name=rec_id)
    except Exception as exc:  # noqa: BLE001 —— 桥断/超时也走同一条"返回可读错误"的路
        return {"success": False, "error": f"注入录制器失败：{exc}"}
    if not out.get("success"):
        return {"success": False,
                "error": out.get("error") or "录制器注入失败（看 Unity Console）"}
    info = _bridge_payload(out)
    meta = {
        "id": rec_id,
        "name": (name or "").strip() or time.strftime("手动录制 %m-%d %H:%M"),
        "status": "recording",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "events": 0,
        "scene": "",
        "subdir": rec_id,
        "unity_file": info.get("file") or "",
        "already": bool(info.get("already")),
    }
    _write_meta(rec_dir, meta)
    _ACTIVE_REC_ID = rec_id
    return {"success": True, "id": rec_id, "meta": meta}


async def record_ui_status() -> dict:
    """录制状态（前端轮询用）：顺带做**心跳自愈** —— 域重载把钩子清掉后自动重挂。"""
    active = _active_recording_id()
    try:
        out = await unity_bridge.record_ui_status()
    except Exception as exc:  # noqa: BLE001
        return {"active": active, "on": False, "error": f"读不到录制状态：{exc}"}
    info = _bridge_payload(out)
    if not out.get("success") or not info.get("ok"):
        return {"active": active, "on": False,
                "error": out.get("error") or info.get("error") or "读不到录制状态"}

    # 注意别写成 `float(x or -1)`：心跳由帧回调**每帧刷新**，age 合法值就是 0.0，
    # 而 `0.0 or -1` 会把它错判成"读不到"（实测踩到，面板显示 -1.0）
    raw_age = info.get("hb_age")
    try:
        hb_age = float(raw_age) if raw_age is not None else -1.0
    except (TypeError, ValueError):
        hb_age = -1.0
    stale = bool(info.get("on")) and hb_age > unity_recorder.HEARTBEAT_STALE_S
    dead = not info.get("on")
    rearmed = False
    rearm_error = ""
    if active and (stale or dead):
        # 钩子没了（域重载 / Unity 侧被清）而平台仍认为在录：用同一个 subdir 重挂。
        # 事件文件与计数都保留，不会把已录的内容截断（见 cs_record_ui_start）。
        try:
            again = await unity_bridge.record_ui_start(name=active)
            rearmed = bool(again.get("success"))
            if not rearmed:
                rearm_error = str(again.get("error") or "重挂失败")
        except Exception as exc:  # noqa: BLE001 —— 重挂失败不该把状态查询也带崩
            rearm_error = str(exc)

    rec_dir = _recording_dir(active) if active else None
    if rec_dir is not None and info.get("events") is not None:
        meta = _read_meta(rec_dir)
        meta["events"] = int(info.get("events") or 0)
        _write_meta(rec_dir, meta)
    return {
        "active": active,
        "on": bool(info.get("on")) or rearmed,
        "events": int(info.get("events") or 0),
        "hb_age": hb_age,
        "reason": info.get("reason") or "",
        "rearmed": rearmed,
        "rearm_error": rearm_error,
    }


async def record_ui_stop() -> dict:
    """停止录制：取回全部事件 -> 落盘 -> 记 meta（状态转 recorded）。"""
    global _ACTIVE_REC_ID
    active = _active_recording_id()
    if not active:
        return {"success": False, "error": "当前没有进行中的录制"}
    rec_dir = _recording_dir(active)

    try:
        out = await unity_bridge.record_ui_stop()
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"停止录制失败：{exc}"}
    info = _bridge_payload(out)
    reason = str(info.get("reason") or "")

    # 分片取事件（MCP 响应有上限）；单次录制事件数也有上限（5000），分片循环留足余量
    chunks: list[str] = []
    since = 0
    total = 0
    fetch_error = ""
    for _ in range(300):
        try:
            out_i = await unity_bridge.record_ui_fetch(since=since)
        except Exception as exc:  # noqa: BLE001
            fetch_error = str(exc)
            break
        info_i = _bridge_payload(out_i)
        if not out_i.get("success") or not info_i.get("ok"):
            fetch_error = str(out_i.get("error") or info_i.get("error") or "取事件失败")
            break
        text = str(info_i.get("text") or "")
        chunks.append(text)
        lines = [ln for ln in text.split("\n") if ln.strip()]
        since += len(lines)
        total = int(info_i.get("total") or total)
        if not info_i.get("more"):
            break
    events_text = "".join(chunks)
    (rec_dir / "events.jsonl").write_text(events_text, encoding="utf-8")

    events = unity_recorder.parse_events_jsonl(events_text)
    steps, stats = unity_recorder.merge_events(events)
    meta = _read_meta(rec_dir)
    started = meta.get("created_at") or ""
    duration_s = None
    if started:
        try:
            duration_s = round((datetime.now(timezone.utc)
                                - datetime.fromisoformat(started)).total_seconds(), 1)
        except ValueError:
            duration_s = None
    meta.update({
        "status": "recorded",
        "events": len(events),
        "steps": len(steps),
        "scene": unity_recorder.first_scene(events),
        "stopped_reason": reason,
        "duration_s": duration_s,
        "stats": stats,
    })
    if total and len(events) != total:
        meta["note"] = f"Unity 侧 {total} 条，取回 {len(events)} 条（有截断）"
    _write_meta(rec_dir, meta)
    _ACTIVE_REC_ID = None
    return {"success": True, "id": active, "meta": meta,
            "events": len(events), "steps": len(steps),
            "stats": stats, "fetch_error": fetch_error}


async def recording_to_script(rec_id: str, *, name: str | None = None,
                              save: bool = True, db=None) -> dict:
    """录制 -> 用例脚本（平台风格 Python）。

    ``save=False`` 只生成预览；``save=True`` 同时落库成 ``draft`` 用例
    （跑通一次才会变 active —— 与「智能体写用例」同一条契约）。
    """
    rec_dir = _recording_dir(rec_id)
    meta = _read_meta(rec_dir)
    if not meta:
        raise LookupError(f"录制不存在: {rec_id}")
    events_text = ""
    try:
        events_text = (rec_dir / "events.jsonl").read_text(encoding="utf-8")
    except OSError:
        pass
    events = unity_recorder.parse_events_jsonl(events_text)
    if not events:
        raise ValueError("这条录制还没有事件：先「停止录制」把操作取回来")

    title = (name or meta.get("name") or "").strip()
    script, stats = unity_recorder.convert_events_to_script(
        events, title=title, created_at=str(meta.get("created_at") or "")[:19])
    (rec_dir / "script.py").write_text(script, encoding="utf-8")
    meta.update({"script_file": "script.py", "script_stats": stats})
    _write_meta(rec_dir, meta)

    script_id = None
    if save:
        if db is None:
            raise ValueError("save=True 需要传 db 会话")
        row = await save_script(
            db, script_id=None,
            name=title or "录制用例",
            content=script,
            description=(f"由手动录制生成（{rec_id}）："
                         f"{stats.get('clicks', 0)} 次点击 / {stats.get('drags', 0)} 次拖拽 / "
                         f"{stats.get('texts', 0)} 处输入 / {stats.get('keys', 0)} 次按键；"
                         f"断言为自动播种，跑通验证后再改。"),
        )
        script_id = str(row.id)
    return {"success": True, "id": rec_id, "script": script,
            "stats": stats, "script_id": script_id}

