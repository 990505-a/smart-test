"""Unity 手动录制器：玩家在编辑器里点游戏，平台把操作录成可回放的用例脚本。

**为什么是"注入式"录制**：平台的铁律是不改被测工程、不建脚本文件（建 .cs 会触发
域重载，可能卡死编辑器——见 unity-ui-test 技能）。所以录制器不是工程里的
MonoBehaviour，而是经 ``execute_code`` 注入的一段**编辑器帧回调**（与录像
``cs_record_start`` 同一套手法：SessionState 存状态 + 临时目录落盘 + 自动退订）。

**录什么**：命中测试（EventSystem.RaycastAll → 命中的 GameObject 沿父链拼路径），
所以录下来的是**语义目标**（``MainHud/BottomBar/BagButton``）而不是坐标——坐标脚本
换个分辨率就废，平台整套用例体系是对象路径驱动的。每次点击顺带记一份"当前可见面板"
快照，转换器据此自动播种断言。

**输入读取**：优先 legacy ``UnityEngine.Input``；工程用新版 Input System 时
（legacy 会抛 InvalidOperationException）反射读 ``UnityEngine.InputSystem.Mouse`` /
``Keyboard``——只用反射是为了不依赖编译期程序集引用，任何工程都能编译通过。
按键用「按住态 + 边缘检测」，不用 ``GetMouseButtonDown`` 这类单帧为真的 API，
编辑器帧回调漏一拍也不丢事件。

**域重载**：进 Play Mode 默认会重载域，把动态钩子清掉。所以钩子带心跳，
平台侧状态轮询发现心跳停了就自动重挂（事件文件与计数保留）。

**回放**：转换器把事件翻译成平台风格的 Python 用例（``u.click`` / ``u.drag`` /
``u.set_text`` / ``u.key``），并对"点击后新出现的面板"自动播种 ``u.expect_exists``。
产出的脚本按平台惯例先存 ``draft``，跑通一次才算 ``active``。
"""

from __future__ import annotations

import json
import re

# ---------------------------------------------------------------------------
# Unity 侧 SessionState 键（与录像器的 unity_auto_rec_* 同族，互不干扰）
# ---------------------------------------------------------------------------

_UI_ON_KEY = "unity_auto_uirec_on"
_UI_FILE_KEY = "unity_auto_uirec_file"
_UI_DIR_KEY = "unity_auto_uirec_dir"
_UI_N_KEY = "unity_auto_uirec_n"
_UI_HB_KEY = "unity_auto_uirec_hb"          # 心跳（Time.realtimeSinceStartup）
_UI_T0_KEY = "unity_auto_uirec_t0"
_UI_WHY_KEY = "unity_auto_uirec_why"

#: 心跳超过这个秒数就算"钩子没了"（域重载会清掉动态注册的回调）
HEARTBEAT_STALE_S = 5.0

#: 录制时长 / 事件数上限（防挂一夜）
DEFAULT_MAX_SECONDS = 3600
DEFAULT_MAX_EVENTS = 5000

#: 单次 fetch 最多回传的行数（MCP 响应体有实际上限，分片取）
FETCH_CHUNK = 300


def _snippet(template: str, **tokens: str | int) -> str:
    """把 ``@@TOKEN@@`` 占位替换掉。

    不用 ``str.format``：C# 代码里满是大括号，逐处转义 ``{{`` 既啰嗦又容易漏
    （漏一个就是 Unity 侧编译错误）。占位符用 C# 里不可能出现的 ``@@…@@``。
    """
    out = template
    for key, value in tokens.items():
        out = out.replace(f"@@{key.upper()}@@", str(value))
    leftover = re.findall(r"@@[A-Z_]+@@", out)
    if leftover:
        raise ValueError(f"C# 片段还有未替换的占位符: {leftover}")
    return out


# ---------------------------------------------------------------------------
# 录制器：安装 / 停止 / 状态 / 取事件
# ---------------------------------------------------------------------------

