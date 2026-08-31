# TMP 文本读取指南

读取 UI 节点文本、验证界面数据展示效果。

适用场景：
- 多按钮共用同一 GameObject 名，需通过显示文本区分（Tab、列表按钮等）
- 验证操作后数值/状态文本是否更新（等级、进度、金币、倒计时等）
- 断言弹窗提示、标签内容、道具名称等文本是否符合预期
- 解析进度条 `当前值/总量` 格式，验证达成条件

## 初始化

```python
from unity_api import UnityClient
from text_reader import TextReader
from ui import UI

client = UnityClient()
tr = TextReader(client)
ui = UI(client)
```

---

## 富文本剥离（strip_tags）

游戏 UI 大量使用 TMP 富文本标签，如 `<color=#E27DFF>衣·灵纱绘羽</color>`、
`<size=42>化</size>神`。几乎所有方法都支持 `strip_tags=True` 自动剥离，
**建议断言时默认开启**，避免颜色/尺寸标签干扰匹配。

```python
# 不剥离（原始值）
raw  = tr.get_text("text_name", window_name="OperateActivityWindow")
# '<color=#E27DFF>衣·灵纱绘羽</color>'

# 自动剥离
pure = tr.get_text("text_name", window_name="OperateActivityWindow", strip_tags=True)
# '衣·灵纱绘羽'
```

---

## 读取文本

### 单节点

使用定向快速路径：Lua 侧按节点名过滤，找到即返回（不再全量扫描所有 TMP 组件）。

```python
# 第一个匹配节点，自动剥离富文本
text = tr.get_text("text_name", window_name="GangRoomWindow", strip_tags=True)
print(text)  # '星痕宗'

# 不限定窗口时，在所有活跃窗口中搜索（慎用，存在同名冲突）
text = tr.get_text("text_level", strip_tags=True)

# 用 instance_id 精确指定 allow_multiple 窗口的某个实例
text = tr.get_text("text_name", instance_id=12345, strip_tags=True)
```

### 按索引取第 N 个同名节点

界面中经常有多个同名节点（列表行、网格格子），用 `get_text_at` 精确定位：

```python
# text_score 共有 3 个节点：40 / 80 / 120
tr.get_text_at("text_score", 0, window_name="OperateActivityWindow")  # '40'
tr.get_text_at("text_score", 1, window_name="OperateActivityWindow")  # '80'
tr.get_text_at("text_score", 2, window_name="OperateActivityWindow")  # '120'

# 索引越界时安全返回 None
tr.get_text_at("text_score", 99, window_name="OperateActivityWindow")  # None
```

### 获取所有同名节点文本列表

```python
# 返回按出现顺序排列的列表
scores = tr.get_texts("text_score", window_name="OperateActivityWindow")
# ['40', '80', '120']

# 自动剥离富文本
names = tr.get_texts("text_name", window_name="OperateActivityWindow", strip_tags=True)
# ['衣·灵纱绘羽', '发·鹤影流韵', '餐霞宝诀', ...]
```

### 批量读取（调试用）

```python
# 返回 {节点名: [文本, ...]} 字典（含富文本原始值）
all_texts = tr.get_all_texts(window_name="OperateActivityWindow")

# 打印所有文本（调试）
tr.print_all_texts(window_name="OperateActivityWindow", strip_tags=True)
```

---

## 进度条解析

进度条文本格式为 `当前值/总量`，可能带富文本，如 `<color=#65dccc>999</color>/100`。

### 读取进度值

```python
# 返回 (current, total) 浮点元组
current, total = tr.get_progress("slider_txt", window_name="OperateActivityWindow")
# (999.0, 100.0)

# 多个同名进度条，用 index 指定
prog1 = tr.get_progress("slider_txt", window_name="OperateActivityWindow", index=1)
# (0.0, 20.0)

# 一次获取所有
all_progs = tr.get_all_progress("slider_txt", window_name="OperateActivityWindow")
# [(999.0, 100.0), (0.0, 20.0), (2.0, 2.0), (70.0, 20.0)]
```

### 断言进度条

