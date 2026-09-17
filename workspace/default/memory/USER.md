# USER.md — 用户画像

> 只写用户明确表达过的偏好，不要从一次对话里推断性格。

## 从旧版记忆迁移

> 来源：EverOS user.md（自动迁移，可自行整理或删除）

---
id: profile_platform
type: user_profile
schema_version: 1
user_id: platform
track: user
summary: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
explicit_info:
- category: 领域知识
  description: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
  evidence: 消息内容明确写道：跨天重置场景必须覆盖周一 04:59/05:00/05:01 三个边界时间点。
- category: 工作方式
  description: 用户习惯以“分类+标识+内容”的结构化格式向系统存入长期记忆，并会根据内容主题选择不同分类与标识（如 domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule）。
  evidence: 2026-08-31 用户以该格式写入 domain_knowledge/daily_reset 与 convention/feishu_export；2026-09-02
    再次以该格式写入 convention/case_review_meeting_schedule；此前已有 domain_knowledge/boundary_rule
    的记录。
- category: 领域知识
  description: 用户记录了飞书思维导图导出的约定：同批节点的 parent 必须已存在，单批不超过 50 个节点，否则需要采用分层分块方式写入。
  evidence: 2026-08-31 用户以“【长期记忆】分类：convention；标识：feishu_export”的格式记录该飞书导出规则。
- category: 领域知识
  description: 用户记录了限时活动重置校验规则：重置校验点应包含活动开始时刻、活动结束时刻与自然日切换点。
  evidence: 2026-08-31 用户以“【长期记忆】分类：domain_knowledge；标识：daily_reset”的格式记录该规则。
- category: 约定
  description: 用户记录了项目约定：用例评审会固定在每周三上午 10 点举行；安排评审、提交用例草稿或申请复核时，需预留时间在周三 10 点前完成准备，以免错过当周评审节点。
  evidence: 2026-09-02 用户以“【长期记忆】分类：convention；标识：case_review_meeting_schedule”的格式记录该约定。
implicit_traits:
- trait: 边界敏感的严谨型思维
  description: 用户在测试与验证工作中高度重视临界条件，倾向于穷举边界点以确保覆盖完整、避免边缘遗漏。
  basis: 用户记录规则时特意列出三个连续的临界时间点（04:59/05:00/05:01），并补充限时活动校验点应包含活动开始/结束时刻与自然日切换点，说明其关注的不只是整点，而是完整的边界时刻集合。
  evidence: 2026-08-31 用户记录跨天重置规则要求覆盖周一 04:59/05:00/05:01；同日又记录限时活动重置校验点应包含活动开始/结束时刻与自然日切换点。
- trait: 结构化知识管理者
  description: 用户偏好用清晰的分类和标签体系来沉淀经验，并会将同一套“分类+标识+内容”格式反复用于不同主题，重视知识的规范性、可检索性与后续复用。
  basis: 用户多次以完全相同的【长期记忆】固定格式写入不同知识（domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule），每次都指定独立分类与标识，说明结构化知识管理是其稳定的行为模式。
  evidence: 2026-08-31 用户以该格式写入 daily_reset 与 feishu_export 两条记忆；2026-09-02 又写入 case_review_meeting_schedule；此前已有
    boundary_rule 记录。
- trait: 风险规避的规则沉淀者
  description: 用户倾向于将操作中易导致失败的前置条件、数量上限、时间节点和兜底策略固化为明确规则，以降低出错概率，属于[风险规避]、[规则导向]型人格。
  basis: 从跨天重置场景的“必须覆盖”、飞书导出的“parent必须已存在、单批不超过50、否则分层分块”，到用例评审“预留时间在周三 10 点前完成准备以免错过”，用户记录的不是孤立经验，而是一系列防错与防遗漏规则，说明其有意识规避技术及流程风险。
  evidence: 2026-09-02 用户记录用例评审会约定时明确给出准备截止节点与错过风险；2026-08-31 记录飞书导出约定时给出前置条件、批量上限和异常兜底方案；此前记录跨天边界规则时同样使用“必须覆盖”的防漏措辞。
profile_timestamp_ms: 1788322228250
---
用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。

