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
from src.app.services import unity_bridge

ROOT = Path(__file__).resolve().parents[3]

#: 单次执行的墙钟上限。比旧值（300s）宽出一截：跑完用例还要收尾——失败现场截图、
#: 把上千帧合成录像，这些都算在这段预算里。用例本身超时仍是它自己的等待上限。
_RUN_TIMEOUT_S = float(os.environ.get("UNITY_RUN_TIMEOUT_S") or 420.0)


# ===========================================================================
# 操作（转发给桥）
# ===========================================================================

async def status() -> dict:
    """桥 / 服务器 / 编辑器状态。"""
    return await unity_bridge.status()


async def editor_action(action: str) -> dict:
    """play / pause / stop / state / refresh。"""
    return await unity_bridge.editor_action(action)


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


async def reset(scene: str = "", wait_for: str = "", timeout: float = 120.0,
                mode: str = "hard", play: bool = True) -> dict:
    """把游戏复位到用例起跑线（探索时想"重来一遍"也用它）。"""
    return await unity_bridge.reset(scene=scene, wait_for=wait_for, timeout=timeout,
                                    mode=mode, play=play)


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
    """
    row: UnityScript | None = None
    if script_id:
        row = (await db.execute(
            select(UnityScript).where(UnityScript.id == UUID(str(script_id)))
        )).scalars().first()
        if row is None:
            raise LookupError(f"脚本不存在: {script_id}")

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

# --- 存证：步骤轨迹 / 录像 / 失败现场 -----------------------------------------
# 用例脚本一行都不用写：轨迹与录像由这里统一开关（Playwright 那边同理 ——
# trace/video 是 runner 的事，不是 spec 的事）。任何一步失败都不影响用例判定。
if os.environ.get("UNITY_TRACE_FILE"):
    u.trace_to(os.environ["UNITY_TRACE_FILE"])

_FAILED = {{"flag": False}}
_RECORD = os.environ.get("UNITY_RECORD", "1").strip().lower() not in ("0", "off", "false")


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
            else:
                print("WARN: 录像没有合成：", out.get("error"))
        except Exception as exc:
            print("WARN: 录像收尾异常（不影响判定）：", exc)


atexit.register(_finalize)

# --- 复位：回到用例起跑线 -----------------------------------------------------
# 用例与用例之间的状态隔离靠它：上一轮把游戏打到一半（战斗中 / 停在某个面板里），
# 这一轮开头先退 Play → 打开起跑场景 → 再进 Play → 等标志物回来，才算站回起点。
# 谁给的参数：用例里写的模块级 ``RESET = {{...}}`` 优先，否则用平台记住的起跑线
# （上次跑通时的现场，start_state.json）。
_RESET_KEYS = ("scene", "wait_for", "timeout", "mode", "play")
_RESET = {{}}
try:
    _raw = json.loads(os.environ.get("UNITY_RESET_JSON") or "{{}}")
    if isinstance(_raw, dict):
        _RESET = {{k: v for k, v in _raw.items() if k in _RESET_KEYS}}
        _dropped = [k for k in _raw if k not in _RESET_KEYS]
        if _dropped:
            print("WARN: RESET 里这些参数不认识，已忽略：", _dropped)
except ValueError as exc:
    print("WARN: RESET 解析不了，跳过复位：", exc)

if _RESET:
    try:
        _info = u.reset(**_RESET)
        print("复位 -> 起跑线：场景=%s 标志物=%s 用时=%.1fs"
              % (_info.get("scene"), _info.get("anchor") or "(不等标志物)",
                 _info.get("seconds") or 0.0))
    except Exception as exc:
        # 复位失败 = 起跑线/环境问题（exit 2），不是用例断言失败（exit 1）——
        # "游戏没回到起点"和"功能不对"是两件事，混在一起人会被带偏。
        _FAILED["flag"] = True
        print("ERROR: 复位失败 ——", exc)
        print("       （起跑线没回来：环境/前置问题，不是断言失败）")
        sys.exit(2)

# --- 起跑线快照：跑通一次就记住这条用例从哪儿起跑 ------------------------------
# 记的是**复位之后、用例动作之前**这一瞬：下一轮复位就有据可依，作者不用手写坐标。
if os.environ.get("UNITY_START_STATE_FILE"):
    try:
        _snap_editor = u.editor_state() or {{}}
        if _snap_editor.get("isPlaying"):
            _snap_scene = u.active_scene() or {{}}
            if _snap_scene.get("path"):
                with open(os.environ["UNITY_START_STATE_FILE"], "w", encoding="utf-8") as _fh:
                    json.dump({{"scene": _snap_scene["path"], "play": True,
                                "mode": "hard", "timeout": 180}}, _fh, ensure_ascii=False)
    except Exception as exc:
        print("WARN: 起跑线没记下来（不影响判定）：", exc)

if _RECORD:
    try:
        _rec = u.record_start(fps=float(os.environ.get("UNITY_RECORD_FPS", "6")))
        print("录像已开始 ->", _rec.get("dir"))
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
# 复位（回到用例起跑线）
# ===========================================================================
#
# 用例与用例之间必须能"各跑各的"：上一轮把游戏停在背包里、打到一半战斗，这一轮
# 不能接着那个状态往下跑。平台上给出的答案是**复位**：跑之前把游戏拉回这条用例
# 的起点（退 Play → 起跑场景 → 再进 Play → 等标志物），对应 Playwright 侧的
# "每次用新 context"。起跑线从哪儿来，两条路：
#   1. 用例里显式写 ``RESET = {"scene": …, "wait_for": …}`` —— 作者说了算；
#   2. **跑通一次就记住**（``start_state.json``）：记住的是"上次跑通时开头那一瞬
#      的场景与标志物"，下一轮自动回到那里。没写过 RESET 的用例因此也能复位 ——
#      把手工前置（"先打开某个场景再进 Play"）变成平台能自己重放的动作。
# 关掉的办法：用例里写 ``RESET = False``，或环境变量 ``UNITY_RESET=0``。

_START_STATE_NAME = "start_state.json"
#: 子进程写的"候选起跑线"：跑通才提升成正式的 start_state.json（跑挂的那次的
#: 开场状态可能是半路状态，记下来只会把下一轮带偏）。
_CANDIDATE_NAME = "start_state.candidate.json"
_RESET_KEYS = ("scene", "wait_for", "timeout", "mode", "play")


def script_dir(script_id: str) -> Path:
    """一份用例的常驻目录（跨执行保留的东西放这儿 —— 起跑线就是其中之一）。"""
    d = settings.workspace_dir / "default" / "unity-auto" / str(script_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def declared_reset(content: str) -> tuple[bool, dict]:
    """读用例里模块级的 ``RESET``，返回 ``(声明了没有, 参数)``。

    认三种写法：``RESET = {...}``（显式起跑线）、``RESET = True``（用平台记住的）、
    ``RESET = False``（这条用例不复位）。解析不了就当作没声明（写错的表达式不该让
    整份用例跑不起来 —— 平台会打印提醒）。
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
            return True, {}          # 明确"不复位"
        return True, {}              # True / 其他真值：用记住的那条
    return False, {}


