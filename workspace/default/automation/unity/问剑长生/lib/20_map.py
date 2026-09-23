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


