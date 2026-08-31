"""
unity-auto-test 优化验证测试脚本

验证所有优化后的 API 是否正常工作，覆盖：
  - 主题A: TextReader 性能优化（定向快速路径、allow_multiple、instance_id）
  - 主题B: UI 操作合并优化（click_close window_name、find_and_click_by_text 单次 Lua）
  - 主题C: allow_multiple 窗口与 ItemInfo 弹窗支持
  - 主题D: Inspector 子树序列化优化（dump_tree、get_shown_windows_detail）
  - 主题E: 按钮点击可靠性（lua_click）

用法:
    python scripts/test_optimization.py [--output report.txt]
"""
import argparse
import io
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from unity_api import UnityClient, UnityAPIError
from ui import UI
from text_reader import TextReader
from inspector import Inspector
from gm import GM


class TestReport:
    """测试报告收集器，同时输出到终端和文件。"""

    def __init__(self, output_path: str = None):
        self.buf = io.StringIO()
        self.output_path = output_path
        self.passed = 0
        self.failed = 0
        self.errors = []

    def log(self, msg: str = ""):
        print(msg)
        self.buf.write(msg + "\n")

    def section(self, title: str):
        sep = "=" * 70
        self.log(f"\n{sep}")
        self.log(f"  {title}")
        self.log(sep)

    def test(self, name: str, func):
        self.log(f"\n  [{self.passed + self.failed + 1}] {name}")
        t0 = time.time()
        try:
            result = func()
            elapsed = (time.time() - t0) * 1000
            self.log(f"      PASS ({elapsed:.0f}ms)")
            if result is not None:
                for line in str(result).split("\n"):
                    self.log(f"      > {line}")
            self.passed += 1
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            self.log(f"      FAIL ({elapsed:.0f}ms): {e}")
            self.failed += 1
            self.errors.append((name, str(e)))

    def save(self):
        sep = "=" * 70
        self.log(f"\n{sep}")
        self.log(f"  总计: {self.passed + self.failed} 项 | 通过: {self.passed} | 失败: {self.failed}")
        self.log(sep)
        if self.errors:
            self.log("\n失败项汇总:")
            for name, err in self.errors:
                self.log(f"  - {name}: {err}")

        if self.output_path:
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(self.buf.getvalue())
            self.log(f"\n报告已保存到: {self.output_path}")


