# world-map

> 世界地图/探雾/坐标换算的完整定论（改地图相关代码前必读）。
>
> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。

- **2026-09-23 04:15** · 领域知识 · _agent_

  **问剑长生：世界地图（WorldMapWindow）自动化的硬约束（2026-09-23 定位）**
  
  根因：`map_content` 是 **9353x15125** 的滚动区，`lossyScale=0.104`，**中心点在屏幕外**。
  而平台的 `u.click` 把对象世界坐标当屏幕坐标用（unity_bridge.py:820-822 `GetWorldCorners`→取中心），
  所以 `u.click(MAP_CONTENT)` 实际点在屏幕外 = **点了个空气**。
  
  - 地图点击的真处理器是 `WorldMapWindow:on_ui_click`（WorldMapWindow.lua:122，注册在 UIMapWindow.lua:205），
    它用**点击坐标**反算目标格 → 空地点击必须给真实屏幕坐标才能工作。
  - **录制器只对拖拽记坐标，点击不记**（unity_recorder.py:411-420 的 `from_x/from_y` 只在 drag 分支）
    → 录制回放里的地图空地点击**原理上不可复现**。这是流程2 最容易卡的地方。
  - 地图格子是"滚到哪、建到哪"，进图后要等一拍才出现；录制稿把格子写成全路径
    （`.../WorldExploreRoleItem_new(Clone)(nil)(57004)/detail/bg`），格子没建出来就白等到超时。
  - **可行做法**：进图先等格子建出来，再**按 id 找那个格子控件并点它** —— 实测点 `57004` 的
    `detail/bg` 正常弹出了「神秘妖王」对话窗（格子控件 activeInHierarchy=true，即它在屏外也能被
    `ExecuteEvents` 点到）。语义是"点这个目标格"，不依赖坐标。
  
  **附：Lua 通道可用**（比坐标试探可靠得多）——`LuaManager.GetState()` → `LuaState`，
  `DoString(lua, chunk)` 注入 + `Item["__probe"]` 索引器读回（注意 `GetMethod` 会撞重载歧义，
  要自己遍历 `GetMethods` 挑 `(string,string)` 那个）。用它查到：房间 12100、`block_touch=nil`、
  `all_visible_entities={57004}`、`WorldMapD/GridMapD/UIMapD/GuideD` 都是全局表。


- **2026-09-23 10:25** · 领域知识 · _agent_

  **问剑长生：世界地图「全迷雾」是流程2 卡死的真因（2026-09-23 实测定论）**
  
  实测数据（房间 12100，进图瞬间）：
  - `UIMapD.entities_func(world, 12100)` = **215 个格子**（地图数据是加载好的）
  - 但 `showUI=0` / `show3d=4` / `all_cells=0` / `cellitem_root` 下**一个格子控件都没有**
    → 地图**初始全迷雾**，必须先"点地图上的可探索格"把迷雾探开，格子才会建出来。
  - 引导文本「神识外放探查迷雾」= `guide_map.lua:25`（`I18n_ID_25534`，`bind_task=Lianqi_1_0`,
    `pos=60004`）—— **这行字就是"请去点地图"的提示**，不是 bug。
  - `GridMapD.is_cell_can_explore` 依赖 `is_cell_around_unlock`（周围已解锁）；引导格 60004
    在 `canVisit=true` 时可点，但**直接调 `WorldMapD.click_position(12100, 60004)` 返回 false**
    —— 因为它少了 `WorldMapWindow:on_ui_click` 里那一步
    `WorldMapEntityD.get_near_vaild_cell(world_pos, position, class_id)`（找最近的有效格）。
    **结论：必须走"真实屏幕坐标点击"，不能走直接调业务接口。**
  
  **怎么拿到"该点哪"的屏幕坐标**：`WorldMapWindow/guide` 这个标记由
  `UIMapWindow:update_guide_position` 摆在**目标格**的位置上 → 取它的屏幕坐标就是要点的位置。
  滚动到目标格用 `w:scroll_to_position(pos, false, true)`（`UIMapWindow.lua:691`）。
  实测 `scroll_to_position(60004)` 后 guide 屏幕坐标 = (320,1106)，在 1080x1920 内。
  
  **平台侧的限制（补全这一环需要改平台）**：`u.click` 把对象世界坐标当屏幕坐标用
  （unity_bridge.py:820-822），而 `map_content` 是 9353x15125、中心点在屏幕外 → 点它等于点空气；
  且**录制器只对拖拽记坐标、点击不记**（unity_recorder.py:411-420）。所以"点地图"在回放里
  只能靠"按 id 找格子控件点它"（格子建出来后可行）或"在屏幕坐标派发点击"（本脚本 map_ready 里做的）。


