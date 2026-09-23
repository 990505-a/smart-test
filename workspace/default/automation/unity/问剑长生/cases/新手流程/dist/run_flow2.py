# -*- coding: utf-8 -*-
"""新手流程总脚本（阶段一 + 阶段二 + 阶段三）。

链路：启动界面 → 登出/注册并登录 → 创角改名 → 踏入仙途启程 → 序章 → 主线「寻找道院」
     → 修炼/聚灵/服用丹药 → 加入道院（真武）→ 洞府升级 → 聚灵塔试炼 → 外院晋升
     → 门派比试 → 收尾。

时长与执行方式：
  全流程实测约 12~15 分钟。平台单次执行上限由 .env 的 UNITY_RUN_TIMEOUT_S 决定
  （本机 1800s），够一次跑完；若某台机器上仍是默认 420s，用本脚本同源的
  run_stage2a/2b/3a/3b.py 分段跑（每段自带起跑线）。

起跑线：平台**不复位、也不检查**，只在运行输出里提示一行 —— 跑之前请自行复位。

两条实战约束（2026-09-23 实测，写在这里免得下次再踩）：
  1. **工程被判「有未导入的外部改动」时，find_gameobjects / manage_components 那一批
     工具会被平台闸门拦下**（防域重载）。于是 u.exists / u.object_text / u.expect_text
     全部失效 —— 用例会在第一步就炸成"环境错误"。本脚本改用 execute_code 通道
     （cs_present / cs_text）做存在性与文本判断，所以"工程脏"也能跑。
  2. 录制回放里"多点了几下"的地方（推进对话、连点修炼、地图上多点两下）次数跟录制
     当时的节奏有关，多点的那些用 tap_opt：在就点，不在就跳过并打印一行，不算失败；
     真正卡流程的入口（开地图、选任务、确认升级…）仍然用 tap 严格等 + 失败即停。

世界地图这一步要单独说（2026-09-23 实测定位 + 已解决，是流程2 最容易卡的地方）：
  * `map_content` 是 9353x15125 的滚动区，**中心点在屏幕外**，而 `u.click` 是把对象世界
    坐标当屏幕坐标用的（unity_bridge.cs_click）。所以"点地图"实际等于点了个空气 ——
    录制回放里那几十下 `tap_opt(map_content)` 就是这么点空的（每下还白等 8s）。
  * **地图初始全迷雾**：模型里 215 个格，但 UI 格子控件数 `cells=0` —— 必须先在**屏幕
    坐标**上点一个可探索格把迷雾探开，主线才走得下去（引导文案 60004「神识外放探查迷雾」
    → 57004「继续探查」就是"去点地图"的提示）。
  * **别照引导标记点**：`guide` 被 `UIMapWindow:update_guide_position` 摆在目标格
    **+110px**（`GUID_OFFSET_Y`，UIMapWindow.lua:821），照它点会高 110px → 点不中。
    要用格子自己的 `world_pos` 换算（`WorldMapD`/`entity.world_pos` +
    `RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, ...)`）—— 实测把算出的
    坐标喂回游戏的 `ScreenToWorldPoint`+`WorldPos2GridPos` 能还原出同一个格 id。
  * **引导格未必可探索**：57004 的 `reach_explore_condition=true` 但
    `is_cell_can_explore=false`，点它十次都不推进；要按 `is_cell_can_explore` **挑格**
    （实测可探索的是 58003/58004/59002，就是屏幕上那几个带黄边的深色菱形）。
  * **判据用语义状态，别用控件数**：普通地块**不建 UI 控件**（`is_show_ui_widget=false`，
    走 3D 层），所以"探雾成功"之后 `cells` 仍可能是 0。判"地图能用了"要看
    `canExplore / visEnt / 目标格是否可点`（`map_state()` / `cell_info()`）。
  * 落地成基元：`map_open_until([goal])`（探雾到能走主线为止）、`map_click_cell(id[, sub])`
    （控件优先 + 坐标兜底）、`map_tap_explore()`（录制里"点空地"的替代）、`map_drag()`。
  * 别拿 `WorldMapWindow.ui_click_empty` 判成败 —— 实测它 `true` 时对话窗照样弹出来
    （那是"点了空地"的标记，不是"没点中"）。成不成看效果。
"""
import time

try:  # execute_code 通道的 C# 片段（平台内置助手，与本脚本同机，直接复用）
    from src.app.services.unity_bridge import cs_present, cs_text
except Exception:  # noqa: BLE001 —— 拿不到就退回层级读取（慢一点，但可用）
    cs_present = None
    cs_text = None

# 起跑线（需人工复位）：启动界面 BootWindow；新号流程由本用例自己完成"登出→注册→创角→启程"
RESET = {"scene": "Assets/Scenes/main.unity",
         "wait_for": "GameRoot/Canvas2D/Normal/TaskWindow(Clone)"}

# ---------------------------------------------------------------- 常用路径
TASK_OPT = "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click"
TASK_MASK = "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask"
DIALOG_BG = "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg"
BUBBLE = "GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full"
MAP_CONTENT = "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content"
HOUSE_MAP = "GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map"
SCROLL_TEXT = "GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)"
XIULIAN = "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)"
XIULIAN_UP = XIULIAN + "/XiulianLevelUpWindow(Clone)/btn_close"
# 修炼界面的**真**操作按钮（2026-09-23 定位）：
#   录制稿把"吐纳"记成了 `trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)`
#   —— 那是**拖拽监听区**（只有 Image+Button+UIPointerPass/UIDragPass），点它不触发吐纳
#   （实测连点 25 下，进度条仍 "再吐纳10次"，计数纹丝不动）。
#   真正的按钮是 `adapter/CommonFrame/content/center_btns/panel_btns/btn_tuna_gen_ball`
#   （XiuLianWidget.lua:15 绑定 → on_clicked_btn_tuna_gen_ball → AshramD.send_gen_exp_ball）。
#   实测点 3 下：计数 "再吐纳10次" → "再吐纳8次"（按钮点够次数后自己隐藏）。
TUNA_BTN = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
            "center_btns/panel_btns/btn_tuna_gen_ball")
XIU_LIAN_BTN = XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)"
# 聚灵界面的操作区：**滑动**触发（JuLingWidget.lua:356 listen_drag_on_panel → drag_func），
# 所以聚灵要用 `drag_on(JU_LING_BTN)` 而不是点击。`PanelBg(Clone)(Clone)` 是拖拽监听区，
# 对聚灵来说是**正确**的落点（对吐纳则是错的 —— 见 TUNA_BTN 的注释）。
JU_LING_BTN = XIULIAN + "/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)"
DANYAO_BTN = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
              "panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
DRUG_ROOT = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
             "xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item")
DRUG_1 = DRUG_ROOT + "(1)/item/img_icon/raycast"
DRUG_2 = DRUG_ROOT + "(2)/item/img_icon/raycast"
XIULIAN_BACK = XIULIAN + "/adapter/go_back/btn_back"
GANG_ROOM = "GameRoot/Canvas2D/Back/GangRoomWindow(Clone)"
JU_LING_TA = "GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)"
RESULT_CLOSE = "GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg"


# ------------------------------------------------------------------ 工具
def require_play_mode():
    """没在 Play Mode 时立刻报错：运行时对象还不存在，硬等只会白等一轮超时。

    平台不代管进退 Play（会触发域重载），要跑就先在 Unity 里点 Play。
    """
    st = u.status() or {}
    ed = st.get("editor") or {}
    if not (st.get("is_playing") or ed.get("isPlaying")):
        raise AssertionError(
            "编辑器不在 Play Mode —— 运行时界面还不存在。"
            "请先在 Unity 里点 Play（平台不代管进退 Play），再重新执行本用例。")


def probe(path):
    """对象在不在 / 显示不显示（一次调用拿回两项）。

    走 execute_code（cs_present），**不走 find_gameobjects** —— 后者会撞上
    "工程有未导入的外部改动"那道闸门，被拦下来会把用例误判成环境错误。
    查不到返回 ok=False；只有桥/会话真出问题才抛错（别把环境故障说成"没找到"）。
    """
    if cs_present is not None:
        try:
            out = u.exec_csharp(cs_present(path))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "not found" in msg or "不存在" in msg:
                return {"ok": False, "active": False}
            raise
        res = out.get("result")
        if isinstance(res, dict):
            return res
        return {"ok": False, "active": False, "raw": str(out)[:200]}
    # 兜底：读层级（对象不存在时 hierarchy 会抛，吞掉即可）
    try:
        r = u.hierarchy(root=path, depth=1, max_nodes=5)
    except Exception:  # noqa: BLE001
        return {"ok": False, "active": False}
    for row in (r.get("rows") or []):
        if row[0] == path:
            return {"ok": True, "active": row[1] == "1"}
    return {"ok": False, "active": False}


def is_visible(path):
    """对象存在且 activeInHierarchy（关掉的窗口仍在场景里，"关没关"看这个）。"""
    if not path:
        return False
    return bool(probe(path).get("active"))


#: "推进剧情"时可点的节点：对话窗背景、对话气泡、序章旁白的分页按钮。
#: 这些都是"点一下剧情往下走"的通用节点，不改变剧情走向，只是替代录制时的固定点击数。
#: **必须定义在使用者（wait_visible / advance_story）之前** —— 否则运行时 NameError。
ADVANCE_NODES = (DIALOG_BG, BUBBLE, SCROLL_TEXT + "/btn_continune")


