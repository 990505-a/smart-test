# -*- coding: utf-8 -*-
"""把库里的 loader 指向新的 dist 路径，并同步描述/版本/状态。

用原始字符串承载 loader 源码，避免 Windows 路径里的 \\u 被当成转义。
"""
import sqlite3
import sys

DB = "smart_test_platform.db"
SID = "b3f642f03a984ee6b97116a60d0fe771"
ROOT = "workspace/default/automation/unity/问剑长生"

LOADER = r'''# 起跑线（人工复位）：场景=Assets/Scenes/main.unity；标志物=GameRoot/Canvas2D/Normal/BootWindow(Clone)
#   平台不复位、也不检查起跑线：跑之前请自行把游戏恢复成上面这个状态
"""新手流程总脚本（问剑长生）—— 入库入口（loader），正文不在这里。

正文由 build.py 把 lib/ 的四个片段 + 本用例的 stage 正文拼成：
  cases/新手流程/dist/新手流程总脚本.py
本文件只负责把它读进来执行（exec）。

改用例：改 lib/ 或 cases/新手流程/ 下的源码 → python cases/新手流程/build.py → 重跑。
**不要手改 dist/ 里的生成物**（会被下次构建覆盖，构建是可复现的）。
"""
import os

HERE = r"E:/test_agent/smart-test-platform/workspace/default/automation/unity/问剑长生"
MAIN = os.path.join(HERE, "cases", "新手流程", "dist", "新手流程总脚本.py")

if not os.path.exists(MAIN):
    raise AssertionError(
        "找不到正文：%s\n请先跑：python cases/新手流程/build.py" % MAIN)

RESET = {"scene": "Assets/Scenes/main.unity",
         "wait_for": "GameRoot/Canvas2D/Normal/BootWindow(Clone)"}

with open(MAIN, encoding="utf-8") as fh:
    exec(compile(fh.read(), MAIN, "exec"), globals())
'''

OLD_POS = """【正文位置】脚本正文较长（1600+ 行），按项目约定用 loader 落库；实际内容在工作区：
  E:\\test_agent\\smart-test-platform\\workspace\\default\\agent\\新手流程总脚本.py
（同目录 flow_header.py 是基元层、stage1_body.py/flow2_body.py 是分段正文、build_flow.py 是组装器）"""

NEW_POS = """【正文位置】正文较长（1802 行），库里只放 loader；实际内容在用例工程里：
  workspace/default/automation/unity/问剑长生/
    lib/00_head.py + 10_ui.py + 20_map.py + 30_flow.py   ← 机制与本游戏对象路径（构建时按序拼接）
    cases/新手流程/{stage1_body.py, flow2_body.py, raw/, dist/}
    build.py 把以上片段拼成 cases/新手流程/dist/新手流程总脚本.py
改用例请改源码后重跑 cases/新手流程/build.py，不要手改 dist/ 生成物。
进度、起跑线、失败历史见 cases/新手流程/case.md。"""

TAIL = ("\n\n【2026-09-23 结构迁移】原 workspace/default/agent/ 下 59 个平铺文件已重排为用例工程"
        "（lib/cases/docs/archive/tools）；产物重建后与原文件逐字节一致（md5 校验通过）。"
        "迁移前快照在 archive/2026-09-23-迁移前/。本次同时把 loader 从「读工作区文件」改为指向"
        "dist/ 生成物，并显式声明 RESET —— 平台从此能解析出起跑线。改内容后未再跑通，状态回落 draft。")


def main() -> int:
    conn = sqlite3.connect(DB)
    row = conn.execute("select description, content, version from unity_scripts where id=?",
                       (SID,)).fetchone()
    if row is None:
        print("找不到脚本行:", SID)
        return 1
    old_desc, old_content, old_ver = row
    if OLD_POS not in old_desc:
        print("描述里未找到【正文位置】段，未改动")
        return 1

    conn.execute("update unity_scripts set description=?, content=?, status=?, version=? where id=?",
                 (old_desc.replace(OLD_POS, NEW_POS) + TAIL, LOADER, "draft", old_ver + 1, SID))
    conn.commit()
    print("content     长度 %d -> %d" % (len(old_content), len(LOADER)))
    print("version     %s -> %s" % (old_ver, old_ver + 1))
    print("status      broken -> draft（改内容后未验证；跑通后平台会自动标回 active）")
    print("description 长度 %d -> %d" % (len(old_desc), len(old_desc.replace(OLD_POS, NEW_POS) + TAIL)))

    sys.path.insert(0, ".")
    from src.app.services.unity_service import declared_reset
    print("平台解析新 loader 的 RESET =", declared_reset(LOADER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
