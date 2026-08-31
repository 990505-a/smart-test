/**
 * 会话取消的纯决策逻辑（从 useChat.ts 抽出以便单元测试）。
 *
 * 背景：LangGraph 的 cancelMany 默认 interrupt 动作要等下一个检查点才
 * 生效，期间 runs.list 仍报 running/pending。重连逻辑若只信服务端状态，
 * 会把「正在死去的 run」误判为活流——切回会话就出现假「输出中」且无输出。
 * 墓碑（tombstone）= 客户端的取消记忆，是服务端异步收敛期间的权威过滤依据。
 */

/** sessionStorage key：墓碑需要撑过页面刷新。 */
export const CANCELLED_RUNS_KEY = "stp.chat.cancelledRuns.v1";

/** runs.list 返回项的最小形状（避免测试依赖 SDK 类型）。 */
export interface RunLike {
  status?: string;
  run_id?: string;
}

export function loadCancelledRuns(): Map<string, Set<string>> {
  if (typeof window === "undefined") return new Map();
  try {
    const raw = window.sessionStorage.getItem(CANCELLED_RUNS_KEY);
    if (!raw) return new Map();
    const parsed = JSON.parse(raw) as Record<string, string[]>;
    return new Map(
      Object.entries(parsed).map(([tid, ids]) => [tid, new Set(ids)]),
    );
  } catch {
    return new Map();
  }
}

export function persistCancelledRuns(map: Map<string, Set<string>>) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      CANCELLED_RUNS_KEY,
      JSON.stringify(
        Object.fromEntries([...map].map(([tid, ids]) => [tid, [...ids]])),
      ),
    );
  } catch {
    // 存储满/隐私模式——墓碑退化为仅内存态，功能仍可用
  }
}

/**
 * 重连时从 runs.list 结果里选活流 run：跳过墓碑项（用户取消过、服务端
 * 状态尚未收敛的 run 不算活流）。
 */
export function pickActiveRun(
  runs: RunLike[],
  tombstone?: Set<string>,
): RunLike | undefined {
  // runs.list 通常按创建时间倒序返回。一个线程可能同时存在“真正执行中的
  // running”和排队等待的 pending（例如恢复/续跑后），必须优先订阅 running；
  // 否则 joinStream 会连到尚未产出事件的 pending，页面只能刷新后靠历史接口
  // 看到最新内容。
  const candidates = runs.filter(
    (r) =>
      (r.status === "running" || r.status === "pending") &&
      !tombstone?.has(r.run_id as string),
  );
  return candidates.find((r) => r.status === "running") ?? candidates[0];
}

/**
 * 清理已不再活跃（进入终态或滚出列表）的墓碑项（防集合无限增长）。
 * 原地删除；返回是否有变更，调用方据此决定是否持久化。
 */
export function pruneTombstones(tomb: Set<string>, runs: RunLike[]): boolean {
  const activeIds = new Set(
    runs
      .filter((r) => r.status === "running" || r.status === "pending")
      .map((r) => r.run_id)
      .filter((id): id is string => !!id),
  );
  let changed = false;
  for (const id of tomb) {
    if (!activeIds.has(id)) {
      tomb.delete(id);
      changed = true;
    }
  }
  return changed;
}

/**
 * 中止后的补刀守卫（sendMessage/resumeInterrupt 的 finally 用）：
 * - owner 为 undefined：用户停止（stopStream 已删除条目）→ 允许取消
 * - owner 仍是自己的 controller → 允许取消
 * - owner 已换成别的 controller：被同线程的新发送顶替，此时取消会
 *   误杀新 run → 拒绝
 */
export function shouldCancelAbortedRun(
  owner: AbortController | undefined,
  mine: AbortController,
): boolean {
  return owner === undefined || owner === mine;
}