- **2026-09-23 16:38** · 领域知识 · _agent_

  **问剑长生「世界地图」自动化：探雾/点格的真解（2026-09-23 实测定论，推翻此前"未解的一环"）**
  
  流程2 卡死在「寻找道院」进地图这一步，真因有三层，全部已修进工作区 `flow_header.py` 的基元层：
  
  1. **地图初始全迷雾，必须先在屏幕坐标上点「可探索格」**：模型里 215 个格，但 `cells=0`（无 UI 控件）。引导文案 60004「神识外放探查迷雾」→ 57004「继续探查」就是"去点地图"的提示。实测点一次 58004 后：`guide` 清空、`visEnt=1`、出现「驱逐拦路妖兽」+ 神秘妖王 NPC。
  2. **不能照引导标记点**：`guide` 被 `UIMapWindow:update_guide_position` 摆在目标格 **+110px**（`GUID_OFFSET_Y`，UIMapWindow.lua:821），照它点会高 110px 点不中。要用格子自己的 `entity.world_pos` + `RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, ...)`（实测把结果喂回游戏的 `ScreenToWorldPoint`+`WorldPos2GridPos` 能还原同一个格 id）。
  3. **引导格未必可探索**：57004 `reach_explore_condition=true` 但 `is_cell_can_explore=false`，点它十次都不推进；要按 `is_cell_can_explore` 挑格（实测可探索的是 58003/58004/59002，即屏幕上那几个黄边深色菱形）。
  
  另两条判据级教训：
  - **别用"格子控件数"判地图好了没**：普通地块 `is_show_ui_widget=false`（走 3D 层），探雾成功后 `cells` 仍可能是 0 → 旧 `map_ready` 白等 120s 还误报"迷雾没探开"（实际迷雾早散了）。判据用语义状态：`canExplore` / `visEnt` / 目标格是否可点。
  - **别用 `WorldMapWindow.ui_click_empty` 判点击成败**：实测它 `true` 时对话窗照样弹出来（那是"点了空地"的标记）。
  
  新增基元：`map_open_until([goal])`、`map_click_cell(id[,sub])`（控件优先+坐标兜底）、`map_tap_explore()`、`map_drag()`、`map_state()`、`cell_info(pos)`、`pick_explore_cell()`、`lua(code, tag)`（Lua 通道）。
  
  **Lua 通道回传别用 JSON**：C# 侧为了把结果塞进 JSON 字符串会把引号换成单引号（`.Replace("\"", "'")`），JSON 解析必然失败、看起来像"没拿到坐标"。改用 `k=v|k=v` 纯文本（`_parse_kv`）。另：`_parse_kv` 必须把 `"true"/"false"` 转成 Python 布尔 —— `bool("false") is True` 的坑让 goal 判定误判成"已就绪"，探雾一次都没点就报成功。
  
  **`UIMapD.entities_func` 返回的是数组**：`for k, e in pairs(all)` 里的 `k` 是下标（1..215）不是格 id，格 id 要用 `e.position`。踩过一次，打出一堆 101/103 的假格号。


- **2026-09-23 16:59** · 领域知识 · _agent_

  **问剑长生：世界地图「探雾」的完整真相与修法（2026-09-23 实测定论，修正此前条目）**
  
  此前的条目说"必须走真实屏幕坐标点击"是对的，但还差三件关键事，缺一个都点不通：
  
  1. **要挑「可探索格」，不能照 guide 标记点。** 引导格本身未必可探索：实测 57004
     `reach_explore_condition=true` 但 `canExplore=false`，点它十次都不推进。
     正确做法：遍历 `UIMapD.entities_func(ui_map_type, room_id)`，挑
     `GridMapD.is_cell_can_explore(room_id, pos)` 为真的格（优先屏内、靠近屏幕中心）。
     实测初始全迷雾时 `canExplore=3`（58003/58004/59002），屏幕上就是那 3 个带黄边的深色菱形。
  2. **事件要直接派发给 map_content，不能走 RaycastAll 的最上层命中。** 地图格坐标上常被
     `WorldMapWindow(Clone)/adapter/HoverTipWidget(Clone)/.../text_content` 盖住，事件被提示层
     吃掉 → `on_ui_click` 收不到、探雾静默失败（实测 `top=text_content`，换成直接 Execute 到
     map_content 立刻生效）。
  3. **判定"地图好了没"要看语义状态，不是格子控件数。** `UIMapCellUIWidget:refresh_visible_cells`
     只给 `cell.is_show_ui_widget` 的格建控件（NPC/妖兽），**普通地块走 3D 层**（is_show_3d_widget）
     → 探雾成功后 `cells` 仍可能是 0。按控件数等会白等 120s 并误报"迷雾没探开"（实际迷雾早散了）。
     可靠判据：`canExplore>0` / `visEnt>0` / 目标格 `cell_info(pos).clickable`。
  
  另外两条：
  * **别用 `WorldMapWindow.ui_click_empty` 判成败** —— 它 true 时对话窗照样弹出（它是"点了空地"
    的标记，不是"没点中"）。成不成看效果：对话窗出现 / 引导推进。
  * **探雾每次只推进一格**（60004「神识外放探查迷雾」→ 57004「继续探查」），要循环点到目标格可点为止。
  
  已落地成基元（工作区 flow_header.py）：`map_state()` / `pick_explore_cell()` / `cell_info(pos)` /
  `map_open_until(goal)` / `map_click_cell(id[,sub])`（控件优先、坐标兜底）/ `map_tap_explore()` /
  `map_drag()`（录制里的 `u.drag(X,X)` 位移为 0，等于没滑）。


