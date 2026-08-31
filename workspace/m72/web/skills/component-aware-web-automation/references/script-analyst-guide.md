# Agent 1 — Script Analyst / 剧本分析师 指导手册

## 使命与职责

剧本分析师是整个组件感知自动化流水线的起点。我们的使命是：

- **扫描源代码**：深入项目源码，发现所有UI组件的定义与使用
- **提取组件语义**：从代码中提取组件的 props、state、交互行为、条件渲染逻辑
- **构建组件注册表**：将提取结果结构化为标准化的 JSON 注册表，供下游 Agent 使用

我们的输出是所有后续 Agent 的基础数据源。注册表的质量直接决定整条流水线的成败。

---

## 各框架提取模式

### React 提取模式

React 组件以函数组件为主流（class component 已趋淘汰），提取重点：

**1. 函数组件识别**
```bash
# 匹配 export default function ComponentName 或 const ComponentName = ...
grep -rE '(export\s+default\s+function|const\s+)\w+[A-Z]\w*\s*(=|\(|<)' src/
```

**2. Props 提取**
- TypeScript interface/type 定义：搜索 `interface Props` 或 `type Props`
- 默认 props：搜索 `.defaultProps` 或函数参数默认值
- Props 解构：从 `(props)` 或 `({ prop1, prop2 })` 参数中提取

**3. State 提取**
- `useState` 调用：提取初始值与 setter 名称
- `useReducer`：提取 reducer 函数名与初始 state
- Context consumers：提取 `useContext(MyContext)` 引用

**4. 交互元素提取**
- onClick / onSubmit / onChange / onInput / onFocus / onBlur
- 表单元素：input, button, select, textarea, a[href]
- 第三方组件：识别 `<Button onClick>`, `<Input onChange>` 等语义化组件

**5. 条件渲染提取**
- 三元表达式：`condition ? <A /> : <B />`
- && 运算符：`condition && <Component />`
- Switch/枚举模式：`{type === 'success' && <SuccessIcon />}`

**6. Feature Flags**
- `if (featureFlag.xxx)` 条件分支
- `useFeatureFlag('xxx')` 调用
- 环境变量条件：`process.env.ENABLE_XXX`

### Vue 提取模式

Vue 组件分 SFC（单文件组件）与 Composition API 两种主流风格：

**1. SFC 识别**
```bash
# 匹配 .vue 文件
find src/ -name '*.vue' -type f
```

**2. Props 提取**
- `defineProps<T>()` TypeScript 泛型定义
- `props: { ... }` Options API 定义（含 type, required, default）
- `withDefaults(defineProps<T>(), { ... })` 默认值

**3. State / 响应式提取**
- `ref(value)` → 提取 ref 名称与初始值
- `reactive({ ... })` → 提取响应式对象字段
- `computed(() => ...)` → 提取计算属性名称与依赖

**4. 交互元素提取**
- `@click`, `@submit`, `@change`, `@input`, `@focus`, `@blur`
- v-model 双向绑定：`v-model="xxx"`, `v-model:value`
- template 中的 `<button>`, `<input>`, `<select>`, `<a>`

**5. 条件渲染提取**
- `v-if`, `v-else`, `v-else-if` 指令
- `v-show` 指令（CSS 级切换）
- `<component :is="xxx">` 动态组件

**6. Feature Flags**
- `v-if="featureFlags.xxx"` 模板条件
- `if (featureFlags.xxx)` script 条件
- `useFeatureFlag('xxx')` Composable

### Angular 提取模式

Angular 使用 TypeScript class + decorator 模式：

**1. 组件识别**
```bash
grep -rE '@Component\s*\(' src/ --include='*.ts'
```

**2. Props（@Input）提取**
- `@Input() propName: Type` 或 `@Input('alias') propName`
- `@Input() propName = defaultValue`

**3. State 提取**
- 类属性直接声明：`isVisible = false`
- BehaviorSubject / Observable：`private data$ = new BehaviorSubject<T>(init)`
- Signals（Angular 17+）：`count = signal(0)`

**4. 交互元素提取**
- `(click)`, `(submit)`, `(change)`, `(input)`
- 模板引用变量：`#myInput`
- Angular Material 组件：`<mat-button>`, `<mat-input>` 等

**5. 条件渲染提取**
- `*ngIf="condition"` 含 else 模板
- `*ngSwitch`, `*ngSwitchCase`, `*ngSwitchDefault`
- `[hidden]="condition"` CSS 级隐藏

### Svelte 提取模式

**1. 组件识别**
```bash
find src/ -name '*.svelte' -type f
```

**2. Props 提取**
- `export let propName: Type = default` 声明
- `export let propName` 无类型声明

**3. State 提取**
- `let count = 0` 本地状态
- `$: doubled = count * 2` 响应式声明
- Svelte 5 runes：`$state(0)`, `$derived(x)`

**4. 交互元素提取**
- `on:click`, `on:submit`, `on:change`
- bind: `bind:value`, `bind:checked`

**5. 条件渲染提取**
- `{#if condition}`, `{:else}`, `{:else if condition}`
- `{#each items as item}` 循环渲染

---

## 组件注册表 Schema

