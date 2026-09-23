/**
 * 「始终允许」规则匹配单元测试（alwaysAllow.ts）。
 *
 * 规则口径：execute 按程序名放行（参数变化不影响）、写入类按目录前缀放行、
 * 其他受控工具按工具名放行；一批动作必须**全部**命中才自动放行。
 */
import { beforeEach, describe, expect, it } from "vitest";
import {
  addAlwaysAllowRules,
  allActionsMatch,
  commandProgram,
  loadAlwaysAllowRules,
  rulesFromActions,
  type AlwaysAllowRule,
  type ApprovableAction,
} from "./alwaysAllow";

const exec = (command: string): ApprovableAction => ({
  name: "execute",
  command,
  args: { command },
});
const write = (file_path: string): ApprovableAction => ({
  name: "write_file",
  command: "",
  args: { file_path },
});

describe("commandProgram", () => {
  it("取命令首 token 的程序名（basename + 去引号 + 小写 + 去 .exe）", () => {
    expect(commandProgram("python run_case.py --case 1")).toBe("python");
    expect(commandProgram('"C:\\Tools\\pytest.exe" -q')).toBe("pytest");
    expect(commandProgram("rg -n \"a|b\" src && cat x")).toBe("rg");
    expect(commandProgram("git branch -D feat")).toBe("git");
    expect(commandProgram("")).toBe("");
  });
});

describe("rulesFromActions", () => {
  it("execute → 程序名规则；write_file → 目录规则；其他 → 工具名规则", () => {
    const rules = rulesFromActions([
      exec("python a.py"),
      write("D:\\repo\\src\\a.ts"),
      { name: "approve_case_document", command: "", args: {} },
    ]);
    expect(rules).toEqual([
      { kind: "execute", program: "python" },
      { kind: "write", dir: "D:/repo/src" },
      { kind: "tool", name: "approve_case_document" },
    ]);
  });
});

describe("allActionsMatch", () => {
  const pyRule: AlwaysAllowRule = { kind: "execute", program: "python" };
  const srcRule: AlwaysAllowRule = { kind: "write", dir: "D:/repo/src" };

  it("execute：同程序不同参数也放行；不同程序不放行", () => {
    expect(allActionsMatch([exec("python b.py --x 2")], [pyRule])).toBe(true);
    expect(allActionsMatch([exec("node server.js")], [pyRule])).toBe(false);
  });

  it("write：目录前缀放行（含大小写/反斜杠差异）；越出目录不放行", () => {
    expect(allActionsMatch([write("d:\\REPO\\src\\deep\\c.ts")], [srcRule])).toBe(true);
    expect(allActionsMatch([write("D:/repo/test/c.ts")], [srcRule])).toBe(false);
  });

  it("一批动作必须全部命中，部分命中仍要弹卡片", () => {
    expect(allActionsMatch([exec("python a.py"), exec("node x.js")], [pyRule])).toBe(false);
    expect(
      allActionsMatch([exec("python a.py"), exec("node x.js")], [pyRule, { kind: "execute", program: "node" }]),
    ).toBe(true);
  });

  it("edit_file/delete 与 write_file 同一套目录规则", () => {
    const rules = rulesFromActions([write("D:\\repo\\src\\a.ts")]);
    expect(
      allActionsMatch(
        [
          { name: "edit_file", command: "", args: { file_path: "D:\\repo\\src\\a.ts" } },
          { name: "delete", command: "", args: { file_path: "D:/repo/src/sub" } },
        ],
        rules,
      ),
    ).toBe(true);
  });

  it("空动作/空规则不匹配", () => {
    expect(allActionsMatch([], [pyRule])).toBe(false);
    expect(allActionsMatch([exec("python a")], [])).toBe(false);
  });
});

describe("storage", () => {
  beforeEach(() => {
    // node 环境无 localStorage，模块内部退化为内存 store：直接测读写闭环
  });

  it("按会话隔离：A 会话的规则不影响 B 会话", () => {
    addAlwaysAllowRules("thread-a", [{ kind: "execute", program: "python" }]);
    expect(allActionsMatch([exec("python x.py")], loadAlwaysAllowRules("thread-a"))).toBe(true);
    expect(allActionsMatch([exec("python x.py")], loadAlwaysAllowRules("thread-b"))).toBe(false);
  });

  it("重复授权去重", () => {
    addAlwaysAllowRules("t1", [{ kind: "execute", program: "python" }]);
    addAlwaysAllowRules("t1", [{ kind: "execute", program: "python" }]);
    const rules = loadAlwaysAllowRules("t1");
    expect(rules.filter((r) => r.kind === "execute").length).toBe(1);
  });
});