# 说明（写给以后改这段 C# 的人）：
# * 片段是**方法体**，必须 return；CodeDom 编译器只认 C# 5 —— 不要用字符串插值
#   `$"…"`、`?.`、lambda、表达式体成员；匿名委托 `delegate { }` 可以。
# * 类型写全名，不能 using。
# * 回调里任何异常都要自己吞掉：抛出去会刷爆 Console，还会让钩子静默失效。
# * 计数/心跳写 SessionState：域重载后平台靠心跳判断要不要重挂。
_UI_REC_START = r"""
var __dir = System.IO.Path.Combine(UnityEngine.Application.temporaryCachePath,
                                   "unity-auto-ui-rec", "@@SUBID@@");
System.IO.Directory.CreateDirectory(__dir);
string __file = UnityEditor.SessionState.GetString("@@FILEKEY@@", "");
bool __armed = UnityEditor.SessionState.GetBool("@@ONKEY@@", false);
// "同一场录制"= 钩子还开着 且 记录的文件就在本次请求的目录下。**换了目录就是新
// 一场**：否则平台侧新建录制会继承上一场（甚至平台没记录过的僵尸钩子）的事件文件。
bool __same = __armed && __file.Length > 0 && System.IO.File.Exists(__file)
    && __file.Replace("\\", "/").StartsWith(__dir.Replace("\\", "/") + "/");
if (__same) {
    // 重挂（域重载后心跳停了）：事件文件与计数保留，不截断
    float __hb0 = UnityEditor.SessionState.GetFloat("@@HBKEY@@", 0f);
    if (UnityEngine.Time.realtimeSinceStartup - __hb0 < 3f) {
        return "{\"ok\":true,\"already\":true,\"file\":\"" + __file.Replace("\\", "/") + "\"}";
    }
} else {
    __file = System.IO.Path.Combine(__dir, "events.jsonl");
    System.IO.File.WriteAllText(__file, "", new System.Text.UTF8Encoding(false));
    UnityEditor.SessionState.SetInt("@@NKEY@@", 0);
}
var __utf8 = new System.Text.UTF8Encoding(false);
UnityEditor.SessionState.SetString("@@FILEKEY@@", __file);
UnityEditor.SessionState.SetString("@@DIRKEY@@", __dir);
UnityEditor.SessionState.SetBool("@@ONKEY@@", true);
UnityEditor.SessionState.SetString("@@WHYKEY@@", "");
UnityEditor.SessionState.SetFloat("@@HBKEY@@", UnityEngine.Time.realtimeSinceStartup);
UnityEditor.SessionState.SetFloat("@@T0KEY@@", UnityEngine.Time.realtimeSinceStartup);
float __maxSec = @@MAXSECONDS@@f;
int __maxEvents = @@MAXEVENTS@@;

// ---- JSON 转义 / 路径 / 描述 ----
System.Func<string, string> __esc = delegate(string __s) {
    if (__s == null) return "";
    var __b = new System.Text.StringBuilder();
    for (int __i = 0; __i < __s.Length; __i++) {
        char __c = __s[__i];
        if (__c == '\\') __b.Append("\\\\");
        else if (__c == '"') __b.Append("\\\"");
        else if (__c == '\n') __b.Append("\\n");
        else if (__c == '\r') __b.Append("\\r");
        else if (__c == '\t') __b.Append("\\t");
        else if (__c < ' ') __b.Append(' ');
        else __b.Append(__c);
    }
    return __b.ToString();
};
System.Func<UnityEngine.Transform, string> __pathOf = delegate(UnityEngine.Transform __t) {
    string __p = __t.name;
    UnityEngine.Transform __cur = __t.parent;
    int __guard = 0;
    while (__cur != null && __guard < 64) { __p = __cur.name + "/" + __p; __cur = __cur.parent; __guard++; }
    return __p;
};
System.Func<UnityEngine.GameObject, string> __compOf = delegate(UnityEngine.GameObject __g) {
    var __names = new System.Collections.Generic.List<string>();
    UnityEngine.Component[] __cs = __g.GetComponents<UnityEngine.Component>();
    for (int __i = 0; __i < __cs.Length && __i < 40; __i++) {
        if (__cs[__i] == null) continue;
        string __n = __cs[__i].GetType().Name;
        if (__n == "Button" || __n == "Toggle" || __n == "Slider" || __n == "Dropdown"
            || __n == "InputField" || __n == "TMP_InputField" || __n == "TMP_Dropdown"
            || __n == "ScrollRect" || __n == "Scrollbar") __names.Add(__n);
    }
    return string.Join(",", __names.ToArray());
};
System.Func<UnityEngine.GameObject, string> __labelOf = delegate(UnityEngine.GameObject __g) {
    UnityEngine.Component[] __all = __g.GetComponentsInChildren<UnityEngine.Component>(true);
    for (int __i = 0; __i < __all.Length && __i < 200; __i++) {
        UnityEngine.Component __c = __all[__i];
        if (__c == null) continue;
        string __tn = __c.GetType().Name;
        if (__tn != "Text" && __tn != "TMP_Text" && __tn != "TextMeshProUGUI") continue;
        System.Reflection.PropertyInfo __pi = __c.GetType().GetProperty("text");
        if (__pi == null || __pi.PropertyType != typeof(string)) continue;
        string __v = __pi.GetValue(__c, null) as string;
        if (!string.IsNullOrEmpty(__v)) {
            __v = __v.Trim();
            return __v.Length > 60 ? __v.Substring(0, 60) : __v;
        }
    }
    return "";
};
System.Func<UnityEngine.GameObject, string> __panelsOf = delegate(UnityEngine.GameObject __g) {
    // 爬到最顶层祖先，列出它的直接子节点里**当前可见**的名字（"现在开着哪些面板"）。
    // 前缀根节点名：不同 Canvas 下的同名面板要靠它区分。
    UnityEngine.Transform __root = __g.transform;
    int __hop = 0;
    while (__root.parent != null && __hop < 64) { __root = __root.parent; __hop++; }
    var __list = new System.Collections.Generic.List<string>();
    int __n = 0;
    foreach (UnityEngine.Transform __c in __root) {
        if (__n++ >= 40) break;
        if (__c.gameObject.activeInHierarchy) __list.Add(__c.name);
    }
    string __joined = string.Join(",", __list.ToArray());
    if (__joined.Length > 400) __joined = __joined.Substring(0, 400);
    return __root.name + "|" + __joined;
};
System.Action<string> __emit = delegate(string __text) {
    try { System.IO.File.AppendAllText(__file, __text + "\n", __utf8); } catch (System.Exception) { }
    UnityEditor.SessionState.SetInt("@@NKEY@@", UnityEditor.SessionState.GetInt("@@NKEY@@", 0) + 1);
};
System.Func<string, string, string> __line = delegate(string __type, string __extra) {
    string __t = UnityEngine.Time.realtimeSinceStartup.ToString("0.###",
        System.Globalization.CultureInfo.InvariantCulture);
    return "{\"t\":" + __t + ",\"type\":\"" + __type + "\""
         + (__extra.Length > 0 ? "," + __extra : "") + "}";
};

// ---- 命中测试（UI 优先，3D 兜底）----
System.Func<UnityEngine.Vector2, UnityEngine.GameObject> __goAt =
    delegate(UnityEngine.Vector2 __p) {
    UnityEngine.GameObject __hitGo = null;
    var __es = UnityEngine.EventSystems.EventSystem.current;
    if (__es != null) {
        var __ped = new UnityEngine.EventSystems.PointerEventData(__es);
        __ped.position = __p;
        var __res = new System.Collections.Generic.List<UnityEngine.EventSystems.RaycastResult>();
        __es.RaycastAll(__ped, __res);
        for (int __i = 0; __i < __res.Count; __i++) {
            if (__res[__i].gameObject != null) { __hitGo = __res[__i].gameObject; break; }
        }
    }
    if (__hitGo == null) {
        var __cam = UnityEngine.Camera.main;
        if (__cam != null) {
            var __ray = __cam.ScreenPointToRay(new UnityEngine.Vector3(__p.x, __p.y, 0f));
            UnityEngine.RaycastHit __rh;
            if (UnityEngine.Physics.Raycast(__ray, out __rh) && __rh.collider != null) {
                __hitGo = __rh.collider.gameObject;
            }
        }
    }
    return __hitGo;
};
System.Func<UnityEngine.GameObject, string[]> __describe =
    delegate(UnityEngine.GameObject __g) {
    string __kind = __g.GetComponent<UnityEngine.RectTransform>() != null ? "ui" : "world";
    return new string[] { __pathOf(__g.transform), __compOf(__g), __labelOf(__g),
                          __panelsOf(__g), __kind };
};
System.Func<UnityEngine.Vector2, UnityEngine.Component> __inputFieldAt =
    delegate(UnityEngine.Vector2 __p) {
    UnityEngine.GameObject __g = __goAt(__p);
    UnityEngine.Transform __node = __g == null ? null : __g.transform;
    for (int __i = 0; __i < 6 && __node != null; __i++) {
        UnityEngine.Component[] __cs = __node.GetComponents<UnityEngine.Component>();
        for (int __j = 0; __j < __cs.Length; __j++) {
            if (__cs[__j] == null) continue;
            string __tn = __cs[__j].GetType().Name;
            if (__tn == "InputField" || __tn == "TMP_InputField") return __cs[__j];
        }
        __node = __node.parent;
    }
    return null;
};

// ---- 输入后端：legacy 优先，新版 Input System 走反射 ----
bool __legacyOk = true;
try { UnityEngine.Input.GetMouseButton(0); } catch (System.Exception) { __legacyOk = false; }
var __kCodes = new UnityEngine.KeyCode[16];
string[] __kLegacy = new string[] { "Escape", "Return", "Space", "Tab", "UpArrow",
    "DownArrow", "LeftArrow", "RightArrow", "W", "A", "S", "D",
    "Alpha1", "Alpha2", "Alpha3", "Backspace" };
string[] __kNew = new string[] { "escape", "enter", "space", "tab", "upArrow",
    "downArrow", "leftArrow", "rightArrow", "w", "a", "s", "d",
    "digit1", "digit2", "digit3", "backspace" };
string[] __kLabels = new string[] { "escape", "enter", "space", "tab", "up",
    "down", "left", "right", "w", "a", "s", "d", "1", "2", "3", "backspace" };
for (int __i = 0; __i < __kLegacy.Length; __i++) {
    __kCodes[__i] = (UnityEngine.KeyCode)System.Enum.Parse(typeof(UnityEngine.KeyCode), __kLegacy[__i]);
}
bool __niTried = false; bool __niOk = false;
System.Type __niKeyEnum = null; object[] __niKeys = null;
System.Reflection.PropertyInfo __niKbCurrent = null;
System.Reflection.PropertyInfo __niKbIndexer = null;
System.Reflection.PropertyInfo __niPressed = null;
bool __niKeyInit = false;
System.Reflection.PropertyInfo __mCurrent = null; System.Reflection.PropertyInfo __mLeft = null;
System.Reflection.PropertyInfo __mPos = null; System.Reflection.PropertyInfo __mPressed = null;
System.Reflection.MethodInfo __mRead = null;
bool __mOk = false;
int __noInputTicks = 0;

// ---- 状态 ----
bool __prevPlaying = UnityEngine.Application.isPlaying;
string __prevScene = "";
int __tick = 0;
bool __prevLeft = false;
UnityEngine.Vector2 __pressPos = UnityEngine.Vector2.zero;
string __pressPath = ""; string __pressComp = ""; string __pressLabel = "";
string __pressPanels = ""; string __pressKind = "";
float __pressT = 0f;
bool __dragging = false;
var __prevKeys = new System.Collections.Generic.Dictionary<string, bool>();
UnityEngine.Component __focusComp = null;
string __focusPath = "";
string __focusText = "";
int __focusTick = 0;

System.Action<string> __flushFocus = delegate(string __reason) {
    if (__focusComp == null) { __focusPath = ""; __focusText = ""; return; }
    string __v = "";
    try {
        System.Reflection.PropertyInfo __pi = __focusComp.GetType().GetProperty("text");
        if (__pi != null) {
            string __raw = __pi.GetValue(__focusComp, null) as string;
            __v = __raw == null ? "" : __raw;
        }
    } catch (System.Exception) { }
    if (__v != __focusText) {
        __emit(__line("text", "\"path\":\"" + __esc(__focusPath) + "\",\"text\":\"" + __esc(__v) + "\""));
        __focusText = __v;
    }
    if (__reason.Length > 0) { __focusComp = null; __focusPath = ""; __focusText = ""; }
};

UnityEditor.EditorApplication.CallbackFunction __cb = null;
System.Action<string> __disarm = delegate(string __why) {
    try { __flushFocus("disarm"); } catch (System.Exception) { }
    UnityEditor.SessionState.SetBool("@@ONKEY@@", false);
    UnityEditor.SessionState.SetString("@@WHYKEY@@", __why);
    UnityEditor.EditorApplication.update -= __cb;
};

__cb = delegate {
    if (!UnityEditor.SessionState.GetBool("@@ONKEY@@", false)) {
        try { __flushFocus("stop"); } catch (System.Exception) { }
        UnityEditor.EditorApplication.update -= __cb;
        return;
    }
    __tick++;
    UnityEditor.SessionState.SetFloat("@@HBKEY@@", UnityEngine.Time.realtimeSinceStartup);
    float __t0 = UnityEditor.SessionState.GetFloat("@@T0KEY@@", 0f);
    if (__t0 > 0f && UnityEngine.Time.realtimeSinceStartup - __t0 > __maxSec) { __disarm("max-seconds"); return; }
    if (UnityEditor.SessionState.GetInt("@@NKEY@@", 0) >= __maxEvents) { __disarm("max-events"); return; }
    try {
        bool __playing = UnityEngine.Application.isPlaying;
        if (__playing != __prevPlaying) {
            __prevPlaying = __playing;
            __emit(__line("play", "\"value\":" + (__playing ? "true" : "false")));
        }
        if (!__playing) return;   // 只在 Play 里记操作：编辑器里的点击不是测试动作

        var __sc = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
        if (__sc.name != __prevScene) {
            __prevScene = __sc.name;
            __emit(__line("scene", "\"name\":\"" + __esc(__sc.name) + "\",\"path\":\"" + __esc(__sc.path) + "\""));
        }

        // ---- 鼠标 ----
        bool __left = false;
        UnityEngine.Vector2 __pos = UnityEngine.Vector2.zero;
        bool __got = false;
        if (__legacyOk) {
            try {
                __left = UnityEngine.Input.GetMouseButton(0);
                __pos = UnityEngine.Input.mousePosition;
                __got = true;
            } catch (System.Exception) { __legacyOk = false; }
        }
        if (!__got && !__niTried) {
            __niTried = true;
            var __mt = System.Type.GetType("UnityEngine.InputSystem.Mouse, Unity.InputSystem");
            if (__mt != null) {
                __mCurrent = __mt.GetProperty("current");
                __mLeft = __mt.GetProperty("leftButton");
                __mPos = __mt.GetProperty("position");
                __mOk = __mCurrent != null && __mLeft != null && __mPos != null;
            }
        }
        if (!__got && __mOk) {
            try {
                object __m = __mCurrent.GetValue(null, null);
                if (__m != null) {
                    object __lb = __mLeft.GetValue(__m, null);
                    if (__mPressed == null) __mPressed = __lb.GetType().GetProperty("isPressed");
                    __left = (bool)__mPressed.GetValue(__lb, null);
                    object __pv = __mPos.GetValue(__m, null);
                    // ReadValue 是**方法**（InputControl<TValue>.ReadValue()），不是属性；
                    // 且 PropertyInfo.Invoke 在这个编译环境不存在 —— 用 MethodInfo
                    if (__mRead == null) __mRead = __pv.GetType().GetMethod("ReadValue", System.Type.EmptyTypes);
                    __pos = (UnityEngine.Vector2)__mRead.Invoke(__pv, null);
                    __got = true;
                }
            } catch (System.Exception) { __mOk = false; }
        }
        if (!__got) {
            __noInputTicks++;
            if (__noInputTicks > 120) { __disarm("no-input-backend"); return; }
            return;
        }
        __noInputTicks = 0;

        if (__left && !__prevLeft) {
            __pressT = UnityEngine.Time.realtimeSinceStartup;
            __pressPos = __pos;
            __dragging = false;
            UnityEngine.GameObject __pg = __goAt(__pos);
            if (__pg != null) {
                string[] __d = __describe(__pg);
                __pressPath = __d[0]; __pressComp = __d[1]; __pressLabel = __d[2];
                __pressPanels = __d[3]; __pressKind = __d[4];
            } else {
                __pressPath = ""; __pressComp = ""; __pressLabel = "";
                __pressPanels = ""; __pressKind = "";
            }
            UnityEngine.Component __nf = __inputFieldAt(__pos);
            if (__nf != __focusComp) {
                __flushFocus("switch");
                if (__nf != null) {
                    __focusComp = __nf;
                    __focusPath = __pathOf(__nf.transform);
                    string __fv = "";
                    try {
                        System.Reflection.PropertyInfo __fpi = __nf.GetType().GetProperty("text");
                        string __fraw = __fpi == null ? null : __fpi.GetValue(__nf, null) as string;
                        __fv = __fraw == null ? "" : __fraw;
                    } catch (System.Exception) { }
                    __focusText = __fv;
                }
            }
        } else if (__left && __prevLeft) {
            if (!__dragging && (__pos - __pressPos).magnitude > 14f) __dragging = true;
        } else if (!__left && __prevLeft) {
            float __dur = UnityEngine.Time.realtimeSinceStartup - __pressT;
            if (__dragging) {
                UnityEngine.GameObject __rg = __goAt(__pos);
                string __toPath = "";
                if (__rg != null) { string[] __rd = __describe(__rg); __toPath = __rd[0]; }
                __emit(__line("drag", "\"from\":\"" + __esc(__pressPath) + "\",\"to\":\"" + __esc(__toPath)
                    + "\",\"from_x\":" + __pressPos.x.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                    + ",\"from_y\":" + __pressPos.y.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                    + ",\"to_x\":" + __pos.x.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                    + ",\"to_y\":" + __pos.y.ToString("0.#", System.Globalization.CultureInfo.InvariantCulture)
                    + ",\"dur\":" + __dur.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture)));
            } else if (__pressPath.Length > 0 && __dur < 2f) {
                __emit(__line("click", "\"path\":\"" + __esc(__pressPath) + "\",\"comp\":\"" + __esc(__pressComp)
                    + "\",\"label\":\"" + __esc(__pressLabel) + "\",\"panels\":\"" + __esc(__pressPanels)
                    + "\",\"kind\":\"" + __esc(__pressKind) + "\""));
            }
            __pressPath = "";
        }
        __prevLeft = __left;

        // ---- 输入框文本（变更即记，转换器合并取最后一次）----
        __focusTick++;
        if (__focusComp != null && __focusTick % 12 == 0) __flushFocus("");

        // ---- 按键（每两拍读一次：按住态 + 边缘检测，漏一拍不丢）----
        if (__tick % 2 == 0) {
            if (!__got) return;
            for (int __ki = 0; __ki < __kLabels.Length; __ki++) {
                bool __down = false;
                if (__legacyOk) {
                    try { __down = UnityEngine.Input.GetKey(__kCodes[__ki]); } catch (System.Exception) { __legacyOk = false; }
                }
                if (!__down && __legacyOk == false) {
                    if (!__niKeyInit) {
                        __niKeyInit = true;
                        var __it = System.Type.GetType("UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
                        var __kt = System.Type.GetType("UnityEngine.InputSystem.Key, Unity.InputSystem");
                        if (__it != null && __kt != null) {
                            __niKbCurrent = __it.GetProperty("current");
                            __niKbIndexer = __it.GetProperty("Item", new System.Type[] { __kt });
                            __niKeyEnum = __kt;
                            __niOk = __niKbCurrent != null && __niKbIndexer != null;
                        }
                    }
                    if (__niOk) {
                        try {
                            object __kb = __niKbCurrent.GetValue(null, null);
                            if (__kb != null) {
                                object __kv = System.Enum.Parse(__niKeyEnum, __kNew[__ki]);
                                object __ctrl = __niKbIndexer.GetValue(__kb, new object[] { __kv });
                                if (__ctrl != null) {
                                    if (__niPressed == null) __niPressed = __ctrl.GetType().GetProperty("isPressed");
                                    __down = (bool)__niPressed.GetValue(__ctrl, null);
                                }
                            }
                        } catch (System.Exception) { __niOk = false; }
                    }
                }
                bool __prevDown = false;
                __prevKeys.TryGetValue(__kLabels[__ki], out __prevDown);
                if (__down && !__prevDown && __focusComp == null) {
                    __emit(__line("key", "\"key\":\"" + __kLabels[__ki] + "\""));
                }
                __prevKeys[__kLabels[__ki]] = __down;
            }
        }
    } catch (System.Exception) { }
};
UnityEditor.EditorApplication.update += __cb;
return "{\"ok\":true,\"file\":\"" + __file.Replace("\\", "/")
     + "\",\"dir\":\"" + __dir.Replace("\\", "/") + "\"}";
"""


