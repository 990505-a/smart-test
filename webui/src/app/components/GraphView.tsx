"use client";

/**
 * Sigma.js (WebGL) rendering of the code knowledge graph.
 *
 * 2026-09 重构:弃用 G6 与 exe 预计算坐标(3D 投影到 2D 后是无结构的一坨,
 * 且 exe 返回的前 N 节点几乎全是同色 File/Module 结构节点)。现改为:
 * - 节点按 label 类型配色(Function/Class/Route/Variable/File…),度数定大小
 * - 客户端 ForceAtlas2 力导向布局(graphology-layout-forceatlas2),聚类清晰
 * - 默认隐藏 File/Folder/Module/Section 等结构节点,只看代码符号
 * - 悬停高亮邻居、搜索降透明、点击出详情(Sigma reducer 实现)
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import SigmaLib from "sigma";
import type { CbmGraphData } from "@/lib/api/useNewModules";

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
const STRUCTURAL = new Set(["File", "Folder", "Module", "Section"]);

/** 边类型 → 颜色 */
const EDGE_COLORS: Record<string, string> = {
  CALLS: "#94a3b8",
  DEFINES: "#a78bfa",
  DEFINES_METHOD: "#a78bfa",
  CONTAINS_FILE: "#cbd5e1",
  CONTAINS_FOLDER: "#cbd5e1",
  CONTAINS_PACKAGE: "#cbd5e1",
  IMPORTS: "#34d399",
  USAGE: "#fbbf24",
  INHERITS: "#f472b6",
  IMPLEMENTS: "#f472b6",
  OVERRIDE: "#f472b6",
};

interface GraphViewProps {
  data: CbmGraphData | null;
  /** 为空 Set 时显示全部边类型 */
  edgeFilter?: Set<string>;
  /** 搜索关键字：命中保持高亮，未命中淡化 */
  search?: string;
  /** 是否显示 File/Folder/Module 等结构节点 */
  showStructural?: boolean;
  onNodeClick?: (node: GraphNodeInfo) => void;
}

