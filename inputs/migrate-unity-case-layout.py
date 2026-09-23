# -*- coding: utf-8 -*-
"""一次性迁移：把 workspace/default/agent/ 的平铺杂物，重排成「用例工程」结构。

目标结构（workspace/default/automation/unity/问剑长生/）：
  lib/     机制与游戏知识（按片段切分，构建时按序拼接回原 flow_header.py）
  cases/新手流程/{,raw/}   本用例的正文、录音原稿、构建器
  cases/新手流程/dist/     生成物（可重建）
  tools/   仍在用的探针
  docs/    按需读的专题知识（后面手工补）
  archive/ 一次性脚本，按日期归档

硬要求：迁移后重新构建的产物必须与迁移前逐字节一致（md5 相同），否则中止。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
O = os.path.join(ROOT, "workspace", "default", "agent")             # 旧目录
N = os.path.join(ROOT, "workspace", "default", "automation", "unity", "问剑长生")

PRODUCTS = ["新手流程总脚本.py", "run_flow2.py", "run_stage2a.py",
            "run_stage2b.py", "run_stage3a.py", "run_stage3b.py"]

#: flow_header.py 的切分点（按行号，边界处都是空行/注释横幅，切完拼接可字节还原）
FRAGMENTS = [
    ("00_head.py", 1, 94),      # 模块文档串 + import + RESET + 本游戏对象路径常量（游戏知识）
    ("10_ui.py", 95, 301),      # 基础操作封装：wait_visible/tap/expect_text/…
    ("20_map.py", 302, 932),    # 地图/探雾/坐标换算/拖拽（内嵌 C#/Lua）
    ("30_flow.py", 933, 10 ** 9),  # 流程节拍与检查：找子节点/推进剧情/console/起跑线
]

ARCHIVE_BY_DATE = {
    "2026-09-22": ["dump_cells.py", "check_quotes.py", "check_quotes2.py", "check_cases.py",
                   "fix_cases.py", "fix_cases3.py", "fix_cases4.py", "fix_cases5.py",
                   "fix_cases6.py", "fix_cases7.py", "fix_cases8.py", "fix_cases9.py",
                   "fix_cases10.py", "fix_cases11.py", "fix_cases12.py",
                   "okzj_cases.md", "okzj_cases_stdout.txt",
                   "feishu_auth_qr.png", "feishu_auth_qr2.png", "mcp_probe_init.json"],
    "2026-09-23": ["_probe_history.py", "probe_api.py", "probe_map_state.py", "probe_cell_screen.py",
                   "probe_map_semantic.py", "probe_cells_onscreen.py", "probe_map_deep.py",
                   "probe_gridinfo.py", "fix_header.py", "fix_header2.py", "fix_header3.py",
                   "fix_header4.py", "fix_header5.py", "fix_build.py",
                   "resume_flow2.py", "resume2.py", "run_full_flow.py",
                   "find_split.py", "show_split.py", "count_pauses.py",
                   "run_stage1.py", "run_stage2.py", "run_stage3.py",
                   "build_out.txt", "sizes.txt"],
}
#: 仍在用的探针（留一份可复现的现场分析工具）
KEEP_TOOLS = ["probe_cell_xy.py"]

report: list[str] = []


def log(msg: str) -> None:
    print(msg)
    report.append(msg)


def md5(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def mkdirs() -> None:
    for sub in ("lib", "cases", "cases/新手流程", "cases/新手流程/raw", "cases/新手流程/dist",
                "tools", "docs", "archive", *(f"archive/{d}" for d in ARCHIVE_BY_DATE)):
        os.makedirs(os.path.join(N, sub), exist_ok=True)
    log(f"[目录] 已建立 {N}")


def _line_offsets(src: str) -> list[int]:
    """按 "\\n" 切的行首偏移（与 sed 行号一致）。

    不能用 str.splitlines()：它还会在 \\x0c / \\u2028 等处切，行号会与 sed/wc 错开。
    """
    offsets = [0]
    for index, ch in enumerate(src):
        if ch == "\n":
            offsets.append(index + 1)
    return offsets


def split_header() -> None:
    """flow_header.py → lib/*.py：只做行区间切分，拼接回来必须逐字节相同。"""
    src = open(os.path.join(O, "flow_header.py"), encoding="utf-8", newline="").read()
    offsets = _line_offsets(src)
    parts = []
    for name, start, end in FRAGMENTS:
        lo = offsets[start - 1]
        hi = offsets[end] if end < len(offsets) else len(src)
        chunk = src[lo:hi]
        open(os.path.join(N, "lib", name), "w", encoding="utf-8", newline="").write(chunk)
        parts.append(chunk)
        log(f"[切分] lib/{name}  {len(chunk)} 字符 / {chunk.count(chr(10))} 行")
    assert "".join(parts) == src, "切分后拼接与原文件不一致 —— 已中止"
    log("[切分] 拼接校验通过：lib/*.py 按序拼回 == 原 flow_header.py")


def copy_sources() -> None:
    """正文、录音原稿、构建器进 cases/新手流程/。"""
    case = os.path.join(N, "cases", "新手流程")
    for name in ("stage1_body.py", "flow2_body.py"):
        shutil.copy2(os.path.join(O, name), os.path.join(case, name))
        log(f"[源码] cases/新手流程/{name}")
    for name in ("flow2_raw.py", "normalize_flow2.py"):
        shutil.copy2(os.path.join(O, name), os.path.join(case, "raw", name))
        log(f"[原稿] cases/新手流程/raw/{name}")


def adapt_builder() -> None:
    """build_flow.py → cases/新手流程/build.py：只改输入/输出路径，逻辑零改动。"""
    src = open(os.path.join(O, "build_flow.py"), encoding="utf-8", newline="").read()
    old_head = '''HERE = os.path.dirname(os.path.abspath(__file__))
HEADER = open(os.path.join(HERE, "flow_header.py"), encoding="utf-8").read()'''
    new_head = '''HERE = os.path.dirname(os.path.abspath(__file__))          # cases/<用例>/
PROJECT = os.path.dirname(os.path.dirname(HERE))             # 用例工程根
LIB = os.path.join(PROJECT, "lib")
DIST = os.path.join(HERE, "dist")

#: lib/ 里的片段按文件名排序拼接 —— 必须与拆分时一致，拼接结果 == 原 flow_header.py
_FRAGMENTS = sorted(n for n in os.listdir(LIB) if n[:2].isdigit() and n.endswith(".py"))
HEADER = "".join(open(os.path.join(LIB, n), encoding="utf-8", newline="").read()
                 for n in _FRAGMENTS)'''
    assert old_head in src, "构建器头部未按预期匹配"
    src = src.replace(old_head, new_head, 1)

    old_write = '''    p = os.path.join(HERE, name)'''
    new_write = '''    p = os.path.join(DIST, name)'''
    assert old_write in src, "构建器写出路径未按预期匹配"
    src = src.replace(old_write, new_write, 1)
    src = src.replace('open(os.path.join(HERE, "stage1_body.py")',
                      'open(os.path.join(HERE, "stage1_body.py")', 1)

    dst = os.path.join(N, "cases", "新手流程", "build.py")
    open(dst, "w", encoding="utf-8", newline="").write(src)
    log("[构建器] cases/新手流程/build.py（仅改输入/输出路径）")


def rebuild_and_verify() -> None:
    """重建产物并与迁移前逐字节比对 —— 这是本次迁移的验收门槛。"""
    case = os.path.join(N, "cases", "新手流程")
    proc = subprocess.run([sys.executable, os.path.join(case, "build.py")],
                          cwd=case, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit("构建失败：\n" + (proc.stdout or "") + (proc.stderr or ""))
    log("[构建] " + (proc.stdout or "").strip().replace("\n", " | ")[:400])

    bad = []
    for name in PRODUCTS:
        a = os.path.join(case, "dist", name)
        b = os.path.join(O, name)
        if not os.path.exists(a):
            bad.append(f"{name} 缺失")
            continue
        same = md5(a) == md5(b)
        log(f"[验收] {'✅ 一致' if same else '❌ 不一致'}  {name}")
        if not same:
            bad.append(name)
    if bad:
        raise SystemExit("产物与迁移前不一致，已中止（旧文件未动）：" + ", ".join(bad))
    log("[验收] 全部产物与迁移前逐字节一致 —— 迁移未改变任何行为")


def archive_old() -> None:
    """产物已验证：旧目录里的东西按类归位或归档。"""
    for name in ARCHIVE_BY_DATE["2026-09-22"]:
        s = os.path.join(O, name)
        if os.path.exists(s):
            shutil.move(s, os.path.join(N, "archive", "2026-09-22", name))
    log("[归档] archive/2026-09-22/（改用例文档与二维码等 %d 项）"
        % len(os.listdir(os.path.join(N, "archive", "2026-09-22"))))

    for name in ARCHIVE_BY_DATE["2026-09-23"]:
        s = os.path.join(O, name)
        if os.path.exists(s):
            shutil.move(s, os.path.join(N, "archive", "2026-09-23", name))
    log("[归档] archive/2026-09-23/（探针/修补/过期分段稿 %d 项）"
        % len(os.listdir(os.path.join(N, "archive", "2026-09-23"))))

    for name in KEEP_TOOLS:
        s = os.path.join(O, name)
        if os.path.exists(s):
            shutil.move(s, os.path.join(N, "tools", name))
            log(f"[工具] tools/{name}")

    shots = os.path.join(O, "shots")
    if os.path.isdir(shots):
        shutil.move(shots, os.path.join(N, "archive", "2026-09-23", "shots"))


def cleanup_old() -> None:
    """旧目录只留空壳（它仍是默认 cwd，平台会往里写新东西）。"""
    for name in os.listdir(O):
        if name == "archive":
            continue
        path = os.path.join(O, name)
        if name == "__pycache__":
            shutil.rmtree(path, ignore_errors=True)
            continue
        log(f"[遗留] 旧目录仍有 {name}（未动，请人工确认）")


def tree() -> None:
    log("\n=== 迁移后的结构 ===")
    for base, dirs, files in os.walk(N):
        depth = base[len(N):].count(os.sep)
        log("  " * depth + f"{os.path.basename(base)}/")
        for f in sorted(files):
            log("  " * (depth + 1) + f)


if __name__ == "__main__":
    mkdirs()
    split_header()
    copy_sources()
    adapt_builder()
    rebuild_and_verify()
    archive_old()
    cleanup_old()
    tree()
    out = os.path.join(ROOT, "inputs", "migrate-unity-case-layout.report.txt")
    open(out, "w", encoding="utf-8").write("\n".join(report))
    print(f"\n报告: {out}")
