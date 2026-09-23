# -*- coding: utf-8 -*-
"""只读探针：算出"引导格 60004 到底在屏幕的哪个像素"。

已知（上一轮实测）：
  * room=12100，block_touch=nil，ui_click_empty=true（点击到了 on_ui_click，但 click_position 返回 false）
  * cells=0（全迷雾），canExplore[60004=true]，其余格全 false
  * guide 标记被 UIMapWindow:update_guide_position 摆在目标格位置 **+ GUID_OFFSET_Y(=110)**
    —— 所以"点 guide 的屏幕坐标"其实点高了 110 像素，这很可能就是探雾失败的原因。

本探针只读：把 60004 的世界坐标、相机、换算出的屏幕坐标全打出来。
"""
LUA_HEAD = (
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


def _lua_tail(tag):
    return (
        "ds.Invoke(s, new object[] { lua, \"p" + tag + "\" });"
        "var ip = st.GetProperty(\"Item\", new System.Type[] { typeof(string) });"
        "var v = ip.GetValue(s, new object[] { \"__" + tag + "\" });"
        "return \"{\\\"lua\\\":\\\"\" + (v == null ? \"null\" : v.ToString().Replace(\"\\\\\", \"/\").Replace(\"\\\"\", \"'\")) + \"\\\"}\";"
    )


def lua(code, tag="z"):
    body = code.replace("__z", "__" + tag)
    out = u.exec_csharp(LUA_HEAD + "string lua = " + _cs_str(body) + ";" + _lua_tail(tag))
    r = out.get("result")
    return r.get("lua") if isinstance(r, dict) else str(out)[:300]


POS = ("local p = {}\n"
       "local ok, err = pcall(function()\n"
       "  local w = UI.query('WorldMapWindow')\n"
       "  local e = UIMapD.entity_func(w.ui_map_type, w.room_id, 60004)\n"
       "  p[#p+1] = 'e=' .. tostring(e ~= nil)\n"
       "  if e == nil then return end\n"
       "  p[#p+1] = 'world=' .. tostring(e.world_pos.x) .. ',' .. tostring(e.world_pos.y)\n"
       "  local ux, uy = UI.world_to_screen_point(e.world_pos)\n"
       "  p[#p+1] = 'uiPos=' .. tostring(ux) .. ',' .. tostring(uy)\n"
       "  local g = w.guide\n"
       "  if g ~= nil then\n"
       "    local ap = g.transform.anchoredPosition\n"
       "    local lp = g.transform.localPosition\n"
       "    p[#p+1] = 'guideAnchored=' .. tostring(ap.x) .. ',' .. tostring(ap.y)\n"
       "    p[#p+1] = 'guideLocal=' .. tostring(lp.x) .. ',' .. tostring(lp.y)\n"
       "    p[#p+1] = 'guideParent=' .. tostring(g.transform.parent.name)\n"
       "  end\n"
       "  local mc = w.map_content\n"
       "  if mc ~= nil then\n"
       "    local s2 = mc.transform.localScale\n"
       "    p[#p+1] = 'mapContentScale=' .. tostring(s2.x) .. ',' .. tostring(s2.y)\n"
       "    local r = mc.transform.rect\n"
       "    p[#p+1] = 'mapContentSize=' .. tostring(r.width) .. 'x' .. tostring(r.height)\n"
       "    local ap2 = mc.transform.anchoredPosition\n"
       "    p[#p+1] = 'mapContentAnchored=' .. tostring(ap2.x) .. ',' .. tostring(ap2.y)\n"
       "  end\n"
       "  p[#p+1] = 'scale=' .. tostring(w.cur_scale)\n"
       "  p[#p+1] = 'svPos=' .. tostring(w.map_sv.horizontalNormalizedPosition) .. ',' .. tostring(w.map_sv.verticalNormalizedPosition)\n"
       "end)\n"
       "if not ok then p[#p+1] = 'ERR:' .. tostring(err) end\n"
       "__z = table.concat(p, ' | ')\n")

print("=== 60004 坐标 ===")
print(lua(POS, "pos"))

# C# 侧：把世界坐标转屏幕坐标（Camera.main），以及 map_content 的屏幕矩形
CS = r'''
var w = UnityEngine.GameObject.Find("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)");
if (w == null) return "{\"ok\":false,\"error\":\"no map window\"}";
var mc = w.transform.Find("map_sv/Viewport/map_content");
var cam = UnityEngine.Camera.main;
string camInfo = cam == null ? "null" : (cam.name + " ortho=" + cam.orthographic + " size=" + cam.orthographicSize);
string mcInfo = "null";
if (mc != null) {
  var rt = mc.GetComponent<UnityEngine.RectTransform>();
  var c = new UnityEngine.Vector3[4];
  rt.GetWorldCorners(c);
  var s0 = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, c[0]);
  var s2 = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, c[2]);
  mcInfo = "screenRect=" + s0.x + "," + s0.y + " .. " + s2.x + "," + s2.y
         + " lossy=" + rt.lossyScale.x + " size=" + rt.rect.width + "x" + rt.rect.height;
}
var g = w.transform.Find("guide");
string gInfo = "null";
if (g != null) {
  var grt = g.GetComponent<UnityEngine.RectTransform>();
  var gc = new UnityEngine.Vector3[4];
  grt.GetWorldCorners(gc);
  var g0 = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, gc[0]);
  var g2 = UnityEngine.RectTransformUtility.WorldToScreenPoint(null, gc[2]);
  gInfo = "screen=" + ((g0.x+g2.x)/2f) + "," + ((g0.y+g2.y)/2f) + " anchored=" + grt.anchoredPosition.x + "," + grt.anchoredPosition.y;
}
return "{\"ok\":true,\"cam\":\"" + camInfo + "\",\"mapContent\":\"" + mcInfo + "\",\"guide\":\"" + gInfo + "\",\"screen\":\"" + UnityEngine.Screen.width + "x" + UnityEngine.Screen.height + "\"}";
'''
out = u.exec_csharp(CS)
print("=== C# 侧 ===")
print(out.get("result"))
