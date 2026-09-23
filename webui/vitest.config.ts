import { defineConfig } from "vitest/config";
import path from "node:path";

/**
 * vitest 独立配置：唯一要做的事是把 tsconfig 的 `@/*` 路径别名接进来。
 *
 * 没有这个配置时，被测模块一旦 `@/…` 导入（项目里的普遍写法）就无法在
 * vitest 里解析——此前几个测试文件（cancellation / subagentActivity /
 * useTodos）全靠相对路径导入才跑得起来，等于逼着新代码迁就测试工具。
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "node",
  },
});