- **2026-09-23 17:13** · 领域知识 · _agent_

  **问剑长生：世界地图（迷雾/探雾）自动化定论（2026-09-23 实机验证）**
  
  流程2「寻找道院」卡在世界地图，根因是**四个叠加的坑**，全部已修进工作区 `flow_header.py`：
  
  1. **`map_ready` 判据错了**（最关键）：原来等"格子控件数 > 0"，但 `UIMapCellUIWidget:refresh_visible_cells` 只给 `cell.is_show_ui_widget` 的格建控件（NPC/妖兽），**普通地块走 3D 层**（`is_show_3d_widget`）。于是探雾其实早就成功、迷雾都散了，脚本还在白等 120s 并误报"迷雾没探开"。
     → 判据改成**语义状态**：`canExplore>0`（有可探索格）/ `visEnt>0`（可交互实体）/ `cells>0`，任一即可。
  2. **别拿 guide 标记的坐标去点**：`UIMapWindow:update_guide_position` 把 guide 摆在**目标格 + GUID_OFFSET_Y(=110)**（UIMapWindow.lua:821），照它点会高 110px，`WorldMapD.click_position` 拿到的是别的格 → 返回 false、迷雾不散。
     → 要用**格子自己的 `entity.world_pos`** 换算：`RectTransformUtility.WorldToScreenPoint(CAMERA.main_camera, world_pos)`（实测反查能回到同一个格 id）。注意相机是 `CAMERA.main_camera`（Camera3D），不是 `Camera.main`。
  3. **指针事件会被悬浮提示层吃掉**：在地图格坐标上 `RaycastAll` 的最上层命中常是 `adapter/HoverTipWidget(Clone)/.../text_content`，事件被它截走、`on_ui_click` 收不到（表现为点了没反应、`ui_click_empty=true`）。
     → 把 down/up/click **直接 Execute 给 map_content**（坐标仍用真实屏幕坐标）。
  4. **引导格未必可探索**：57004 的 `reach_explore_condition=true` 但 `canExplore=false`（`is_cell_around_unlock=false`），点它十次都不推进。探雾要按 `pick_explore_cell()` 挑**真正 `is_cell_can_explore` 的格**。
  
  **地图格点击要"控件优先、坐标兜底"**：特殊格（NPC/妖兽）有控件、还能点到子控件（`go_info/bg_threat`）；普通地块没控件、只能按坐标点。`map_click_cell(pos, sub)` 两条都试。
  
  **判定用效果、不要用 `ui_click_empty`**：实测它 `true` 时对话窗照样弹了出来（那是"点了空地"的标记，不是"没点中"）。
  
  **另外两个通用坑**：
  - Lua 回传通道会把结果里的 `"` 换成 `'`（C# 侧 `.Replace("\"", "'")`），**JSON 解析必失败** → 统一用 `k=v|k=v` 纯文本回传（`_parse_kv`）。这个坑表现为"探雾静默失效"，很难查。
  - `tap(map_click_cell(...))` 会把**布尔返回值**当路径 → `wait_visible(True)` 报 "True 未显示" 白等 45s。地图格那行必须**裸调用**。
  
  **环境**：本次服务器 127.0.0.1:5002（认证服）连不上，探雾的服务端确认会延迟数分钟才生效；`map_open_until` 的等待上限已放宽。