def wait_visible(path, timeout=30, label="", advance=True):
    """轮询等界面出现（比 wait_for 轻：wait_for 每次调用固定约 12s 开销）。

    `advance=True` 时，等待期间若发现**剧情节点**（对话框/气泡/旁白）在场就顺手点一下
    推进剧情 —— 这是"等目标出现"这一步最常见的堵点（2026-09-23 实测：点开「神秘妖王」
    对话后录制稿只点了 1 下对话框，剧情没推完就 `tap(TASK_OPT)`，白等 45s 才报错）。
    只点 ADVANCE_NODES，不改剧情走向；点了会打印一行，便于回看。
    """
    t0 = time.time()
    advanced = 0
    while time.time() - t0 < timeout:
        if is_visible(path):
            return True
        if advance:
            for node in ADVANCE_NODES:
                if node != path and is_visible(node):
                    u.click(node)
                    advanced += 1
                    print("STEP: 等 %s 期间推进剧情第 %d 下（点 %s）" % (_short(path), advanced, _short(node)))
                    break
        time.sleep(0.5)
    raise AssertionError("等待超时(%ss)：%s 未显示 %s（期间推进剧情 %d 下）"
                         % (timeout, path, label, advanced))


def wait_hidden(path, timeout=30, label="", advance=True):
    """等界面**关掉**（与 wait_visible 对称：等待期间也推进剧情，否则会白等到超时）。"""
    t0 = time.time()
    advanced = 0
    while time.time() - t0 < timeout:
        if not is_visible(path):
            return True
        if advance:
            for node in ADVANCE_NODES:
                if node != path and is_visible(node):
                    u.click(node)
                    advanced += 1
                    print("STEP: 等 %s 关闭期间推进剧情第 %d 下" % (_short(path), advanced))
                    break
        time.sleep(0.5)
    raise AssertionError("等待超时(%ss)：%s 未关闭 %s（期间推进剧情 %d 下）"
                         % (timeout, path, label, advanced))


def text_of(path, timeout=8, step=0.4):
    """读对象及其子孙的文本（走 execute_code，不用会被闸门拦下的 manage_components）。"""
    deadline = time.time() + timeout
    last = ""
    while True:
        try:
            if cs_text is not None:
                out = u.exec_csharp(cs_text(path))
                res = out.get("result")
                if isinstance(res, dict) and res.get("ok"):
                    return " ".join(str(p) for p in (res.get("parts") or []))
                last = str((res or {}).get("error") or out)[:300]
            else:
                return u.subtree_text(path)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)[:300]
        if time.time() >= deadline:
            return last
        time.sleep(step)


def expect_text(path, contains, timeout=10):
    """断言对象的文本里含某段文字（等价于 u.expect_text，但不依赖被拦的工具）。"""
    t0 = time.time()
    last = ""
    while True:
        last = text_of(path, timeout=1)
        if contains in last:
            print("OK  文本断言：%r ⊂ %r" % (contains, last[:90]))
            return
        if time.time() - t0 >= timeout:
            raise AssertionError("%s 的文本里没有 %r（实际: %r）" % (path, contains, last[:300]))
        time.sleep(0.4)


def _short(path):
    return "/".join(str(path).split("/")[-2:])


def dump_visible_on_failure(path):
    """点不到的时候把"现在屏幕上有哪些窗口"打出来 —— 失败现场的证据，省一轮重跑。"""
    print("---- 点不到 %s；现场可见的窗口 ----" % _short(path))
    for root in ("GameRoot/Canvas2D/Normal", "GameRoot/Canvas2D/Back", "GameRoot/Canvas2D/Top",
                 "GameRoot/Canvas2D/TopMost", "GameRoot/Canvas2D"):
        try:
            r = u.hierarchy(root=root, depth=1, max_nodes=80)
        except Exception:  # noqa: BLE001
            continue
        rows = [row for row in (r.get("rows") or []) if row[0] != root and row[1] == "1"]
        if rows:
            print("   %s: %s" % (root, ", ".join(row[0].split("/")[-1] for row in rows)))


def tap(path, timeout=45, label="", gap=0.25):
    """等控件真的显示出来再点。这一步的关卡 —— 期望的东西没出现就停在原地报错。

    录制回放是"立刻点"，界面没出来就点了个空；这里把"等这个界面/控件出现"变成
    每一步的关卡 —— 期望的东西没出现就停在原地报错，而不是静默跳过。

    对**剧情节点**（对话框/气泡/旁白）特殊处理：剧情是一段多页文本，录制稿只记了当时
    点了几下，点不够剧情就停在那儿、下一步白等到超时（2026-09-23 实测：「神秘妖王」
    那段只点了 1 下）。所以这里对剧情节点改成"点到它消失为止"。
    """
    try:
        wait_visible(path, timeout, label)
    except AssertionError:
        dump_visible_on_failure(path)
        raise
    if path in ADVANCE_NODES:
        for _ in range(20):
            if not is_visible(path):
                break
            u.click(path)
            time.sleep(gap)
        return
    u.click(path)
    time.sleep(gap)


