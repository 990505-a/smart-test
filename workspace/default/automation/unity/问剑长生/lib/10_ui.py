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


