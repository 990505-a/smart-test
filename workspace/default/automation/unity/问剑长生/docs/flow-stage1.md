# flow-stage1

> 阶段一（注册创角启程）的实测要点与逐步验证记录。
>
> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。

- **2026-09-22 16:57** · 领域知识 · _agent_

  **问剑长生（Unity）新手流程第一阶段自动化要点（2026-09-22 实测）**
  
  流程（已验证）：BootWindow 右上角头像 `panel/right_top_panel/btn_user_center` → 已登录则 UserCenterWindow 的 `btn_logout` 登出 → 再点头像 → AccountWindow `adapter/btn_list/btn_register`（切注册页）→ `adapter/btn_random`（自动填账号+密码）→ `adapter/btn_list/btn_register_and_login` → 等过场动画结束出现 `CreateCharacterWindow(Clone)` → `root/panel_select_body/btn_select`（选择角色）→ `root/face_state/choose_life_panel/choose_shape/btn_face_next`（下一步）→ `root/panel_select_face/bottom/tab_root/btn_face_apply`（进入预览）→ 写 `root/face_state/panel_create/bottom/input_name` → `root/face_state/panel_create/btn_ok`（踏入仙途）→ `GuideChooseSkipWindow(Clone)/CommonFrame/content/btn_go`（启程）→ 落地 `TaskWindow(Clone)`（新手主界面）。
  
  坑（都实际踩过）：
  1. **角色名必须唯一**：用固定名（如"剑无痕"）会撞服务端「名字已存在，请重新输入。」（提示在 `GameRoot/Canvas2D/Top/SimpleTipWindow(Clone)/simpleTip/text_simple`），服务端拒绝创角 → 客户端**退回 AccountWindow** → 后续等 GuideChooseSkipWindow 永久超时。做法：名字带唯一后缀，且**长度 ≤ 6 字符**（`CreateNameWidget._cn_limit_len = 6`，`StrD.utf8len` 汉字算 1 字符，超限会标红/被拒）。
  2. **关窗判定用 `state="hidden"` 不是 `"absent"`**：UserCenterWindow / CreateCharacterWindow 关闭是 setActive(false)（对象仍在场景里），`wait_for(state="absent")` 会一直超时。
  3. **`wait_for` 每次调用有 ~12s 固定开销**（实测 ms=12300 且 ok=true），长流程累加会撞平台 420s 执行上限；改用 `u.exists()` + 短 sleep 的轻量轮询。`u.hierarchy()` 单次约 1s。
  4. **`u.object_text()` 在用例脚本里返回字符串**（不是 dict），不要 `.get("text")`；而工具版 `unity_object_text` 返回 dict。
  5. 点「踏入仙途」后先等 GuideChooseSkipWindow（服务端创角+加载），再点启程，不要固定 sleep。
  6. 环境侧：实测编辑器会中途掉线重连（`no_unity_session`，`connected_at` 变化）并伴随域重载 → 游戏被重置回 BootWindow，整轮用例作废，需重跑（属环境问题，非用例失败）。


- **2026-09-22 18:15** · 领域知识 · _agent_

  **问剑长生（Unity）新手流程第一阶段 2026-09-22 17:34~18:13 实跑记录（逐步验证）**
  
  本次实际是**未登录**状态：点右上角头像 `GameRoot/Canvas2D/Normal/BootWindow(Clone)/panel/right_top_panel/btn_user_center` 后直接打开 `AccountWindow(Clone)`（没有 UserCenterWindow，故跳过"退出登录"这一步）；流程步骤全部走通：
  头像 → `AccountWindow(Clone)/adapter/btn_list/btn_register`（注册）→ `adapter/btn_random`（随机账号 1790069812，同时填密码+确认密码）→ `adapter/btn_list/btn_register_and_login` → 过场动画（「星辰易位」→「再造新天」约 90s，右上「长按屏幕跳过」）→ `CreateCharacterWindow(Clone)` → `root/panel_select_body/btn_select`（选择角色）→ `root/face_state/choose_life_panel/choose_shape/btn_face_next`（下一步，出身三选一：世家子弟/江湖游侠/一方富商）→ `root/panel_select_face/bottom/tab_root/btn_face_apply`（进入预览）→ 写 `root/face_state/panel_create/bottom/input_name` → `root/face_state/panel_create/btn_ok`（踏入仙途）→ `GuideChooseSkipWindow(Clone)/CommonFrame/content/btn_go`（启程，弹窗「请选择你的身份」）。
  
  新确认的两点：
  1. **角色名 3 个中文字符「云中鹤」被服务端接受**（无重名提示、无长度标红），与"2~6 个中文字符"的要求一致；判断写入成功用读回 `TMP_InputField.text`（工具 `unity_set_text` 会返回 `written:1`），不要靠截图。
  2. **点启程后可能长时间卡在「连接中...」**：`GameRoot/Canvas2D/Back/FullBackWindow(Clone)/CommonLoadingWindow` 一直 active、文本「连接中...」，此时 `main` 场景已加载、`TaskWindow(Clone)`/`ScrollTextWindow(Clone)` 已激活，但 `HudWindow(Clone)` 的 layout 等子节点全 off、`MainWindow(Clone)` 不存在。本次持续 >15 分钟未恢复 —— 属**连接游戏服未完成（环境/服务端问题）**，不是流程步骤失败。判定"流程走完"应以"启程已点 + TaskWindow 激活"为准，别把"连接中"当成自己点错了。
  
  另：创角及之后的阶段 `unity_screenshot` 只有 3D 层（UI 不入镜），但对象树里 UI 的 alpha/屏幕坐标都正常 —— 断言一律走对象树。

