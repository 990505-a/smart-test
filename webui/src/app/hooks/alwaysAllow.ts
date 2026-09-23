/**
 * 审批「始终允许」规则（会话内生效，localStorage 持久化到本会话）。
 *
 * 设计取向（对齐 Claude Code 的 allow 规则而非裸的 allowed-once）：
 * - execute：按**程序名**放行（命令首 token 取 basename，如 python / npx /
 *   pytest）——测试会话里智能体会反复跑同一工具链，命令参数每次都不同，
 *   精确匹配整条命令等于没有「始终允许」。
 * - write_file / edit_file / delete：按**目录前缀**放行——授权写
 *   D:\repo\src 就放行它下面的所有文件（挂载仓库场景批量落盘）。
 * - 其他受控工具（能力里 human_gated 的业务动作）：按工具名放行。
 *
 * 匹配是保守的：认不出形态的操作不匹配任何规则，照常弹卡片。
 * 范围只到「本会话」：跨会话自动放行越权操作的口子不开。
 */

export type AlwaysAllowRule =
  | { kind: "execute"; program: string }
  | { kind: "write"; dir: string }
  | { kind: "tool"; name: string };

/** 会触发审批的文件写入类工具（与后端 permission_gate._WRITE_TOOLS 对齐）。 */
const WRITE_TOOLS = new Set(["write_file", "edit_file", "delete"]);

export interface ApprovableAction {
  name: string;
  command: string;
  args: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// 归一化
// ---------------------------------------------------------------------------

/** 路径归一：反斜杠→正斜杠、去首尾空白。比较时再统一小写（Windows 语义）。 */
function normalizePath(raw: string): string {
  return raw.trim().replace(/\\/g, "/").replace(/\/+$/, "");
}

/** 取命令的程序名：首段（遇 && ; | 换行截断）→ 首 token → basename → 小写。 */
export function commandProgram(command: string): string {
  const firstSegment = command.split(/&&|\|\||[;|\n]/)[0] ?? "";
  const firstToken = (firstSegment.trim().split(/\s+/)[0] ?? "").replace(/^["']|["']$/g, "");
  if (!firstToken) return "";
  const base = firstToken.split(/[\\/]/).pop() ?? firstToken;
  // Windows 上 python.exe 与 python 是同一个程序
  return base.toLowerCase().replace(/\.exe$/, "");
}

/** 文件写入类动作的目标目录（无路径返回空串）。 */
function writeDir(path: string): string {
  const normalized = normalizePath(path);
  if (!normalized) return "";
  const idx = normalized.lastIndexOf("/");
  return idx === -1 ? "" : normalized.slice(0, idx);
}

// ---------------------------------------------------------------------------
// 规则生成与匹配
// ---------------------------------------------------------------------------

/** 从一次审批的动作生成「始终允许」规则（每个动作一条）。 */
export function rulesFromActions(actions: ApprovableAction[]): AlwaysAllowRule[] {
  const rules: AlwaysAllowRule[] = [];
  for (const action of actions) {
    if (action.name === "execute") {
      const program = commandProgram(action.command);
      if (program) rules.push({ kind: "execute", program });
    } else if (WRITE_TOOLS.has(action.name)) {
      const dir = writeDir(String(action.args?.file_path ?? ""));
      if (dir) rules.push({ kind: "write", dir });
    } else {
      rules.push({ kind: "tool", name: action.name });
    }
  }
  return rules;
}

/** 单个动作是否命中一条规则。 */
export function actionMatchesRule(action: ApprovableAction, rule: AlwaysAllowRule): boolean {
  if (rule.kind === "execute") {
    return action.name === "execute" && commandProgram(action.command) === rule.program;
  }
  if (rule.kind === "write") {
    if (!WRITE_TOOLS.has(action.name)) return false;
    const target = normalizePath(String(action.args?.file_path ?? ""));
    if (!target) return false;
    const t = target.toLowerCase();
    const d = rule.dir.toLowerCase();
    return t === d || t.startsWith(`${d}/`);
  }
  return action.name === rule.name;
}

/** 一批动作是否**全部**命中（部分命中仍要弹卡片——decisions 必须整批放行）。 */
export function allActionsMatch(actions: ApprovableAction[], rules: AlwaysAllowRule[]): boolean {
  if (actions.length === 0 || rules.length === 0) return false;
  return actions.every((action) => rules.some((rule) => actionMatchesRule(action, rule)));
}

// ---------------------------------------------------------------------------
// 存储（按会话隔离；node/test 环境无 localStorage 时退化为内存）
// ---------------------------------------------------------------------------

const STORAGE_KEY = "smart-test:always-allow";
const MAX_RULES_PER_THREAD = 50;

// node/test 环境没有 localStorage 时的内存兜底（模块级单例，页面生命周期内有效）
const _memoryStore = new Map<string, string>();

function backingStore(): Pick<Storage, "getItem" | "setItem"> {
  if (typeof window !== "undefined" && window.localStorage) return window.localStorage;
  return {
    getItem: (k: string) => (_memoryStore.has(k) ? (_memoryStore.get(k) as string) : null),
    setItem: (k: string, v: string) => void _memoryStore.set(k, v),
  };
}

function loadAll(): Record<string, AlwaysAllowRule[]> {
  try {
    const raw = backingStore().getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, AlwaysAllowRule[]>;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function loadAlwaysAllowRules(threadId: string): AlwaysAllowRule[] {
  if (!threadId) return [];
  return loadAll()[threadId] ?? [];
}

export function saveAlwaysAllowRules(threadId: string, rules: AlwaysAllowRule[]): void {
  if (!threadId) return;
  const all = loadAll();
  // 只留最近 MAX 条（新授权在前）
  all[threadId] = rules.slice(-MAX_RULES_PER_THREAD).reverse();
  try {
    backingStore().setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    // 存储满/隐私模式：规则退化为仅本次页面生命周期内可用（调用方内存里仍有）
  }
}

/** 追加规则（「始终允许」按钮的入口）。 */
export function addAlwaysAllowRules(threadId: string, rules: AlwaysAllowRule[]): void {
  if (!threadId || rules.length === 0) return;
  const existing = loadAlwaysAllowRules(threadId);
  // 简单去重（JSON 相等即同规则）
  const seen = new Set(existing.map((r) => JSON.stringify(r)));
  const merged = [...existing];
  for (const rule of rules) {
    const key = JSON.stringify(rule);
    if (!seen.has(key)) {
      seen.add(key);
      merged.push(rule);
    }
  }
  saveAlwaysAllowRules(threadId, merged);
}
