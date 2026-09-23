# -*- coding: utf-8 -*-
"""新手流程总脚本（阶段一 + 阶段二 + 阶段三）。

链路：启动界面 → 登出/注册并登录 → 创角改名 → 踏入仙途启程 → 序章 → 主线「寻找道院」
     → 修炼/聚灵/服用丹药 → 加入道院（真武）→ 洞府升级 → 聚灵塔试炼 → 外院晋升
     → 门派比试 → 收尾。

时长与执行方式：
  全流程实测约 12~15 分钟。平台单次执行上限由 .env 的 UNITY_RUN_TIMEOUT_S 决定
  （本机 1800s），够一次跑完；若某台机器上仍是默认 420s，用本脚本同源的
  run_stage2a/2b/3a/3b.py 分段跑（每段自带起跑线）。

起跑线：平台**不复位、也不检查**，只在运行输出里提示一行 —— 跑之前请自行复位。

两条实战约束（2026-09-23 实测，写在这里免得下次再踩）：
  1. **工程被判「有未导入的外部改动」时，find_gameobjects / manage_components 那一批
     工具会被平台闸门拦下**（防域重载）。于是 u.exists / u.object_text / u.expect_text
     全部失效 —— 用例会在第一步就炸成"环境错误"。本脚本改用 execute_code 通道
     （cs_present / cs_text）做存在性与文本判断，所以"工程脏"也能跑。
  2. 录制回放里"多点了几下"的地方（推进对话、连点修炼、地图上多点两下）次数跟录制
     当时的节奏有关，多点的那些用 tap_opt：在就点，不在就跳过并打印一行，不算失败；
     真正卡流程的入口（开地图、选任务、确认升级…）仍然用 tap 严格等 + 失败即停。

世界地图这一步要单独说（2026-09-23 实测定位 + 已解决，是流程2 最容易卡的地方）：
  * `map_content` 是 9353x15125 的滚动区，**中心点在屏幕外**，而 `u.click` 是把对象世界
    坐标当屏幕坐标用的（unity_bridge.cs_click）。所以"点地图"实际等于点了个空气 ——
    录制回放里那几十下 `tap_opt(map_content)` 就是这么点空的（每下还白等 8s）。
  * **地图初始全迷雾**：模型里 215 个格，但 UI 格子控件数 `cells=0` —— 必须先在**屏幕
    坐标**上点一个可探索格把迷雾探开，主线才走得下去（引导文案 60004「神识外放探查迷雾」
    → 57004「继续探查」就是"去点地图"的提示）。
  * **别照引导标记点**：`guide` 被 `UIMapWindow:update_guide_position` 摆在目标格
    **+110px**（`GUID_OFFSET_Y`，UIMapWindow.lua:821），照它点会高 110px → 点不中。
    要用格子自己的 `world_pos` 换算（`WorldMapD`/`entity.world_pos` +
    `RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, ...)`）—— 实测把算出的
    坐标喂回游戏的 `ScreenToWorldPoint`+`WorldPos2GridPos` 能还原出同一个格 id。
  * **引导格未必可探索**：57004 的 `reach_explore_condition=true` 但
    `is_cell_can_explore=false`，点它十次都不推进；要按 `is_cell_can_explore` **挑格**
    （实测可探索的是 58003/58004/59002，就是屏幕上那几个带黄边的深色菱形）。
  * **判据用语义状态，别用控件数**：普通地块**不建 UI 控件**（`is_show_ui_widget=false`，
    走 3D 层），所以"探雾成功"之后 `cells` 仍可能是 0。判"地图能用了"要看
    `canExplore / visEnt / 目标格是否可点`（`map_state()` / `cell_info()`）。
  * 落地成基元：`map_open_until([goal])`（探雾到能走主线为止）、`map_click_cell(id[, sub])`
    （控件优先 + 坐标兜底）、`map_tap_explore()`（录制里"点空地"的替代）、`map_drag()`。
  * 别拿 `WorldMapWindow.ui_click_empty` 判成败 —— 实测它 `true` 时对话窗照样弹出来
    （那是"点了空地"的标记，不是"没点中"）。成不成看效果。
"""
import time

try:  # execute_code 通道的 C# 片段（平台内置助手，与本脚本同机，直接复用）
    from src.app.services.unity_bridge import cs_present, cs_text
except Exception:  # noqa: BLE001 —— 拿不到就退回层级读取（慢一点，但可用）
    cs_present = None
    cs_text = None

# 起跑线（需人工复位）：启动界面 BootWindow；新号流程由本用例自己完成"登出→注册→创角→启程"
RESET = {"scene": "Assets/Scenes/main.unity",
         "wait_for": "GameRoot/Canvas2D/Normal/BootWindow(Clone)"}

# ---------------------------------------------------------------- 常用路径
TASK_OPT = "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click"
TASK_MASK = "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask"
DIALOG_BG = "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg"
BUBBLE = "GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full"
MAP_CONTENT = "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content"
HOUSE_MAP = "GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map"
SCROLL_TEXT = "GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)"
XIULIAN = "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)"
XIULIAN_UP = XIULIAN + "/XiulianLevelUpWindow(Clone)/btn_close"
# 修炼界面的**真**操作按钮（2026-09-23 定位）：
#   录制稿把"吐纳"记成了 `trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)`
#   —— 那是**拖拽监听区**（只有 Image+Button+UIPointerPass/UIDragPass），点它不触发吐纳
#   （实测连点 25 下，进度条仍 "再吐纳10次"，计数纹丝不动）。
#   真正的按钮是 `adapter/CommonFrame/content/center_btns/panel_btns/btn_tuna_gen_ball`
#   （XiuLianWidget.lua:15 绑定 → on_clicked_btn_tuna_gen_ball → AshramD.send_gen_exp_ball）。
#   实测点 3 下：计数 "再吐纳10次" → "再吐纳8次"（按钮点够次数后自己隐藏）。
TUNA_BTN = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
            "center_btns/panel_btns/btn_tuna_gen_ball")
XIU_LIAN_BTN = XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)"
# 聚灵界面的操作区：**滑动**触发（JuLingWidget.lua:356 listen_drag_on_panel → drag_func），
# 所以聚灵要用 `drag_on(JU_LING_BTN)` 而不是点击。`PanelBg(Clone)(Clone)` 是拖拽监听区，
# 对聚灵来说是**正确**的落点（对吐纳则是错的 —— 见 TUNA_BTN 的注释）。
JU_LING_BTN = XIULIAN + "/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)"
DANYAO_BTN = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
              "panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
DRUG_ROOT = (XIULIAN + "/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/"
             "xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item")
DRUG_1 = DRUG_ROOT + "(1)/item/img_icon/raycast"
DRUG_2 = DRUG_ROOT + "(2)/item/img_icon/raycast"
XIULIAN_BACK = XIULIAN + "/adapter/go_back/btn_back"
GANG_ROOM = "GameRoot/Canvas2D/Back/GangRoomWindow(Clone)"
JU_LING_TA = "GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)"
RESULT_CLOSE = "GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg"