def learned_start_state(script_id: str) -> dict:
    """上次跑通时记下的起跑线（没有就给空 dict）。"""
    path = script_dir(script_id) / _START_STATE_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in _RESET_KEYS} if isinstance(data, dict) else {}


def reset_plan(content: str, script_id: str) -> dict:
    """这次执行要不要复位、复到什么状态（空 dict = 不复位）。

    显式声明优先；没写的用例用记住的起跑线 —— 但**只在这条用例真的跑通过一次之后**
    （没记过就什么都不做，老用例的行为一点不变）。
    """
    if str(os.environ.get("UNITY_RESET", "1")).strip().lower() in ("0", "off", "false"):
        return {}
    declared, cfg = declared_reset(content)
    if declared:
        # ``RESET = False`` 与"解析失败"都是空 dict：都没得复位。区别在 resolve：
        # 显式写了 False 就是"别复位"，不能又拿记住的那条顶上。
        return {**learned_start_state(script_id), **cfg} if cfg else {}
    return learned_start_state(script_id)


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
    script_file = workdir / "case.py"
    script_file.write_text(_prelude() + "\n" + content, encoding="utf-8")
    # 存证落盘位置一并交给脚本：轨迹写这一步的目录、不带文件名的截图也落这里，
    # 这样"这次执行有哪些产物"只有一个答案（运行目录里有什么就是什么）。
    plan = reset_plan(content, script_id)
    env = {
        **os.environ,
        "UNITY_TRACE_FILE": str(workdir / "steps.jsonl"),
        "UNITY_SHOT_DIR": str(workdir),
        "UNITY_RESET_JSON": json.dumps(plan, ensure_ascii=False) if plan else "",
        "UNITY_START_STATE_FILE": str(workdir / _CANDIDATE_NAME),
    }
    try:
        out_bytes, _err_bytes, exit_code = await run_subprocess(
            sys.executable, str(script_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(workdir),
            env=env,
            timeout=_RUN_TIMEOUT_S,
        )
        output = out_bytes.decode("utf-8", errors="replace")
    except TimeoutError:
        output, exit_code = f"执行超时({int(_RUN_TIMEOUT_S)}s)", -1
    except OSError as exc:
        output, exit_code = str(exc), -2

    # 跑通才认这条起跑线：挂掉的那次开场状态可能只是"半路"，记下来会把下一轮带偏。
    learned = _promote_start_state(script_id, workdir, content) if exit_code == 0 else None
    if learned and not declared_reset(content)[0]:
        print("起跑线已记住 ->", learned.get("scene"),
              "标志物", learned.get("wait_for") or "(无)")

    return {
        "exit_code": exit_code,
        "status": "passed" if exit_code == 0 else ("failed" if exit_code == 1 else "error"),
        "output": output[-30_000:],
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

#: 执行记录挂着 "running" 多久就当它僵死了（平台重启/进程被杀留下的）。
#: 超过这个时长就不再拦删除 —— 否则一条永远跑不完的记录会让脚本永远删不掉。
RUN_STALE_AFTER_S = 600.0


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
                if r.status == "running" and run_age_s(r) < RUN_STALE_AFTER_S]
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
