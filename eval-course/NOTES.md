# Teaching notes（测评课）

## 用户偏好

- 中文讲解；结论要落到**文件与符号**（`EVAL.md`、`src/app/eval/*.py`、页面路径），不空谈概念。
- 每节课短，且必须能在真实平台上看到一次结果（一个批次、一张分数表、一条 trace、一条门禁结论）。
- 用户熟悉 Python，已在用这套平台；不要从"什么是测试"讲起，直接从评测集字段与分数语义切入。

## 环境

- 平台：`http://localhost:5013`（前端）/ `http://localhost:5012`（后端）/ 公网 `https://smarttest.h3comfyui.art`（Basic Auth）。
- Langfuse：`http://localhost:3000`（自建 4.36.1-zh，项目 `名著智能体`，`ui_eval` 同属组织 `ui自动化测评`）。
- 重置环境：`bash tools/reset-data.sh`（备份到 `~/smart-test-backups/<时间戳>/`；保留账号、设置、Langfuse 项目与密钥）。
- 评测集是仓库文件（`datasets/*.yaml`），**不受重置影响**。

## 已知坑（讲课时要主动提醒）

- **两个 SQLite 库**：容器（网页、`docker compose exec`）用 `docker-data/smart_test_platform.db`；
  宿主机直接跑 CLI 会用仓库根目录的 `smart_test_platform.db`——在命令行跑的批次，网页上看不到。
  教学一律走网页，或 `docker compose exec fastapi python -m src.app.eval.cli …`。
- **门禁留空时 `passed` 只代表"没有执行异常"**，不代表分数达标。
- **judge 与被测 agent 共用同一个模型端点**（默认都是 `glm-4.7`）时，评判偏好会同时影响两边。
- 一条用例可能跑十几分钟（Web-UI 智能体要起浏览器、可能自修复重跑）；实时面板的心跳才是判活依据。

## 教学顺序（默认）

1. **写一条用例，跑出分数与门禁结论**（当前：第 1 课）——把整条闭环先走一遍。
2. 读一条 trace：分数与轨迹的对应关系（Langfuse 里定位瓶颈/失败点）。
3. 用例设计进阶：expected 与 judge 的边界、可判定性、反例（把"能自动判"写在 expected）。
4. 回归：同一评测集跑两个版本（改提示词/换模型），用门禁做可比对结论。

## 进度

- 2026-09-17：环境重置为干净状态；建立课程工作区；产出第 1 课与速查参考。
