/**
 * 行级 diff —— 用于「AI 自修复把用例改成什么样了」。
 *
 * 自己实现而不是引第三方：只需要「并排看改了哪几行」，LCS 三十行就够，
 * 不值得为此加一个依赖（diff 库在浏览器里动辄上百 KB）。
 */

export type DiffOp = { type: "same" | "add" | "del"; text: string; leftNo?: number; rightNo?: number };

/** 最长公共子序列的动态规划表，O(n*m) 内存；spec 文件量级（几百行）完全够用。 */
function lcsMatrix(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j]
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

export function diffLines(before: string, after: string): DiffOp[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const table = lcsMatrix(a, b);
  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  let leftNo = 1;
  let rightNo = 1;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      ops.push({ type: "same", text: a[i], leftNo: leftNo++, rightNo: rightNo++ });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      ops.push({ type: "del", text: a[i], leftNo: leftNo++ });
      i += 1;
    } else {
      ops.push({ type: "add", text: b[j], rightNo: rightNo++ });
      j += 1;
    }
  }
  while (i < a.length) ops.push({ type: "del", text: a[i++], leftNo: leftNo++ });
  while (j < b.length) ops.push({ type: "add", text: b[j++], rightNo: rightNo++ });
  return ops;
}

/** 变更摘要：加了/删了多少行，用来在列表里给一句人话。 */
export function diffSummary(before: string, after: string): { added: number; removed: number } {
  const ops = diffLines(before, after);
  return {
    added: ops.filter((op) => op.type === "add").length,
    removed: ops.filter((op) => op.type === "del").length,
  };
}