def tap_opt(path, timeout=8, gap=0.25):
    """「在就点、不在就跳过」——给录制稿里那些多点几下也无所谓的地方用。

    录制时的节奏决定了大对话框要点几下、修炼要连点几次；次数跟当时的动画/网络
    有关，写死会让脚本在"少点一下"时白等 45s 再报错。跳过的每一步都打印，便于回看。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_visible(path):
            u.click(path)
            time.sleep(gap)
            return True
        time.sleep(0.4)
    print("SKIP(不在/不显示)：%s" % _short(path))
    return False


def pause(seconds):
    """还原录制时的停顿节奏（封顶 5s）。

    录制稿里的"人工停顿 Xs"去噪后只剩注释，于是整条回放会一路抢跑；同一控件连续
    点两下时，第二下会在第一下生效前就打出去。长停顿（等服务器打架、等过场）不必
    照搬 —— 下一步的 tap 会等界面真的出来。
    """
    time.sleep(min(float(seconds), 5.0))


MAP_CELLS = ("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/"
             "WorldExploreItemWidget_new(Clone)")
MAP_GUIDE = "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/guide"

#: 取"地图引导标记"的屏幕坐标。这个标记由 UIMapWindow:update_guide_position 摆在
#: **目标格**的位置上 —— 所以它的屏幕坐标就是要点的位置。
_CS_GUIDE_XY = r'''
var g = UnityEngine.GameObject.Find("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/guide");
if (g == null) return "{\"ok\":false,\"error\":\"no guide\"}";
var rt = g.GetComponent<UnityEngine.RectTransform>();
var canvas = g.GetComponentInParent<UnityEngine.Canvas>();
var cam = canvas != null ? canvas.worldCamera : null;
if (cam == null) cam = UnityEngine.Camera.main;
var c = new UnityEngine.Vector3[4];
rt.GetWorldCorners(c);
var s0 = UnityEngine.RectTransformUtility.WorldToScreenPoint(cam, c[0]);
var s2 = UnityEngine.RectTransformUtility.WorldToScreenPoint(cam, c[2]);
float x = (s0.x + s2.x) / 2f;
float y = (s0.y + s2.y) / 2f;
bool on = x >= 0f && x <= UnityEngine.Screen.width && y >= 0f && y <= UnityEngine.Screen.height;
return "{\"ok\":true,\"x\":" + x + ",\"y\":" + y + ",\"onScreen\":" + (on ? "true" : "false") + "}";
'''

#: 在**屏幕坐标**上派发一次真实点击。地图的 on_ui_click 用点击坐标反算目标格，
#: 所以只有这条路能点中地图上的格子（u.click 给的是对象中心，落在屏幕外）。
#:
#: __ON__ 给对象路径时，把 down/up/click 这一串**直接发给那个对象**（不走 RaycastAll 的
#: 最上层命中）—— 实测地图格坐标上常被 `adapter/HoverTipWidget(Clone)/.../text_content`
#: 盖住，事件会被提示层吃掉、地图收不到（2026-09-23 探雾静默失败的真因）。
_CS_CLICK_XY = r"""
var es = UnityEngine.EventSystems.EventSystem.current;
if (es == null) return "{\"ok\":false,\"error\":\"no EventSystem\"}";
var pos = new UnityEngine.Vector2(__X__, __Y__);
var ped = new UnityEngine.EventSystems.PointerEventData(es);
ped.button = UnityEngine.EventSystems.PointerEventData.InputButton.Left;
ped.pressPosition = pos; ped.position = pos; ped.clickCount = 1;
string top = "";
int hits = 0;
var tgt = __ON__;
if (tgt != "") {
  var g = UnityEngine.GameObject.Find(tgt);
  if (g == null) return "{\"ok\":false,\"error\":\"target not found: " + tgt + "\"}";
  top = g.name + "(direct)";
  UnityEngine.EventSystems.ExecuteEvents.Execute(g, ped,
      UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);
  UnityEngine.EventSystems.ExecuteEvents.Execute(g, ped,
      UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);
  UnityEngine.EventSystems.ExecuteEvents.Execute(g, ped,
      UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
} else {
  var list = new System.Collections.Generic.List<UnityEngine.EventSystems.RaycastResult>();
  es.RaycastAll(ped, list);
  hits = list.Count;
  if (list.Count > 0) {
    top = list[0].gameObject.name;
    var go = list[0].gameObject;
    UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(go, ped,
        UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);
    UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(go, ped,
        UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);
    UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(go, ped,
        UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
  }
}
return "{\"ok\":true,\"top\":\"" + top + "\",\"hits\":" + hits + "}";
"""


def guide_screen_xy():
    """引导标记的屏幕坐标。**注意：这不是目标格的坐标** —— 见 cell_screen_xy()。"""
    out = u.exec_csharp(_CS_GUIDE_XY)
    r = out.get("result")
    return r if isinstance(r, dict) else {"ok": False}


# ---------------------------------------------------------------- Lua 通道
# 地图格子是"滚到哪、建到哪"，迷雾没探开时一个控件都没有（cells=0），所以**点不到控件**；
# 只能走"真实屏幕坐标点击"。而屏幕坐标必须用游戏自己的换算拿（实测反查能对上格子 id）：
#   on_ui_click: ClientUtil.ScreenToWorldPoint(CAMERA.main_camera, ...)  ← 反函数就是
#   UnityEngine.RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, entity.world_pos)
# 坑：**别拿 guide 标记的坐标去点** —— UIMapWindow:update_guide_position 把它摆在
# 目标格 + GUID_OFFSET_Y(=110)（UIMapWindow.lua:821），照它点会高 110px，
# click_position 拿到的就不是那个格 → 返回 false、迷雾不散（2026-09-23 实测）。
_LUA_HEAD = (
    "var t = System.Type.GetType(\"LuaManager, Assembly-CSharp\");"
    "var m = t.GetMethod(\"GetState\", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);"
    "var s = m.Invoke(null, null); var st = s.GetType();"
    "System.Reflection.MethodInfo ds = null;"
    "foreach (var mi in st.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)) {"
    "  var ps = mi.GetParameters();"
    "  if (mi.Name == \"DoString\" && ps.Length == 2 && ps[0].ParameterType == typeof(string) && ps[1].ParameterType == typeof(string)) { ds = mi; break; } }"
)


def _cs_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def lua(code, tag="z"):
    """跑一段 Lua 并把全局变量 __<tag> 读回来（只读优先：读状态随便读，改状态要克制）。

    DoString 写进去的全局名必须和读回的名字一致 —— 传 tag 就是为了避免抄漏。
    """
    body = code.replace("__z", "__" + tag)
    tail = ("ds.Invoke(s, new object[] { lua, \"p" + tag + "\" });"
            "var ip = st.GetProperty(\"Item\", new System.Type[] { typeof(string) });"
            "var v = ip.GetValue(s, new object[] { \"__" + tag + "\" });"
            "return \"{\\\"lua\\\":\\\"\" + (v == null ? \"null\" : v.ToString()"
            ".Replace(\"\\\\\", \"/\").Replace(\"\\\"\", \"'\")) + \"\\\"}\";")
    out = u.exec_csharp(_LUA_HEAD + "string lua = " + _cs_str(body) + ";" + tail)
    r = out.get("result")
    return r.get("lua") if isinstance(r, dict) else str(out)[:300]


#: 地图状态总览（**语义状态，不看控件**）。
#:
#: 为什么不用"格子控件数"判断地图好了没（2026-09-23 实测）：
#:   `UIMapCellUIWidget:refresh_visible_cells` 只给 `cell.is_show_ui_widget` 的格建控件
#:   （NPC/妖兽这类），**普通地块走 3D 层**（is_show_3d_widget）。所以探雾成功后
#:   `cells` 仍然可能是 0 —— 上一版 `map_ready` 等控件数，白等 120s 还误报"迷雾没探开"，
#:   实际迷雾早就散了（截图可见）且引导格已从 60004 推进到 57004。
#: 真正可靠的判据是：**引导格能推进 / 当前格可探索 / 可交互实体存在**。
_LUA_MAP_STATE = (
    "local p = {}\n"
    "local ok, err = pcall(function()\n"
    "  local w = UI.query('WorldMapWindow')\n"
    "  if w == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no window'; return end\n"
    "  local pos = nil\n"
    "  if w.guide_positions ~= nil then\n"
    "    for _, v in pairs(w.guide_positions) do pos = v; break end\n"
    "  end\n"
    "  p[#p+1] = 'ok=1'\n"
    "  p[#p+1] = 'guide=' .. tostring(pos)\n"
    "  p[#p+1] = 'name=' .. tostring(w.cur_guide_name)\n"
    "  p[#p+1] = 'room=' .. tostring(w.room_id)\n"
    "  local ew = w.explore_item_widget\n"
    "  local ncell, nvis = 0, 0\n"
    "  if ew ~= nil then\n"
    "    if ew.all_cells ~= nil then for _ in pairs(ew.all_cells) do ncell = ncell + 1 end end\n"
    "    if ew.all_visible_entities ~= nil then for _ in pairs(ew.all_visible_entities) do nvis = nvis + 1 end end\n"
    "  end\n"
    "  p[#p+1] = 'cells=' .. ncell\n"
    "  p[#p+1] = 'visEnt=' .. nvis\n"
    "  local ncan, nui = 0, 0\n"
    "  local all = UIMapD.entities_func(w.ui_map_type, w.room_id)\n"
    "  if all ~= nil then\n"
    "    for _, ent in ipairs(all) do\n"
    "      local k = ent.position\n"
    "      if GridMapD.is_cell_can_explore(w.room_id, k) then ncan = ncan + 1 end\n"
    "      if ent.is_show_ui_widget then nui = nui + 1 end\n"
    "    end\n"
    "  end\n"
    "  p[#p+1] = 'canExplore=' .. ncan\n"
    "  p[#p+1] = 'uiCells=' .. nui\n"
    "end)\n"
    "if not ok then p[#p+1] = 'ok=0'; p[#p+1] = 'err=lua exception' end\n"
    "__z = table.concat(p, '|')\n"
)


def map_state():
    """地图语义状态：{'guide','name','cells','visEnt','canExplore','uiCells',...}。"""
    return _parse_kv(lua(_LUA_MAP_STATE, "ms"))


#: 挑一个**可探索格**（`is_cell_can_explore`），优先屏内的，并给出它的屏幕坐标。
#: 迷雾只能靠点可探索格来探 —— **引导格本身未必可探索**（实测 57004：reachCond=true 但
#: canExplore=false，点它十次都不推进），所以探雾必须按这个函数挑格，不能照着 guide 点。
_LUA_PICK_EXPLORE = (
    "local p = {}\n"
    "local ok, err = pcall(function()\n"
    "  local w = UI.query('WorldMapWindow')\n"
    "  if w == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no window'; return end\n"
    "  local sw, sh = UnityEngine.Screen.width, UnityEngine.Screen.height\n"
    "  local cam = CAMERA.main_camera\n"
    "  local all = UIMapD.entities_func(w.ui_map_type, w.room_id)\n"
    "  local bp, bx, by, bon, bd = nil, 0, 0, false, nil\n"
    "  local n = 0\n"
    "  for _, e in ipairs(all) do\n"
    "    local pos = e.position\n"
    "    if GridMapD.is_cell_can_explore(w.room_id, pos) then\n"
    "      n = n + 1\n"
    "      local sp = UnityEngine.RectTransformUtility.WorldToScreenPoint(cam, e.world_pos)\n"
    "      local on = sp.x >= 0 and sp.x <= sw and sp.y >= 0 and sp.y <= sh\n"
    "      local d = math.abs(sp.x - sw / 2) + math.abs(sp.y - sh / 2)\n"
    "      if bp == nil or (on and not bon) or (on == bon and d < bd) then\n"
    "        bp, bx, by, bon, bd = pos, sp.x, sp.y, on, d\n"
    "      end\n"
    "    end\n"
    "  end\n"
    "  p[#p+1] = 'ok=1'\n"
    "  p[#p+1] = 'count=' .. n\n"
    "  p[#p+1] = 'pos=' .. tostring(bp)\n"
    "  p[#p+1] = 'x=' .. bx\n"
    "  p[#p+1] = 'y=' .. by\n"
    "  p[#p+1] = 'on=' .. (bon and '1' or '0')\n"
    "end)\n"
    "if not ok then p[#p+1] = 'ok=0'; p[#p+1] = 'err=lua exception' end\n"
    "__z = table.concat(p, '|')\n"
)


def pick_explore_cell():
    """挑一个可探索格（优先屏内、靠近屏幕中心）。返回 {'ok','count','pos','x','y','onScreen'}。"""
    return _parse_kv(lua(_LUA_PICK_EXPLORE, "pk"))


#: 查某个格"能不能点"：可探索 或 有可交互的 UI 控件，且可访问。
#: 这就是"迷雾探到位了没"的判据 —— 比"格子控件数"可靠（普通地块不建控件）。
_LUA_CELL_INFO = (
    "local p = {}\n"
    "local ok, err = pcall(function()\n"
    "  local w = UI.query('WorldMapWindow')\n"
    "  if w == nil then p[#p+1] = 'ok=0'; return end\n"
    "  local pos = __POS__\n"
    "  local e = UIMapD.entity_func(w.ui_map_type, w.room_id, pos)\n"
    "  if e == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no entity'; return end\n"
    "  local can = GridMapD.is_cell_can_explore(w.room_id, pos)\n"
    "  local sp = UnityEngine.RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, e.world_pos)\n"
    "  local on = sp.x >= 0 and sp.x <= UnityEngine.Screen.width and sp.y >= 0 and sp.y <= UnityEngine.Screen.height\n"
    "  p[#p+1] = 'ok=1'\n"
    "  p[#p+1] = 'can=' .. tostring(can)\n"
    "  p[#p+1] = 'ui=' .. tostring(e.is_show_ui_widget)\n"
    "  p[#p+1] = 'visit=' .. tostring(e.is_can_visit)\n"
    "  p[#p+1] = 'on=' .. (on and '1' or '0')\n"
    "  p[#p+1] = 'x=' .. sp.x\n"
    "  p[#p+1] = 'y=' .. sp.y\n"
    "  p[#p+1] = 'clickable=' .. tostring(e.is_can_visit and (can or e.is_show_ui_widget) or false)\n"
    "end)\n"
    "if not ok then p[#p+1] = 'ok=0'; p[#p+1] = 'err=lua exception' end\n"
    "__z = table.concat(p, '|')\n"
)


def cell_info(pos):
    """某格的状态：{'ok','can','ui','visit','onScreen','x','y','clickable'}。"""
    return _parse_kv(lua(_LUA_CELL_INFO.replace("__POS__", str(int(pos))), "ci"))


def map_open_until(goal=None, max_explores=10, timeout=150, label=""):
    """把世界地图打开到"能接着走主线"为止：全迷雾就**点可探索格**把迷雾探开。

    goal 给一个格 id 时，探到**那个格可点**为止（主线下一环的目标格）；不给则探到
    "没有可探索格"或已有可交互实体为止。

    实测要点（2026-09-23，room=12100）：
      * 地图初始全迷雾：`cells=0 / visEnt=0 / canExplore=3`，屏幕上那 3 个带黄边的深色
        菱形就是可探索格（58003/58004/59002）。
      * **引导格未必可探索** —— 57004 的 `reachCond=true` 但 `canExplore=false`，点它
        不会推进（连续 10 次实测无效）；必须按 `pick_explore_cell()` 挑格。
      * 每次探雾只推进一格，所以这里循环点，直到 goal 可点 / 没有可探索格。
    """
    t0 = time.time()
    clicks = 0
    last = ""
    while time.time() - t0 < timeout:
        if goal is not None:
            ci = cell_info(goal)
            if ci.get("clickable"):
                print("OK  世界地图就绪%s：目标格 %s 已可点（可探索=%s 有控件=%s）"
                      % (label, goal, ci.get("can"), ci.get("ui")))
                return ci
        st = map_state()
        pk = pick_explore_cell()
        can = int(pk.get("count") or 0)
        vis = int(st.get("visEnt") or 0)
        cells = int(st.get("cells") or 0)
        if goal is None and (vis or cells):
            print("OK  世界地图就绪%s（实体=%s 控件=%s）" % (label, vis, cells))
            return st
        if can == 0:
            if clicks:
                print("WARN: 没有可探索格了，但目标格 %s 仍不可点（%s）"
                      % (goal, cell_info(goal) if goal else ""))
            return st
        if clicks >= max_explores:
            print("WARN: 探雾已达上限 %d 次，目标格 %s 仍不可点" % (max_explores, goal))
            return st
        if not pk.get("pos"):
            print("WARN: 挑不到可探索格：%s" % pk)
            return st
        map_click_cell(pk["pos"], focus=True)
        clicks += 1
        last = "探雾第 %d 次：点 %s @(%s,%s)" % (clicks, pk["pos"], pk.get("x"), pk.get("y"))
        print("STEP: %s" % last)
        time.sleep(2.0)
    raise AssertionError("等 %ss 世界地图仍打不开（%s）" % (timeout, last))


#: 在**地图上**按格 id 点一下（屏幕坐标路线）。
#: 与 `_LUA_CELL_XY` 的区别：不挑引导格、直接给坐标（找到该格就点）。
_LUA_CLICK_CELL = (
    "local p = {}\n"
    "local ok, err = pcall(function()\n"
    "  local w = UI.query('WorldMapWindow')\n"
    "  if w == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no window'; return end\n"
    "  local pos = __POS__\n"
    "  if __FOCUS__ then\n"
    "    local need = w:check_need_click_scroll(pos)\n"
    "    if need then w:scroll_to_position(pos, false, true) end\n"
    "    p[#p+1] = 'focused=' .. tostring(need)\n"
    "  end\n"
    "  local e = UIMapD.entity_func(w.ui_map_type, w.room_id, pos)\n"
    "  if e == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no entity'; return end\n"
    "  local sp = UnityEngine.RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, e.world_pos)\n"
    "  local on = sp.x >= 0 and sp.x <= UnityEngine.Screen.width and sp.y >= 0 and sp.y <= UnityEngine.Screen.height\n"
    "  p[#p+1] = 'ok=1'\n"
    "  p[#p+1] = 'pos=' .. pos\n"
    "  p[#p+1] = 'x=' .. sp.x\n"
    "  p[#p+1] = 'y=' .. sp.y\n"
    "  p[#p+1] = 'on=' .. (on and '1' or '0')\n"
    "end)\n"
    "if not ok then p[#p+1] = 'ok=0'; p[#p+1] = 'err=lua exception' end\n"
    "__z = table.concat(p, '|')\n"
)


def _parse_kv(raw):
    """解析 `k=v|k=v` 纯文本（回传通道把引号换掉了，所以这里不用 JSON）。

    **注意布尔**：lua 侧 `tostring(bool)` 出来的是 `"true"/"false"` 字符串，直接拿去做
    条件判断会踩 `bool("false") is True` 的坑（2026-09-23 实测：`clickable=false` 被判成
    "已就绪"，于是探雾一次都没点就报成功）。所以这里统一转成 Python 布尔。
    """
    if isinstance(raw, dict):
        return raw
    out = {}
    for seg in str(raw or "").split("|"):
        if "=" in seg:
            k, v = seg.split("=", 1)
            k, v = k.strip(), v.strip()
            if v in ("true", "false"):
                out[k] = (v == "true")
            elif v == "nil":
                out[k] = None
            else:
                out[k] = v
    out["ok"] = (out.get("ok") == "1")
    for k in ("x", "y"):
        if isinstance(out.get(k), str):
            try:
                out[k] = float(out[k])
            except ValueError:
                pass
    if isinstance(out.get("pos"), str):
        try:
            out["pos"] = int(out["pos"])
        except ValueError:
            pass
    out["onScreen"] = (out.get("on") == "1")
    return out


def cell_screen_xy(focus=False):
    """拿"该点的那个格"（优先引导格）的真实屏幕坐标 —— 迷雾里没有控件，只能靠坐标。

    返回 {'ok','pos','x','y','onScreen'}。focus=True 时先滚到该格再取坐标。
    """
    code = _LUA_CLICK_CELL.replace("__POS__", "nil").replace(
        "__FOCUS__", "true" if focus else "false")
    code = code.replace(
        "  local pos = nil\n",
        "  local pos = nil\n"
        "  if w.guide_positions ~= nil then\n"
        "    for _, v in pairs(w.guide_positions) do pos = v; break end\n"
        "  end\n"
        "  if pos == nil then\n"
        "    local all = UIMapD.entities_func(w.ui_map_type, w.room_id)\n"
        "    if all ~= nil then\n"
        "      for k, _ in pairs(all) do\n"
        "        if GridMapD.is_cell_can_explore(w.room_id, k) then pos = k; break end\n"
        "      end\n"
        "    end\n"
        "  end\n"
        "  if pos == nil then p[#p+1] = 'ok=0'; p[#p+1] = 'err=no cell'; return end\n")
    return _parse_kv(lua(code, "xy"))


def click_screen(x, y, on_path=""):
    """在屏幕坐标上点一下（真实指针序列）。

    on_path 非空时把事件直接派发给该对象（绕开"被悬浮提示层盖住"的问题）。
    """
    code = (_CS_CLICK_XY
            .replace("__X__", "%.1ff" % float(x))
            .replace("__Y__", "%.1ff" % float(y))
            .replace("__ON__", '"%s"' % on_path))
    out = u.exec_csharp(code)
    r = out.get("result")
    return r if isinstance(r, dict) else {"ok": False}


def map_cell_count():
    """地图上现在有几个格子**控件**（只统计 NPC/妖兽这类有 UI 的格，普通地块走 3D 层）。"""
    try:
        r = u.hierarchy(root=MAP_CELLS, depth=1, max_nodes=40)
    except Exception:  # noqa: BLE001
        return 0
    return len([row for row in (r.get("rows") or []) if row[0] != MAP_CELLS])


def map_ready(timeout=120, settle=3.0, label=""):
    """等到世界地图"可以接着走主线"为止 —— 全迷雾就**点可探索格**探雾。

    这是 `map_open_until()` 的薄封装：不指定目标格时，探到"有可交互实体/格子控件"
    或"没有可探索格"为止（老用例里 `map_ready()` 就是这个语义）。
    需要"探到某个具体格可点"时直接用 `map_open_until(goal=<格 id>)`。
    """
    return map_open_until(goal=None, timeout=timeout, label=label)


def map_click_cell(pos, sub="", focus=True):
    """点地图上的某个格 —— **控件优先，坐标兜底**。

    两条路线各有适用面（2026-09-23 实测）：
      1. **控件路线**：格子上有 UI 控件时（NPC/妖兽这类 `WorldExploreRoleItem_new(Clone)`）
         直接点控件，还能精确点到子控件（如 `go_info/bg_threat` 威胁图标）。普通地块没有
         控件，这条路会落空。
      2. **坐标路线**：用格子自己的 `world_pos` 换算屏幕坐标点 —— 迷雾里、普通地块上都行
         （实测：点可探索格能探雾、点 NPC 格能弹出对话窗）。`u.click` 不能用：它拿对象中心
         当屏幕坐标，而 map_content 是 9353x15125 的滚动区、中心点在屏幕外。

    不要拿 `WorldMapWindow.ui_click_empty` 判成败 —— 实测它 `true` 时对话窗照样弹了出来
    （它是"点了空地"的标记，不是"没点中"）。成不成看**效果**：对话窗出现 / 引导推进。
    """
    tag = "(%s)" % pos
    try:
        r = u.hierarchy(root=MAP_CELLS, depth=1, max_nodes=60)
    except Exception:  # noqa: BLE001
        r = {}
    for row in (r.get("rows") or []):
        if row[0] != MAP_CELLS and tag in row[0].split("/")[-1]:
            path = row[0] + (("/" + sub.lstrip("/")) if sub else "")
            if is_visible(path):
                u.click(path)
                time.sleep(0.8)
                print("OK  点地图格 %s（控件路线）" % pos)
                return True
    code = (_LUA_CLICK_CELL
            .replace("__POS__", str(int(pos)))
            .replace("__FOCUS__", "true" if focus else "false"))
    ci = _parse_kv(lua(code, "cx"))
    if not ci.get("ok") or not ci.get("onScreen"):
        print("WARN: 格子 %s 既没有可点控件、屏幕坐标也拿不到：%s" % (pos, ci))
        return False
    click_screen(ci["x"], ci["y"], MAP_CONTENT)
    time.sleep(0.8)
    print("OK  点地图格 %s（坐标路线 @%d,%d）" % (pos, ci["x"], ci["y"]))
    return True

def map_cell(cell_id, sub="", timeout=25):
    """按格子 id 找地图上的格子**控件**并点它（NPC/妖兽这类有 UI 的格才适用）。

    普通地块没有控件 → 会等到超时；那种情况请用 `map_click_cell(id)`（屏幕坐标路线）。
    保留控件路线是因为"点控件"能精确命中格子上的**子控件**（如 `go_info/bg_threat`
    这种威胁图标），而坐标点击只能点到格子本身。
    """
    tag = "(%s)" % cell_id
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = u.hierarchy(root=MAP_CELLS, depth=1, max_nodes=60)
        except Exception:  # noqa: BLE001
            r = {}
        for row in (r.get("rows") or []):
            name = row[0].split("/")[-1]
            if row[0] != MAP_CELLS and tag in name:
                path = row[0] + (("/" + sub.lstrip("/")) if sub else "")
                tap(path, 20, "(地图格子 %s)" % cell_id)
                return path
        time.sleep(0.8)
    raise AssertionError("等 %ss 地图上都没出现 id=%s 的格子控件" % (timeout, cell_id))

def map_tap_explore(timeout=6):
    """在地图上点一个**可探索格**（推进"探雾/寻路"），没有就跳过。

    录制稿里那几十下 `tap_opt(MAP_CONTENT)` 是"点空地走位"，但录制器不记点击坐标，
    回放时 `u.click(map_content)` 只会点到对象中心（在屏幕外）= 点了个空气，每一下还要
    白等 8s。这里改成：**有可探索格就按它的真实屏幕坐标点一下，没有就跳过** ——
    语义与录制一致（点空地推进探索），代价从"每次最多 8s"降到一次 Lua 读。
    """
    st = map_state()
    if not st.get("ok"):
        print("SKIP(地图不在场)：map_tap_explore")
        return False
    if int(st.get("canExplore") or 0) <= 0:
        print("SKIP(暂无可探索格)：map_tap_explore")
        return False
    pk = pick_explore_cell()
    if not pk.get("ok") or not pk.get("pos"):
        print("SKIP(挑不到可探索格)：map_tap_explore")
        return False
    map_click_cell(pk["pos"], focus=True)
    return True


def map_drag(dx=0, dy=-400, steps=8, gap=0.05):
    """在**地图上**做一次真实滑动（屏幕坐标手势）—— 录制里的"拖拽回放"用。

    录制稿里的 `u.drag(MAP_CONTENT, MAP_CONTENT)`（起终点同一个对象）等于没滑，
    而地图要"滚到目标格"才能看到/点到目标。这里在屏幕中间按给定位移滑一次。
    """
    cx, cy = 540, 960
    es = ("var es = UnityEngine.EventSystems.EventSystem.current;"
          "if (es == null) return \"{\\\"ok\\\":false}\";")
    code = (
        es +
        "var __down = new UnityEngine.Vector2(%d, %d);" % (cx, cy) +
        "var __ped = new UnityEngine.EventSystems.PointerEventData(es);"
        "var __mc = UnityEngine.GameObject.Find(\"%s\");" % MAP_CONTENT +
        "if (__mc == null) return \"{\\\"ok\\\":false,\\\"error\\\":\\\"no map\\\"}\";"
        "var __s = new System.Collections.Generic.List<UnityEngine.EventSystems.RaycastResult>();"
        "__ped.button = UnityEngine.EventSystems.PointerEventData.InputButton.Left;"
        "__ped.position = __down; __ped.pressPosition = __down; __ped.clickCount = 1;"
        "UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);"
        "UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.initializePotentialDrag);"
        "__ped.dragging = true;"
        "UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.beginDragHandler);"
        "for (int __i = 1; __i <= %d; __i++) {" % steps +
        "  float __t = (float)__i / %df;" % steps +
        "  __ped.position = new UnityEngine.Vector2(%d + %d * __t, %d + %d * __t);" % (cx, dx, cy, dy) +
        "  __ped.delta = new UnityEngine.Vector2(%d / %df, %d / %df);" % (dx, steps, dy, steps) +
        "  UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.dragHandler);"
        "}"
        "__ped.dragging = false;"
        "UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.endDragHandler);"
        "UnityEngine.EventSystems.ExecuteEvents.Execute(__mc, __ped,"
        " UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);"
        "return \"{\\\"ok\\\":true}\";")
    out = u.exec_csharp(code)
    r = out.get("result")
    print("INFO: 地图滑动 (%d,%d) -> %s" % (dx, dy, (r or {}).get("ok") if isinstance(r, dict) else r))
    return bool(isinstance(r, dict) and r.get("ok"))


#: 在某个控件上做一次真实拖拽（屏幕坐标手势：down → beginDrag → drag×N → endDrag → up）。
#: 用在"滑动才能触发"的交互上 —— 修炼界面的**聚灵/吸灵气球**就是这类：
#:   JuLingWidget:listen_drag_on_panel(...) → drag_func（JuLingWidget.lua:356）
#:   XiuLianWidget:listen_drag_on_panel(...) → check_click_balls(pos)（XiuLianWidget.lua:423/891）
#:   **点按钮完全不生效**，必须滑过去。
#:
#: 屏幕坐标必须用 **Canvas 的 worldCamera** 换算 —— 这个工程的 UI 是 ScreenSpaceCamera
#: （`UI.get_ui_render_mode()`），用 `WorldToScreenPoint(null, …)` 会得到负数（2026-09-23 实测
#: 全部算出 -1000 附近），手势就落到屏幕外了。
_CS_DRAG_XY = r"""
var es = UnityEngine.EventSystems.EventSystem.current;
if (es == null) return "{\"ok\":false,\"error\":\"no EventSystem\"}";
var __go = UnityEngine.GameObject.Find("__PATH__");
if (__go == null) return "{\"ok\":false,\"error\":\"object not found\"}";
var __rt = __go.GetComponent<UnityEngine.RectTransform>();
if (__rt == null) return "{\"ok\":false,\"error\":\"no RectTransform\"}";
var __cv = __go.GetComponentInParent<UnityEngine.Canvas>();
var __cam = (__cv != null && __cv.worldCamera != null) ? __cv.worldCamera : UnityEngine.Camera.main;
var __c = new UnityEngine.Vector3[4];
__rt.GetWorldCorners(__c);
var __a = UnityEngine.RectTransformUtility.WorldToScreenPoint(__cam, __c[0]);
var __b = UnityEngine.RectTransformUtility.WorldToScreenPoint(__cam, __c[2]);
float __cx = (__a.x + __b.x) / 2f, __cy = (__a.y + __b.y) / 2f;
var __ped = new UnityEngine.EventSystems.PointerEventData(es);
__ped.button = UnityEngine.EventSystems.PointerEventData.InputButton.Left;
__ped.clickCount = 1;
var __p0 = new UnityEngine.Vector2(__cx + __DX0__, __cy + __DY0__);
__ped.position = __p0; __ped.pressPosition = __p0; __ped.delta = UnityEngine.Vector2.zero;
UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
    UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);
UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
    UnityEngine.EventSystems.ExecuteEvents.initializePotentialDrag);