## 从旧版记忆迁移

> 来源：EverOS user.md（自动迁移，可自行整理或删除）

---
id: profile_platform
type: user_profile
schema_version: 1
user_id: platform
track: user
summary: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
explicit_info:
- category: 领域知识
  description: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
  evidence: 消息内容明确写道：跨天重置场景必须覆盖周一 04:59/05:00/05:01 三个边界时间点。
- category: 工作方式
  description: 用户习惯以“分类+标识+内容”的结构化格式向系统存入长期记忆，并会根据内容主题选择不同分类与标识（如 domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule）。
  evidence: 2026-08-31 用户以该格式写入 domain_knowledge/daily_reset 与 convention/feishu_export；2026-09-02
    再次以该格式写入 convention/case_review_meeting_schedule；此前已有 domain_knowledge/boundary_rule
    的记录。
- category: 领域知识
  description: 用户记录了飞书思维导图导出的约定：同批节点的 parent 必须已存在，单批不超过 50 个节点，否则需要采用分层分块方式写入。
  evidence: 2026-08-31 用户以“【长期记忆】分类：convention；标识：feishu_export”的格式记录该飞书导出规则。
- category: 领域知识
  description: 用户记录了限时活动重置校验规则：重置校验点应包含活动开始时刻、活动结束时刻与自然日切换点。
  evidence: 2026-08-31 用户以“【长期记忆】分类：domain_knowledge；标识：daily_reset”的格式记录该规则。
- category: 约定
  description: 用户记录了项目约定：用例评审会固定在每周三上午 10 点举行；安排评审、提交用例草稿或申请复核时，需预留时间在周三 10 点前完成准备，以免错过当周评审节点。
  evidence: 2026-09-02 用户以“【长期记忆】分类：convention；标识：case_review_meeting_schedule”的格式记录该约定。
implicit_traits:
- trait: 边界敏感的严谨型思维
  description: 用户在测试与验证工作中高度重视临界条件，倾向于穷举边界点以确保覆盖完整、避免边缘遗漏。
  basis: 用户记录规则时特意列出三个连续的临界时间点（04:59/05:00/05:01），并补充限时活动校验点应包含活动开始/结束时刻与自然日切换点，说明其关注的不只是整点，而是完整的边界时刻集合。
  evidence: 2026-08-31 用户记录跨天重置规则要求覆盖周一 04:59/05:00/05:01；同日又记录限时活动重置校验点应包含活动开始/结束时刻与自然日切换点。
- trait: 结构化知识管理者
  description: 用户偏好用清晰的分类和标签体系来沉淀经验，并会将同一套“分类+标识+内容”格式反复用于不同主题，重视知识的规范性、可检索性与后续复用。
  basis: 用户多次以完全相同的【长期记忆】固定格式写入不同知识（domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule），每次都指定独立分类与标识，说明结构化知识管理是其稳定的行为模式。
  evidence: 2026-08-31 用户以该格式写入 daily_reset 与 feishu_export 两条记忆；2026-09-02 又写入 case_review_meeting_schedule；此前已有
    boundary_rule 记录。
- trait: 风险规避的规则沉淀者
  description: 用户倾向于将操作中易导致失败的前置条件、数量上限、时间节点和兜底策略固化为明确规则，以降低出错概率，属于[风险规避]、[规则导向]型人格。
  basis: 从跨天重置场景的“必须覆盖”、飞书导出的“parent必须已存在、单批不超过50、否则分层分块”，到用例评审“预留时间在周三 10 点前完成准备以免错过”，用户记录的不是孤立经验，而是一系列防错与防遗漏规则，说明其有意识规避技术及流程风险。
  evidence: 2026-09-02 用户记录用例评审会约定时明确给出准备截止节点与错过风险；2026-08-31 记录飞书导出约定时给出前置条件、批量上限和异常兜底方案；此前记录跨天边界规则时同样使用“必须覆盖”的防漏措辞。
profile_timestamp_ms: 1788322228250
---
用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。

## 从旧版记忆迁移（画像）

> 来源：EverOS user.md（自动迁移，可自行整理或删除）

