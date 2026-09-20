# MEMORY.md — 长期记忆

> 跨会话仍然成立的结论。每条带上日期与来源，便于判断是否过期。

## 从旧版记忆迁移（经历）

> 来源：EverOS episodes（自动迁移，可自行整理或删除）

- 平台写入长期记忆：跨天重置场景须覆盖周一04:59/05:00/05:01三个边界时间点
- 平台记录用例评审会固定每周三上午10点举行的项目约定

- **2026-09-17 23:27** · 平台约定 · _agent_

  ## 平台门禁语义（2026-09-17，ruoyi-login 实测）
  
  - review_case_document 返回 verdict=needs_revision 但同时 review_status=passed：批准门禁只看有无 blocker/high；medium/low 不阻断批准，可原样列给用户决策。
  - save_requirement_package 的规范性召回检查会把 source_manifest 里列出的文件一并扫描：代码文件的注解/注释（@NotEmpty、yaml「必填」等）会被当成规范性语句造成未覆盖噪音。正确做法：source_manifest 只放需求文档；代码证据以「代码依据：文件:行」行写进需求文档条目下，再以 repo: 引用放 requirements[].source_refs。
  - 需求包 coverage_plan 不写某 REQ 时，save_case_document/lint 会报 REQUIREMENT_NOT_COVERED 阻断；「不适用/挂起/阻塞」也要落一条用例（含状态与执行条件行）并在 coverage_plan 给 case_ids 才能过门禁。
  - 长中文 payload 经 save_* 工具仍会偶发截断/篡改（本次把「观察」写成「觃察」、需求文档丢行）；每次保存后必须回读，发现损坏整体重发。

- **2026-09-18 08:19** · Web-UI 自动化 · _agent_

  2026-09-18 · 豆瓣 www.douban.com/explore/ 探索实测（匿名桌面端，Playwright 1.56.1）
  
  - 页面结构：/explore/（人气创作）与 /explore/recommend（为你推荐）共用 .explore-tab 页签（当前项为 span，另一项为 a 链接）；主信息流容器为 #explore-root 或 #gallery_main_frame，条目选择器 li.item（含 .usr-pic 作者区、.title a 标题链接、a.cover 封面）；侧栏「热门话题」模块 id=#hot-topics-mod，入口链接 href="/gallery/"。
  - 关键现象：匿名桌面端 /explore/ 主信息流 JS 渲染依赖登录态，始终停在 loading gif（frodo_landing 接口只返回 banner 数据）；/explore/recommend 是服务端渲染，匿名可正常出 9 条内容。测豆瓣浏览发现优先测 /explore/recommend。
  - 404 行为：无效路径返回 HTTP 404，文案「呃...你想访问的页面不存在」，约 1 秒后自动跳回首页。
  - 已入库用例：script_id=81ba7068-33fc-4cbe-a451-9fdf925b2367（豆瓣浏览发现 · 匿名桌面端冒烟，6 条全过）。
  - 定位教训：条目作者区 .usr-pic 内有两个 a（头像+用户名），toBeVisible 断言前必须 .first() 否则 strict mode violation。