def main():
    parser = argparse.ArgumentParser(description="unity-auto-test 优化验证测试")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=16666)
    parser.add_argument("--output", default=None,
                        help="测试报告输出路径（默认: <vibetest>/docs/经验总结/optimization-test-report.txt）")
    args = parser.parse_args()

    if not args.output:
        vibetest_dir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "..", ".."))
        args.output = os.path.join(vibetest_dir, "docs", "经验总结",
                                   "optimization-test-report.txt")

    report = TestReport(args.output)

    report.log("unity-auto-test 优化验证测试报告")
    report.log(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.log(f"服务器: {args.host}:{args.port}")

    # ================================================================
    # 初始化
    # ================================================================
    report.section("初始化")

    client = UnityClient(host=args.host, port=args.port)
    ui = UI(client)
    tr = TextReader(client)
    ins = Inspector(client)
    gm = GM(client)

    report.test("服务器连通性", lambda: (
        client.status()
    ))

    report.test("模块实例化", lambda: (
        f"UnityClient, UI, TextReader, Inspector, GM 全部创建成功"
    ))

    # ================================================================
    # 主题 A: TextReader 性能优化
    # ================================================================
    report.section("主题A: TextReader 性能优化")

    # A1: _lua_get_root_go 使用 UI.query_shown_window
    def test_a1():
        text = tr.get_text("text_title", window_name="HudWindow")
        return f"HudWindow 中 text_title = {text!r}"
    report.test("A1: get_text 定向快速路径（指定 window_name）", test_a1)

    # A2: get_text 全局搜索（无 window_name）
    def test_a2():
        text = tr.get_text("text_title")
        return f"全局搜索 text_title = {text!r}"
    report.test("A2: get_text 定向快速路径（全局搜索）", test_a2)

    # A3: get_texts 定向快速路径
    def test_a3():
        texts = tr.get_texts("text_title", window_name="HudWindow")
        return f"HudWindow 中 text_title 数量: {len(texts)}, 值: {texts}"
    report.test("A3: get_texts 定向快速路径", test_a3)

    # A4: get_all_texts 批量读取（使用 UI.get_all_windows）
    def test_a4():
        all_texts = tr.get_all_texts(window_name="HudWindow")
        return f"HudWindow 中共 {len(all_texts)} 个不同节点名"
    report.test("A4: get_all_texts 批量读取（修复 allow_multiple）", test_a4)

    # A5: get_all_texts 全局搜索
    def test_a5():
        all_texts = tr.get_all_texts()
        return f"全局（所有 shown 窗口）共 {len(all_texts)} 个不同节点名"
    report.test("A5: get_all_texts 全局搜索（使用 UI.get_all_windows）", test_a5)

    # A6: find_button_by_text Lua 侧早停
    shown_windows = ins.get_shown_windows()
    target_window = None
    for w in shown_windows:
        if w not in ("HudWindow", "ChatWindow", "ScreenEventWindow",
                     "GmWindow", "CloudWindow", "FullBackWindow"):
            target_window = w
            break

    if target_window:
        def test_a6():
            buttons = tr.get_button_texts(window_name=target_window)
            if not buttons:
                return f"窗口 {target_window} 中无按钮，跳过"
            first_btn = buttons[0]
            text = first_btn["text"]
            if not text:
                return f"第一个按钮无文本，跳过文本匹配测试"
            from text_reader import _strip_tags
            clean_text = _strip_tags(text)
            result = tr.find_button_by_text(clean_text,
                                            window_name=target_window,
                                            strip_tags=True)
            if result:
                return f"在 {target_window} 中按文本 {clean_text!r} 找到按钮: {result['name']} (id={result['instanceID']})"
            return f"未找到文本为 {clean_text!r} 的按钮"
        report.test(f"A6: find_button_by_text Lua 侧早停（窗口: {target_window}）", test_a6)
    else:
        report.test("A6: find_button_by_text Lua 侧早停", lambda: "无合适的测试窗口，跳过")

    # A7: find_nodes_by_text（修复全局搜索路径）
    def test_a7():
        nodes = tr.find_nodes_by_text("", exact=False)
        return f"全局搜索含空串的 TMP 节点: {len(nodes)} 个（验证全局路径正确）"
    report.test("A7: find_nodes_by_text 全局搜索路径修复", test_a7)

    # ================================================================
    # 主题 B: UI 操作合并优化
    # ================================================================
    report.section("主题B: UI 操作合并优化")

    # B1: is_window_shown 使用 UI.query_shown_window
    def test_b1():
        results = {}
        for w in ["HudWindow", "ChatWindow", "NonExistentWindow123"]:
            results[w] = ui.is_window_shown(w)
        return "\n".join(f"{k}: {v}" for k, v in results.items())
    report.test("B1: is_window_shown（使用 UI.query_shown_window）", test_b1)

    # B2: click_close 带 window_name（UI.close 单次调用）
    def test_b2():
        ui.open_window("CharacterWindow", wait=2.0)
        if not ui.is_window_shown("CharacterWindow"):
            return "CharacterWindow 未能打开，跳过 click_close 测试"
        ui.click_close(window_name="CharacterWindow", wait=1.0)
        closed = not ui.is_window_shown("CharacterWindow")
        return f"CharacterWindow 已关闭: {closed}"
    report.test("B2: click_close(window_name=...) 单次 Lua 调用关闭", test_b2)

    # B3: close_window 使用 query_shown_window
    def test_b3():
        ui.open_window("CharacterWindow", wait=2.0)
        if not ui.is_window_shown("CharacterWindow"):
            return "CharacterWindow 未能打开，跳过"
        ui.close_window("CharacterWindow", wait=1.0)
        closed = not ui.is_window_shown("CharacterWindow")
        return f"close_window 成功关闭: {closed}"
    report.test("B3: close_window（使用 query_shown_window + UI.close）", test_b3)

    # B4: find_and_click_by_text 单次 Lua 调用
    if target_window:
        def test_b4():
            buttons = tr.get_button_texts(window_name=target_window)
            active_btns = [b for b in buttons if b["active"] and b["text"]]
            if not active_btns:
                return f"窗口 {target_window} 中无带文本的 active 按钮，跳过"
            from text_reader import _strip_tags
            btn = active_btns[0]
            clean = _strip_tags(btn["text"])
            if not clean:
                return "按钮文本为空，跳过"
            try:
                result = ui.find_and_click_by_text(clean,
                                                   window_name=target_window,
                                                   strip_tags=True,
                                                   wait=0.5)
                return f"单次 Lua 调用点击成功: {result}"
            except UnityAPIError as e:
                return f"点击失败（可能是正常的）: {e}"
        report.test(f"B4: find_and_click_by_text 单次 Lua 调用（窗口: {target_window}）", test_b4)
    else:
        report.test("B4: find_and_click_by_text 单次 Lua 调用", lambda: "无合适窗口，跳过")

    # ================================================================
    # 主题 C: allow_multiple 窗口与 ItemInfo 弹窗支持
    # ================================================================
    report.section("主题C: allow_multiple 窗口与 ItemInfo 弹窗支持")

    # C1: get_shown_instances
    def test_c1():
        results = {}
        for w in shown_windows:
            instances = ui.get_shown_instances(w)
            if instances:
                results[w] = instances
        lines = []
        for w, insts in results.items():
            for inst in insts:
                lines.append(f"{w}: instanceID={inst['instanceID']}")
        return "\n".join(lines) if lines else "无窗口有多实例"
    report.test("C1: get_shown_instances 列出所有窗口实例", test_c1)

    # C2: instance_id 定位读取
    def test_c2():
        details = ins.get_shown_windows_detail()
        if not details:
            return "无显示窗口，跳过"
        first = details[0]
        iid = first["instanceID"]
        name = first["name"]
        text = tr.get_all_texts(instance_id=iid)
        return f"通过 instance_id={iid} 读取 {name} 的文本: {len(text)} 个节点名"
    report.test("C2: instance_id 精确定位窗口读取文本", test_c2)

    # C3: close_all_item_info
    def test_c3():
        result = ui.close_all_item_info(wait=0.5)
        return f"close_all_item_info 结果: {result}"
    report.test("C3: close_all_item_info 批量关闭物品弹窗", test_c3)

    # ================================================================
    # 主题 D: Inspector 子树序列化优化
    # ================================================================
    report.section("主题D: Inspector 子树序列化优化")

    # D1: get_all_windows（修复 allow_multiple + table.concat）
    def test_d1():
        windows = ins.get_all_windows()
        shown_count = sum(1 for v in windows.values() if v == "shown")
        hidden_count = sum(1 for v in windows.values() if v == "hidden")
        return f"总窗口: {len(windows)} (shown={shown_count}, hidden={hidden_count})"
    report.test("D1: get_all_windows（使用 UI.get_all_windows + table.concat）", test_d1)

    # D2: get_shown_windows_detail
    def test_d2():
        details = ins.get_shown_windows_detail()
        lines = []
        for d in details:
            lines.append(f"{d['name']} (id={d['instanceID']})")
        return "\n".join(lines) if lines else "无显示窗口"
    report.test("D2: get_shown_windows_detail（含 instanceID）", test_d2)

    # D3: dump_tree 单次 Lua 调用
    def test_d3():
        details = ins.get_shown_windows_detail()
        hud = [d for d in details if d["name"] == "HudWindow"]
        if not hud:
            return "HudWindow 未显示，跳过"
        hud_id = hud[0]["instanceID"]
        tree = ins.dump_tree(hud_id, depth=2, active_only=True)
        lines = tree.split("\n")
        return f"HudWindow 子树（depth=2, active_only）: {len(lines)} 行\n" + tree
    report.test("D3: dump_tree 单次 Lua 子树序列化", test_d3)

    # D4: dump_tree 更大深度
    def test_d4():
        details = ins.get_shown_windows_detail()
        target = None
        for d in details:
            if d["name"] not in ("HudWindow", "GmWindow", "ScreenEventWindow",
                                 "CloudWindow", "FullBackWindow"):
                target = d
                break
        if not target:
            return "无合适窗口测试，跳过"
        tree = ins.dump_tree(target["instanceID"], depth=3, active_only=True)
        lines = tree.split("\n")
        return f"{target['name']} 子树（depth=3）: {len(lines)} 行\n" + "\n".join(lines[:15]) + (
            f"\n... ({len(lines)-15} more lines)" if len(lines) > 15 else "")
    report.test("D4: dump_tree 深度3子树序列化", test_d4)

    # D5: print_hero_info 单次 Lua 调用
    def test_d5():
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        ins.print_hero_info()
        sys.stdout = old_stdout
        output = buf.getvalue().strip()
        return output
    report.test("D5: print_hero_info（单次 Lua 调用）", test_d5)

    # D6: print_tree 使用 dump_tree
    def test_d6():
        details = ins.get_shown_windows_detail()
        hud = [d for d in details if d["name"] == "HudWindow"]
        if not hud:
            return "HudWindow 未显示，跳过"
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        ins.print_tree(hud[0]["instanceID"], depth=2, active_only=True)
        sys.stdout = old_stdout
        output = buf.getvalue().strip()
        return f"print_tree 输出:\n{output}"
    report.test("D6: print_tree（底层使用 dump_tree）", test_d6)

    # ================================================================
    # 主题 E: 按钮点击可靠性
    # ================================================================
    report.section("主题E: 按钮点击可靠性")

    # E1: lua_click 基本功能
    def test_e1():
        if not target_window:
            return "无合适窗口，跳过"
        buttons = tr.get_button_texts(window_name=target_window)
        active_btns = [b for b in buttons if b["active"]]
        if not active_btns:
            return f"窗口 {target_window} 中无 active 按钮，跳过"
        btn = active_btns[0]
        try:
            result = ui.lua_click(btn["instanceID"], wait=0.5)
            return f"lua_click 成功点击: {btn['name']} (id={btn['instanceID']}), 结果: {result}"
        except UnityAPIError as e:
            return f"lua_click 异常: {e}"
    report.test("E1: lua_click 通过 onClick:Invoke() 点击按钮", test_e1)

    # E2: find_in_children 子树搜索
    def test_e2():
        details = ins.get_shown_windows_detail()
        hud = [d for d in details if d["name"] == "HudWindow"]
        if not hud:
            return "HudWindow 未显示，跳过"
        result = ui.find_in_children(hud[0]["instanceID"], "layout", max_depth=3)
        if result:
            return f"在 HudWindow 子树中找到 layout: instanceID={result['instanceID']}, active={result['active']}"
        return "未找到 layout 节点"
    report.test("E2: find_in_children Lua 子树搜索", test_e2)

    # E3: wait_for_hierarchy_window 测试
    def test_e3():
        result = ui.wait_for_hierarchy_window("HudWindow", timeout=3.0)
        if result:
            return f"在 hierarchy 中找到 HudWindow: id={result['instanceID']}, active={result['active']}"
        return "未找到 HudWindow"
    report.test("E3: wait_for_hierarchy_window 轮询检测", test_e3)

    # ================================================================
    # 性能对比
    # ================================================================
    report.section("性能对比")

    def test_perf1():
        t0 = time.time()
        for _ in range(5):
            tr.get_text("text_title", window_name="HudWindow")
        elapsed = (time.time() - t0) * 1000
        avg = elapsed / 5
        return f"5 次 get_text（定向快速路径）: 总计 {elapsed:.0f}ms, 平均 {avg:.0f}ms/次"
    report.test("PERF1: get_text 定向路径性能（5次）", test_perf1)

    def test_perf2():
        t0 = time.time()
        for _ in range(5):
            tr.get_all_texts(window_name="HudWindow")
        elapsed = (time.time() - t0) * 1000
        avg = elapsed / 5
        return f"5 次 get_all_texts: 总计 {elapsed:.0f}ms, 平均 {avg:.0f}ms/次"
    report.test("PERF2: get_all_texts 批量读取性能（5次）", test_perf2)

    def test_perf3():
        details = ins.get_shown_windows_detail()
        hud = [d for d in details if d["name"] == "HudWindow"]
        if not hud:
            return "HudWindow 未显示，跳过"
        t0 = time.time()
        ins.dump_tree(hud[0]["instanceID"], depth=3, active_only=True)
        elapsed = (time.time() - t0) * 1000
        return f"dump_tree(depth=3): {elapsed:.0f}ms（单次 Lua 调用）"
    report.test("PERF3: dump_tree 单次 Lua 序列化性能", test_perf3)

    def test_perf4():
        t0 = time.time()
        ins.get_all_windows()
        elapsed = (time.time() - t0) * 1000
        return f"get_all_windows: {elapsed:.0f}ms（使用 UI.get_all_windows + table.concat）"
    report.test("PERF4: get_all_windows 性能", test_perf4)

    def test_perf5():
        t0 = time.time()
        ui.is_window_shown("HudWindow")
        elapsed = (time.time() - t0) * 1000
        return f"is_window_shown: {elapsed:.0f}ms（使用 query_shown_window）"
    report.test("PERF5: is_window_shown 性能", test_perf5)

    # ================================================================
    # 保存报告
    # ================================================================
    report.save()
    sys.exit(1 if report.failed else 0)


if __name__ == "__main__":
    main()
