"""检查最近 code_analyst 会话的工具调用轨迹。"""

import json
import urllib.request

TID = "01a0569a-eeee-73b3-bbf7-8abb84409147"
url = f"http://localhost:5011/threads/{TID}/history?limit=100"
with urllib.request.urlopen(url) as resp:
    d = json.loads(resp.read().decode("utf-8"))

if isinstance(d, dict):
    d = d.get("values") or []
latest = d[0] if d else {}
state = latest.get("values", latest) if isinstance(latest, dict) else {}
msgs = state.get("messages", [])
print("message count:", len(msgs))
print("=" * 70)

tool_call_names = {}
for m in msgs:
    t = m.get("type", "?")
    if t == "human":
        c = m.get("content", "")
        print("[用户]", (c if isinstance(c, str) else str(c))[:300])
    elif t == "ai":
        for tc in m.get("tool_calls", []) or []:
            name = tc.get("name", "?")
            tool_call_names[name] = tool_call_names.get(name, 0) + 1
            args = json.dumps(tc.get("args", {}), ensure_ascii=False)[:250]
            print(f"  [调用] {name}({args})")
        c = m.get("content", "")
        if isinstance(c, str) and c.strip():
            print("[回答]", c[:1800])
    elif t == "tool":
        c = m.get("content", "")
        preview = (c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))[:260]
        print(f"    └ 返回: {preview}")

print("=" * 70)
print("工具调用统计:", tool_call_names)