```python
# 进度 >= 100%（已完成）
tr.assert_progress("slider_txt", min_ratio=1.0, window_name="OperateActivityWindow")

# 当前值为 0（未开始）
tr.assert_progress("slider_txt", index=1, exact_val=0,
                   window_name="OperateActivityWindow")

# 当前值在 5~20 之间
tr.assert_progress("slider_txt", index=2, min_val=5, max_val=20,
                   window_name="OperateActivityWindow")

# 进度不超过 100%（正常范围）
tr.assert_progress("slider_txt", max_ratio=1.0, window_name="OperateActivityWindow")
```

---

## 数值断言

适用于 `text_num`、`text_score`、`text_level` 等纯数字节点（自动剥离富文本）。

### 读取数值

```python
n = tr.get_number("text_score", window_name="OperateActivityWindow", index=0)
# 40.0

# 获取所有同名节点的数值（跳过无法解析的）
nums = tr.get_numbers("text_score", window_name="OperateActivityWindow")
# [40.0, 80.0, 120.0]
```

### 比较断言

```python
tr.assert_number("text_score", index=0, gte=40)        # >= 40
tr.assert_number("text_score", index=2, eq=120)        # == 120
tr.assert_number("text_level", gte=10, lt=100)         # 10 <= x < 100
tr.assert_number("text_num",   index=2, gt=0, lte=20)  # 0 < x <= 20
```

---

## 正则断言

适用于含动态数字/时间的文本，精确值随时间变化但格式固定。

```python
# 倒计时格式："活动结束：3天0小时"
tr.assert_text_pattern("text_refresh", r"\d+天\d+小时",
                        window_name="OperateActivityWindow",
                        index=1)          # 默认 strip_tags=True

# 解锁提示："3天后解锁后续任务"
tr.assert_text_pattern("text_tips", r"\d+天后解锁",
                        window_name="OperateActivityWindow")

# 进度状态："100历练值可领取（已达成）"
tr.assert_text_pattern("text_state", r"\d+历练值可领取",
                        window_name="OperateActivityWindow")
```

> `strip_tags` 默认为 `True`（剥离后再做正则匹配），因为动态文本通常带颜色标签。

---

## 文本断言（精确/包含）

```python
# 精确匹配（自动剥离富文本）
tr.assert_text("text_name", "衣·灵纱绘羽",
               window_name="OperateActivityWindow", strip_tags=True)

# 包含匹配
tr.assert_text("text_state", "已达成",
               window_name="OperateActivityWindow",
               contains=True, strip_tags=True)

# 按索引断言（列表项场景）
tr.assert_text_at("text_score", 0, "40", window_name="OperateActivityWindow")
tr.assert_text_at("text_score", 2, "120", window_name="OperateActivityWindow")

# 带自定义错误信息
tr.assert_text("text_title", "心法道途",
               window_name="OperateActivityWindow",
               strip_tags=True,
               msg="活动标题不是心法道途，Tab 可能切换错误")
```

---

## 按钮文本读取与查找

### 打印调试（开发时）

```python
tr.print_button_texts(window_name="OperateActivityWindow")
# instanceID    active  name                                 text
# ──────────────────────────────────────────────────────────────────
# -110814            Y  btn_rank                             '天骄排行'
# -116320            Y  item-109884                          '星官赐福'
# -110436            Y  item-109884                          '心法道途'
```

### 按显示文本查找按钮

`find_button_by_text` 使用 Lua 侧早停匹配，找到第一个匹配按钮立即返回（不再拉全量按钮列表）。

```python
# 精确匹配（带富文本的按钮用 strip_tags=True）
btn = tr.find_button_by_text("衣·灵纱绘羽",
                              window_name="OperateActivityWindow",
                              strip_tags=True)
if btn:
    ui.lua_click(btn["instanceID"])  # 推荐用 lua_click

# 包含匹配
btn = tr.find_button_by_text("宗门", window_name="GangRoomWindow", exact=False)

# 对 allow_multiple 窗口，用 instance_id 精确定位
btn = tr.find_button_by_text("关闭", window_name="ItemInfoSimpleWindow",
                              instance_id=12345)
```

> **推荐**: 如果只需要"找到并点击"，直接用 `ui.find_and_click_by_text()` 更高效（单次 Lua 调用完成查找+点击）。

---

## 等待文本变化

UI 更新通常是异步的，操作后需等待文本刷新。