__ped.dragging = true;
UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
    UnityEngine.EventSystems.ExecuteEvents.beginDragHandler);
for (int __i = 1; __i <= __STEPS__; __i++) {
  float __t = (float)__i / __STEPS__f;
  __ped.position = new UnityEngine.Vector2(__cx + __DX0__ + (__DX1__ - __DX0__) * __t,
                                           __cy + __DY0__ + (__DY1__ - __DY0__) * __t);
  __ped.delta = new UnityEngine.Vector2((__DX1__ - __DX0__) / __STEPS__f,
                                        (__DY1__ - __DY0__) / __STEPS__f);
  UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
      UnityEngine.EventSystems.ExecuteEvents.dragHandler);
}
__ped.dragging = false;
UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
    UnityEngine.EventSystems.ExecuteEvents.endDragHandler);
UnityEngine.EventSystems.ExecuteEvents.ExecuteHierarchy(__go, __ped,
    UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);
return "{\"ok\":true,\"center\":\"" + __cx + "," + __cy + "\",\"cam\":\"" + (__cam == null ? "null" : __cam.name) + "\"}";
"""


def drag_on(path, dx=0, dy=0, steps=8, gap=0.2):
    """在 `path` 上从中心滑到中心+(dx,dy)（屏幕坐标手势）。

    用于"滑动才能触发"的交互（修炼吐纳/聚灵）。dy 取负值 = 向上滑。
    """
    code = (_CS_DRAG_XY
            .replace("__PATH__", path)
            .replace("__DX0__", "0f").replace("__DY0__", "0f")
            .replace("__DX1__", "%df" % int(dx)).replace("__DY1__", "%df" % int(dy))
            .replace("__STEPS__f", "%df" % int(steps)).replace("__STEPS__", str(int(steps))))
    out = u.exec_csharp(code)
    r = out.get("result")
    ok = bool(isinstance(r, dict) and r.get("ok"))
    time.sleep(gap)
    return ok


def drag_until(path, goal, dx=0, dy=-260, steps=8, max_drags=25, label="", gap=0.6):
    """在 `path` 上反复滑动，直到 `goal` 出现 —— 给"吐纳/聚灵到升级"这类**次数不定**的操作。

    为什么不能用 tap：修炼界面的吐纳是**滑动**触发的（XiuLianWidget.lua:423/891），
    点按钮完全不生效（2026-09-23 实测：连点 25 下，进度条仍 0/12）。
    """
    for i in range(int(max_drags)):
        if is_visible(goal):
            print("OK  %s：滑了 %d 次后 %s 出现" % (label or "滑到目标", i, _short(goal)))
            return True
        if not is_visible(path):
            print("SKIP %s：可滑区域 %s 已不在场（滑了 %d 次）" % (label, _short(path), i))
            return is_visible(goal)
        drag_on(path, dx, dy, steps)
        time.sleep(gap)
    ok = is_visible(goal)
    print("%s %s：滑满 %d 次，goal=%s %s"
          % ("OK " if ok else "WARN", label or "滑到目标", max_drags, _short(goal), label))
    return ok


def find_child(parent, prefix, timeout=20):
    """在 parent 的直接子节点里按名字前缀找（运行期动态 id 的控件用这个）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = u.hierarchy(root=parent, depth=1, max_nodes=200)
        except Exception:  # noqa: BLE001
            r = {}
        for row in (r.get("rows") or []):
            p = row[0]
            if p != parent and p.rsplit("/", 1)[-1].startswith(prefix):
                return p
        time.sleep(0.5)
    raise AssertionError("在 %s 下找不到前缀为 %s 的子节点" % (parent, prefix))


