import { forceLayout } from "./force";
import type { GraphEdgeData, GraphNodeData, LayoutOptions, Point } from "./types";

export type LayoutKind = "document" | "function" | "force" | "bipartite";
export type { LayoutOptions, Point };

const ROW_HEIGHT = 44;
const TOP_PADDING = 48;

/** 一个节点在某种分组口径下属于哪条泳道。没有分组信息的一律归入"未覆盖"。 */
function laneOf(node: GraphNodeData, kind: LayoutKind): string {
  if (kind === "function") return node.functions[0] ?? "—";
  return node.group ?? "—";
}

/** 分组布局：一条泳道一列，列内按 code 升序。确定性来自排序，不依赖插入顺序。 */
function laneLayout(
  nodes: GraphNodeData[],
  kind: LayoutKind,
  options: LayoutOptions,
): Map<string, Point> {
  const lanes = [...new Set(nodes.map((node) => laneOf(node, kind)))].sort();
  const positions = new Map<string, Point>();
  const laneCount = Math.max(lanes.length, 1);
  lanes.forEach((lane, laneIndex) => {
    const members = nodes
      .filter((node) => laneOf(node, kind) === lane)
      .sort((a, b) => a.code.localeCompare(b.code));
    const x = Math.round(((laneIndex + 0.5) * options.width) / laneCount);
    members.forEach((node, rowIndex) => {
      positions.set(node.key, { x, y: TOP_PADDING + rowIndex * ROW_HEIGHT });
    });
  });
  return positions;
}

/** 二部布局：左控制点、右框架项，各自按 code 升序。 */
function bipartiteLayout(nodes: GraphNodeData[], options: LayoutOptions): Map<string, Point> {
  const positions = new Map<string, Point>();
  const columns: [GraphNodeData["kind"], number][] = [
    ["control", Math.round(options.width * 0.22)],
    ["framework_item", Math.round(options.width * 0.78)],
  ];
  for (const [kind, x] of columns) {
    nodes
      .filter((node) => node.kind === kind)
      .sort((a, b) => a.code.localeCompare(b.code))
      .forEach((node, index) => {
        positions.set(node.key, { x, y: TOP_PADDING + index * ROW_HEIGHT });
      });
  }
  return positions;
}

export function layout(
  kind: LayoutKind,
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  options: LayoutOptions,
): Map<string, Point> {
  if (kind === "force") return forceLayout(nodes, edges, options);
  if (kind === "bipartite") return bipartiteLayout(nodes, options);
  return laneLayout(nodes, kind, options);
}