---
id: profile_platform
type: user_profile
schema_version: 1
user_id: platform
track: user
summary: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
explicit_info:
- category: 领域知识
  description: 用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
  evidence: 消息内容明确写道：跨天重置场景必须覆盖周一 04:59/05:00/05:01 三个边界时间点。
- category: 工作方式
  description: 用户习惯以“分类+标识+内容”的结构化格式向系统存入长期记忆，并会根据内容主题选择不同分类与标识（如 domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule）。
  evidence: 2026-08-31 用户以该格式写入 domain_knowledge/daily_reset 与 convention/feishu_export；2026-09-02
    再次以该格式写入 convention/case_review_meeting_schedule；此前已有 domain_knowledge/boundary_rule
    的记录。
- category: 领域知识
  description: 用户记录了飞书思维导图导出的约定：同批节点的 parent 必须已存在，单批不超过 50 个节点，否则需要采用分层分块方式写入。
  evidence: 2026-08-31 用户以“【长期记忆】分类：convention；标识：feishu_export”的格式记录该飞书导出规则。
- category: 领域知识
  description: 用户记录了限时活动重置校验规则：重置校验点应包含活动开始时刻、活动结束时刻与自然日切换点。
  evidence: 2026-08-31 用户以“【长期记忆】分类：domain_knowledge；标识：daily_reset”的格式记录该规则。
- category: 约定
  description: 用户记录了项目约定：用例评审会固定在每周三上午 10 点举行；安排评审、提交用例草稿或申请复核时，需预留时间在周三 10 点前完成准备，以免错过当周评审节点。
  evidence: 2026-09-02 用户以“【长期记忆】分类：convention；标识：case_review_meeting_schedule”的格式记录该约定。
implicit_traits:
- trait: 边界敏感的严谨型思维
  description: 用户在测试与验证工作中高度重视临界条件，倾向于穷举边界点以确保覆盖完整、避免边缘遗漏。
  basis: 用户记录规则时特意列出三个连续的临界时间点（04:59/05:00/05:01），并补充限时活动校验点应包含活动开始/结束时刻与自然日切换点，说明其关注的不只是整点，而是完整的边界时刻集合。
  evidence: 2026-08-31 用户记录跨天重置规则要求覆盖周一 04:59/05:00/05:01；同日又记录限时活动重置校验点应包含活动开始/结束时刻与自然日切换点。
- trait: 结构化知识管理者
  description: 用户偏好用清晰的分类和标签体系来沉淀经验，并会将同一套“分类+标识+内容”格式反复用于不同主题，重视知识的规范性、可检索性与后续复用。
  basis: 用户多次以完全相同的【长期记忆】固定格式写入不同知识（domain_knowledge/boundary_rule、domain_knowledge/daily_reset、convention/feishu_export、convention/case_review_meeting_schedule），每次都指定独立分类与标识，说明结构化知识管理是其稳定的行为模式。
  evidence: 2026-08-31 用户以该格式写入 daily_reset 与 feishu_export 两条记忆；2026-09-02 又写入 case_review_meeting_schedule；此前已有
    boundary_rule 记录。
- trait: 风险规避的规则沉淀者
  description: 用户倾向于将操作中易导致失败的前置条件、数量上限、时间节点和兜底策略固化为明确规则，以降低出错概率，属于[风险规避]、[规则导向]型人格。
  basis: 从跨天重置场景的“必须覆盖”、飞书导出的“parent必须已存在、单批不超过50、否则分层分块”，到用例评审“预留时间在周三 10 点前完成准备以免错过”，用户记录的不是孤立经验，而是一系列防错与防遗漏规则，说明其有意识规避技术及流程风险。
  evidence: 2026-09-02 用户记录用例评审会约定时明确给出准备截止节点与错过风险；2026-08-31 记录飞书导出约定时给出前置条件、批量上限和异常兜底方案；此前记录跨天边界规则时同样使用“必须覆盖”的防漏措辞。
profile_timestamp_ms: 1788322228250
---
用户掌握并记录了跨天重置场景的测试规则，即必须覆盖周一 04:59、05:00、05:01 三个临界时间点。