def cs_record_ui_start(subdir: str, *, max_seconds: int = DEFAULT_MAX_SECONDS,
                       max_events: int = DEFAULT_MAX_EVENTS) -> str:
    """安装（或重挂）UI 录制器。幂等：钩子活着时不重复挂（防双份事件）。"""
    return _snippet(
        _UI_REC_START,
        subid=_safe_subdir(subdir),
        maxseconds=int(max_seconds),
        maxevents=int(max_events),
        onkey=_UI_ON_KEY, filekey=_UI_FILE_KEY, dirkey=_UI_DIR_KEY, nkey=_UI_N_KEY,
        hbkey=_UI_HB_KEY, t0key=_UI_T0_KEY, whykey=_UI_WHY_KEY,
    )


_UI_REC_STOP = r"""
UnityEditor.SessionState.SetBool("@@ONKEY@@", false);
System.Threading.Thread.Sleep(200);   // 给帧回调一拍时间收尾（落最后一条输入框文本）
int __n = UnityEditor.SessionState.GetInt("@@NKEY@@", 0);
string __file = UnityEditor.SessionState.GetString("@@FILEKEY@@", "");
string __why = UnityEditor.SessionState.GetString("@@WHYKEY@@", "");
return "{\"ok\":true,\"events\":" + __n
     + ",\"reason\":\"" + __why.Replace("\\", "\\\\").Replace("\"", "'") + "\""
     + ",\"file\":\"" + __file.Replace("\\", "/") + "\"}";
"""


