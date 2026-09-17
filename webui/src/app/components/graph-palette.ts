/**
 * 代码图谱的展示常量（与 WebGL 渲染解耦）。
 *
 * 为什么要单独一个文件：渲染层 `GraphView` 依赖 sigma（WebGL），而它的模块顶层
 * 就引用了 `WebGL2RenderingContext`——在 Node（SSR / 预渲染）里 require 会直接抛
 * `ReferenceError`。颜色与节点类型是纯数据，页面（图例、详情卡）也要用，放在这里
 * 就能让页面不经过 sigma 拿到它们，渲染层再用 next/dynamic(ssr:false) 加载。
 */

export interface GraphNodeInfo {
  id: number;
  name: string;
  label: string;
  qualified_name?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  color: string;
  status?: string;
  in_calls?: number;
}

/** 节点 label → 颜色(与页面图例一致) */
export const NODE_PALETTE: Record<string, string> = {
  Function: "#3b82f6",
  Method: "#3b82f6",
  Class: "#a78bfa",
  Interface: "#a78bfa",
  Struct: "#a78bfa",
  Route: "#f472b6",
  Variable: "#fbbf24",
  Constant: "#fbbf24",
  File: "#94a3b8",
  Module: "#cbd5e1",
  Folder: "#94a3b8",
  Section: "#cbd5e1",
};

/** 结构类节点（默认隐藏，只看代码符号） */
export const STRUCTURAL_LABELS = new Set(["File", "Folder", "Module", "Section"]);
