# -*- coding: utf-8 -*-
"""组装「新手流程总脚本」以及分段运行稿。

产物（都写到本目录）：
  新手流程总脚本.py   三段合一（需把 UNITY_RUN_TIMEOUT_S 调到 ≥1500 才能一次跑完）
  run_stage2.py       只跑 STAGE 2（新手主界面 → 加入道院 → 洞府升级）
  run_stage3.py       只跑 STAGE 3（聚灵塔试炼 → 外院晋升 → 门派比试）

组装动作全部是"可核对的机械变换"，每条都在这里打印替换次数：
  1. 修掉录制稿里被截断的对象名（TMP SubMeshUI[...] → text_content）；
  2. 长路径字面量 → 常量名（整体替换带引号的字面量，不做子串匹配）；
  3. 在几个关键节点插入里程碑断言（道院选择/洞府升级/门派比试结算）；
  4. 可选/连点的 tap → tap_opt，恢复"人工停顿"为真正的 pause()（节奏修正）。
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))          # cases/<用例>/
PROJECT = os.path.dirname(os.path.dirname(HERE))             # 用例工程根
LIB = os.path.join(PROJECT, "lib")
DIST = os.path.join(HERE, "dist")

#: lib/ 里的片段按文件名排序拼接 —— 必须与拆分时一致，拼接结果 == 原 flow_header.py
_FRAGMENTS = sorted(n for n in os.listdir(LIB) if n[:2].isdigit() and n.endswith(".py"))
HEADER = "".join(open(os.path.join(LIB, n), encoding="utf-8", newline="").read()
                 for n in _FRAGMENTS)
STAGE1 = open(os.path.join(HERE, "stage1_body.py"), encoding="utf-8").read()
BODY = open(os.path.join(HERE, "flow2_body.py"), encoding="utf-8").read().splitlines()

# --- 1. 录制稿截断对象名修正 ------------------------------------------------
fixed = []
n_fix = 0
for ln in BODY:
    if "TMP SubMeshUI [" in ln:
        ln = ln.split("/TMP SubMeshUI [")[0] + '")'
        n_fix += 1
    fixed.append(ln)
BODY = fixed
print("fix truncated name:", n_fix)

# --- 2. 切段 -----------------------------------------------------------------
# body[0:11] = 录制头部（起跑线注释 + Dialog x3 + 主线选项）→ 由 STAGE2 头部替换
# body[11:192] = STAGE2；body[192:] = STAGE3
assert "DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg" in BODY[7], BODY[7]
assert "content_option/btn_click" in BODY[9], BODY[9]
assert "AshramHouseLevelUpWindow(Clone)/btn_close" in BODY[191], BODY[191]
assert "trans_widgets/XiuLianWidget(Clone)" in BODY[192], BODY[192]
S2_BODY = BODY[11:192]
S3_BODY = BODY[192:]
print("stage2 body lines:", len(S2_BODY), "stage3 body lines:", len(S3_BODY))

# --- 3. 长路径 → 常量 --------------------------------------------------------
PAIRS = [
    ("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click", "TASK_OPT"),
    ("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask", "TASK_MASK"),
    ("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "DIALOG_BG"),
    ("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full", "BUBBLE"),
    ("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", "MAP_CONTENT"),
    ("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map", "HOUSE_MAP"),
    ("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)", "SCROLL_TEXT"),
    ("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close", "XIULIAN_UP"),
    # 修炼界面的**吐纳**：录制稿记的是拖拽监听区 PanelBg（点它不生效，实测连点 25 下计数不动），
    # 真按钮是 btn_tuna_gen_ball（XiuLianWidget.lua:15）。这里直接换成真按钮。
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)",
     "TUNA_BTN"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)", "JU_LING_BTN"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text", "DANYAO_BTN"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast", "DRUG_1"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(2)/item/img_icon/raycast", "DRUG_2"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back", "XIULIAN_BACK"),
    ("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)", "GANG_ROOM"),
    ("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)", "JU_LING_TA"),
    ("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg", "RESULT_CLOSE"),
    ("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)", "XIULIAN"),
]


def to_const(lines):
    lines = list(lines)
    for lit, name in PAIRS:
        q = '"%s"' % lit
        n = 0
        for i, ln in enumerate(lines):
            if q in ln:
                n += ln.count(q)
                lines[i] = ln.replace(q, name)
        if n:
            print("  %-14s <- %d" % (name, n))
    return lines


print("const substitution (stage2):")
S2_BODY = to_const(S2_BODY)
print("const substitution (stage3):")
S3_BODY = to_const(S3_BODY)

# --- 4. 里程碑断言 ----------------------------------------------------------
INSERTS = [
    ("tap(\"GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_choose/sect_zhenwu/name_text\")",
     ["# 里程碑：道院选择界面出现（选中真武宗门）",
      'wait_visible("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)", 90, "(道院选择界面)")',
      'expect_text("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_zhenwu/name_text", "真武")'],
     "before"),
    ("tap(\"GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update\")",
     ['wait_visible("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)", 30, "(洞府升级结果)")'],
     "after"),
    ("tap(\"GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)/adapter/content/btn_close\")",
     ['# 里程碑：门派比试结算界面（前面几场比试是服务端跑，最长一段等待约 50s）',
      'wait_visible("GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)", 200, "(门派比试结算)")'],
     "before"),
]


def insert_marks(lines):
    lines = list(lines)
    for anchor, code, where in INSERTS:
        idx = [i for i, ln in enumerate(lines) if ln.strip().startswith(anchor)]
        if not idx:
            print("  !! anchor not found:", anchor[:70])
            continue
        print("  anchor x%d (%s): %s..." % (len(idx), where, anchor[:60]))
        for i in reversed(idx):
            at = i if where == "before" else i + 1
            lines[at:at] = code
    return lines


print("milestones (stage2):")
S2_BODY = insert_marks(S2_BODY)
print("milestones (stage3):")
S3_BODY = insert_marks(S3_BODY)

# --- 4.5 录制稿的节奏修正（两条都与流程语义无关，只改"点空了怎么办"）---------
#  ① 多点的那些 → tap_opt：在就点、不在就跳过。录制时的节奏决定了大对话框要点几下、
#     修炼要连点几次，写死会让脚本在"少点一下"时白等 45s 再报错；而这些位置多点/
#     少点一下都不影响流程。真正卡流程的入口仍然用 tap（严格等 + 失败即停）。
#  ② "人工停顿 Xs" → pause(X)：去噪后停顿只剩注释，回放会一路抢跑 —— 同一控件连续
#     点两下时，第二下会在第一下生效前就打出去。
import re

_OPT_ALWAYS = frozenset((
    "DIALOG_BG", "BUBBLE", "TASK_MASK", "MAP_CONTENT", "HOUSE_MAP", "XIULIAN_UP",
    "XIU_LIAN_BTN", "JU_LING_BTN", "DRUG_1", "DRUG_2", "RESULT_CLOSE",
))
_TAP_RX = re.compile(r'^(\s*)tap\((.+?)\)(\s*#.*)?$')
_PAUSE_RX = re.compile(r'^#\s*（人工停顿 ([0-9.]+)s）\s*$')


def soften_taps(lines):
    """把可选/连点的 tap 换成 tap_opt；返回 (新行, 换了几条)。"""
    out, n, prev = [], 0, None
    for ln in lines:
        if ln.strip().startswith("#"):        # 注释不打断"连续点同一个控件"的判定
            out.append(ln)
            continue
        m = _TAP_RX.match(ln)
        if not m:
            if ln.strip():
                prev = None
            out.append(ln)
            continue
        arg = m.group(2).strip()
        if arg in _OPT_ALWAYS or arg == prev:
            out.append("%stap_opt(%s)%s" % (m.group(1), arg, m.group(3) or ""))
            n += 1
        else:
            out.append(ln)
        prev = arg
    return out, n


def expand_pauses(lines):
    """把"人工停顿"注释展开成真的 pause(秒) 调用。"""
    out, n = [], 0
    for ln in lines:
        m = _PAUSE_RX.match(ln.strip())
        if m:
            out.append("# （人工停顿 %ss）" % m.group(1))
            out.append("pause(%s)" % m.group(1))
            n += 1
        else:
            out.append(ln)
    return out, n


# --- 4.6 世界地图格子：全路径硬编码 → 按 id 找格子 ------------------------------
# 录制稿里地图格子写的是全路径（`...WorldExploreRoleItem_new(Clone)(nil)(57004)/detail/bg`）。
# 实测这条会在"点下去那一瞬格子还没建出来"时白等 45s 然后报错（地图是滚到哪建到哪，
# 进图后要等一拍），而且换台机器/换个节奏就复现 —— 2026-09-23 阶段二就卡在这一步。
# 改成 map_cell(id)：等带这个 id 的格子出现再点，语义不变、不再等死。
_MAPCELL_RX = re.compile(
    r'"GameRoot/Canvas2D/Back/WorldMapWindow\(Clone\)/cellitem_root/'
    r'WorldExploreItemWidget_new\(Clone\)/([^"]+)"')
#: 地图格容器的直接子节点名 —— 按类型各有前缀（Role=人物/妖兽、Temple=洞府、Monster=妖物…），
#: 但**路径形状一致**：`<cellitem_root>/WorldExploreItemWidget_new(Clone)/<某类型格>(...)(id)/<子路径>`。
#: 所以只认"前缀是 WorldExploreXxxItem_new"就够了，别把类型名写死（洞府那格就漏过）。
_MAPCELL_ANY_RX = re.compile(
    r'"GameRoot/Canvas2D/Back/WorldMapWindow\(Clone\)/cellitem_root/'
    r'WorldExploreItemWidget_new\(Clone\)/(WorldExplore[A-Za-z]*Item_new[^"]*)"')
_TAP_LINE_RX = re.compile(r'^\s*tap(_opt)?\(')


def _cell_to_call(lit: str) -> str:
    """`.../WorldExploreTempleItem_new(Clone)(神秘洞府)(55008)/normal/bg_name`
    → `map_cell("55008", "normal/bg_name")`。

    兼容所有 `WorldExplore*Item_new` 格子类型（Role / Temple / Monster …）。
    """
    m = _MAPCELL_ANY_RX.match('"%s"' % lit)
    if not m:
        return '"%s"' % lit
    rest = m.group(1)
    parts = rest.split("/")
    head, sub = parts[0], "/".join(parts[1:])
    ids = re.findall(r"\((\d+)\)", head)
    if not ids:
        return '"%s"' % lit
    # 取**第一个** id：`(nil)(53010)(地块)(46011)(地块)(46011)` 这种，首个才是目标格
    return 'map_cell("%s"%s)' % (ids[0], (', "%s"' % sub) if sub else "")


def fix_map_cells(lines):
    """① tap/tap_opt 里的地图格子全路径 → **裸调用** `map_click_cell(id, sub)`；
       ② 拖拽里的格子端点 → `map_drag()`。

    注意必须是**裸调用**、不能写成 `tap(map_click_cell(...))` —— `map_click_cell` 返回
    布尔（点了没有），套进 tap 会变成 `wait_visible(True)` → 报 "True 未显示" 然后白等 45s
    （2026-09-23 踩过）。
    """
    out, n_tap = [], 0
    for ln in lines:
        s = ln.strip()
        if s.startswith("#") or not s:
            out.append(ln)
            continue
        if _TAP_LINE_RX.match(ln):
            m = re.match(r'^(?P<ind>\s*)tap(?:_opt)?\(\s*(?P<inner>.+?)\s*\)\s*(?:#.*)?$', ln)
            if m and _MAPCELL_ANY_RX.match('"%s"' % m.group("inner").strip('"')):
                call = _cell_to_call(m.group("inner").strip().strip('"'))
                call = call.replace("map_cell(", "map_click_cell(")
                out.append("%s%s" % (m.group("ind"), call))
                n_tap += 1
                continue
        out.append(ln)
    return out, n_tap


# --- 4.7 地图操作：点空地 / 拖拽 → 真基元 --------------------------------------
# 录制稿里三类"地图操作"在回放里都是空的或错的（2026-09-23 定位）：
#   ① `tap_opt(MAP_CONTENT)`（几十下"点空地走位"）：u.click 给的是**对象中心**，而
#      map_content 是 9353x15125 的滚动区、中心点在屏幕外 → 每一下都是点空气 + 白等 8s；
#   ② `u.drag(格子, map_content)`（**从某个格子起拖**）：录制器只对拖拽记坐标，玩家当时
#      其实是"点那个格子"（如 `...WorldExploreTempleItem_new(Clone)(神秘洞府)(55008)/normal/bg_name`
#      = 点神秘洞府）→ **不能换成盲目的 map_drag()**，那样会丢掉目标格、流程直接走偏
#      （2026-09-23 实测：换成 map_drag 后卡在「雾中洞府」再也走不到洞府）。要还原成
#      `map_click_cell("55008", ...)`。
#   ③ `u.drag(X, X)`（起终点同一个对象）：位移为 0，等于没滑 → 只留停顿。
_MAP_TAP_RX = re.compile(r'^(?P<ind>\s*)tap(?:_opt)?\(\s*MAP_CONTENT\s*\)\s*(?:#.*)?$')
_MAP_DRAG_RX2 = re.compile(
    r'^\s*u\.drag\([^)]*(?:MAP_CONTENT|map_content|content_map)[^)]*\)\s*(?:#.*)?$')
_SELF_DRAG_RX = re.compile(r'^\s*u\.drag\("(?P<p>[^"]+)",\s*"(?P=p)"\)\s*(?:#.*)?$')
#: `u.drag("<格子全路径>", "<地图滚动区>")` —— 起点是地图格，语义是"点这个格"。
_DRAG_FROM_CELL_RX = re.compile(
    r'^(?P<ind>\s*)u\.drag\(\s*"(?P<cell>[^"]*WorldExploreItemWidget_new[^"]*)"\s*,')


def fix_map_ops(lines):
    """点空地 → map_tap_explore()；**从格子起拖 → 点那个格**；其余地图拖拽 → map_drag()。"""
    out, n_tap, n_drag, n_self, n_cell = [], 0, 0, 0, 0
    for ln in lines:
        s = ln.strip()
        if s.startswith("#") or not s:
            out.append(ln)
            continue
        if _MAP_TAP_RX.match(ln):
            out.append("%smap_tap_explore()" % _MAP_TAP_RX.match(ln).group("ind"))
            n_tap += 1
            continue
        # 先判"从格子起拖"（语义=点这个格），再判普通地图拖拽 —— 顺序不能反。
        m = _DRAG_FROM_CELL_RX.match(ln)
        if m:
            call = _cell_to_call(m.group("cell"))
            call = call.replace("map_cell(", "map_click_cell(")
            out.append("%s# 录制里这是\"从格子起拖\"（录制器只对拖拽记坐标）→ 还原成点该格" % m.group("ind"))
            out.append("%s%s" % (m.group("ind"), call))
            n_cell += 1
            continue
        if _MAP_DRAG_RX2.match(ln):
            out.append("map_drag()")
            n_drag += 1
            continue
        m = _SELF_DRAG_RX.match(ln)
        if m:
            # 起终点同一个对象 = 位移 0，本来就没滑；留一句停顿还原节奏即可
            out.append('print("SKIP(录制里的空拖拽，起终点同一对象)：%s")'
                       % m.group("p").split("/")[-1])
            n_self += 1
            continue
        out.append(ln)
    return out, n_tap, n_drag, n_self, n_cell


# --- 4.8 连续剧情点击 → advance_story ----------------------------------------
# 录制稿里"点对话框/旁白推进剧情"是**按录制当时的节奏**记的（3 下对话框、2 下旁白…）。
# 剧情一长（点开「神秘妖王」之后那段）次数就不够 → 脚本卡在"等下一个界面"白等到超时。
# 把**连续 3 次以上**的同类剧情点击合并成一次 advance_story(target)：语义相同（推进剧情），
# 但"点到目标出现为止"，不再依赖录制时的次数。单次/两次的点击保持原样（它们常是
# "确认某个选项"，多点会改变走向）。
_STORY_NODE_NAMES = ("DIALOG_BG", "BUBBLE")
_STORY_TAP_RX = re.compile(r'^(?P<ind>\s*)tap(?:_opt)?\(\s*(?P<arg>DIALOG_BG|BUBBLE)\s*\)\s*(?:#.*)?$')
_TAP_ANY_RX = re.compile(r'^\s*tap(?:_opt)?\(')


def coalesce_story_clicks(lines, min_run=3):
    """把连续 >=min_run 次的剧情点击合并成 advance_story(下一个 tap 的目标)。"""
    out, i, n = [], 0, 0
    while i < len(lines):
        m = _STORY_TAP_RX.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < len(lines) and _STORY_TAP_RX.match(lines[j]):
            j += 1
        run = j - i
        # 往后找下一个严格 tap 的目标（跳过注释与 pause/print 之类的噪音）
        target, k = None, j
        while k < len(lines):
            s = lines[k].strip()
            if _TAP_ANY_RX.match(lines[k]) and not _STORY_TAP_RX.match(lines[k]):
                mm = re.match(r'^\s*tap\(\s*("(?:[^"]+)"|\w+)\s*[,)]', lines[k])
                if mm:
                    target = mm.group(1)
                break
            if s and not s.startswith("#") and not s.startswith(("pause(", "print(")):
                break
            k += 1
        if run >= min_run and target:
            out.append("%s# 录制稿里这一串 %d 次剧情点击 → 点到下一个界面出现为止"
                       % (m.group("ind"), run))
            out.append('%sadvance_story(%s, max_clicks=%d, label="推进剧情")'
                       % (m.group("ind"), target, max(run + 6, 12)))
            n += 1
            i = j
        else:
            out.extend(lines[i:j])
            i = j
    return out, n


# --- 4.9 连点同一个控件 → tap_until/tap_n -------------------------------------
# 录制稿里"修炼/吐纳"是**同一个按钮连点若干下**（吐纳 12 次才生成灵气），次数是录制
# 当时的节奏。次数一变就点到空气，或点不够导致后面等升级弹窗超时。
# 判据改成"点到升级弹窗出现为止"（次数自适应），语义不变。
_UP_WINDOWS = ("XIULIAN_UP",)
_CLICK_LINE_RX = re.compile(
    r'^(?P<ind>\s*)tap(?:_opt)?\(\s*(?P<arg>TUNA_BTN|XIU_LIAN_BTN|XIULIAN_UP)\s*\)\s*(?:#.*)?$')
_DRAG_LINE_RX = re.compile(
    r'^(?P<ind>\s*)tap(?:_opt)?\(\s*(?P<arg>JU_LING_BTN)\s*\)\s*(?:#.*)?$')


def coalesce_repeat_clicks(lines, min_run=2):
    """把重复的**点击**合并成 tap_until/tap_n，把**聚灵**改成滑动（drag_until）。

    两条机制不同（2026-09-23 定位）：
      * 吐纳 = 点 `btn_tuna_gen_ball`（点 N 次生成灵气，次数由服务端算）→ tap_until；
      * 聚灵 = **滑动**（JuLingWidget.lua:356 listen_drag_on_panel → drag_func）→ drag_until。
    录制稿把两者都记成了"点 PanelBg"，回放里两个都不生效。
    """
    out, i, n, nd = [], 0, 0, 0
    while i < len(lines):
        m = _CLICK_LINE_RX.match(lines[i]) or _DRAG_LINE_RX.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        rx = _CLICK_LINE_RX if _CLICK_LINE_RX.match(lines[i]) else _DRAG_LINE_RX
        j = i
        while j < len(lines) and rx.match(lines[j]):
            j += 1
        run = j - i
        arg = rx.match(lines[i]).group("arg")
        # 往后找升级弹窗（跳过注释 / 空行）
        goal = None
        for k in range(j, min(j + 6, len(lines))):
            s = lines[k].strip()
            if s.startswith("#") or not s:
                continue
            for up in _UP_WINDOWS:
                if up in lines[k]:
                    goal = up
            break
        ind = m.group("ind")
        is_drag = (arg == "JU_LING_BTN")
        if run >= min_run:
            if is_drag:
                out.append("%s# 录制稿里这一串 %d 次点击 → 聚灵是**滑动**触发，改成滑动" % (ind, run))
                out.append('%sdrag_until(%s, %s, dy=-300, max_drags=%d, label="聚灵")'
                           % (ind, arg, goal or "XIULIAN_UP", max(run + 4, 10)))
                nd += 1
            elif goal and goal != arg:
                out.append("%s# 录制稿里这一串 %d 次点击 → 点到升级弹窗出现为止" % (ind, run))
                out.append('%stap_until(%s, %s, max_clicks=%d, label="连点到升级")'
                           % (ind, arg, goal, max(run + 6, 14)))
                n += 1
            else:
                out.append("%s# 录制稿里这一串 %d 次点击 → 连点（控件不在场就停）" % (ind, run))
                out.append('%stap_n(%s, %d, label="连点")' % (ind, arg, max(run + 3, 6)))
                n += 1
            i = j
        else:
            out.extend(lines[i:j])
            i = j
    return out, n, nd


for tag in ("stage2", "stage3"):
    body = S2_BODY if tag == "stage2" else S3_BODY
    body, n_story = coalesce_story_clicks(body)
    body, n_rep, n_drg = coalesce_repeat_clicks(body)
    body, n_soft = soften_taps(body)
    body, n_cell = fix_map_cells(body)
    body, n_mtap, n_mdrag, n_self, n_dcell = fix_map_ops(body)
    body, n_pause = expand_pauses(body)
    print("  %s: 剧情连点→advance_story x%d, 重复点击→tap_until/tap_n x%d, 聚灵→drag_until x%d, "
          "tap_opt x%d, 地图格→map_click_cell x%d, 从格子起拖→点该格 x%d, 点空地→map_tap_explore x%d, "
          "地图拖拽→map_drag x%d, 空拖拽跳过 x%d, pause x%d"
          % (tag, n_story, n_rep, n_drg, n_soft, n_cell, n_dcell, n_mtap, n_mdrag, n_self, n_pause))
    if tag == "stage2":
        S2_BODY = body
    else:
        S3_BODY = body

# --- 5. 段落开头/结尾 --------------------------------------------------------
S2_HEAD = '''# ============================================================================
# STAGE 2　新手主界面 → 序章 → 主线「寻找道院」→ 修炼聚灵 → 加入道院 → 洞府升级
#   起跑线：新手主界面（STAGE 1 刚落地；序章文字窗可能还开着）
#   来源：手动录制稿（rec_20260923_005533_005a）的去噪版 —— 点击步骤一条不少，
#         只是把"立刻点"改成"等控件显示出来再点"，并把动态 id 换成前缀查找。
# ============================================================================
stage("STAGE 2 寻找道院 → 加入道院 → 洞府升级")
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
'''

S2_TAIL = '''
wait_visible(XIULIAN, 45, "(修炼界面)")
u.screenshot("19_stage2_done.png")
check_console("STAGE2")
print("STAGE 2 DONE: 寻找道院 → 修炼聚灵 → 加入道院 → 洞府升级")
'''

S3_HEAD = '''# ============================================================================
# STAGE 3　聚灵塔试炼 → 道院外院晋升 → 功法装配 → 门派比试 → 收尾
#   起跑线：修炼界面（STAGE 2 结束在 XiulianMainWindow，洞府升级弹窗已关）
# ============================================================================
stage("STAGE 3 聚灵塔试炼 → 外院晋升 → 门派比试")
require_play_mode()
check_console("baseline")
at_start_line(XIULIAN, "(修炼界面)")
wait_visible(XIULIAN, 60, "(修炼界面)")
'''

S3_TAIL = '''
check_console("STAGE3")
u.screenshot("30_stage3_done.png")
print("STAGE 3 DONE: 聚灵塔试炼 → 晋升 → 门派比试")
'''

TAIL_ALL = '''
check_console("ALL")
u.screenshot("99_newbie_flow_done.png")
print("PASS: 新手流程总脚本跑完（注册创角启程 → 寻找道院 → 修炼加入道院 → 洞府 → 试炼/比试）")
'''

# --- 6. 切段 -----------------------------------------------------------------
# 依据：录制稿里的"人工停顿"就是等游戏，用它 + 每步开销估算整段耗时。
# 实测：STAGE2 约 375s、STAGE3 约 600s，都贴/超平台单次执行上限（UNITY_RUN_TIMEOUT_S
# 默认 420s，超时被硬杀 exit -1），所以每段再切一刀，切点自动选"让较长的那段最短"。
import re as _re


def _cost(seg):
    v = [float(x) for x in _re.findall(r"人工停顿 ([0-9.]+)s", "\n".join(seg))]
    acts = sum(1 for l in seg if l.strip().startswith(("tap(", "u.click(", "u.drag(")))
    return acts, sum(v), sum(v) + acts * 1.3


def _best_split(seg, lo=20, pad=20):
    best, best_cost = None, None
    for i in range(lo, len(seg) - pad):
        m = max(_cost(seg[:i])[2], _cost(seg[i:])[2])
        if best_cost is None or m < best_cost:
            best, best_cost = i, m
    return best


print("stage2 whole: acts=%d pause=%.0fs est=%.0fs" % _cost(S2_BODY))
_k2 = _best_split(S2_BODY)
print("stage2 split @%d: %s" % (_k2, S2_BODY[_k2].strip()[:110]))
print("   2a: acts=%d pause=%.0fs est=%.0fs" % _cost(S2_BODY[:_k2]))
print("   2b: acts=%d pause=%.0fs est=%.0fs" % _cost(S2_BODY[_k2:]))
S2A_BODY, S2B_BODY = S2_BODY[:_k2], S2_BODY[_k2:]

S2A_HEAD = S2_HEAD.replace('stage("STAGE 2 寻找道院 → 加入道院 → 洞府升级")',
                           'stage("STAGE 2A 寻找道院 → 修炼聚灵")')
S2A_TAIL = '''
check_console("STAGE2A")
u.screenshot("18_stage2a_done.png")
print("STAGE 2A DONE: 寻找道院 → 修炼/聚灵/丹药")
'''
S2B_HEAD = '''# ============================================================================
# STAGE 2B　继续主线 → 加入道院（真武）→ 洞府升级 → 聚灵塔试炼
#   起跑线：STAGE 2A 结束时的现场（世界地图 / 洞府一带）
# ============================================================================
stage("STAGE 2B 加入道院 → 洞府升级")
require_play_mode()
check_console("baseline")
'''

print("stage3 whole: acts=%d pause=%.0fs est=%.0fs" % _cost(S3_BODY))
_k3 = _best_split(S3_BODY)
print("stage3 split @%d: %s" % (_k3, S3_BODY[_k3].strip()[:110]))
print("   3a: acts=%d pause=%.0fs est=%.0fs" % _cost(S3_BODY[:_k3]))
print("   3b: acts=%d pause=%.0fs est=%.0fs" % _cost(S3_BODY[_k3:]))
S3A_BODY, S3B_BODY = S3_BODY[:_k3], S3_BODY[_k3:]

S3A_HEAD = S3_HEAD.replace('STAGE 3　聚灵塔试炼', 'STAGE 3A　聚灵塔试炼').replace(
    'stage("STAGE 3 聚灵塔试炼 → 外院晋升 → 门派比试")',
    'stage("STAGE 3A 聚灵塔试炼 → 外院晋升")')
S3A_TAIL = '''
check_console("STAGE3A")
u.screenshot("29_stage3a_done.png")
print("STAGE 3A DONE: 聚灵塔试炼 → 外院晋升 → 功法装配")
'''
S3B_HEAD = '''# ============================================================================
# STAGE 3B　聚灵 → 门派比试 → 收尾（比试是服务端跑，单场最长约 50s）
#   起跑线：修炼界面（STAGE 3A 结束在 XiulianMainWindow）
# ============================================================================
stage("STAGE 3B 聚灵 → 门派比试")
require_play_mode()
check_console("baseline")
wait_visible(XIULIAN, 60, "(修炼界面)")
'''
S3B_TAIL = '''
check_console("STAGE3B")
u.screenshot("30_stage3b_done.png")
print("STAGE 3B DONE: 聚灵 → 门派比试 → 收尾")
'''

MERGED = (
    HEADER
    + "\n" + STAGE1
    + "\n" + S2A_HEAD + "\n".join(S2A_BODY) + "\n" + S2A_TAIL
    + "\n" + S2B_HEAD + "\n".join(S2B_BODY) + "\n" + S2_TAIL
    + "\n" + S3A_HEAD + "\n".join(S3A_BODY) + "\n" + S3A_TAIL
    + "\n" + S3B_HEAD + "\n".join(S3B_BODY) + "\n" + S3B_TAIL
    + TAIL_ALL
)


def with_reset(reset, tail):
    head = HEADER.replace(
        'RESET = {"scene": "Assets/Scenes/main.unity",\n'
        '         "wait_for": "GameRoot/Canvas2D/Normal/BootWindow(Clone)"}',
        reset)
    assert reset in head, "RESET 替换失败"
    return head + "\n" + tail


RUN2A = with_reset(
    'RESET = {"scene": "Assets/Scenes/main.unity",\n'
    '         "wait_for": "GameRoot/Canvas2D/Normal/TaskWindow(Clone)"}',
    S2A_HEAD + "\n".join(S2A_BODY) + "\n" + S2A_TAIL)
RUN2B = with_reset(
    'RESET = {"scene": "Assets/Scenes/main.unity",\n'
    '         "wait_for": "GameRoot/Canvas2D/Normal/TaskWindow(Clone)"}',
    S2B_HEAD + "\n".join(S2B_BODY) + "\n" + S2_TAIL)
RUN3A = with_reset(
    'RESET = {"scene": "Assets/Scenes/main.unity",\n'
    '         "wait_for": "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)"}',
    S3A_HEAD + "\n".join(S3A_BODY) + "\n" + S3A_TAIL)
RUN3B = with_reset(
    'RESET = {"scene": "Assets/Scenes/main.unity",\n'
    '         "wait_for": "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)"}',
    S3B_HEAD + "\n".join(S3B_BODY) + "\n" + S3B_TAIL)

# 流程二（阶段一跑完之后的全部内容）：一次跑完 STAGE 2A → 3B，起跑线=新手主界面
RUN_FLOW2 = with_reset(
    'RESET = {"scene": "Assets/Scenes/main.unity",\n'
    '         "wait_for": "GameRoot/Canvas2D/Normal/TaskWindow(Clone)"}',
    S2A_HEAD + "\n".join(S2A_BODY) + "\n" + S2A_TAIL
    + "\n" + S2B_HEAD + "\n".join(S2B_BODY) + "\n" + S2_TAIL
    + "\n" + S3A_HEAD + "\n".join(S3A_BODY) + "\n" + S3A_TAIL
    + "\n" + S3B_HEAD + "\n".join(S3B_BODY) + "\n" + S3B_TAIL
    + TAIL_ALL)

for name, text in [("新手流程总脚本.py", MERGED), ("run_flow2.py", RUN_FLOW2),
                   ("run_stage2a.py", RUN2A), ("run_stage2b.py", RUN2B),
                   ("run_stage3a.py", RUN3A), ("run_stage3b.py", RUN3B)]:
    p = os.path.join(DIST, name)
    open(p, "w", encoding="utf-8").write(text)
    print("%-22s %d chars / %d lines" % (name, len(text), text.count("\n") + 1))
