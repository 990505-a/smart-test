# Juice Shop P0 冒烟 · Web-UI 自动化执行报告

- 执行时间：2026-09-17（本轮会话）
- 被测站点：http://juice-shop:3000（OWASP Juice Shop v20.2.0，Angular SPA，hash 路由）
- 执行器：Playwright CLI 1.56.1（playwright-runner sidecar，chromium）
- 视口：Desktop Chrome（桌面）
- 用例依据：/app/workspace/default/cases/juice-shop.md（CASE-JS-005 / 006 / 010 / 016）
- 最终结果：**4 通过 / 0 失败**（最终轮总耗时 19.1s）

## 一、用例清单与结果

| # | 用例名 | 需求/用例编号 | 结果 | 断言要点 | 耗时 |
|---|---|---|---|---|---|
| 1 | REQ-AUTH-002 正确凭据登录成功且出现用户菜单 | REQ-AUTH-002 / CASE-JS-005 | ✅ 通过 | token 写入 localStorage；跳转 /#/search；账户菜单展开显示 admin@juice-sh.op 与 Logout | 4.7s |
| 2 | REQ-AUTH-002 错误密码登录失败且停留在登录页 | REQ-AUTH-002 / CASE-JS-006 | ✅ 通过 | 提示 "Invalid email or password." 可见；URL 仍为 /#/login；表单可见；localStorage 无 token | 4.7s |
| 3 | REQ-CAT-002 搜索 apple 命中 Apple 与 Pineapple 商品 | REQ-CAT-002 / CASE-JS-010 | ✅ 通过 | 结果 3 条（Apple Juice / Apple Pomace / Pineapple Juice）；条目数>0；全部命中 apple 子串；含 pineapple 模糊匹配 | 4.7s |
| 4 | REQ-CART-001 加入购物车后商品存在且数量为 1 | REQ-CART-001 / CASE-JS-016 | ✅ 通过 | 成功提示 "Placed Apple Juice (1000ml) into basket."；角标 0→1；购物车 mat-row 存在；数量列=1；Total Price 1.99 可见 | 4.6s |

## 二、执行过程与自修复记录

- 第 0 轮（侦察）：7 次侦察/探路执行，确认了该版本的 DOM 与既有草稿的差异。
- 第 1 轮（首轮正式执行）：1 通过 / 3 失败。
  失败原因均与站点实际 DOM 有关，属「spec 需适配真实 DOM」，非站点缺陷：
  1. 登录成功断言依赖成功提示条 "You successfully logged in"——**本版本登录成功无提示条**，
     改为断言 token 写入 + 跳转 + 账户菜单出现（含邮箱与 Logout）。
  2. 商品名选择器 .item-name 在本版本不存在——商品名渲染在 `mat-card .info-box .name`。
  3. 详情对话框内无 "Add to Basket" 按钮——加购按钮在商品卡片 footer 上
     （aria-label="Add to Basket"）；详情对话框实为评论信息框（含 Reviews 与 Submit）。
  4. 购物车行不是 `tbody tr`——是 `mat-row`（Angular Material 表），数量列在
     `.mat-column-quantity span.cell-initial-font`。
- 第 2 轮（修复后执行）：**4/4 全部通过**。
- 是否发生过自修复：**是**（1 轮修复后全部通过，未删任何断言，均改为与真实 DOM/版本行为一致的等价断言）。

## 三、产物位置

- 入库脚本：平台「Web-UI 自动化」页 → `juice-shop-p0-smoke`（id: a2580811-3341-4d79-be09-d1be31584fee，module=smoke）
- 最终 spec 归档：/app/workspace/default/specs/juice-shop-p0-smoke.spec.ts
- 通过用例截图（运行目录 artifacts/）：
  - 01-登录成功-用户菜单出现.png
  - 02-登录失败-错误提示且停留登录页.png
  - 03-搜索apple结果.png
  - 04-购物车-商品存在数量1.png
- 官方 HTML 报告（含 trace 回放）：每轮执行的 html-report 产物
  - 最终通过轮 runner_run_id：2026-09-17T05-58-37-957Z-4c3cdf14
- 首轮失败存证（供回溯）：runner_run_id 2026-09-17T05-45-46-077Z-1dd8b8fe（含失败截图与 trace.zip）

## 四、遗留风险与说明

1. 覆盖范围为三条主流程各一条正向/反向用例，共 4 条；用例文档中的其余 31 条
   （注册、语言切换、结算、边界与安全类）本轮未执行。
2. 登录成功用例使用预置管理员账号 admin@juice-sh.op，仅做登录态断言，未做任何写操作
   （未改资料、未下单）；购物车用例向匿名购物车加入 1 件商品，属浏览类会话数据，
   未结算、未修改站点种子数据。
3. Juice Shop 首次加载有欢迎横幅与 Cookie 横幅遮挡，spec 已内置自动关闭逻辑
   （dismissBanners），后续新用例建议复用。
4. 站点为 SPA + hash 路由，页面就绪依赖异步渲染，统一用 expect 可见性等待，
   未使用硬等时。
