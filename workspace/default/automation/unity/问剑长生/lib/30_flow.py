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