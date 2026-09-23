# -*- coding: utf-8 -*-
"""记忆重组：MEMORY.md 的 36KB 拆成「常驻铁律 + 索引 + 项目 docs/ 专题」。

原则：**只搬不改写**。规则类条目逐字留在 MEMORY.md，游戏专属知识整条移到
cases 工程的 docs/ 下（按需读，不再每轮注入）。

条目按出现顺序编号（见 --dry-run 输出）。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "workspace", "default", "memory")
DOCS = os.path.join(ROOT, "workspace", "default", "automation", "unity", "问剑长生", "docs")
ARCH = os.path.join(ROOT, "workspace", "default", "automation", "unity", "问剑长生", "archive")

#: 条目编号 → 去处（"MEMORY"=留在常驻；docs 文件名为相对 docs/ 的路径）
TARGET = {
    0: "game-ui-paths.md",
    1: "screenshot-boundary.md",
    2: "MEMORY",
    3: "MEMORY",
    4: "MEMORY",
    5: "MEMORY",
    6: "MEMORY",
    7: "flow-stage1.md",
    8: "script-api-pitfalls.md",
    9: "game-ui-paths.md",
    10: "flow-stage1.md",
    11: "world-map.md",
    12: "MEMORY",
    13: "world-map.md",
    14: "world-map.md",
    15: "world-map.md",
    16: "MEMORY",
    17: "world-map.md",
    18: "SUPERSEDED",
    19: "flow-pitfalls.md",
}

DOC_INTRO = {
    "game-ui-paths.md": "问剑长生的 UI 对象路径（按流程位置整理）。改用例要点哪个控件时先查这里。",
    "screenshot-boundary.md": "截图什么时候能用、什么时候不能用。判断界面状态前先读。",
    "flow-stage1.md": "阶段一（注册创角启程）的实测要点与逐步验证记录。",
    "script-api-pitfalls.md": "用例脚本 API 的实测坑（写脚本前读）。",
    "world-map.md": "世界地图/探雾/坐标换算的完整定论（改地图相关代码前必读）。",
    "flow-pitfalls.md": "新手流程 2 的四个真坑与修法（已修在 lib/ 里，改之前先看为什么这么写）。",
}

INDEX_ROWS = [
    ("游戏 UI 对象路径表", "game-ui-paths.md"),
    ("截图能力的边界（什么时候不能靠截图）", "screenshot-boundary.md"),
    ("阶段一实测要点与实跑记录", "flow-stage1.md"),
    ("用例脚本 API 的实测坑", "script-api-pitfalls.md"),
    ("世界地图 / 探雾 / 坐标换算的定论", "world-map.md"),
    ("新手流程 2 的四个真坑", "flow-pitfalls.md"),
]

HEADER = """# MEMORY.md — 长期记忆（常驻部分）

> 这里只放**每次都要遵守**的铁律：跨项目、短、且立刻用得上。
> 具体到某款游戏/某条用例的知识不在这里 —— 见下方索引，用到时再读。
> 拆分于 2026-09-23：原来 36KB 的 20 条日记式条目，规则留下、专题搬到
> `workspace/default/automation/unity/问剑长生/docs/`（按需读，不占常驻上下文）。

## 铁律

"""

INDEX_HEAD = """
## 索引（用到再读，别一次全读）

| 主题 | 位置 |
|---|---|
"""

INDEX_TAIL = """
读取方式：`read_file("<上面的路径>")`，路径相对 `workspace/default/automation/unity/问剑长生/docs/`。
这条用例本身的进度/起跑线/失败历史：`cases/新手流程/case.md`；工程形状：项目根的 `README.md`。
"""


def entries(lines: list[str]) -> list[tuple[int, int]]:
    starts = [i for i, l in enumerate(lines) if re.match(r"^- \*\*\d{4}-\d{2}-\d{2}", l)]
    return [(i, starts[k + 1] if k + 1 < len(starts) else len(lines)) for k, i in enumerate(starts)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = open(os.path.join(MEM, "MEMORY.md"), encoding="utf-8", newline="").read()
    lines = src.split("\n")
    spans = entries(lines)
    assert len(spans) == len(TARGET), f"条目数变了：{len(spans)} != {len(TARGET)}"

    buckets: dict[str, list[str]] = {}
    kept: list[str] = []
    superseded: list[str] = []
    for idx, (a, b) in enumerate(spans):
        block = "\n".join(lines[a:b]).rstrip("\n")
        dest = TARGET[idx]
        if dest == "MEMORY":
            kept.append(block)
        elif dest == "SUPERSEDED":
            superseded.append(block)
        else:
            buckets.setdefault(dest, []).append(block)

    for name, blocks in buckets.items():
        print(f"[docs] {name:<26} {len(blocks)} 条 / {sum(len(b) for b in blocks)} 字符")
    print(f"[常驻] MEMORY.md                 {len(kept)} 条 / {sum(len(b) for b in kept)} 字符")
    print(f"[归档] 被取代条目                 {len(superseded)} 条 / {sum(len(s) for s in superseded)} 字符")
    if args.dry_run:
        return 0

    os.makedirs(DOCS, exist_ok=True)
    for name, blocks in buckets.items():
        body = (f"# {name[:-3]}\n\n> {DOC_INTRO.get(name, '')}\n>\n"
                f"> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。\n\n"
                + "\n\n".join(blocks) + "\n")
        open(os.path.join(DOCS, name), "w", encoding="utf-8", newline="").write(body)
    print(f"[写出] {len(buckets)} 个专题 → {DOCS}")

    index = INDEX_HEAD + "".join(f"| {topic} | `docs/{path}` |\n" for topic, path in INDEX_ROWS) + INDEX_TAIL
    new_memory = HEADER + "\n\n".join(kept) + "\n" + index
    shutil.copy2(os.path.join(MEM, "MEMORY.md"), os.path.join(ARCH, "2026-09-23-迁移前",
                                                              "MEMORY.md.全文备份"))
    open(os.path.join(MEM, "MEMORY.md"), "w", encoding="utf-8", newline="").write(new_memory)
    snap = os.path.join(MEM, ".snapshot")
    if os.path.isdir(snap):
        open(os.path.join(snap, "MEMORY.md"), "w", encoding="utf-8", newline="").write(new_memory)
        print("[快照] memory/.snapshot/MEMORY.md 已同步")
    if superseded:
        open(os.path.join(ARCH, "2026-09-23-迁移前", "MEMORY.被取代条目.md"), "w",
             encoding="utf-8", newline="").write("\n\n".join(superseded) + "\n")

    print(f"[结果] MEMORY.md {len(src)} -> {len(new_memory)} 字符"
          f"（常驻从 {len(src)} 降到 {len(new_memory)}，专题 {sum(len(b) for bs in buckets.values() for b in bs)} 字符改为按需）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