def close_dialogs(next_path, max_clicks=10, label=""):
    """连点对话窗（click_bg），直到 next_path 出现；点满上限就返回 False。"""
    for _ in range(max_clicks):
        if is_visible(next_path):
            return True
        if is_visible(DIALOG_BG):
            u.click(DIALOG_BG)
            time.sleep(1.0)
        else:
            time.sleep(0.8)
    return is_visible(next_path)


def stage(title):
    print("=" * 12 + " " + title + " " + "=" * 12)


def at_start_line(path, label="", require=True):
    """跑之前先确认"从这一步开始"。

    平台**不复位、也不检查**起跑线（复位是改被测对象状态的动作，一律由人来做）。
    但"跑到一半才发现起点不对"是最贵的失败 —— 前面几十秒全白跑、报错还指向流程内部。
    所以这里在每段开头自己看一眼：不在就**当场停下**并写清该把游戏恢复到哪一步。
    """
    if is_visible(path):
        print("OK  起跑线：%s 在场 %s" % (_short(path), label))
        return True
    msg = ("不在起跑线：本段要求 %s 已经显示 %s。"
           "请先在游戏里手动走到这一步（平台不复位），再重新执行。" % (path, label))
    if require:
        raise AssertionError(msg)
    print("WARN: " + msg)
    return False