def cs_record_ui_stop() -> str:
    """停止录制：置标志让帧回调自己退订（回调持有委托实例，只有它能 -= 自己）。"""
    return _snippet(_UI_REC_STOP, onkey=_UI_ON_KEY, nkey=_UI_N_KEY,
                    filekey=_UI_FILE_KEY, whykey=_UI_WHY_KEY)


_UI_REC_STATUS = r"""
bool __on = UnityEditor.SessionState.GetBool("@@ONKEY@@", false);
int __n = UnityEditor.SessionState.GetInt("@@NKEY@@", 0);
float __hb = UnityEditor.SessionState.GetFloat("@@HBKEY@@", 0f);
float __age = __hb > 0f ? (UnityEngine.Time.realtimeSinceStartup - __hb) : -1f;
string __why = UnityEditor.SessionState.GetString("@@WHYKEY@@", "");
string __file = UnityEditor.SessionState.GetString("@@FILEKEY@@", "");
return "{\"ok\":true,\"on\":" + (__on ? "true" : "false")
     + ",\"events\":" + __n
     + ",\"hb_age\":" + __age.ToString("0.0", System.Globalization.CultureInfo.InvariantCulture)
     + ",\"reason\":\"" + __why.Replace("\\", "\\\\").Replace("\"", "'") + "\""
     + ",\"file\":\"" + __file.Replace("\\", "/") + "\"}";
"""


