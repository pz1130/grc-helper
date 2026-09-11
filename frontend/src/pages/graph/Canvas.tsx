import type { LayoutKind, Point } from "./layout";
import { layout } from "./layout";
import type { GraphData, GraphEdgeData, GraphNodeData } from "./types";

const EDGE_COLOR: Record<string, string> = {
  depends_on: "var(--accent-blue)",
  duplicates: "var(--accent-purple)",
  // M10 的 conflict_detection 一落库就自动点亮，这里不必回头改。
  conflicts_with: "var(--accent-ruby)",
  full: "var(--accent-emerald)",
  partial: "var(--accent-cyan)",
  supporting: "var(--accent-amber)",
};

export interface CanvasProps {
  data: GraphData;
  layoutKind: LayoutKind;
  width: number;
  height: number;
  onSelectNode: (node: GraphNodeData) => void;
  onSelectEdge: (edge: GraphEdgeData) => void;
}

export function Canvas({ data, layoutKind, width, height, onSelectNode, onSelectEdge }: CanvasProps) {
  const positions: Map<string, Point> = layout(layoutKind, data.nodes, data.edges, { width, height });

  return (
    <svg
      id="graph-canvas"
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Control graph"
      style={{ background: "var(--stage-card-subtle)", borderRadius: 12 }}
    >
      {data.edges.map((edge) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const length = Math.hypot(dx, dy);
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        return (
          <g
            key={edge.key}
            data-edge-key={edge.key}
            data-kind={edge.kind}
            data-status={edge.status}
            style={{ cursor: "pointer" }}
            onClick={() => onSelectEdge(edge)}
          >
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={EDGE_COLOR[edge.kind] ?? "var(--text-tertiary)"}
              strokeWidth={edge.kind === "conflicts_with" ? 3.5 : 1.5}
              strokeDasharray={edge.status === "pending" ? "5 4" : undefined}
            />
            <rect
              x={from.x}
              y={from.y - 8}
              width={length}
              height={16}
              transform={`rotate(${angle} ${from.x} ${from.y})`}
              fill="transparent"
            />
          </g>
        );
      })}
      {data.nodes.map((node) => {
        const point = positions.get(node.key);
        if (!point) return null;
        return (
          <g
            key={node.key}
            data-node-key={node.key}
            data-kind={node.kind}
            transform={`translate(${point.x},${point.y})`}
            style={{ cursor: "pointer" }}
            onClick={() => onSelectNode(node)}
          >
            <circle
              r={node.kind === "framework_item" ? 6 : 8}
              fill={node.is_gap ? "var(--accent-ruby-bg)" : "var(--accent-blue-bg)"}
              stroke={node.is_gap ? "var(--accent-ruby)" : "var(--accent-blue)"}
              strokeWidth={1.5}
            />
            <text x={12} y={4} fontSize={11} fill="var(--text-secondary)">
              {node.code}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
