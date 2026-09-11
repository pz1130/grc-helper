import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";
import { Canvas } from "./Canvas";
import { Drawer } from "./Drawer";
import type { LayoutKind } from "./layout";
import type { GraphData, GraphEdgeData, GraphNodeData } from "./types";

const WIDTH = 960;
const HEIGHT = 560;

export function Graph() {
  const { t } = useTranslation();
  const [layoutKind, setLayoutKind] = useState<LayoutKind>("document");
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeData | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["graph", "relations"],
    queryFn: () => request<GraphData>("/api/graph/relations"),
  });

  return (
    <section>
      <h1>{t("graph.title")}</h1>
      <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
        {(["document", "function", "force"] as LayoutKind[]).map((kind) => (
          <button
            key={kind}
            type="button"
            className={layoutKind === kind ? "kn-button" : "kn-button kn-button-ghost"}
            aria-pressed={layoutKind === kind}
            onClick={() => setLayoutKind(kind)}
          >
            {t(`graph.layout.${kind}`)}
          </button>
        ))}
      </div>
      {isLoading && <p style={{ color: "var(--text-tertiary)" }}>{t("common.loading")}</p>}
      {data && (
        <>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
            {t("graph.stats", { nodes: data.stats.nodes, edges: data.stats.edges })}
          </p>
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Canvas
                data={data}
                layoutKind={layoutKind}
                width={WIDTH}
                height={HEIGHT}
                onSelectNode={(node) => {
                  setSelectedEdge(null);
                  setSelectedNode(node);
                }}
                onSelectEdge={(edge) => {
                  setSelectedNode(null);
                  setSelectedEdge(edge);
                }}
              />
            </div>
            <Drawer
              node={selectedNode}
              edge={selectedEdge}
              onClose={() => {
                setSelectedNode(null);
                setSelectedEdge(null);
              }}
            />
          </div>
          <ul style={{ display: "flex", gap: 16, listStyle: "none", padding: 0, marginTop: 12 }}>
            {data.groups.map((group) => (
              <li key={group.key} style={{ color: "var(--text-secondary)", fontSize: "0.75rem" }}>
                {group.label}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