def cs_record_ui_status() -> str:
    """轻量状态查询（每次轮询都跑，必须小）：开没开 / 已录几条 / 心跳多旧。"""
    return _snippet(_UI_REC_STATUS, onkey=_UI_ON_KEY, nkey=_UI_N_KEY,
                    hbkey=_UI_HB_KEY, whykey=_UI_WHY_KEY, filekey=_UI_FILE_KEY)


_UI_REC_FETCH = r"""
string __file = UnityEditor.SessionState.GetString("@@FILEKEY@@", "");
if (__file.Length == 0 || !System.IO.File.Exists(__file)) {
    return "{\"ok\":false,\"error\":\"录制文件不存在（还没开始录，或 Unity 侧被清掉了）\"}";
}
string[] __lines = System.IO.File.ReadAllLines(__file);
int __total = __lines.Length;
int __since = @@SINCE@@;
if (__since < 0) __since = 0;
if (__since > __total) __since = __total;
int __end = System.Math.Min(__total, __since + @@CAP@@);
var __sb = new System.Text.StringBuilder();
for (int __i = __since; __i < __end; __i++) { __sb.Append(__lines[__i]); __sb.Append("\n"); }
string __payload = __sb.ToString();
var __b = new System.Text.StringBuilder();
for (int __i = 0; __i < __payload.Length; __i++) {
    char __c = __payload[__i];
    if (__c == '\\') __b.Append("\\\\");
    else if (__c == '"') __b.Append("\\\"");
    else if (__c == '\n') __b.Append("\\n");
    else if (__c == '\r') __b.Append("\\r");
    else if (__c == '\t') __b.Append("\\t");
    else if (__c < ' ') __b.Append(' ');
    else __b.Append(__c);
}
return "{\"ok\":true,\"total\":" + __total + ",\"since\":" + __since
     + ",\"more\":" + (__end < __total ? "true" : "false")
     + ",\"text\":\"" + __b.ToString() + "\"}";
"""