```json
{
  "$schema": "https://component-aware.schema/v1/registry",
  "metadata": {
    "repo": "https://github.com/org/project",
    "branch": "main",
    "framework": "react",
    "scanTimestamp": "2026-04-18T12:00:00Z",
    "totalComponents": 42
  },
  "components": [
    {
      "id": "LoginForm",
      "filePath": "src/components/LoginForm.tsx",
      "framework": "react",
      "type": "function-component",
      "props": [
        {
          "name": "onSubmit",
          "type": "(credentials: Credentials) => void",
          "required": true,
          "defaultValue": null,
          "description": "登录成功回调"
        },
        {
          "name": "isLoading",
          "type": "boolean",
          "required": false,
          "defaultValue": "false",
          "description": "加载状态"
        },
        {
          "name": "errorMessage",
          "type": "string | null",
          "required": false,
          "defaultValue": "null",
          "description": "错误消息"
        }
      ],
      "state": [
        {
          "name": "email",
          "type": "string",
          "initialValue": "",
          "setter": "setEmail"
        },
        {
          "name": "password",
          "type": "string",
          "initialValue": "",
          "setter": "setPassword"
        },
        {
          "name": "rememberMe",
          "type": "boolean",
          "initialValue": "false",
          "setter": "setRememberMe"
        }
      ],
      "interactiveElements": [
        {
          "elementType": "input",
          "role": "email-input",
          "binding": "email",
          "handler": "onChange → setEmail",
          "attributes": { "type": "email", "placeholder": "Enter email" }
        },
        {
          "elementType": "input",
          "role": "password-input",
          "binding": "password",
          "handler": "onChange → setPassword",
          "attributes": { "type": "password" }
        },
        {
          "elementType": "input",
          "role": "remember-checkbox",
          "binding": "rememberMe",
          "handler": "onChange → setRememberMe",
          "attributes": { "type": "checkbox" }
        },
        {
          "elementType": "button",
          "role": "submit-button",
          "binding": null,
          "handler": "onClick → handleSubmit",
          "attributes": { "type": "submit", "disabled": "isLoading" }
        }
      ],
      "conditionalRendering": [
        {
          "condition": "errorMessage !== null",
          "renders": "ErrorAlert",
          "type": "error-state"
        },
        {
          "condition": "isLoading",
          "renders": "SpinnerOverlay",
          "type": "loading-state"
        }
      ],
      "featureFlags": [],
      "childComponents": ["ErrorAlert", "SpinnerOverlay"],
      "accessibilityInfo": {
        "ariaLabels": ["form[aria-label='Login form']"],
        "roles": ["form[role='form']"]
      }
    }
  ]
}
```

---

## 噪音过滤规则

提取过程中会遇到大量噪音，必须按以下规则过滤：

| 规则编号 | 噪音类型 | 过滤策略 |
|---------|---------|---------|
| NF-01 | 内部工具函数（非UI组件） | 忽略不以大写字母开头的 export（React约定） |
| NF-02 | HOC / Wrapper 函数 | 仅提取最终渲染的组件，跳过中间包装层 |
| NF-03 | Storybook stories | 标记为 `type: "story"`，不作为主组件注册 |
| NF-04 | Test 文件中的 mock 组件 | 忽略 `*.test.*`, `*.spec.*` 中的组件定义 |
| NF-05 | 类型定义文件 | 忽略 `*.d.ts` 中的 interface/type，仅提取有实现的 |
| NF-06 | 第三方库组件引用 | 仅记录使用，不注册为项目组件 |
| NF-07 | CSS-in-JS 样式组件 | 标记 `type: "styled-component"`，不提取交互语义 |
| NF-08 | Fragment 容器 | 忽略 `<Fragment>` / `<></>` 等纯容器 |
| NF-09 | Provider 组件 | 标记 `type: "context-provider"`，不提取交互语义 |
| NF-10 | Portal 渲染目标 | 仅记录 portal target，不作为独立组件 |

---

## 实战示例

### React LoginForm 提取流程

```
步骤 1: 发现 → grep 发现 src/components/LoginForm.tsx
步骤 2: 读取 → 文件内容解析
步骤 3: Props → 识别 interface LoginFormProps { onSubmit, isLoading, errorMessage }
步骤 4: State → 识别 useState(email), useState(password), useState(rememberMe)
步骤 5: 交互 → 识别 <input type="email>, <input type="password>, <input type="checkbox>, <button type="submit>
步骤 6: 条件 → 识别 errorMessage && <ErrorAlert />, isLoading && <SpinnerOverlay />
步骤 7: 注册 → 写入组件注册表 JSON
```

### Vue DataTable 提取流程

```
步骤 1: 发现 → find 发现 src/components/DataTable.vue
步骤 2: 读取 → SFC 三段（template + script + style）解析
步骤 3: Props → 识别 defineProps<{ columns, data, sortable, pageSize }>
步骤 4: State → 识别 ref(currentPage), ref(sortColumn), ref(sortDirection), ref(selectedRows)
步骤 5: 交互 → 识别 @click="handleSort", @click="handlePageChange", v-model="searchQuery"
步骤 6: 条件 → 识别 v-if="sortable", v-if="data.length === 0"
步骤 7: 注册 → 写入组件注册表 JSON
```

---

## 最佳实践

1. **全量扫描**：不要遗漏任何组件目录，包括 `pages/`, `views/`, `layouts/`
2. **语义优先**：提取时关注业务语义而非代码结构细节
3. **版本标注**：注册表中标注框架版本（如 React 18, Vue 3, Angular 17）
4. **增量更新**：支持 diff 模式，仅提取变更组件而非全量重建
5. **验证闭环**：提取完成后运行 schema 验证，确保 JSON 格式合规