```python
# 等待文本精确变为某值
ok = tr.wait_for_text("text_gold", "9999",
                       window_name="ShopWindow",
                       strip_tags=True,
                       timeout=5.0)
assert ok, "购买后金币未更新"

# 等待文本包含某关键词
ok = tr.wait_for_text("text_tips", "已达成",
                       window_name="OperateActivityWindow",
                       exact=False, strip_tags=True)

# 等待文本发生任意变化（记录变化前后的值）
before = tr.get_text("text_exp", window_name="CharacterWindow")
ui.find_and_click("btn_fight")
new_val = tr.wait_for_text_change("text_exp",
                                   window_name="CharacterWindow",
                                   strip_tags=True,
                                   timeout=10.0)
assert new_val is not None, "战斗后经验值未变化"
print(f"经验: {before} → {new_val}")
```

---

## Tab 切换（通用）

`switch_tab_by_text` 适用于任何含 Tab 结构的窗口，通过显示文本点击 Tab 按钮。
HudWindow 的 Tab 用专用的 `ui.switch_hud_tab()`；其他窗口用此方法。

```python
# 基础切换
ui.switch_tab_by_text("心法道途", window_name="OperateActivityWindow")

# 切换后验证内容是否加载（推荐）
ui.switch_tab_and_verify(
    "心法道途",
    window_name="OperateActivityWindow",
    verify_node="title_tex",
    verify_text="累计进行100次",  # 包含匹配
)

# 切换并验证积分门槛数值
ui.switch_tab_by_text("境界奖励", window_name="OperateActivityWindow")
tr.assert_number("text_score", index=0, gte=40,
                  window_name="OperateActivityWindow")
```

---

## 典型测试流程

以下示例展示对 `OperateActivityWindow` 的完整功能验证：

```python
from unity_api import UnityClient
from ui import UI
from text_reader import TextReader

client = UnityClient()
ui = UI(client)
tr = TextReader(client)

# 1. 切换到心法道途 Tab 并验证内容加载
ui.switch_tab_and_verify(
    "心法道途",
    window_name="OperateActivityWindow",
    verify_node="title_tex",
    verify_text="累计进行",
)

# 2. 验证积分门槛（40 / 80 / 120）
tr.assert_text_at("text_score", 0, "40",  window_name="OperateActivityWindow")
tr.assert_text_at("text_score", 1, "80",  window_name="OperateActivityWindow")
tr.assert_text_at("text_score", 2, "120", window_name="OperateActivityWindow")

# 3. 验证进度条：第一条已完成（进度 >= 100%）
tr.assert_progress("slider_txt", index=0, min_ratio=1.0,
                   window_name="OperateActivityWindow")

# 4. 验证活动倒计时格式正确
tr.assert_text_pattern("text_refresh", r"\d+天\d+小时",
                        window_name="OperateActivityWindow", index=1)

# 5. 验证道具名称（带颜色标签）
tr.assert_text("text_name", "衣·灵纱绘羽",
               window_name="OperateActivityWindow",
               strip_tags=True)

# 6. 点击"天骄排行"按钮
ui.find_and_click_by_text("天骄排行", window_name="OperateActivityWindow")

# 7. 截图保存结果
ui.screenshot("activity_result.png")
```

---

## 注意事项

- **`index` 包含 inactive 节点**：默认 `include_inactive=True`，
  所以 `index=0` 可能是不可见节点。若只针对可见内容，
  传 `include_inactive=False`，或先用 `get_texts` 检查列表确认正确索引。
- **进度条格式要求**：`get_progress` 严格要求纯文本为 `数字/数字`，
  含其他字符时返回 `None`。
- **`strip_tags` 不改变 `index` 顺序**：剥离只影响返回值的显示，
  不影响节点遍历顺序。
- **性能**：`get_text` / `get_texts` 使用定向快速路径，Lua 侧只收集匹配节点（约 100-150ms）；
  `get_all_texts` 扫描整个子树（约 150-400ms）。高频轮询时建议设置合理的 `interval`。
- **instance_id**：所有方法支持 `instance_id` 参数，用于精确指定 `allow_multiple` 窗口的某个实例。
  通过 `ui.get_shown_instances("WindowName")` 获取实例列表。
- **正则断言默认剥离标签**：`assert_text_pattern` 的 `strip_tags` 默认为 `True`，
  因为动态文本中的数字通常被 `<color=...>` 包裹。