def cs_record_ui_fetch(since: int = 0, cap: int = FETCH_CHUNK) -> str:
    """分片取事件（MCP 响应有实际上限，长录制必须分片，否则截断后 JSON 解析失败）。"""
    return _snippet(_UI_REC_FETCH, filekey=_UI_FILE_KEY,
                    since=int(since), cap=int(cap))


# ---------------------------------------------------------------------------
# 回放辅助：拖拽 / 按键（录下来的动作要能原样回放）
# ---------------------------------------------------------------------------

#: 对象解析（名字 → 全路径 → 半截路径 → 可见文本），与 cs_click 同一套规则。
#: 这里用「去转义版」再按 token 替换：本模块的新片段不用 str.format，
#: 免得为 C# 的每个大括号写 {{ }}（漏一个就是 Unity 侧编译错误）。
_CS_FIND_PLAIN = r"""
var __target = @@TARGET@@;   // 值自带引号与转义（见 _cs_quote），模板不要重复加
var __want = __target.Trim();
UnityEngine.GameObject __go = null;
for (int __pass = 0; __pass < 2 && __go == null; __pass++) {
  bool __active = (__pass == 0);
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {
    if (__active && !__g.activeInHierarchy) continue;
    if (__g.name.Trim() == __want) { __go = __g; break; }
  }
  if (__go != null) break;
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {
    if (__active && !__g.activeInHierarchy) continue;
    var __p = __g.name; var __t = __g.transform.parent;
    while (__t != null) { __p = __t.name + "/" + __p; __t = __t.parent; }
    if (__p.Trim() == __want) { __go = __g; break; }
  }
  if (__go != null) break;
  foreach (var __g in UnityEngine.Object.FindObjectsOfType<UnityEngine.GameObject>(true)) {
    if (__active && !__g.activeInHierarchy) continue;
    var __p2 = __g.name; var __t2 = __g.transform.parent;
    while (__t2 != null) { __p2 = __t2.name + "/" + __p2; __t2 = __t2.parent; }
    if (__p2.Trim().EndsWith("/" + __want)) { __go = __g; break; }
  }
}
"""

_CS_SCREEN_POS = r"""
System.Func<UnityEngine.GameObject, UnityEngine.Vector2> __screenPos =
    delegate(UnityEngine.GameObject __g) {
  var __rt = __g.GetComponent<UnityEngine.RectTransform>();
  if (__rt != null) {
    var __c = new UnityEngine.Vector3[4];
    __rt.GetWorldCorners(__c);
    return new UnityEngine.Vector2((__c[0].x + __c[2].x) / 2f, (__c[0].y + __c[2].y) / 2f);
  }
  var __cam = UnityEngine.Camera.main;
  if (__cam != null) {
    var __sp = __cam.WorldToScreenPoint(__g.transform.position);
    return new UnityEngine.Vector2(__sp.x, __sp.y);
  }
  return new UnityEngine.Vector2(0f, 0f);
};
"""

_UI_DRAG = r"""
UnityEngine.GameObject __goA = null;
{
@@FIND_A@@
  __goA = __go;
}
UnityEngine.GameObject __goB = null;
{
@@FIND_B@@
  __goB = __go;
}
if (__goA == null) return "{\"ok\":false,\"error\":\"drag source not found: @@FROM@@\"}";
if (__goB == null) return "{\"ok\":false,\"error\":\"drag target not found: @@TO@@\"}";
@@SCREEN_POS@@
var __es = UnityEngine.EventSystems.EventSystem.current;
if (__es == null) return "{\"ok\":false,\"error\":\"no EventSystem in scene\"}";
var __ped = new UnityEngine.EventSystems.PointerEventData(__es);
__ped.button = UnityEngine.EventSystems.PointerEventData.InputButton.Left;
__ped.clickCount = 1;
var __from = __screenPos(__goA);
var __to = __screenPos(__goB);
__ped.position = __from;
__ped.pressPosition = __from;
__ped.pointerDrag = __goA;
__ped.dragging = false;
UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
    UnityEngine.EventSystems.ExecuteEvents.initializePotentialDrag);
UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
    UnityEngine.EventSystems.ExecuteEvents.pointerDownHandler);
UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
    UnityEngine.EventSystems.ExecuteEvents.beginDragHandler);
__ped.dragging = true;
int __steps = @@STEPS@@;
for (int __i = 1; __i <= __steps; __i++) {
  float __f = (float)__i / (float)__steps;
  __ped.position = UnityEngine.Vector2.Lerp(__from, __to, __f);
  __ped.delta = __ped.position - __ped.pressPosition;
  UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
      UnityEngine.EventSystems.ExecuteEvents.dragHandler);
}
__ped.position = __to;
UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
    UnityEngine.EventSystems.ExecuteEvents.endDragHandler);
UnityEngine.EventSystems.ExecuteEvents.Execute(__goA, __ped,
    UnityEngine.EventSystems.ExecuteEvents.pointerUpHandler);
UnityEngine.EventSystems.ExecuteEvents.Execute(__goB, __ped,
    UnityEngine.EventSystems.ExecuteEvents.dropHandler);
UnityEngine.EventSystems.ExecuteEvents.Execute(__goB, __ped,
    UnityEngine.EventSystems.ExecuteEvents.pointerClickHandler);
return "{\"ok\":true,\"from\":\"@@FROM@@\",\"to\":\"@@TO@@\",\"steps\":" + __steps + "}";
"""


def cs_drag(from_target: str, to_target: str, steps: int = 12) -> str:
    """拖拽回放：完整指针序列（potentialDrag→down→beginDrag→drag×N→endDrag→up→drop）。

    为什么不用 ``Input`` 合成鼠标：编辑器里合成不了真实指针（见技能文档"键盘输入
    合成不可靠"）。这里直接走 ``ExecuteEvents`` —— 与 cs_click 的非 Button 路径
    同一手法，对实现 ``IDragHandler``/``IDropHandler`` 的控件通用。
    """
    find_a = _snippet(_CS_FIND_PLAIN, target=_cs_quote(from_target))
    find_b = _snippet(_CS_FIND_PLAIN, target=_cs_quote(to_target))
    return _snippet(
        _UI_DRAG,
        find_a=find_a, find_b=find_b, screen_pos=_CS_SCREEN_POS,
        steps=max(2, min(60, int(steps))),
        **{"from": _json_escape_in_cs(from_target), "to": _json_escape_in_cs(to_target)},
    )


