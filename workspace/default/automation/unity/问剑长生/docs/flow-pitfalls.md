# flow-pitfalls

> 新手流程 2 的四个真坑与修法（已修在 lib/ 里，改之前先看为什么这么写）。
>
> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。

- **2026-09-23 17:33** · 领域知识 · _agent_

  **问剑长生（Unity）新手流程2 的四个真坑 —— 2026-09-23 实测定位（都改在 flow_header.py / build_flow.py 里了）**
  
  1. **世界地图「全迷雾」不是 bug，是流程**：进图 `cells=0 / visEnt=0 / canExplore=N`（普通地块走 3D 层、**不建 UI 控件**），屏幕上那几个带黄边的深色菱形就是可探索格。必须按**真实屏幕坐标**点可探索格把迷雾探开（每次只推进一格，引导文案 60004「神识外放探查迷雾」→ 57004「继续探查」→「驱逐拦路妖兽」）。
     - 判据要用**语义状态**（`canExplore>0` / `visEnt>0`），**不要等"格子控件数"** —— 上一版 `map_ready` 等控件数，白等 120s 还误报"迷雾没探开"，实际迷雾早散了。
     - **引导格未必可探索**（57004 `reachCond=true` 但 `canExplore=false`），别照着 guide 点；用 `pick_explore_cell()` 挑。
     - **别拿 guide 标记的屏幕坐标去点**：它被摆在目标格 +`GUID_OFFSET_Y(=110)`（UIMapWindow.lua:821），照它点会高 110px → `click_position` 返回 false、迷雾不散。要用格子自己的 `world_pos` 换算（`RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, e.world_pos)`，实测反查能回到同一个格 id）。
     - **事件会被悬浮提示层吃掉**：地图格坐标上 RaycastAll 的最上层常是 `adapter/HoverTipWidget(Clone)/.../text_content`，事件到不了 `map_content`。要把 down/up/click **直接 Execute 到 map_content**。
     - 服务端确认有延迟：点探雾后 `canExplore` 可能几分钟后才变（Console 里认证服 5002 连不上时更久），别以为没生效。
  
  2. **修炼界面的「吐纳」和「聚灵」是两套机制，录制稿都记错了**：
     - 吐纳 = **点** `XiuLianWidget(Clone)/adapter/CommonFrame/content/center_btns/panel_btns/btn_tuna_gen_ball`（XiuLianWidget.lua:15 → `on_clicked_btn_tuna_gen_ball` → `AshramD.send_gen_exp_ball`）。录制稿记的 `adapter/drag_parent/PanelBg(Clone)(Clone)` 是**拖拽监听区**，点它完全不生效（连点 25 下、计数纹丝不动）。按钮**条件显示**：`tuna_count < begin_auto_bron_exp_balls_value(=10) && can_tuna_gen_exp()`，点够/修为满就自己隐藏。
     - 聚灵/吸灵气球 = **滑动**（`JuLingWidget.lua:356` / `XiuLianWidget.lua:423` 的 `listen_drag_on_panel` → `drag_func` / `check_click_balls`），点没用，必须滑过去。
  
  3. **屏幕坐标换算必须用 Canvas 的 worldCamera**：这个工程 UI 是 `ScreenSpaceCamera`，`RectTransformUtility.WorldToScreenPoint(null, …)` 会算出 **-1000 附近的负数**（手势落到屏幕外）。要用 `GetComponentInParent<Canvas>().worldCamera`（退化才用 `Camera.main`）。
  
  4. **录制稿的三类"看起来对、回放是空的"操作**（组装器已自动改写）：
     - `tap_opt(MAP_CONTENT)` ×几十下（点空地走位）→ `map_tap_explore()`（按可探索格真实坐标点，没有就跳过）；
     - `u.drag(X, X)` 起终点同一对象（位移 0）→ `map_drag()` 或跳过；
     - 连续 N 次剧情点击（按录制节奏记的）→ `advance_story()`（点到剧情节点消失为止）。
     **注意 `advance_story` 不能写成"target 一可见就返回"** —— `advance_story(XIU_LIAN_BTN)` 里该控件在修炼界面上一直可见，会 0 下就"成功"返回，后面等任务窗直接超时。
  
  另：`map_click_cell()` 返回**布尔**，不能套进 `tap(...)`（会变成 `wait_visible(True)` → 报 "True 未显示" 白等 45s），必须裸调用。
