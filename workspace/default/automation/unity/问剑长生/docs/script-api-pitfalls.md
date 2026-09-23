# script-api-pitfalls

> 用例脚本 API 的实测坑（写脚本前读）。
>
> 来源：原 memory/MEMORY.md，2026-09-23 结构迁移时按主题拆出（内容逐字保留）。

- **2026-09-22 17:05** · 领域知识 · _agent_

  **Unity 用例脚本 API 实测坑（问剑长生，2026-09-22）**
  
  1. `u.wait_for(target, state="absent")` 判的是**对象是否还在场景里**。这个游戏关面板是「隐藏」（activeSelf=false）而非销毁，所以 `state="absent"` 会一直等到超时，报错提示本身就写了：关面板要用 `state="hidden"`（或 `u.expect_hidden`）。判"窗口真的关了"一律用 hidden。
  2. `u.object_text(target)` 在**用例脚本里返回字符串**（`"a b c"`），不是 dict —— 别写 `.get("text")`；`unity_object_text` 工具返回的才是 dict（`parts`/`text`）。
  3. `u.wait_for` / `expect_exists` 单次调用有**固定约 12s 开销**（不是只在等待时才耗时），且 `u.hierarchy` 读根节点要扫 7000+ 对象（约 1s）。长流程（20+ 步）用这些原语累加很容易撞平台 420s 执行上限 → 用 `time.sleep(1)` + `u.exists()`（0.05s）自己写轻量轮询 `wait_shown()`，只在等界面出现时轮询。
  4. 判"某窗口是否显示"不能只用 `u.exists()`：`u.hierarchy(root=path, depth=1)` 返回的 `rows` 里该行第 2 列就是可见性（"1"/"0"）；窗口不存在时 `u.hierarchy` 会**抛异常**，要 try/except 包住。
  5. 复位（lua 模式）本身约 22s；整轮「注册并登录→创角→启程」的净流程约 4 分钟，跑全流程用例要把平台超时放宽到 600s 以上。
  
  相关：新手流程第一阶段的完整对象路径与流程见 MEMORY.md 里的「问剑长生 Unity 客户端 UI 对象路径」条目；用例脚本已入库（`新手流程第一阶段-注册创角启程`，module=新手流程；另有 `Unity桥健康检查-PlayMode与启动界面`）。