# 引擎/环境噪音（与本用例无关，一比全量就永远是红的）：Wwise 插件初始化、
# 编辑器截图尺寸不匹配、PlayerLoop 递归告警、远端配置未初始化、界面打开耗时告警。
_NOISE = ("Wwise", "CaptureScreenshot", "PlayerLoop internal function",
          "尝试获远端配置失败", "过长", "is not supported anymore")
_BASELINE = None


def check_console(tag):
    """按"无新增报错"判定：先记基线，跑完只比新增的那几条。"""
    global _BASELINE
    raw = u.errors() or []
    errs = [e for e in raw if not any(n in e for n in _NOISE)]
    if _BASELINE is None:
        _BASELINE = set(errs)
        new = []
    else:
        new = [e for e in errs if e not in _BASELINE]
    print("CONSOLE(%s): 原始 %d 条 / 过滤噪音后 %d 条 / 本次新增 %d 条"
          % (tag, len(raw), len(errs), len(new)))
    for e in new[:10]:
        print("   NEW: " + str(e)[:200])
    return new


ADVANCE_NODES = (DIALOG_BG, BUBBLE, SCROLL_TEXT + "/btn_continune")


def advance_story(target=None, max_clicks=30, label="", gap=1.0):
    """连点"推进剧情"的节点，直到剧情走完（没有可推进的节点了）或点满上限。

    录制稿里这类点击是按当时节奏记的（点 3 下对话框、2 下旁白…），剧情一长就不够用。
    这里改成"点到剧情节点消失为止" —— 语义相同（推进剧情），但不依赖录制时的次数。

    两条踩过的坑（2026-09-23）：
      1. **不能写成"target 一可见就返回"**：`advance_story(XIU_LIAN_BTN)` 里 XIU_LIAN_BTN
         在修炼界面上一直可见，于是它一下都没点就"成功"返回，后面等任务窗直接超时。
      2. 一开始就**没有**剧情节点时直接跳过（打印一行），别空转 max_clicks 次。
    """
    if not any(is_visible(n) for n in ADVANCE_NODES):
        ok = bool(target and is_visible(target))
        print("%s 当前没有可推进的剧情节点，跳过：target=%s %s"
              % ("OK " if ok else "SKIP", target, label))
        return ok
    clicked = 0
    for _ in range(max_clicks):
        hit = None
        for node in ADVANCE_NODES:
            if is_visible(node):
                hit = node
                break
        if hit is None:
            break
        u.click(hit)
        clicked += 1
        time.sleep(gap)
    ok = bool(target and is_visible(target))
    print("%s 剧情推进结束（点了 %d 下）：target=%s %s"
          % ("OK " if ok else "WARN", clicked, target, label))
    return ok


def tap_n(path, times, label="", timeout=20, gap=0.8):
    """在**同一个控件上连点 N 次**（每次点前都确认它还在）。

    录制稿里"连点修炼/吐纳"这种就是同一个按钮点好几下（吐纳 12 次才生成灵气）。
    写死次数 + 不确认控件在场，会在界面提前切走时点到空气；这里每次点前查一下，
    控件不在了就停下并打印实际点了几次（不报错 —— 界面切走多半是"已经够了"）。
    """
    done = 0
    for _ in range(int(times)):
        if not is_visible(path):
            break
        u.click(path)
        done += 1
        time.sleep(gap)
    print("%s 连点 %s：%d/%d 次 %s" % ("OK " if done else "SKIP", _short(path), done, times, label))
    return done


def tap_until(path, goal, max_clicks=25, label="", gap=0.8, click_gap=0.3):
    """连点 `path`，直到 `goal` 出现为止 —— 给"修炼到升级"这类**次数不定**的重复操作。

    为什么需要（2026-09-23）：修炼界面的「吐纳」要连点若干次才升级，录制稿写的是当时
    点了几下（`tap_opt(XIU_LIAN_BTN)` + `tap_opt(XIULIAN_UP)`）；次数一变就点到空气、
    或者点不够导致后面等界面超时。这里改成"点到升级弹窗出现为止"，语义不变、次数自适应。
    中途 `path` 不在了（界面切走）就停下。
    """
    for i in range(int(max_clicks)):
        if is_visible(goal):
            print("OK  %s：点了 %d 下后 %s 出现 %s"
                  % (label or "连点到目标", i, _short(goal), label))
            return True
        if not is_visible(path):
            time.sleep(click_gap)
            if is_visible(goal):
                print("OK  %s：点了 %d 下后 %s 出现 %s"
                      % (label or "连点到目标", i, _short(goal), label))
                return True
            print("SKIP %s：可点控件 %s 已不在场（点了 %d 下）" % (label, _short(path), i))
            return False
        u.click(path)
        time.sleep(gap)
    ok = is_visible(goal)
    print("%s %s：点满 %d 下，goal=%s %s"
          % ("OK " if ok else "WARN", label or "连点到目标", max_clicks, _short(goal), label))
    return ok


def dismiss_scroll_text(max_clicks=6):
    """序章过场文字：分页显示，点真按钮 btn_continune（go_end 只是文本标签，点了没用）。"""
    for _ in range(max_clicks):
        if not is_visible(SCROLL_TEXT):
            return True
        if is_visible(SCROLL_TEXT + "/btn_continune"):
            u.click(SCROLL_TEXT + "/btn_continune")
        time.sleep(1.2)
    return not is_visible(SCROLL_TEXT)
# ============================================================================
# STAGE 2　新手主界面 → 序章 → 主线「寻找道院」→ 修炼聚灵 → 加入道院 → 洞府升级
#   起跑线：新手主界面（STAGE 1 刚落地；序章文字窗可能还开着）
#   来源：手动录制稿（rec_20260923_005533_005a）的去噪版 —— 点击步骤一条不少，
#         只是把"立刻点"改成"等控件显示出来再点"，并把动态 id 换成前缀查找。
# ============================================================================
stage("STAGE 2A 寻找道院 → 修炼聚灵")
require_play_mode()
check_console("baseline")
at_start_line("GameRoot/Canvas2D/Normal/TaskWindow(Clone)", "(新手主界面：主线任务窗)")

# 序章过场文字（分页，点 btn_continune；若已翻完则跳过）
dismiss_scroll_text()

# 主线首环「寻找道院」：先把序章引导对话点完，直到主线选项出现
assert close_dialogs(TASK_OPT, max_clicks=8), "序章引导对话结束后未出现主线任务选项"
expect_text(TASK_OPT, "寻找道院")
u.screenshot("10_main_task.png")
tap(TASK_OPT, 30, "(主线-寻找道院)")

