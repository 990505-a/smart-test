/**
 * 取消决策逻辑单元测试（cancellation.ts）。
 *
 * 每个用例对应一个真实竞态场景，断言决策函数在服务端状态滞后窗口内
 * （cancelMany 的 interrupt 要等下一个检查点才生效）的行为。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CANCELLED_RUNS_KEY,
  type RunLike,
  loadCancelledRuns,
  persistCancelledRuns,
  pickActiveRun,
  pruneTombstones,
  shouldCancelAbortedRun,
} from "./cancellation";

// ---- sessionStorage 桩（node 环境没有 window） -----------------------------
class MemoryStorage {
  private map = new Map<string, string>();
  getItem(key: string) {
    return this.map.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.map.set(key, value);
  }
  removeItem(key: string) {
    this.map.delete(key);
  }
}

let storage: MemoryStorage;

beforeEach(() => {
  storage = new MemoryStorage();
  vi.stubGlobal("window", { sessionStorage: storage });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---- 墓碑持久化 ------------------------------------------------------------

describe("loadCancelledRuns / persistCancelledRuns", () => {
  it("空存储 → 空 Map", () => {
    expect(loadCancelledRuns().size).toBe(0);
  });

  it("持久化 → 读取 round-trip 保真（多线程多 run）", () => {
    const map = new Map<string, Set<string>>([
      ["thread-a", new Set(["run-1", "run-2"])],
      ["thread-b", new Set(["run-3"])],
    ]);
    persistCancelledRuns(map);

    const loaded = loadCancelledRuns();
    expect(loaded.get("thread-a")).toEqual(new Set(["run-1", "run-2"]));
    expect(loaded.get("thread-b")).toEqual(new Set(["run-3"]));
  });

  it("写入的 JSON 形状为 { threadId: [runId, ...] }", () => {
    persistCancelledRuns(new Map([["t", new Set(["r1", "r2"])]]));
    expect(storage.getItem(CANCELLED_RUNS_KEY)).toBe(
      JSON.stringify({ t: ["r1", "r2"] }),
    );
  });

  it("损坏的 JSON → 返回空 Map 而非抛异常", () => {
    storage.setItem(CANCELLED_RUNS_KEY, "{not json");
    expect(loadCancelledRuns().size).toBe(0);
  });

  it("SSR（无 window）→ 读取返回空 Map、写入为 no-op 不抛异常", () => {
    vi.unstubAllGlobals();
    expect(loadCancelledRuns().size).toBe(0);
    expect(() =>
      persistCancelledRuns(new Map([["t", new Set(["r"])]])),
    ).not.toThrow();
  });
});

// ---- 重连活流选择（核心：原 bug 的决策点） ----------------------------------

describe("pickActiveRun", () => {
  it("无墓碑时选中 running run（原有回归：真活流照常重连）", () => {
    const runs: RunLike[] = [{ status: "success" }, { status: "running", run_id: "r1" }];
    expect(pickActiveRun(runs)?.run_id).toBe("r1");
  });

  it("pending run 也算活流", () => {
    const runs: RunLike[] = [{ status: "pending", run_id: "r1" }];
    expect(pickActiveRun(runs)?.run_id).toBe("r1");
  });

  it("【本次 bug 回归】running 与 pending 并存时优先 running", () => {
    // runs.list 按创建时间倒序时，最新的 pending 可能排在真正 running 前面；
    // 重连必须订阅 running，否则 joinStream 没有实时事件。
    const runs: RunLike[] = [
      { status: "pending", run_id: "queued-resume" },
      { status: "running", run_id: "actual-stream" },
    ];
    expect(pickActiveRun(runs)?.run_id).toBe("actual-stream");
  });

  it("终态（success/error/timeout/interrupted）不选中", () => {
    for (const status of ["success", "error", "timeout", "interrupted"]) {
      expect(pickActiveRun([{ status, run_id: "r1" }])).toBeUndefined();
    }
  });

  it("【原 bug 场景】用户停止后、服务端仍报 running 的 run 被墓碑挡下", () => {
    // 停止 → cancelMany 已发但 interrupt 等检查点 → runs.list 仍 running
    const runs: RunLike[] = [{ status: "running", run_id: "dying-run" }];
    const tomb = new Set(["dying-run"]);
    expect(pickActiveRun(runs, tomb)).toBeUndefined();
  });

  it("墓碑 run + 更新的真活 run → 选中新 run（切回会话接上真流）", () => {
    // runs.list 按时间倒序：新 run 在前，被取消的旧 run 在后
    const runs: RunLike[] = [
      { status: "running", run_id: "new-run" },
      { status: "running", run_id: "cancelled-run" },
    ];
    const tomb = new Set(["cancelled-run"]);
    expect(pickActiveRun(runs, tomb)?.run_id).toBe("new-run");
  });

  it("全部活跃 run 都在墓碑里 → 不选中任何一个", () => {
    const runs: RunLike[] = [
      { status: "running", run_id: "a" },
      { status: "pending", run_id: "b" },
    ];
    const tomb = new Set(["a", "b"]);
    expect(pickActiveRun(runs, tomb)).toBeUndefined();
  });

  it("墓碑为 undefined → 不做过滤（与旧行为一致）", () => {
    expect(pickActiveRun([{ status: "running", run_id: "r" }], undefined)?.run_id).toBe("r");
  });
});

// ---- 墓碑清理 --------------------------------------------------------------

describe("pruneTombstones", () => {
  it("清掉已离开活跃列表的墓碑项，保留仍在跑的", () => {
    const tomb = new Set(["stale-1", "stale-2", "still-active"]);
    const activeRuns: RunLike[] = [
      { status: "running", run_id: "still-active" },
      { status: "success", run_id: "other" },
    ];
    const changed = pruneTombstones(tomb, activeRuns);
    expect(changed).toBe(true);
    expect(tomb).toEqual(new Set(["still-active"]));
  });

  it("无变更时返回 false（调用方不必重写 sessionStorage）", () => {
    const tomb = new Set(["still-active"]);
    const changed = pruneTombstones(tomb, [{ status: "running", run_id: "still-active" }]);
    expect(changed).toBe(false);
    expect(tomb.size).toBe(1);
  });

  it("空墓碑 → false", () => {
    expect(pruneTombstones(new Set(), [{ status: "running", run_id: "r" }])).toBe(false);
  });

  it("活跃列表里缺 run_id 的条目不参与判定", () => {
    const tomb = new Set(["r1"]);
    const changed = pruneTombstones(tomb, [{ status: "running" }]);
    expect(changed).toBe(true);
    expect(tomb.size).toBe(0);
  });
});

// ---- 中止后补刀守卫（防误杀同线程新 run） ----------------------------------

describe("shouldCancelAbortedRun", () => {
  it("owner 为 undefined（用户停止，stopStream 已删条目）→ 允许取消", () => {
    const mine = new AbortController();
    expect(shouldCancelAbortedRun(undefined, mine)).toBe(true);
  });

  it("owner 仍是自己的 controller（停止且未被顶替）→ 允许取消", () => {
    const mine = new AbortController();
    expect(shouldCancelAbortedRun(mine, mine)).toBe(true);
  });

  it("owner 已换成新 controller（被同线程新发送顶替）→ 拒绝，防误杀新 run", () => {
    const mine = new AbortController();
    const newer = new AbortController();
    expect(shouldCancelAbortedRun(newer, mine)).toBe(false);
  });
});

// ---- 组合场景：完整决策链时序（不打 React，纯函数串联） --------------------

describe("取消→切换→切回 的决策链时序", () => {
  it("停止后服务端状态滞后窗口内切回：不选活流；收敛后墓碑被清", () => {
    // t0: 用户停止 dying-run（stopStream: abort + 墓碑 + cancelMany）
    const tomb = new Set(["dying-run"]);

    // t1: cancelMany 已发但 interrupt 未生效，runs.list 仍报 running
    //     ——用户此时切回会话，重连决策：
    let runs: RunLike[] = [{ status: "running", run_id: "dying-run" }];
    expect(pickActiveRun(runs, tomb)).toBeUndefined(); // ← 不再假「输出中」

    // t2: 服务端收敛，run 进入终态
    runs = [{ status: "error", run_id: "dying-run" }];
    expect(pickActiveRun(runs, tomb)).toBeUndefined();

    // t3: 下次重连时墓碑项被清（防无限增长）
    expect(pruneTombstones(tomb, runs)).toBe(true);
    expect(tomb.size).toBe(0);
  });

  it("停止→立刻发新消息→旧流 finally 补刀被守卫拦下，新 run 存活", () => {
    const oldController = new AbortController();
    const newController = new AbortController();
    // 新发送顶替：abort 旧 controller 并写入 abortMapRef[tid] = newController
    oldController.abort();
    const ownerAfterSupersede: AbortController | undefined = newController;
    // 旧流的 finally 补刀守卫：
    expect(shouldCancelAbortedRun(ownerAfterSupersede, oldController)).toBe(false);
    // 新 run 不在墓碑里，若用户切走再切回，重连照常接上：
    const tomb = new Set<string>(); // 墓碑里只有旧 run（略），新 run 不在
    const runs: RunLike[] = [{ status: "running", run_id: "new-run" }];
    expect(pickActiveRun(runs, tomb)?.run_id).toBe("new-run");
  });
});
