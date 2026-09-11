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
  const [focus, setFocus] = useState<string>("");
  const [hops, setHops] = useState<number>(1);
  const [includePending, setIncludePending] = useState(false);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(false);
  const [onlyConflicts, setOnlyConflicts] = useState(false);
  const [frameworkId, setFrameworkId] = useState<string>("");

  const params = new URLSearchParams();
  if (focus) params.set("focus", focus);
  params.set("hops", String(hops));
  if (includePending) params.set("include_pending", "true");
  if (onlyConflicts) params.set("types", "conflicts_with");
  if (frameworkId) params.set("framework_id", frameworkId);

  const { data: raw, isLoading } = useQuery({
    queryKey: ["graph", "relations", params.toString()],
    queryFn: () => request<GraphData>(`/api/graph/relations?${params.toString()}`),
  });
  const { data: documents } = useQuery({
    queryKey: ["graph", "documents"],
    queryFn: () => request<{ id: number; title: string }[]>("/api/documents"),
  });
  const { data: controls } = useQuery({
    queryKey: ["graph", "controls"],
    queryFn: () => request<{ id: number; code: string; title: string }[]>("/api/controls"),
  });
  const { data: frameworks } = useQuery({
    queryKey: ["graph", "frameworks"],
    queryFn: () => request<{ id: number; name_en: string }[]>("/api/frameworks"),
  });

  const data: GraphData | undefined = raw && onlyUnconfirmed
    ? (() => {
        const edges = raw.edges.filter((edge) => edge.status === "pending");
        const kept = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
        return {
          ...raw,
          edges,
          nodes: raw.nodes.filter((node) => kept.has(node.key)),
          stats: { ...raw.stats, edges: edges.length },
        };
      })()
    : raw;

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
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", margin: "12px 0" }}>
        <label>
          {t("graph.focus")}
          <select value={focus} onChange={(event) => setFocus(event.target.value)}>
            <option value="">{t("graph.panorama")}</option>
            {documents?.map((document) => (
              <option key={`document:${document.id}`} value={`document:${document.id}`}>
                {document.title}
              </option>
            ))}
            {controls?.map((control) => (
              <option key={`control:${control.id}`} value={`control:${control.id}`}>
                {control.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("graph.hops")}
          <select value={hops} onChange={(event) => setHops(Number(event.target.value))}>
            <option value={1}>1</option>
            <option value={2}>2</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={includePending} onChange={(event) => setIncludePending(event.target.checked)} />
          {t("graph.filters.pending")}
        </label>
        <label>
          <input type="checkbox" checked={onlyUnconfirmed} onChange={(event) => setOnlyUnconfirmed(event.target.checked)} />
          {t("graph.filters.onlyUnconfirmed")}
        </label>
        <label>
          <input type="checkbox" checked={onlyConflicts} onChange={(event) => setOnlyConflicts(event.target.checked)} />
          {t("graph.filters.onlyConflicts")}
        </label>
        <label>
          {t("graph.filters.framework")}
          <select value={frameworkId} onChange={(event) => setFrameworkId(event.target.value)}>
            <option value="">{t("graph.filters.allFrameworks")}</option>
            {frameworks?.map((framework) => (
              <option key={framework.id} value={framework.id}>{framework.name_en}</option>
            ))}
          </select>
        </label>
      </div>
      {isLoading && <p style={{ color: "var(--text-tertiary)" }}>{t("common.loading")}</p>}
      {data && (
        <>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
            {t("graph.stats", { nodes: data.stats.nodes, edges: data.stats.edges })}
            {data.stats.pending_edges > 0 && ` · ${t("graph.pendingCount", { count: data.stats.pending_edges })}`}
            {data.stats.truncated && ` · ${t("graph.truncated")}`}
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
