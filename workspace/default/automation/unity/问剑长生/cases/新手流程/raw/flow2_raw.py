# 起跑线（人工复位）：场景=Assets/Scenes/main.unity；标志物=GameRoot
#   平台不复位、也不检查起跑线：跑之前请自行把游戏恢复成上面这个状态
# 手动录制生成：新手流程2（录制）（2026-09-22T16:55:34）
# 录制的是操作轨迹；断言由平台自动播种（标 [自动播种]），跑一遍验证后再改成用例。
# 回放前请自行确认起跑线（平台不复位、不检查）。

RESET = {"scene": "Assets/Scenes/main.unity", "wait_for": "GameRoot"}

u.expect_exists("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click", timeout=10)  # [自动播种]  # 寻找道院
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 1.7s）
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(57004)/detail/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(57004)/detail/bg")
u.expect_exists("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/dialog/bg_big_dialog/panel_not_layout/info_player/player_hor", timeout=10)  # [自动播种]  # 我
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/dialog/bg_big_dialog/panel_not_layout/info_player/player_hor")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask", "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 33.5s）
u.expect_exists("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)/btn_continune", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)/btn_continune")  # Button
u.click("GameRoot/Canvas2D/Normal/ScrollTextWindow(Clone)/btn_continune")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
# （人工停顿 4.4s）
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 2.2s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.drag("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreTempleItem_new(Clone)(神秘洞府)(55008)/normal/bg_name", "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 1.6s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 3.9s）
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
# （人工停顿 13.0s）
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(53010)/detail/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(53010)/detail/bg")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour", timeout=10)  # [自动播种]  # 灌注
灵气
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text", timeout=10)  # [自动播种]  # 灌注
灵气
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 2.3s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(50010)/go_info/bg_threat", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(50010)/go_info/bg_threat")
u.expect_exists("GameRoot/Canvas2D/Normal/SeaEnterWindow(Clone)/adapter/content/desc/layout/btn_changlle", timeout=10)  # [自动播种]  # 挑战
u.click("GameRoot/Canvas2D/Normal/SeaEnterWindow(Clone)/adapter/content/desc/layout/btn_changlle")
# （人工停顿 13.0s）
u.expect_exists("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg")  # Button
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
# （人工停顿 3.5s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(53010)(地块)(46011)(地块)(46011)/normal/bg_name/name", timeout=10)  # [自动播种]  # 遗落包袱
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(53010)(地块)(46011)(地块)(46011)/normal/bg_name/name")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour")  # Button
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/bottom_panel/fill_lingqi_panel/btn_pour/text")
u.expect_exists("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/CommonTabsWidget_V2(Clone)/back/btn_back/raycast", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/CommonTabsWidget_V2(Clone)/back/btn_back/raycast")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 17.3s）
u.expect_exists("GameRoot/Canvas2D/Top/BlackBGWindow(Clone)/black_bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Top/BlackBGWindow(Clone)/black_bg")
u.click("GameRoot/Canvas2D/Top/BlackBGWindow(Clone)/black_bg")
# （人工停顿 3.0s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
# （人工停顿 1.9s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
# （人工停顿 1.5s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map")
u.drag("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/wild/bg_normal/img", "GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/wild/bg_normal/img")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 1.5s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(46013)/detail/bg_unlock", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(46013)/detail/bg_unlock")
u.expect_exists("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1", timeout=10)  # [自动播种]  # 破除
u.click("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRewardItem_new(Clone)(发光的石头)(45016)/normal/bg_name/name", timeout=10)  # [自动播种]  # 发光的石头
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRewardItem_new(Clone)(发光的石头)(45016)/normal/bg_name/name")
u.expect_exists("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1", timeout=10)  # [自动播种]  # 开采
u.click("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/神秘罗盘_40031_N4003112002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/gua_panel/gua_content/item_1/process_des/txt_num", timeout=10)  # [自动播种]  # <color=#FFFFFF>0</color>/6
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureWindow(Clone)/adapter/root/DestinyTreasureWidget(Clone)/adapter/gua_panel/gua_content/item_1/process_des/txt_num")
u.expect_exists("GameRoot/Canvas2D/Normal/DestinyTreasureDetailWindow(Clone)/adapter/bottom_panel/btn_repair/btn_repair_text", timeout=10)  # [自动播种]  # 修复
u.click("GameRoot/Canvas2D/Normal/DestinyTreasureDetailWindow(Clone)/adapter/bottom_panel/btn_repair/btn_repair_text")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
# （人工停顿 2.1s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(46019)/normal/bg_name/name", timeout=10)  # [自动播种]  # 白发修士
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(nil)(46019)/normal/bg_name/name")
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/item_option(Clone)/btn_click/panel_normal", timeout=10)  # [自动播种]  # 上前搭话
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/item_option(Clone)/btn_click/panel_normal")
# （人工停顿 4.1s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 2.3s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
# （人工停顿 2.4s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
u.expect_exists("GameRoot/Canvas2D/Normal/ExpUpWindow(Clone)/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ExpUpWindow(Clone)/btn_close")  # Button
# （人工停顿 3.6s）
u.expect_exists("GameRoot/Canvas2D/Top/MessageBoxWindow(Clone)/adapter/common_bg/content/btn_right/text_btn_right", timeout=10)  # [自动播种]  # 前往
u.click("GameRoot/Canvas2D/Top/MessageBoxWindow(Clone)/adapter/common_bg/content/btn_right/text_btn_right")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.4s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text", timeout=10)  # [自动播种]  # 丹药
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(2)/item/img_icon/raycast", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(2)/item/img_icon/raycast")
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport", timeout=10)  # [自动播种]  # <color=#84a4d8><size=44>炼</size>气</color>
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.1s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.2s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 3.0s）
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des", timeout=10)  # [自动播种]  # 前往道院
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
# （人工停顿 2.1s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
# （人工停顿 2.0s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
# （人工停顿 2.6s）
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRewardItem_new(Clone)(废弃洞府)(40026)/detail/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRewardItem_new(Clone)(废弃洞府)(40026)/detail/bg")
u.expect_exists("GameRoot/Canvas2D/Normal/OptionWindow(Clone)/adapter/content/desc/btn_content/btn(1)/text", timeout=10)  # [自动播种]  # 探查一番
u.click("GameRoot/Canvas2D/Normal/OptionWindow(Clone)/adapter/content/desc/btn_content/btn(1)/text")
# （人工停顿 1.8s）
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(38028)/go_info/bg_threat", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(38028)/go_info/bg_threat")
u.click("GameRoot/Canvas2D/Normal/SeaEnterWindow(Clone)/adapter/content/desc/layout/btn_changlle")
# （人工停顿 8.7s）
u.click("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg")  # Button
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(36030)/detail/bg_unlock", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(36030)/detail/bg_unlock")
u.click("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1/text_commit1")
# （人工停顿 19.8s）
u.expect_exists("GameRoot/Canvas2D/Normal/SelectGangWindow(Clone)/adapter/btn_select", timeout=10)  # [自动播种]  # 加入道院
u.click("GameRoot/Canvas2D/Normal/SelectGangWindow(Clone)/adapter/btn_select")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskConsumeWindow(Clone)/CommonSmallWindow/content/root/btn_all/btn_right/text", timeout=10)  # [自动播种]  # 确定
u.click("GameRoot/Canvas2D/Normal/TaskConsumeWindow(Clone)/CommonSmallWindow/content/root/btn_all/btn_right/text")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/传功弟子_44401_N0000AAC6EB0B0000/click", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/传功弟子_44401_N0000AAC6EB0B0000/click")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_choose/sect_zhenwu/name_text", timeout=10)  # [自动播种]  # 真武
u.click("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_choose/sect_zhenwu/name_text")
u.expect_exists("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_single/btn_join/text_select", timeout=10)  # [自动播种]  # 拜入
u.click("GameRoot/Canvas2D/Normal/DaoyuanSectWindow(Clone)/adapter/sect_single/btn_join/text_select")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 1.5s）
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/传功弟子_44401_N0000AAC6EB0B0000/click")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/text_level_name", timeout=10)  # [自动播种]  # <color=#9bb6d8><size=36>炼</size>气</color>
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/text_level_name")
u.expect_exists("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/part_room_grade/btn_speed_up/text_ashram_house", timeout=10)  # [自动播种]  # <color=#D8F2F8>一阶洞府</color>
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/part_room_grade/btn_speed_up/text_ashram_house")
u.expect_exists("GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update", timeout=10)  # [自动播种]  # 升级
u.click("GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 1.9s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 1.6s）
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main", timeout=10)  # [自动播种]  # 主线
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/传功弟子_44401_N0000AAC6EB0B0000/click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/NormalGetNewWindow(Clone)/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/NormalGetNewWindow(Clone)/btn_close")  # Button
# （人工停顿 1.7s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(2)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.1s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content", timeout=10)  # [自动播种]  # 修炼至炼气7层
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(1)/img_icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(1)/img_icon")
u.click("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(43030)/detail/bg_unlock", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreJinZhiItem_new(Clone)(神秘禁制)(43030)/detail/bg_unlock")
u.click("GameRoot/Canvas2D/Normal/SimpleDialogWindow(Clone)/adapter/content/desc/btn_commit1")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 1.9s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.drag("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.drag("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreMonsterItem_new(Clone)(妖兽)(44034)/go_info/name")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.drag("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content", "GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreTempleItem_new(Clone)(十万灵山)(47038)/normal/bg_name/name", timeout=10)  # [自动播种]  # 十万灵山
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreTempleItem_new(Clone)(十万灵山)(47038)/normal/bg_name/name")
u.expect_exists("GameRoot/Canvas2D/Normal/TempleInfoWindowExplore(Clone)/adapter/content/desc/btn_layout/btn_enter/text_enter", timeout=10)  # [自动播种]  # 进入秘境
u.click("GameRoot/Canvas2D/Normal/TempleInfoWindowExplore(Clone)/adapter/content/desc/btn_layout/btn_enter/text_enter")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/map_sv/Viewport/map_content/icon_root/monster_root/normal_monster(Clone)/icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/map_sv/Viewport/map_content/icon_root/monster_root/normal_monster(Clone)/icon")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/shown_area/btn_enter/go_enter/txt", timeout=10)  # [自动播种]  # 进入
u.click("GameRoot/Canvas2D/Normal/NormalTransportMapWindow(Clone)/shown_area/btn_enter/go_enter/txt")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 16.1s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_quality", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_quality")
u.click("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3097400/btn_challenge/text", timeout=10)  # [自动播种]  # 领取
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3097400/btn_challenge/text")
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/challenge_top/slider_root/reward_box_root/reward_box(Clone)/icon_canget/bg/bg_2", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/challenge_top/slider_root/reward_box_root/reward_box(Clone)/icon_canget/bg/bg_2")
u.expect_exists("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Battle/MainWindow(Clone)/widget_panel/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des/complete_team", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Battle/MainWindow(Clone)/widget_panel/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des/complete_team")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/normal_condition/btn_level_up/text", timeout=10)  # [自动播种]  # 晋升
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/normal_condition/btn_level_up/text")
u.expect_exists("GameRoot/Canvas2D/Normal/GangDutyImproveWindow(Clone)/root/btn_mask", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/GangDutyImproveWindow(Clone)/root/btn_mask")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/GongfaCompositeWindow(Clone)/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/GongfaCompositeWindow(Clone)/bg")  # Button
# （人工停顿 3.6s）
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/bg_content/jihuo_root/condition_item2/text_condition", timeout=10)  # [自动播种]  # 达到筑基中期(<color=#a63a3a>0</color>/1)
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/DiweiWidget(Clone)/bg_content/jihuo_root/condition_item2/text_condition")
# （人工停顿 1.9s）
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 1.7s）
u.expect_exists("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des", timeout=10)  # [自动播种]  # 外院晋升
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/gongfa/txt", timeout=10)  # [自动播种]  # 功法
u.click("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/gongfa/txt")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/equip_panel/btn_equip/select/text", timeout=10)  # [自动播种]  # 装配
u.click("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/equip_panel/btn_equip/select/text")
u.expect_exists("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/skill_overview/main_panel/viewport/content/ceng-2351368/list/shentong_equip(Clone)/gongfa_item/item/cilck", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/skill_overview/main_panel/viewport/content/ceng-2351368/list/shentong_equip(Clone)/gongfa_item/item/cilck")
u.expect_exists("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/btn_equip_back", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/GongfaRoomWindow(Clone)/simple_content/shentong/main_panel/panel/btn_equip_back")  # Button
# （人工停顿 2.9s）
u.expect_exists("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/house/bg_normal/img", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/house/bg_normal/img")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(2)/img_icon")
u.click("GameRoot/Canvas2D/Normal/ItemInfoSimpleWindow(Clone)/adapter/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 1.7s）
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 7.1s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 4.5s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_xiulian/unselect/icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_xiulian/unselect/icon")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/part_room_grade/btn_speed_up/text_ashram_house")
u.click("GameRoot/Canvas2D/Normal/RoomImproveWindow(Clone)/adapter/CommonMidWindow/content/btn_update")  # Button
u.click("GameRoot/Canvas2D/Normal/AshramHouseLevelUpWindow(Clone)/btn_close")  # Button
# （人工停顿 2.9s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.2s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/传功弟子_44401_N0000AAC6EB0B0000/click")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/ChatWindow(Clone)/sv/Viewport", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/ChatWindow(Clone)/sv/Viewport")
u.expect_exists("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/adapter/content/adapter1/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/adapter/content/adapter1/bg")
u.expect_exists("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/FullChatWindow(Clone)/btn_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/pos/root_ziwei_treasure/recharge_item(Clone)/btn_click/icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/pos/root_ziwei_treasure/recharge_item(Clone)/btn_click/icon")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn", timeout=10)  # [自动播种]  # 精选特惠
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
# （人工停顿 2.2s）
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/btn_speical_free/speical_icon/CommonGetBoxReward/bg/bg_2", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/btn_speical_free/speical_icon/CommonGetBoxReward/bg/bg_2")
u.click("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn", timeout=10)  # [自动播种]  # 日礼包
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy", timeout=10)  # [自动播种]  # 领取
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy")  # Button
u.click("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
# （人工停顿 2.2s）
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy")  # Button
# （人工停顿 2.0s）
u.expect_exists("GameRoot/Canvas2D/Normal/RechargeConfirmWindow(Clone)/adapter/common_bg/content/btn_left/text_btn_left", timeout=10)  # [自动播种]  # 取消
u.click("GameRoot/Canvas2D/Normal/RechargeConfirmWindow(Clone)/adapter/common_bg/content/btn_left/text_btn_left")
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn", timeout=10)  # [自动播种]  # 周礼包
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy/btn_buy_txt", timeout=10)  # [自动播种]  # 领取
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/btn_state_ctrl/btn_buy/btn_buy_txt")
u.click("GameRoot/Canvas2D/Normal/GetItemsEffectWindow(Clone)/btn_bg_close")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_6/btn", timeout=10)  # [自动播种]  # 玲珑阁
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_6/btn")  # Button
u.drag("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/gift_money_panel/text_other_reward", "GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/Content/shop_item(Clone)/gift_money_panel/bg_first/text", "GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/top_panel/top_tab_root/bg_layout/TabBtn(Clone)/click/text", timeout=10)  # [自动播种]  # 仙元
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/top_panel/top_tab_root/bg_layout/TabBtn(Clone)/click/text")
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/top_panel/top_tab_root/bg_layout/TabBtn(Clone)/click/text")
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_1/btn", timeout=10)  # [自动播种]  # 双卡
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_1/btn")  # Button
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_2/btn")  # Button
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_4/btn")  # Button
# （人工停顿 2.1s）
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/left_tab_panel/tab_5/btn")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/reward/content/sv/viewport/content/reward_item(Clone)/img_icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/reward/content/sv/viewport/content/reward_item(Clone)/img_icon")
u.expect_exists("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
u.click("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
u.click("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
u.click("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/content/bottom_content/sv/Viewport/content/bg_reward/panel_probability_reward/content_probability/probability_item_go(Clone)/reward_item/img_icon")
# （人工停顿 1.7s）
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
# （人工停顿 2.0s）
u.expect_exists("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/ItemInfoDetailWindow(Clone)/adapter/btn_close")  # Button
# （人工停顿 1.9s）
u.expect_exists("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/btn/btn_enter/text_btn_enter", timeout=10)  # [自动播种]  # 进入
u.click("GameRoot/Canvas2D/Normal/ZiweiTreasuryExternalWindow(Clone)/panel/content/bottom_panel/shop_content/right_panel/sv/viewport/content/group_item/item_enter_server_week_gift/btn/btn_enter/text_btn_enter")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.drag("GameRoot/Canvas2D/Normal/ServerWeekGiftWindow(Clone)/adapter/content/gift_sv/Viewport/content_gift/gift_item(Clone)/bg/gift_base_panel/reward_content/reward_item(Clone)/img_icon", "GameRoot/Canvas2D/Normal/ServerWeekGiftWindow(Clone)/adapter/content/gift_sv/Viewport")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.key("escape")  # 键盘合成尽力而为（实测常不生效）；失败就改用可点路径
# （人工停顿 6.2s）
u.drag("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content", "GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/content_map")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.expect_exists("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content", timeout=10)  # [自动播种]  # 击败20只炼气一层以上秘境怪物
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/adapter/panel_left_top/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3238972/btn_challenge/text", timeout=10)  # [自动播种]  # 领取
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3238972/btn_challenge/text")
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Back/HudWindow(Clone)/layout/house/bg_normal/img")
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/修炼_40022_N4002212002/click")  # Button
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
u.expect_exists("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_quality", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_quality")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
# （人工停顿 2.2s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/drag_parent/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 1.7s）
u.drag("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map", "GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/MapScrollView/Viewport/content_map")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 2.4s）
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content/TMP SubMeshUI [FangZhengKaiTiJianTi-1 SDF Material + FangZhengKaiTiJianTi-1 SDF Atlas 1]", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content/TMP SubMeshUI [FangZhengKaiTiJianTi-1 SDF Material + FangZhengKaiTiJianTi-1 SDF Atlas 1]")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(邪修NPC)(45044)/detail/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(邪修NPC)(45044)/detail/bg")
# （人工停顿 1.6s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.drag("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/panel_reward/bg/panel_item/sv_reward/Viewport/content_reward/item_reward(1)/img_quality", "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click", "GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 13.3s）
u.click("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/dialog/bg_big_dialog/panel_not_layout/info_player/player_hor", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 1.8s）
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(邪修NPC)(45044)(邪修NPC)(45044)(邪修NPC)(44052)/detail/bg", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/cellitem_root/WorldExploreItemWidget_new(Clone)/WorldExploreRoleItem_new(Clone)(邪修NPC)(45044)(邪修NPC)(45044)(邪修NPC)(44052)/detail/bg")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.drag("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg", "GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/bg_mask")
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 14.8s）
u.click("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg")  # Button
# （人工停顿 5.6s）
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/map_sv/Viewport/map_content")
u.expect_exists("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content", timeout=10)  # [自动播种]  # 向师兄汇报<color=#FF9E2B>(可接取)</color>
u.click("GameRoot/Canvas2D/Back/WorldMapWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/text_content")
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/DialogWindow(Clone)/big_root/dialog_wnd/root/click_bg")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 4.2s）
u.expect_exists("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/小比管事_44413_N0000AAC6EC090001/click", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/小比管事_44413_N0000AAC6EC090001/click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/TopMost/DialogueBubbleWindow(Clone)/click_bg_full")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_improve/text_start", timeout=10)  # [自动播种]  # 提升修为
u.click("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_improve/text_start")
u.expect_exists("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content/list_item-3414512/btn_all/text", timeout=10)  # [自动播种]  # 去服用
u.click("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content/list_item-3414512/btn_all/text")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/panel_xiulian/part_arcanum/xiuwei_miyao/icon_xiulian_danyao_rukou/text")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/XiuLianWidget(Clone)/adapter/CommonFrame/content/xiulian_drug_root/XiulianDrug(Clone)/scroll_view/Viewport/list_drug/prefab_drug_item(1)/item/img_icon/raycast")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 8.5s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
# （人工停顿 3.2s）
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 4.1s）
u.click("GameRoot/Canvas2D/Normal/XiulianLevelUpWindow(Clone)/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_back/btn_back")  # Button
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content", timeout=10)  # [自动播种]  # 击败30只炼气一层以上秘境怪物
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_not_main/text_content")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3431916/btn_challenge/text", timeout=10)  # [自动播种]  # 领取
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonFrame/content/status_main/trans_widgets/ShiLianWidget(Clone)/sv_challengeitem/Viewport/content/challengeitem-3431916/btn_challenge/text")
u.click("GameRoot/Canvas2D/Normal/JuLingTaDetailsWindow(Clone)/CommonTabsWidget_V3(Clone)/back/btn_back/raycast")
u.expect_exists("Camera3D", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessi", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 3.4s）
u.click("GameRoot/Canvas2D/Back/HouseRoomWindow(Clone)/adapter/HoverTipWidget(Clone)/root_new/panel_task/item_list_main/bg_tast_title/text_title_des")
u.click("GameRoot/Canvas2D/Back/GangRoomWindow(Clone)/MapScrollView/Viewport/小比管事_44413_N0000AAC6EC090001/click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.expect_exists("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_start/text_start", timeout=10)  # [自动播种]  # 参加比试
u.click("GameRoot/Canvas2D/Normal/GangBattleSelectInfoWindow(Clone)/adapter/CommonFrame/content/bottom/layout/btn_start/text_start")
# （人工停顿 14.3s）
u.expect_exists("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next", timeout=10)  # [自动播种]  # 参战
u.click("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 38.2s）
u.click("GameRoot/Canvas2D/Normal/CommonResultWindow(Clone)/btn_close_bg")  # Button
# （人工停顿 9.7s）
u.click("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 42.0s）
u.click("GameRoot/Canvas2D/Normal/GangSelectBattleWindow(Clone)/adapter/CommonFrame/content/btn_next/text_btn_next")
# （人工停顿 49.7s）
u.expect_exists("GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)/adapter/content/btn_close", timeout=10)  # [自动播种]
u.click("GameRoot/Canvas2D/Normal/GangBattleResultWindow(Clone)/adapter/content/btn_close")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
u.click("GameRoot/Canvas2D/Normal/TaskWindow(Clone)/root/bg_big_dialog/content_option/btn_click")  # Button
# （人工停顿 2.2s）
u.expect_exists("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content/list_item-3656816/btn_all/text", timeout=10)  # [自动播种]  # 去服用
u.click("GameRoot/Canvas2D/Normal/AcquisitionCultivationWindow(Clone)/adapter/CommonBigWindow/content/sv_list/viewport/content/list_item-3656816/btn_all/text")
u.expect_exists("Dialog", timeout=10)  # [自动播种] 点击后新出现
u.expect_exists("UIModelShotProcessing", timeout=10)  # [自动播种] 点击后新出现
# （人工停顿 2.0s）
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_biguan/unselect/icon")
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # Button
# （人工停顿 9.1s）
u.drag("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)", "GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/trans_widgets/JuLingWidget(Clone)/PanelBg(Clone)(Clone)")  # 拖拽回放（录制）：如不生效，改用例里的路径或改用 exec_csharp
u.click("GameRoot/Canvas2D/Normal/XiulianMainWindow(Clone)/adapter/go_bottom_layout/btn_xiulian/unselect/icon")

print("PASS: 录制回放通过（351 次点击 / 32 次拖拽 / 0 处输入 / 5 次按键）")
