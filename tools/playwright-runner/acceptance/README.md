# Web-UI 自动化页面验收（浏览器级）

驱动真实 Chromium 打开平台自己的「Web-UI 自动化」页，断言**用户能看见的东西**：
图表真的画出来了、签名 URL 的截图真的解码成功、官方报告在新标签页里真的渲染出
测试树与 trace 回放。每一步都留截图到 `artifacts/`。

## 为什么不能只打接口

接口 200 不等于页面能用。写这套用例的当天就抓到一个只靠接口测不出来的 bug：
产物 URL 少了 `/api/v2` 前缀 → 后端返回 404 的 JSON → 浏览器按 ORB 把它拦成
`ERR_BLOCKED_BY_ORB`，表现是"截图挂了一张，但接口全绿"。

## 运行

```bash
cd tools/playwright-runner/acceptance

export WEBUI_BASE=http://127.0.0.1:5013          # 前端
export WEBUI_API=http://127.0.0.1:5012           # 后端
export WEBUI_USER=$(grep '^AUTH_DEFAULT_ADMIN_USERNAME=' ../../../.env | cut -d= -f2-)
export WEBUI_PASS=$(grep '^AUTH_DEFAULT_ADMIN_PASSWORD=' ../../../.env | cut -d= -f2-)

../node_modules/.bin/playwright test --config playwright.config.ts
```

依赖宿主机的 `@playwright/test` 与 chromium（`npx playwright install chromium`）。

## 验收项

| 用例 | 验的是什么 |
|---|---|
| 01 概览 | 四张统计卡 + recharts 趋势图（`.recharts-surface`）+ 失败榜真的渲染 |
| 02 列表 | 运行环境/最近结果列有内容、搜索筛选真的改变结果集 |
| 03 编辑器 | CodeMirror 加载、设备与浏览器矩阵控件在位、修复历史面板可开 |
| 04 执行详情 | 失败用例自动展开、`文件:行号` 定位可见、签名 URL 的失败截图解码成功（`naturalWidth>0`）、视频与 trace 可下载 |
| 05 官方报告 | 新标签页打开报告、SPA 测试树渲染（依赖相对路径取回 `data/*.json`）、View Trace 打开回放器 |
| 06 分享链接 | 全新浏览器上下文（无登录态）也能打开报告；签名被改动必须 403 |
| 07 执行中看进度 | 点「执行」后列表立刻出现「运行中」；详情里的进度面板会实时更新（已完成数从 0 涨上去）、CLI 输出尾在动；跑完自动收敛成结果。用的是夹具自己的冒烟脚本（**不再依赖用户用例库里的脚本**——清空过数据的环境里那样会直接跑不起来） |
| 08 录像回放 | 失败录像能播、`seekable` 非空、拖进度条后 currentTime 真的变了（依赖服务端 Range 支持） |
| 09 产物被清理 | 把运行目录删掉后，页面必须说明「产物已不在服务器上」，且不再渲染任何指向已删产物的图片（用例明细仍然有效） |
| 10 trace 链接 | 测评页的 trace 链接必须带 `/project/<id>/` 前缀（少了必然 404），且不能是容器内地址 |
| 11 设置页 Langfuse | 地址是宿主视角、Secret 只回显掩码、Public Key 可见、测试连通返回项目名与项目 id |
| 12 设置页 LLM 裁判 | 卡片必须写出**实际生效的模型**与**来源（独立配置 / 继承主 LLM）**、留空即继承写在占位符里、API Key 只回显掩码、自检（走真实打分通道）有结果、测评页同样标出来源 |

另有跑测评页的两个文件（`eval-live.spec.ts` / `eval-datasets.spec.ts`）：

| 用例 | 验的是什么 |
|---|---|
| 01 评测集页面上增删改 | 新建评测集 → 文件真的落到 `datasets/`（块标量、中文、id 都对）→ 列表多一行；编辑加一条用例 → 保存后文件里出现；「启动测评」下拉里立刻能选到；删除 → 文件真的从磁盘消失、列表恢复。**不跑 agent，几秒完成** |

| 用例 | 验的是什么 |
|---|---|
| 01 测评执行中看进度 | 起一个真实测评批次后打开详情，必须看到「正在执行」+「agent 在做什么」活动流（模型生成 / 工具调用）+ 实时日志尾；跑完完成数涨到 1/1、用例行真的落到表格里（证明是**跑一条落一条**而不是整轮结束才写库）。**这条会真跑 `datasets/smoke-webui.yaml`（1 条用例，约 40–60s）** |

## 夹具

`global-setup.ts` 会通过接口造一条「故意失败」的用例并执行，供失败路径验收；
`global-teardown.ts` 跑完删掉它——不在平台里留常驻失败用例（否则会污染通过率趋势
和「失败最多的用例」榜）。

产物目录 `artifacts/` 已在 `.gitignore` 中忽略；失败时 `artifacts/test-results/` 里
有 trace.zip 可 `npx playwright show-trace` 回放。