_UI_KEY = r"""
string __label = "@@LABEL@@";
bool __viaEvents = false;
var __es = UnityEngine.EventSystems.EventSystem.current;
if (__es != null && __es.currentSelectedGameObject != null) {
  var __ped = new UnityEngine.EventSystems.PointerEventData(__es);
  if (__label == "escape") {
    UnityEngine.EventSystems.ExecuteEvents.Execute(__es.currentSelectedGameObject, __ped,
        UnityEngine.EventSystems.ExecuteEvents.cancelHandler);
    __viaEvents = true;
  } else if (__label == "enter" || __label == "space") {
    UnityEngine.EventSystems.ExecuteEvents.Execute(__es.currentSelectedGameObject, __ped,
        UnityEngine.EventSystems.ExecuteEvents.submitHandler);
    __viaEvents = true;
  }
}
bool __viaInput = false;
try {
  var __isType = System.Type.GetType("UnityEngine.InputSystem.InputSystem, Unity.InputSystem");
  var __kbType = System.Type.GetType("UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
  var __ksType = System.Type.GetType("UnityEngine.InputSystem.KeyboardState, Unity.InputSystem");
  var __keyType = System.Type.GetType("UnityEngine.InputSystem.Key, Unity.InputSystem");
  if (__isType != null && __kbType != null && __ksType != null && __keyType != null) {
    object __kb = __kbType.GetProperty("current").GetValue(null, null);
    object __key = System.Enum.Parse(__keyType, "@@KEYNAME@@");
    var __ctor = __ksType.GetConstructor(new System.Type[] { __keyType });
    object __state = __ctor.Invoke(new object[] { __key });
    var __queue = __isType.GetMethod("QueueStateEvent");
    var __gm = __queue.MakeGenericMethod(new System.Type[] { __kbType });
    __gm.Invoke(null, new object[] { __kb, __state });
    __isType.GetMethod("Update").Invoke(null, null);
    __viaInput = true;
  }
} catch (System.Exception) { }
return "{\"ok\":true,\"key\":\"" + __label + "\",\"via_events\":" + (__viaEvents ? "true" : "false")
     + ",\"via_input\":" + (__viaInput ? "true" : "false")
     + ",\"verified\":false,\"hint\":\"键盘合成是尽力而为（实测对游戏的 InputAction 常不生效）；失败就改用可点路径\"}";
"""

#: 平台标签 → 新版 Input System 的 Key 枚举名
_KEY_NEW_NAMES = {
    "escape": "escape", "enter": "enter", "space": "space", "tab": "tab",
    "up": "upArrow", "down": "downArrow", "left": "leftArrow", "right": "rightArrow",
    "backspace": "backspace", "delete": "delete",
    **{c: c for c in "wasd"},
    **{str(d): f"digit{d}" for d in range(1, 10)},
}


def cs_key(label: str) -> str:
    """按键回放（尽力而为）：先走事件系统（Esc=取消 / Enter=提交），再试输入系统合成。"""
    key = str(label or "").strip().lower()
    if key not in _KEY_NEW_NAMES:
        raise ValueError(f"不支持的按键: {label}（可用: {', '.join(sorted(_KEY_NEW_NAMES))}）")
    return _snippet(_UI_KEY, label=key, keyname=_KEY_NEW_NAMES[key])


def _cs_quote(value: str) -> str:
    """C# 字符串字面量（含引号与反斜杠转义）。"""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _json_escape_in_cs(value: str) -> str:
    """嵌进 C# 里那段手搓 JSON 的字符串（反斜杠要双写、引号换单引号）。"""
    return str(value).replace("\\", "\\\\").replace('"', "'")


def _safe_subdir(subdir: str) -> str:
    """录制目录名只允许安全字符（它会被拼进 Unity 侧路径）。"""
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "_", str(subdir or ""))[:64]
    return cleaned or "rec"


# ---------------------------------------------------------------------------
# 事件 → 用例脚本（确定性基线；智能体随后去噪、补注释、跑通验证）
# ---------------------------------------------------------------------------

#: 同一路径的重复点击在这个窗口内视为一次（手抖/双击）
_DEDUPE_CLICK_WINDOW_S = 0.35
#: 事件间隔超过它就记一条"人工停顿"注释（不生成 sleep：平台的纪律是不硬等）
_GAP_COMMENT_S = 1.5


def _py(value: str) -> str:
    """Python 字符串字面量（json 的转义规则是它的子集，直接借用）。"""
    return json.dumps(str(value), ensure_ascii=False)


def _panels_of(event: dict) -> set[str]:
    raw = str(event.get("panels") or "")
    if "|" not in raw:
        return set()
    root, _, joined = raw.partition("|")
    return {p for p in joined.split(",") if p} | ({root} if root else set())