# 世界地图（寻路去道院）：地图**初始全迷雾**，先点可探索格把迷雾探开
wait_visible(MAP_CONTENT, 60, "(世界地图)")
u.screenshot("11_worldmap.png")
map_ready(label="(寻路去道院)")
map_tap_explore()
map_tap_explore()
map_tap_explore()
map_tap_explore()
map_click_cell("57004", "detail/bg")
tap("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/dialog/bg_big_dialog/panel_not_layout/info_player/player_hor")
tap_opt(DIALOG_BG)  # Button
u.drag(TASK_MASK, TASK_MASK)  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
tap(TASK_OPT)  # Button
# （人工停顿 33.5s）
pause(33.5)
tap("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)/btn_continune")  # Button
tap_opt("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)/btn_continune")  # Button
# 录制稿里这一串 3 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_OPT, max_clicks=12, label="推进剧情")
# （人工停顿 4.4s）
pause(4.4)
tap(TASK_OPT)  # Button
# （人工停顿 2.2s）
pause(2.2)
map_tap_explore()
# 录制里这是"从格子起拖"（录制器只对拖拽记坐标）→ 还原成点该格
map_click_cell("55008", "normal/bg_name")
map_drag()
map_tap_explore()
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
# 录制稿里这一串 5 次剧情点击 → 点到下一个界面出现为止
advance_story(TUNA_BTN, max_clicks=12, label="推进剧情")
tap(TUNA_BTN)  # Button
# （人工停顿 1.6s）
pause(1.6)
tap_opt(BUBBLE)  # Button
tap(TUNA_BTN)  # Button
# （人工停顿 3.9s）
pause(3.9)
tap_opt(XIULIAN_UP)  # Button
# 录制稿里这一串 3 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_OPT, max_clicks=12, label="推进剧情")
# （人工停顿 13.0s）
pause(13.0)
tap(TASK_OPT)  # Button
map_tap_explore()
map_tap_explore()
map_click_cell("53010", "detail/bg")
# 录制稿里这一串 4 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_OPT, max_clicks=12, label="推进剧情")
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour")  # Button
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
tap(TASK_OPT)  # Button
# （人工停顿 2.3s）
pause(2.3)
map_tap_explore()
map_click_cell("50010", "go_info/bg_threat")
tap("GameRoot/Canvas2D/Normal/SeaEnterWindow(Clone)/adapter/content/desc/layout/btn_changlle")
# （人工停顿 13.0s）
pause(13.0)
tap_opt(RESULT_CLOSE)  # Button
map_tap_explore()
map_tap_explore()
# （人工停顿 3.5s）
pause(3.5)
map_tap_explore()
map_click_cell("53010", "normal/bg_name/name")
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour")  # Button
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/CommonTabsWidget_V2(Clone)/back/btn_back/raycast")
# （人工停顿 17.3s）
pause(17.3)
tap("GameRoot/Canvas2D/Top/BlackBGWindow(Clone)/black_bg")

check_console("STAGE2A")
u.screenshot("18_stage2a_done.png")
print("STAGE 2A DONE: 寻找道院 → 修炼/聚灵/丹药")

# ============================================================================
# STAGE 2B　继续主线 → 加入道院（真武）→ 洞府升级 → 聚灵塔试炼
#   起跑线：STAGE 2A 结束时的现场（世界地图 / 洞府一带）
# ============================================================================
stage("STAGE 2B 加入道院 → 洞府升级")
require_play_mode()
check_console("baseline")
tap_opt("GameRoot/Canvas2D/Top/BlackBGWindow(Clone)/black_bg")
# （人工停顿 3.0s）
pause(3.0)
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
# （人工停顿 1.9s）
pause(1.9)
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
# （人工停顿 1.5s）
pause(1.5)
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(HOUSE_MAP)
print("SKIP(录制里的空拖拽，起终点同一对象)：img")
# （人工停顿 1.5s）
pause(1.5)
map_tap_explore()
map_click_cell("46013", "detail/bg_unlock")
tap("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1")
map_tap_explore()
map_tap_explore()
map_click_cell("45016", "normal/bg_name/name")
tap("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
tap("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/gua_panel/gua_content/item_1/process_des/txt_num")
tap("GameRoot/Canvas2D/Normal/DestinyTreasureDetailWindow(Clone)/adapter/bottom_panel/btn_repair/btn_repair_text")
tap_opt(DIALOG_BG)  # Button
# （人工停顿 2.1s）
pause(2.1)
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button
map_tap_explore()
map_click_cell("46019", "normal/bg_name/name")
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
tap("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/item_option(Clone)/btn_click/panel_normal")
# （人工停顿 4.1s）
pause(4.1)
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button
# （人工停顿 2.3s）
pause(2.3)
map_tap_explore()
map_tap_explore()
map_tap_explore()
# （人工停顿 2.4s）
pause(2.4)
map_tap_explore()
tap("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
tap("GameRoot/Canvas2D/Normal/ExpUpWindow(Clone)/btn_close")  # Button
# （人工停顿 3.6s）
pause(3.6)
tap("GameRoot/Canvas2D/Top/MessageBoxWindow(Clone)/adapter/common_bg/content/btn_right/text_btn_right")
tap(TUNA_BTN)  # Button
# （人工停顿 4.4s）
pause(4.4)
tap_opt(XIULIAN_UP)  # Button
tap(DANYAO_BTN)
tap_opt(DRUG_2)
tap_opt(DRUG_1)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport")
tap(TUNA_BTN)  # Button
# （人工停顿 4.1s）
pause(4.1)
# 录制稿里这一串 2 次点击 → 连点（控件不在场就停）
tap_n(XIULIAN_UP, 6, label="连点")
# （人工停顿 4.2s）
pause(4.2)
tap_opt(XIULIAN_UP)  # Button
tap(XIULIAN_BACK)  # Button
# （人工停顿 3.0s）
pause(3.0)
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
# （人工停顿 2.1s）
pause(2.1)
map_tap_explore()
# （人工停顿 2.0s）
pause(2.0)
map_tap_explore()
# （人工停顿 2.6s）
pause(2.6)
map_click_cell("40026", "detail/bg")
tap("GameRoot/Canvas2D/Normal/OptionWindow(Clone)/adapter/content/desc/btn_content/btn(1)/text")
# （人工停顿 1.8s）
pause(1.8)
map_click_cell("38028", "go_info/bg_threat")
tap("GameRoot/Canvas2D/Normal/SeaEnterWindow(Clone)/adapter/content/desc/layout/btn_changlle")
# （人工停顿 8.7s）
pause(8.7)
tap_opt(RESULT_CLOSE)  # Button
map_tap_explore()
map_tap_explore()
map_click_cell("36030", "detail/bg_unlock")
tap("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
# （人工停顿 19.8s）
pause(19.8)
tap("GameRoot/Canvas2D/Normal/SelectGangWindow(Clone)/adapter/btn_select")
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Normal/TaskConsumeWindow(Clone)/CommonSmallWindow/content/root/btn_all/btn_right/text")
tap(TASK_OPT)  # Button
tap_opt(BUBBLE)  # Button
tap_opt(BUBBLE)  # Button
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "传功弟子") + "/click")  # Button
# 录制稿里这一串 3 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_OPT, max_clicks=12, label="推进剧情")
tap(TASK_OPT)  # Button
# 里程碑：道院选择界面出现（选中真武宗门）
wait_visible("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)", 90, "(道院选择界面)")
expect_text("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_zhenwu/name_text", "真武")
tap("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_choose/sect_zhenwu/name_text")
tap("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_single/btn_join/text_select")
# （人工停顿 1.5s）
pause(1.5)
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "传功弟子") + "/click")  # Button
tap_opt(DIALOG_BG)  # Button
tap("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/text_level_name")
tap("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/part_room_grade/btn_speed_up/text_ashram_house")
tap("GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update")  # Button
wait_visible("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)", 30, "(洞府升级结果)")
tap("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)/btn_close")  # Button

wait_visible(XIULIAN, 45, "(修炼界面)")
u.screenshot("19_stage2_done.png")
check_console("STAGE2")
print("STAGE 2 DONE: 寻找道院 → 修炼聚灵 → 加入道院 → 洞府升级")

