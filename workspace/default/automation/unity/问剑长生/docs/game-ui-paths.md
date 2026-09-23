# game-ui-paths

> 问剑长生的 UI 对象路径（按流程位置整理）。改用例要点哪个控件时先查这里。
>
> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。

- **2026-09-21 22:05** · 领域知识 · _agent_

  **游戏「问剑长生」Unity 客户端 UI 对象路径（新手流程实测，2026-09-21）**

  启动界面（BootWindow）：
  - 右上角人物头像 = `GameRoot/Canvas2D/Normal/BootWindow(Clone)/panel/right_top_panel/btn_user_center`（已登录 → 打开 `UserCenterWindow(Clone)`，内有 `btn_logout`「登出」；未登录 → 打开 `AccountWindow(Clone)` 登录/注册窗）
  - 登录/注册窗 `GameRoot/Canvas2D/Normal/AccountWindow(Clone)/adapter/`：`btn_random`（随机账号，按下会同时填账号+密码）、`btn_register`（注册）、`btn_list/btn_register_and_login`（注册并登录）

  创角流程（`GameRoot/Canvas2D/Normal/CreateCharacterWindow(Clone)/root/`）：
  - `panel_select_body/btn_select`（选择角色）→ 面板切到 `face_state`（`family_panel` + `choose_life_panel` 可见）
  - 出身面板的「下一步」= `face_state/choose_life_panel/choose_shape/btn_face_next`
  - 「进入预览」= `panel_select_face/bottom/tab_root/btn_face_apply`
  - 输入角色名 = `face_state/panel_create/bottom/input_name`（上限 6 汉字/10 字符，校验提示在 `text_check_name`）
  - 「踏入仙途」= `face_state/panel_create/btn_ok`
  - 「启程」= `GameRoot/Canvas2D/Normal/GuideChooseSkipWindow(Clone)/CommonFrame/content/btn_go`（弹窗标题「请选择你的身份」）

  注：面板切换按钮的点击处理器常挂在父节点，按文字找到的 `.../text` 节点用 `unity_click` 会走 pointer-sequence，直接点父按钮更稳。注册并登录后会播放过场动画（提示「长按屏幕跳过」），动画结束才出现创角界面，别用固定 sleep 猜时长，轮询界面对象即可。


- **2026-09-22 17:08** · 领域知识 · _agent_

  **新手流程第一阶段（注册→创角→启程）完整对象路径 —— 问剑长生实测 2026-09-22**
  
  流程：点右上角头像 →（已登录则登出再点一次）→ 注册 → 随机账号 → 注册并登录 → 等过场 → 选择角色 → 下一步 → 进入预览 → 输入角色名 → 踏入仙途 → 启程。
  
  - 启动界面根：`GameRoot/Canvas2D/Normal/BootWindow(Clone)`；右上角头像 `.../panel/right_top_panel/btn_user_center`
  - 已登录 → `GameRoot/Canvas2D/Normal/UserCenterWindow(Clone)`（文本「用户中心 / 登出 / 用户名：xxx」），登出按钮 `.../btn_logout`（**登出后该窗是隐藏，不是销毁**）
  - 未登录 → `GameRoot/Canvas2D/Normal/AccountWindow(Clone)/adapter/`：`btn_list/btn_register`（注册页签）、`btn_random`（随机账号，点一下同时填账号+密码，注册页签下才可见）、`btn_list/btn_register_and_login`（注册并登录）
  - 注册并登录后**播过场动画**（本次实测约 90s，机器卡时更久）→ `GameRoot/Canvas2D/Normal/CreateCharacterWindow(Clone)`
  - 创角：`.../root/panel_select_body/btn_select`（选择角色）→ `.../root/face_state/choose_life_panel/choose_shape/btn_face_next`（下一步）→ `.../root/panel_select_face/bottom/tab_root/btn_face_apply`（进入预览，文字节点在 `.../btn_face_apply/text`）→ 命名 `.../root/face_state/panel_create/bottom/input_name`（上限 6 汉字/10 字符，计数在 `bottom` 子树里显示 "n/6"）→ `.../root/face_state/panel_create/btn_ok`（踏入仙途）
  - 踏入仙途后**服务端创角要等 1~2 分钟**（服务端需建角色）→ `GameRoot/Canvas2D/Normal/GuideChooseSkipWindow(Clone)/CommonFrame/content/btn_go`（启程；弹窗标题「请选择你的身份」，另有 btn_first/btn_experienced）
  - 启程落地：`GameRoot/Canvas2D/Normal/TaskWindow(Clone)`（主线任务）+ `ScrollTextWindow(Clone)`（开场旁白，「点击结束/点击跳过」）
  
  注意：`btn_ok` 在未满足条件时也 `interactable=true`、点击不报错但**不推进**（有 `btn_ok/img_cant_click` 灰显子节点作提示）。若点击后界面不动且 Console 无异常，先确认角色名是否真的写进了输入框。