export default function GraphView({ data, edgeFilter, search, showStructural = false,
                                    onNodeClick }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<SigmaLib | null>(null);
  const hoverRef = useRef<string | null>(null);
  const searchRef = useRef(search);
  const clickRef = useRef(onNodeClick);
  searchRef.current = search;
  clickRef.current = onNodeClick;
  const [layoutBusy, setLayoutBusy] = useState(false);

  // 原始数据 → graphology 图(过滤边、隐藏结构节点、只保留有可见边的节点)
  const graph = useMemo(() => {
    if (!data) return null;
    // multi: 同一对节点间可能有多条不同类型的边(DEFINES + CALLS 等),必须用多重图
    const g = new Graph({ multi: true, type: "directed" });
    const degree = new Map<number, number>();
    const edges: { source: number; target: number; type: string }[] = [];
    for (const e of data.edges) {
      if (edgeFilter && edgeFilter.size > 0 && !edgeFilter.has(e.type)) continue;
      edges.push(e);
      degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
      degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
    }
    const labelCount = new Map<string, number>();
    for (const n of data.nodes) {
      if (!STRUCTURAL.has(n.label) || showStructural) labelCount.set(n.label, (labelCount.get(n.label) ?? 0) + 1);
    }
    const rng = mulberry32(42);
    for (const n of data.nodes) {
      if (STRUCTURAL.has(n.label) && !showStructural) continue;
      if ((degree.get(n.id) ?? 0) === 0) continue; // 无可见边的节点不画,减少噪点
      const deg = degree.get(n.id) ?? 0;
      g.addNode(n.id, {
        label: n.name,
        nodeType: n.label,
        size: Math.min(16, 4 + Math.sqrt(deg) * 2.2),
        color: NODE_PALETTE[n.label] ?? "#64748b",
        x: rng() * 1000 - 500,
        y: rng() * 1000 - 500,
        meta: n,
      });
    }
    edges.forEach((e, i) => {
      if (g.hasNode(e.source) && g.hasNode(e.target)) {
        g.addEdgeWithKey(`e${i}`, e.source, e.target, {
          color: EDGE_COLORS[e.type] ?? "#94a3b8",
          size: 0.7,
          type: "line",
          hidden: false,
        });
      }
    });
    void labelCount;
    return g;
  }, [data, edgeFilter, showStructural]);

  // 布局 + 渲染(每次数据/过滤变化重建)
  useEffect(() => {
    if (!containerRef.current || !graph || graph.order === 0) return;
    setLayoutBusy(true);
    // 让浏览器先画出"布局中"提示再同步跑 FA2
    const handle = window.setTimeout(() => {
      try {
        forceAtlas2.assign(graph, {
          iterations: 100,
          settings: {
            barnesHutOptimize: graph.order > 1500,
            gravity: 1.2,
            scalingRatio: 2.4,
            slowDown: 2.5,
            linLogMode: true,
          },
        });
      } catch {
        /* 布局失败则保留随机初始位置 */
      }

      if (sigmaRef.current) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
      const sigma = new SigmaLib(graph, containerRef.current!, {
        renderEdgeLabels: false,
        labelDensity: 0.4,
        labelGridCellSize: 90,
        labelRenderedSizeThreshold: 9,
        zIndex: true,
        minCameraRatio: 0.05,
        maxCameraRatio: 8,
      });

      const applyReducers = () => {
        const kw = (searchRef.current ?? "").trim().toLowerCase();
        sigma.setSetting("nodeReducer", (node, attrs) => {
          const a = graph.getNodeAttribute(node, "meta") as CbmGraphData["nodes"][number];
          const hover = hoverRef.current;
          if (hover && hover !== node && !graph.areNeighbors(hover, node) && !graph.hasEdge(hover, node)) {
            return { ...attrs, color: "#e2e8f0", label: "", zIndex: 0 };
          }
          if (kw) {
            const hit = `${a?.name ?? ""} ${a?.qualified_name ?? ""} ${a?.file_path ?? ""}`
              .toLowerCase().includes(kw);
            return hit
              ? { ...attrs, zIndex: 2, highlighted: true }
              : { ...attrs, color: "#e2e8f0", label: "", zIndex: 0 };
          }
          return attrs;
        });
        sigma.setSetting("edgeReducer", (edge, attrs) => {
          const hover = hoverRef.current;
          if (hover) {
            const [source, target] = graph.extremities(edge);
            const near = source === hover || target === hover;
            return near ? { ...attrs, hidden: false, size: 1.6 } : { ...attrs, hidden: true };
          }
          return attrs;
        });
      };
      applyReducers();

      sigma.on("enterNode", ({ node }) => { hoverRef.current = node; applyReducers(); });
      sigma.on("leaveNode", () => { hoverRef.current = null; applyReducers(); });
      sigma.on("clickNode", ({ node }) => {
        const meta = graph.getNodeAttribute(node, "meta") as CbmGraphData["nodes"][number];
        clickRef.current?.({
          id: meta.id, name: meta.name, label: meta.label,
          qualified_name: meta.qualified_name, file_path: meta.file_path,
          start_line: meta.start_line, end_line: meta.end_line,
          color: meta.color, status: meta.status, in_calls: meta.in_calls,
        });
      });

      sigmaRef.current = sigma;
      setLayoutBusy(false);
    }, 30);
    return () => {
      window.clearTimeout(handle);
      sigmaRef.current?.kill();
      sigmaRef.current = null;
    };
  }, [graph]);

  // 搜索变化只重设 reducer(不重算布局)
  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma || !graph) return;
    const kw = (search ?? "").trim().toLowerCase();
    sigma.setSetting("nodeReducer", (node, attrs) => {
      const hover = hoverRef.current;
      if (hover && hover !== node && !graph.areNeighbors(hover, node) && !graph.hasEdge(hover, node)) {
        return { ...attrs, color: "#e2e8f0", label: "", zIndex: 0 };
      }
      if (kw) {
        const meta = graph.getNodeAttribute(node, "meta") as CbmGraphData["nodes"][number];
        const hit = `${meta?.name ?? ""} ${meta?.qualified_name ?? ""} ${meta?.file_path ?? ""}`
          .toLowerCase().includes(kw);
        return hit
          ? { ...attrs, zIndex: 2, highlighted: true }
          : { ...attrs, color: "#e2e8f0", label: "", zIndex: 0 };
      }
      return attrs;
    });
  }, [search, graph]);

  return (
    <div className="relative">
      <div ref={containerRef} className="h-[620px] w-full rounded-lg border bg-background" />
      {layoutBusy && (
        <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-background/70 text-sm text-muted-foreground">
          正在计算力导向布局（节点越多越慢,通常 1-3 秒）…
        </div>
      )}
    </div>
  );
}

/** 确定性随机(固定种子,布局可复现) */
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