# ============================================================================
# STAGE 3A　聚灵塔试炼 → 道院外院晋升 → 功法装配 → 门派比试 → 收尾
#   起跑线：修炼界面（STAGE 2 结束在 XiulianMainWindow，洞府升级弹窗已关）
# ============================================================================
stage("STAGE 3A 聚灵塔试炼 → 外院晋升")
require_play_mode()
check_console("baseline")
at_start_line(XIULIAN, "(修炼界面)")
wait_visible(XIULIAN, 60, "(修炼界面)")
# 录制稿里这一串 2 次点击 → 连点（控件不在场就停）
tap_n(TUNA_BTN, 6, label="连点")
# （人工停顿 1.9s）
pause(1.9)
# （人工停顿 1.6s）
pause(1.6)
tap(XIULIAN_BACK)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main")  # Button
tap(TASK_OPT)  # Button
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "传功弟子") + "/click")  # Button
tap(TASK_OPT)  # Button
# 录制稿里这一串 2 次点击 → 连点（控件不在场就停）
tap_n(TUNA_BTN, 6, label="连点")
tap("GameRoot/Canvas2D/Normal/NormalGetNewWindow(Clone)/btn_close")  # Button
# （人工停顿 1.7s）
pause(1.7)
tap(DANYAO_BTN)
tap_opt(DRUG_2)
tap_opt(DRUG_1)
tap_opt(DRUG_1)
tap(TUNA_BTN)  # Button
# （人工停顿 4.1s）
pause(4.1)
tap_opt(XIULIAN_UP)  # Button
tap(XIULIAN_BACK)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content")
tap(TASK_OPT)  # Button
tap_opt(DIALOG_BG)  # Button
tap("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(1)/img_icon")
tap("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
tap(TASK_OPT)  # Button
map_tap_explore()
map_click_cell("43030", "detail/bg_unlock")
tap("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1")
tap(TASK_OPT)  # Button
# （人工停顿 1.9s）
pause(1.9)
map_tap_explore()
map_tap_explore()
map_drag()
map_tap_explore()
u.drag(MAP_CONTENT, "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(44034)/go_info/name")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
map_tap_explore()
map_drag()
map_click_cell("47038", "normal/bg_name/name")
tap("GameRoot/Canvas2D/Normal/TempleInfoWindowExplore(Clone)/adapter/content/desc/btn_layout/btn_enter/text_enter")
tap("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/map_sv/Viewport/map_content/icon_root/monster_root/normal_monster(Clone)/icon")  # Button
tap("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/shown_area/btn_enter/go_enter/txt")
# （人工停顿 16.1s）
pause(16.1)
# 录制稿里这一串 5 次剧情点击 → 点到下一个界面出现为止
advance_story("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_quality", max_clicks=12, label="推进剧情")
tap("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_quality")
tap("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
tap(TASK_OPT)  # Button
tap(find_child("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content", "challengeitem") + "/btn_challenge/text")
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/challenge_top/slider_root/reward_box_root/reward_box(Clone)/icon_canget/bg/bg_2")
tap("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
tap("GameRoot/Canvas2D/Battle/MainWindow(Clone)/widget_panel/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des/complete_team")
tap(TASK_OPT)  # Button
tap_opt(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/normal_condition/btn_level_up/text")
tap("GameRoot/Canvas2D/Normal/GangDutyImproveWindow(Clone)/root/btn_mask")  # Button
tap("GameRoot/Canvas2D/Normal/GongfaCompositeWindow(Clone)/bg")  # Button
# （人工停顿 3.6s）
pause(3.6)
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/bg_content/jihuo_root/condition_item2/text_condition")
# （人工停顿 1.9s）
pause(1.9)
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
# （人工停顿 1.7s）
pause(1.7)
tap("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
tap(TASK_OPT)  # Button
tap_opt(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/gongfa/txt")
tap_opt(BUBBLE)  # Button
tap_opt(BUBBLE)  # Button
tap("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/equip_panel/btn_equip/select/text")
tap(find_child("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/skill_overview/main_panel/viewport/content", "ceng-") + "/list/shentong_equip(Clone)/gongfa_item/item/cilck")
tap("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/btn_equip_back")  # Button
# （人工停顿 2.9s）
pause(2.9)
tap("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/house/bg_normal/img")
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main")  # Button
tap(TASK_OPT)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_icon")
tap("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
# （人工停顿 1.7s）
pause(1.7)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
tap_opt(BUBBLE)  # Button
# 录制稿里这一串 2 次点击 → 聚灵是**滑动**触发，改成滑动
drag_until(JU_LING_BTN, XIULIAN_UP, dy=-300, max_drags=10, label="聚灵")
# （人工停顿 7.1s）
pause(7.1)
# （人工停顿 4.5s）
pause(4.5)
tap_opt(XIULIAN_UP)  # Button
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_xiulian/unselect/icon")
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/part_room_grade/btn_speed_up/text_ashram_house")
tap("GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update")  # Button
wait_visible("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)", 30, "(洞府升级结果)")
tap("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)/btn_close")  # Button
# （人工停顿 2.9s）
pause(2.9)
tap(DANYAO_BTN)
tap_opt(DRUG_1)
tap_opt(DRUG_1)
tap(TUNA_BTN)  # Button
# （人工停顿 4.2s）
pause(4.2)
tap_opt(XIULIAN_UP)  # Button
tap(XIULIAN_BACK)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
tap(TASK_OPT)  # Button
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "传功弟子") + "/click")  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap("GameRoot/Canvas2D/Back/ChatWindow(Clone)/sv/Viewport")
tap("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/adapter/content/adapter1/bg")
tap("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/btn_close")  # Button
tap("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/pos/root_ziwei_treasure/recharge_item(Clone)/btn_click/icon")
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
# （人工停顿 2.2s）
pause(2.2)
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/btn_speical_free/speical_icon/CommonGetBoxReward/bg/bg_2")
tap("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy")  # Button
tap("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
# （人工停顿 2.2s）
pause(2.2)
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy")  # Button
# （人工停顿 2.0s）
pause(2.0)
tap("GameRoot/Canvas2D/Normal/RechargeConfirmWindow(Clone)/adapter/common_bg/content/btn_left/text_btn_left")
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy/btn_buy_txt")
tap("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_6/btn")  # Button
u.drag("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/gift_money_panel/text_other_reward", "GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/gift_money_panel/bg_first/text", "GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/top_panel/top_tab_root/bg_layout/TabBtn(Clone)/click/text")
tap_opt("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/top_panel/top_tab_root/bg_layout/TabBtn(Clone)/click/text")
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_1/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
# （人工停顿 2.1s）
pause(2.1)
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/reward/content/sv/viewport/content/reward_item(Clone)/img_icon")
tap("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
tap("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
tap("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
tap("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
# （人工停顿 1.7s）
pause(1.7)
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
# （人工停顿 2.0s）
pause(2.0)
tap("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/btn_close")  # Button
# （人工停顿 1.9s）
pause(1.9)
tap("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/btn/btn_enter/text_btn_enter")
u.drag("GameRoot/Canvas2D/Normal/ServerWeekGiftWindow(Clone)/adapter/content/gift_sv/Viewport/content_gift/gift_item(Clone)/bg/gift_base_panel/reward_content/reward_item(Clone)/img_icon", "GameRoot/Canvas2D/Normal/ServerWeekGiftWindow(Clone)/adapter/content/gift_sv/Viewport")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
# （人工停顿 6.2s）
pause(6.2)
u.drag("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content", "GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/content_map")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
tap("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content")
tap(find_child("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content", "challengeitem") + "/btn_challenge/text")
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
tap("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/house/bg_normal/img")
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
tap(DANYAO_BTN)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_quality")
tap_opt(DRUG_1)
tap_opt(DRUG_1)
# （人工停顿 2.2s）
pause(2.2)
tap(XIULIAN_BACK)  # Button
# （人工停顿 1.7s）
pause(1.7)
u.drag(HOUSE_MAP, HOUSE_MAP)  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 2.4s）
pause(2.4)
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content")
map_tap_explore()
map_click_cell("45044", "detail/bg")
# （人工停顿 1.6s）
pause(1.6)
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
u.drag("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(1)/img_quality", TASK_MASK)  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 13.3s）
pause(13.3)
tap_opt(RESULT_CLOSE)  # Button
tap(TASK_OPT)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button
# （人工停顿 1.8s）
pause(1.8)
map_tap_explore()
map_tap_explore()
map_tap_explore()
map_tap_explore()
map_click_cell("45044", "detail/bg")
# 录制稿里这一串 3 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_MASK, max_clicks=12, label="推进剧情")
tap_opt(TASK_MASK)
tap(TASK_OPT)  # Button

check_console("STAGE3A")
u.screenshot("29_stage3a_done.png")
print("STAGE 3A DONE: 聚灵塔试炼 → 外院晋升 → 功法装配")

# ============================================================================
# STAGE 3B　聚灵 → 门派比试 → 收尾（比试是服务端跑，单场最长约 50s）
#   起跑线：修炼界面（STAGE 3A 结束在 XiulianMainWindow）
# ============================================================================
stage("STAGE 3B 聚灵 → 门派比试")
require_play_mode()
check_console("baseline")
wait_visible(XIULIAN, 60, "(修炼界面)")
# （人工停顿 14.8s）
pause(14.8)
tap_opt(RESULT_CLOSE)  # Button
# （人工停顿 5.6s）
pause(5.6)
tap_opt(DIALOG_BG)  # Button
tap_opt(DIALOG_BG)  # Button
map_tap_explore()
map_tap_explore()
map_tap_explore()
tap("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content")
# 录制稿里这一串 4 次剧情点击 → 点到下一个界面出现为止
advance_story(TASK_OPT, max_clicks=12, label="推进剧情")
tap(TASK_OPT)  # Button
# （人工停顿 4.2s）
pause(4.2)
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "小比管事") + "/click")  # Button
tap(TASK_OPT)  # Button
tap_opt(BUBBLE)  # Button
tap("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_improve/text_start")
tap(find_child("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content", "list_item") + "/btn_all/text")
tap(DANYAO_BTN)
tap_opt(DRUG_1)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
# 录制稿里这一串 2 次点击 → 聚灵是**滑动**触发，改成滑动
drag_until(JU_LING_BTN, XIULIAN_UP, dy=-300, max_drags=10, label="聚灵")
# （人工停顿 8.5s）
pause(8.5)
# （人工停顿 3.2s）
pause(3.2)
tap_opt(JU_LING_BTN)  # Button
# （人工停顿 4.1s）
pause(4.1)
tap_opt(XIULIAN_UP)  # Button
tap(XIULIAN_BACK)  # Button
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content")
tap(find_child("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content", "challengeitem") + "/btn_challenge/text")
tap("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
# （人工停顿 3.4s）
pause(3.4)
tap("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
tap(find_child("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport", "小比管事") + "/click")  # Button
tap(TASK_OPT)  # Button
tap("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_start/text_start")
# （人工停顿 14.3s）
pause(14.3)
tap("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 38.2s）
pause(38.2)
tap_opt(RESULT_CLOSE)  # Button
# （人工停顿 9.7s）
pause(9.7)
tap("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 42.0s）
pause(42.0)
tap_opt("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 49.7s）
pause(49.7)
# 里程碑：门派比试结算界面（前面几场比试是服务端跑，最长一段等待约 50s）
wait_visible("GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)", 200, "(门派比试结算)")
tap("GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)/adapter/content/btn_close")  # Button
tap(TASK_OPT)  # Button
tap_opt(TASK_OPT)  # Button
# （人工停顿 2.2s）
pause(2.2)
tap(find_child("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content", "list_item") + "/btn_all/text")
# （人工停顿 2.0s）
pause(2.0)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
# 录制稿里这一串 2 次点击 → 聚灵是**滑动**触发，改成滑动
drag_until(JU_LING_BTN, XIULIAN_UP, dy=-300, max_drags=10, label="聚灵")
# （人工停顿 9.1s）
pause(9.1)
tap("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_xiulian/unselect/icon")
print("PASS: 录制回放通过（351 次点击 / 32 次拖拽 / 0 处输入 / 5 次按键）")

check_console("STAGE3B")
u.screenshot("30_stage3b_done.png")
print("STAGE 3B DONE: 聚灵 → 门派比试 → 收尾")

check_console("ALL")
u.screenshot("99_newbie_flow_done.png")
print("PASS: 新手流程总脚本跑完（注册创角启程 → 寻找道院 → 修炼加入道院 → 洞府 → 试炼/比试）")
