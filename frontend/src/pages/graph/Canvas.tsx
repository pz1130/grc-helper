import { useMemo } from "react";

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
  selectedNodeKey?: string | null;
  selectedEdgeKey?: string | null;
  labelLimit?: number;
}

export function Canvas({
  data,
  layoutKind,
  width,
  height,
  onSelectNode,
  onSelectEdge,
  selectedNodeKey,
  selectedEdgeKey,
  labelLimit,
}: CanvasProps) {
  const positions: Map<string, Point> = useMemo(
    () => layout(layoutKind, data.nodes, data.edges, { width, height }),
    [layoutKind, data.nodes, data.edges, width, height],
  );

  // 全景下 146 个节点全画标签就是一团糊：只给度数最高的若干个画，
  // 并列时按 code 升序取，保证确定性。
  const labelled = useMemo(() => {
    const degree = new Map<string, number>();
    for (const edge of data.edges) {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    }
    return new Set(
      labelLimit === undefined
        ? data.nodes.map((node) => node.key)
        : [...data.nodes]
            .sort((a, b) => (degree.get(b.key) ?? 0) - (degree.get(a.key) ?? 0) || a.code.localeCompare(b.code))
            .slice(0, labelLimit)
            .map((node) => node.key),
    );
  }, [data.edges, data.nodes, labelLimit]);

  return (
    <svg
      id="graph-canvas"
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Control graph"
      style={{
        background: "var(--stage-card-subtle)",
        borderRadius: 16,
        display: "block",
        transition: "var(--transition-smooth)",
      }}
    >
      {/* 边渲染 */}
      {data.edges.map((edge) => {
        const from = positions.get(edge.source);
        const to = positions.get(edge.target);
        if (!from || !to) return null;
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const length = Math.hypot(dx, dy);
        const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
        const isSelected = selectedEdgeKey === edge.key;
        const strokeColor = EDGE_COLOR[edge.kind] ?? "var(--text-tertiary)";
        const baseWidth = edge.kind === "conflicts_with" ? 3.5 : 1.5;

        return (
          <g
            key={edge.key}
            data-edge-key={edge.key}
            data-kind={edge.kind}
            data-status={edge.status}
            strokeDasharray={edge.status === "pending" ? "5 4" : undefined}
            style={{ cursor: "pointer", transition: "opacity 0.2s ease" }}
            onClick={() => onSelectEdge(edge)}
          >
            {/* 选中高亮外发光 */}
            {isSelected && (
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={strokeColor}
                strokeWidth={baseWidth + 5}
                opacity={0.38}
              />
            )}
            <line
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke={strokeColor}
              strokeWidth={isSelected ? baseWidth + 1 : baseWidth}
              strokeDasharray={edge.status === "pending" ? "5 4" : undefined}
            />
            {/* 易点击透明区域 */}
            <rect
              x={from.x}
              y={from.y - 10}
              width={length}
              height={20}
              transform={`rotate(${angle} ${from.x} ${from.y})`}
              fill="transparent"
            />
          </g>
        );
      })}

      {/* 节点渲染 */}
      {data.nodes.map((node) => {
        const point = positions.get(node.key);
        if (!point) return null;
        const isSelected = selectedNodeKey === node.key;
        const radius = node.kind === "framework_item" ? 6 : 8;
        const strokeColor = node.is_gap ? "var(--accent-ruby)" : "var(--accent-blue)";
        const fillColor = node.is_gap ? "var(--accent-ruby-bg)" : "var(--accent-blue-bg)";

        return (
          <g
            key={node.key}
            data-node-key={node.key}
            data-kind={node.kind}
            data-gap={node.is_gap ? "true" : "false"}
            transform={`translate(${point.x},${point.y})`}
            style={{ cursor: "pointer", transition: "transform 0.2s ease" }}
            onClick={() => onSelectNode(node)}
          >
            {/* 选中高亮光环 */}
            {isSelected && (
              <circle
                r={radius + 5}
                fill="none"
                stroke={strokeColor}
                strokeWidth={2}
                opacity={0.7}
              />
            )}
            {/* 主节点圆圈 */}
            <circle
              r={radius}
              fill={fillColor}
              stroke={strokeColor}
              strokeWidth={isSelected ? 2.5 : 1.5}
            />
            {/* 差距节点中心红点指示 */}
            {node.is_gap && (
              <circle
                r={2}
                fill="var(--accent-ruby)"
                stroke="none"
              />
            )}
            {/* 节点文本 */}
            {labelled.has(node.key) && (
              <text
                data-node-label={node.key}
                x={radius + 5}
                y={4}
                fontSize={11}
                fontWeight={isSelected ? 600 : 400}
                fill={isSelected ? "var(--text-primary)" : "var(--text-secondary)"}
                style={{ userSelect: "none" }}
              >
                {node.code}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
