# -*- coding: utf-8 -*-
"""把录制稿 flow2_raw.py 机械化去噪成可回放的用例体（不新增/不删业务步骤）。

规则（每条都只做"等价替换"，不改流程语义）：
 1. 去掉录制器自动播种的噪音断言：Dialog / UIModelShotProcessi(ng) / Camera3D ——
    这些是"点击后新出现"的对象（相机、加载遮罩、通用对话节点），不是用例要验的期望。
 2. u.click(P) → tap(P)：先等控件真的显示再点（录制回放是立刻点，界面没出来就点了个空）。
 3. u.drag(A, A)/u.drag(A, B) 里的"自拖拽"：目标是滚动容器（map_content / Viewport /
    content_map / bg_mask / img / sv）的保留（是真的滑动）；目标是按钮/对话点击区
    （click_bg / PanelBg / btn_click）的丢弃（录制噪声，等价于点了一下）。
 4. 含运行期动态 id 的路径（challengeitem-xxx / list_item-xxx / ceng-xxx /
    传功弟子_xxxx / 小比管事_xxxx）改成按前缀查找子节点，换角色也能命中。
"""
import re

SRC = r"E:\test_agent\smart-test-platform\workspace\default\agent\flow2_raw.py"
DST = r"E:\test_agent\smart-test-platform\workspace\default\agent\flow2_body.py"

# 录制器自动播种的 expect_exists 全部丢弃：它们验的是"点击后新出现的对象"
# （相机 / 加载遮罩 / 通用对话节点 / 各种瞬时面板），不是这条用例的期望值。
# 去噪后真正的关卡交给 tap() —— "等控件显示出来再点"，面板没出来就点不动。
NOISE_PREFIX = (
    'u.expect_exists(',
)
SCROLL_HINT = ("map_content", "content_map", "Viewport", "bg_mask", "img", "sv/")

# 动态 id → 前缀查找表达式：把**整个路径字面量**换成 "find_child(前缀, 名字) + 尾段"
def _dyn(name: str):
    return lambda m: 'find_child("%s", "%s") + "%s"' % (m.group(1), name, m.group(2))


DYN = [
    (re.compile(r'"([^"]*)/challengeitem-\d+([^"]*)"'), _dyn("challengeitem")),
    (re.compile(r'"([^"]*)/list_item-\d+([^"]*)"'), _dyn("list_item")),
    (re.compile(r'"([^"]*)/ceng-\d+([^"]*)"'), _dyn("ceng-")),
    # 传功弟子 / 小比管事：名字后面跟的是运行期唯一号（N0000AAC6…）
    (re.compile(r'"([^"]*)/传功弟子_[^/"]+([^"]*)"'), _dyn("传功弟子")),
    (re.compile(r'"([^"]*)/小比管事_[^/"]+([^"]*)"'), _dyn("小比管事")),
]


def dyn(line: str) -> str:
    for rx, rep in DYN:
        line = rx.sub(rep, line)
    return line


def is_scroll_drag(args: str) -> bool:
    return any(h in args for h in SCROLL_HINT)


out = []
for raw in open(SRC, encoding="utf-8").read().splitlines():
    s = raw.strip()
    if not s:
        continue
    if any(s.startswith(p) for p in NOISE_PREFIX):
        continue
    # 录制注释被拆行产生的孤立文本（"# 灌注" 换行后的 "灵气"）—— 不是代码
    if not (s.startswith("u.") or s.startswith("tap(") or s.startswith("#")
            or s.startswith("RESET") or s.startswith("print(") or s.startswith("import ")):
        continue
    # 序号标注：注释里的"人工停顿"留着当说明
    s = dyn(s)
    if s.startswith("u.click("):
        m = re.match(r'u\.click\((.*?)\)(\s*#.*)?$', s)
        if m:
            s = "tap(%s)%s" % (m.group(1), m.group(2) or "")
    elif s.startswith("u.drag("):
        m = re.match(r'u\.drag\((.*)\)(\s*#.*)?$', s)
        args = m.group(1) if m else ""
        if not is_scroll_drag(args):
            continue  # 点了一下被记成拖拽 → 丢弃
    out.append(s)

open(DST, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("body lines:", len(out))
print("tap:", sum(1 for x in out if x.startswith("tap(")))
print("drag kept:", sum(1 for x in out if x.startswith("u.drag(")))