def merge_events(events: list[dict]) -> tuple[list[dict], dict]:
    """把原始事件流压成"人看得懂的动作序列"。

    - 同路径、``_DEDUPE_CLICK_WINDOW_S`` 内的重复点击 → 一次（注释里说明）；
    - 同一输入框的连续 text 事件 → 只留最后一次（中途每个字符都记过）；
    - 空目标的点击（命中测试落空）→ 丢掉并计数（噪声：点到窗口外/UI 之外）。
    """
    steps: list[dict] = []
    stats = {"clicks": 0, "drags": 0, "texts": 0, "keys": 0,
             "dropped": 0, "merged_clicks": 0, "merged_texts": 0}
    for event in events:
        kind = str(event.get("type") or "")
        if kind == "click":
            path = str(event.get("path") or "")
            if not path:
                stats["dropped"] += 1
                continue
            last = steps[-1] if steps else None
            if (last and last["kind"] == "click" and last["path"] == path
                    and float(event.get("t", 0)) - float(last.get("t", 0)) < _DEDUPE_CLICK_WINDOW_S):
                stats["merged_clicks"] += 1
                last["t"] = float(event.get("t", 0))
                last["panels"] = _panels_of(event)
                continue
            stats["clicks"] += 1
            steps.append({
                "kind": "click", "t": float(event.get("t", 0)), "path": path,
                "comp": str(event.get("comp") or ""), "label": str(event.get("label") or ""),
                # 快照是"这一刻界面上有哪些面板"；"点击后新出现"由转换器用
                # **下一次交互**的快照对比得出（见 convert_events_to_script）
                "panels": _panels_of(event),
                "gap": 0.0,
            })
        elif kind == "drag":
            from_path = str(event.get("from") or "")
            to_path = str(event.get("to") or "")
            if not from_path or not to_path:
                stats["dropped"] += 1
                continue
            stats["drags"] += 1
            steps.append({"kind": "drag", "t": float(event.get("t", 0)),
                          "from": from_path, "to": to_path, "gap": 0.0})
        elif kind == "text":
            path = str(event.get("path") or "")
            text = str(event.get("text") or "")
            if not path or not text:
                stats["dropped"] += 1
                continue
            last = steps[-1] if steps else None
            if last and last["kind"] == "text" and last["path"] == path:
                stats["merged_texts"] += 1
                last["text"] = text
                last["t"] = float(event.get("t", 0))
                continue
            stats["texts"] += 1
            steps.append({"kind": "text", "t": float(event.get("t", 0)),
                          "path": path, "text": text, "gap": 0.0})
        elif kind == "key":
            key = str(event.get("key") or "")
            if not key:
                stats["dropped"] += 1
                continue
            stats["keys"] += 1
            steps.append({"kind": "key", "t": float(event.get("t", 0)), "key": key, "gap": 0.0})
    # 时间间隔（生成"人工停顿"注释用）
    for index in range(1, len(steps)):
        steps[index]["gap"] = max(0.0, steps[index]["t"] - steps[index - 1]["t"])
    return steps, stats


def first_scene(events: list[dict]) -> str:
    for event in events:
        if str(event.get("type")) == "scene":
            return str(event.get("path") or event.get("name") or "")
    return ""


def _root_of(path: str) -> str:
    return path.split("/", 1)[0] if path else ""


def convert_events_to_script(events: list[dict], *, title: str = "",
                             created_at: str = "") -> tuple[str, dict]:
    """事件流 → 平台风格的 Python 用例脚本（draft 基线）。

    生成的脚本遵守平台契约：prelude 注入 ``u``、不 import、不写 ``__main__``；
    起跑线用模块级 ``RESET = {...}`` 声明（``start_line()`` 认这个形态）。
    """
    steps, stats = merge_events(events)
    scene = first_scene(events)
    first_click = next((s for s in steps if s["kind"] == "click"), None)
    wait_for = _root_of(first_click["path"]) if first_click else ""

    out: list[str] = []
    out.append(f"# 手动录制生成{'：' + title if title else ''}"
               f"{'（' + created_at + '）' if created_at else ''}")
    out.append("# 录制的是操作轨迹；断言由平台自动播种（标 [自动播种]），跑一遍验证后再改成用例。")
    out.append("# 回放前请自行确认起跑线（平台不复位、不检查）。")
    out.append("")
    if scene or wait_for:
        parts = []
        if scene:
            parts.append(f'"scene": {_py(scene)}')
        if wait_for:
            parts.append(f'"wait_for": {_py(wait_for)}')
        out.append("RESET = {" + ", ".join(parts) + "}")
        out.append("")

    seen_paths: set[str] = set()
    seeded = 0
    # "点击后新出现"要拿**下一次交互时**的面板快照来比：事件自带的快照是点击
    # 那一刻的状态，点击的效果还没发生；下一次交互时的快照才是它带来的结果。
    clicks = [i for i, s in enumerate(steps) if s["kind"] == "click"]
    next_panels: dict[int, set[str]] = {}
    for pos, idx in enumerate(clicks):
        nxt = steps[clicks[pos + 1]] if pos + 1 < len(clicks) else None
        next_panels[idx] = set(nxt.get("panels", set())) if nxt else set()

    for index, step in enumerate(steps):
        if step.get("gap", 0) >= _GAP_COMMENT_S:
            out.append(f"# （人工停顿 {step['gap']:.1f}s）")
        if step["kind"] == "click":
            path = step["path"]
            if path not in seen_paths:
                seen_paths.add(path)
                label = f"  # {step['label']}" if step.get("label") else ""
                out.append(f'u.expect_exists({_py(path)}, timeout=10)  # [自动播种]{label}')
                seeded += 1
            comp = f"  # {step['comp']}" if step.get("comp") else ""
            out.append(f'u.click({_py(path)}){comp}')
            # 点击后新出现的面板 → 断言候选（录到的"打开成功"证据）
            appeared = sorted(next_panels.get(index, set()) - step.get("panels", set()))
            for name in appeared[:2]:
                if len(name) < 2:
                    continue
                out.append(f'u.expect_exists({_py(name)}, timeout=10)  # [自动播种] 点击后新出现')
                seeded += 1
        elif step["kind"] == "drag":
            out.append(f'u.drag({_py(step["from"])}, {_py(step["to"])})'
                       f'  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp')
        elif step["kind"] == "text":
            out.append(f'u.set_text({_py(step["path"])}, {_py(step["text"])})')
        elif step["kind"] == "key":
            out.append(f'u.key({_py(step["key"])})'
                       f'  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径')
    if not steps:
        out.append("# （没有录到任何操作：开始录制后要在 Play 里点游戏）")
    out.append("")
    out.append(f'print("PASS: 录制回放通过（{stats["clicks"]} 次点击 / '
               f'{stats["drags"]} 次拖拽 / {stats["texts"]} 处输入 / {stats["keys"]} 次按键）")')
    out.append("")

    stats_out = {**stats, "assertions_seeded": seeded, "steps": len(steps), "scene": scene}
    return "\n".join(out), stats_out


def parse_events_jsonl(text: str) -> list[dict]:
    """JSONL → 事件列表；坏行跳过（Unity 侧写盘中断可能留半行）。"""
    events: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and item.get("type"):
            events.append(item)
    return events
