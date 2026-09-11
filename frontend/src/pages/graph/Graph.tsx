import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";
import { Canvas } from "./Canvas";
import { Drawer } from "./Drawer";
import { downloadGraph } from "./export";
import { canvasHeight, MIN_CANVAS_HEIGHT, type LayoutKind } from "./layout";
import type { GraphData, GraphEdgeData, GraphNodeData } from "./types";

const WIDTH = 960;

export function Graph() {
  const { t } = useTranslation();
  const [view, setView] = useState<"relations" | "mappings">("relations");
  const [layoutKind, setLayoutKind] = useState<LayoutKind>("document");
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeData | null>(null);
  const [focus, setFocus] = useState<string>("");
  const [hops, setHops] = useState<number>(1);
  const [includePending, setIncludePending] = useState(false);
  const [onlyUnconfirmed, setOnlyUnconfirmed] = useState(false);
  const [onlyConflicts, setOnlyConflicts] = useState(false);
  const [frameworkId, setFrameworkId] = useState<string>("");
  const [thinLabels, setThinLabels] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const canvasWrapper = useRef<HTMLDivElement>(null);

  const exportGraph = async (format: "svg" | "png") => {
    const svg = canvasWrapper.current?.querySelector("svg");
    if (!svg) return;
    setExportError(null);
    try {
      await downloadGraph(svg as SVGSVGElement, format);
    } catch (error) {
      // 导出失败必须说出来。从前这里什么都不做，用户看到的就是点了没反应。
      setExportError(error instanceof Error ? error.message : "graph.exportFailed");
    }
  };

  const params = new URLSearchParams();
  if (focus) params.set("focus", focus);
  params.set("hops", String(hops));
  if (includePending) params.set("include_pending", "true");
  if (onlyConflicts) params.set("types", "conflicts_with");
  if (frameworkId) params.set("framework_id", frameworkId);

  const { data: documents } = useQuery({
    queryKey: ["graph", "documents"],
    queryFn: () => request<{ id: number; title: string }[]>("/api/documents"),
  });
  const { data: controls } = useQuery({
    queryKey: ["graph", "controls"],
    queryFn: () => request<{ id: number; code: string; title: string }[]>("/api/controls?limit=500"),
  });
  const { data: frameworks } = useQuery({
    queryKey: ["graph", "frameworks"],
    queryFn: () => request<{ id: number; name_en: string }[]>("/api/frameworks"),
  });

  const activeFrameworkId = frameworkId || (frameworks?.[0]?.id ? String(frameworks[0].id) : "");
  const mappingParams = new URLSearchParams();
  mappingParams.set("framework_id", activeFrameworkId);
  if (focus) mappingParams.set("focus", focus);
  mappingParams.set("hops", String(hops));
  if (includePending) mappingParams.set("include_pending", "true");

  const { data: raw, isLoading } = useQuery({
    queryKey: ["graph", view, view === "relations" ? params.toString() : mappingParams.toString()],
    queryFn: () =>
      request<GraphData>(
        view === "relations"
          ? `/api/graph/relations?${params.toString()}`
          : `/api/graph/mappings?${mappingParams.toString()}`,
      ),
    enabled: view === "relations" || activeFrameworkId !== "",
  });

  const data: GraphData | undefined = raw && onlyUnconfirmed
    ? (() => {
        const edges = raw.edges.filter((edge) => edge.status === "pending");
        const kept = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
        const nodes = raw.nodes.filter((node) => kept.has(node.key));
        return {
          ...raw,
          edges,
          nodes,
          stats: { ...raw.stats, nodes: nodes.length, edges: edges.length },
        };
      })()
    : raw;

  const activeLayout: LayoutKind = view === "mappings" ? "bipartite" : layoutKind;
  const height = data ? canvasHeight(activeLayout, data.nodes) : MIN_CANVAS_HEIGHT;

  return (
    <section>
      <h1>{t("graph.title")}</h1>
      <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
        {(["relations", "mappings"] as const).map((kind) => (
          <button
            key={kind}
            type="button"
            className={view === kind ? "kn-button" : "kn-button kn-button-ghost"}
            aria-pressed={view === kind}
            onClick={() => setView(kind)}
          >
            {t(`graph.view.${kind}`)}
          </button>
        ))}
      </div>
      {view === "relations" && (
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
      )}
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
          <input
            type="checkbox"
            checked={onlyUnconfirmed}
            onChange={(event) => {
              const checked = event.target.checked;
              setOnlyUnconfirmed(checked);
              if (checked) setIncludePending(true);
            }}
          />
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
        <label>
          <input type="checkbox" checked={thinLabels} onChange={(event) => setThinLabels(event.target.checked)} />
          {t("graph.thinLabels")}
        </label>
      </div>
      {isLoading && <p style={{ color: "var(--text-tertiary)" }}>{t("common.loading")}</p>}
      {data && (
        <>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
            {t("graph.stats", { nodes: data.stats.nodes, edges: data.stats.edges })}
            {data.stats.pending_edges > 0 && ` · ${t("graph.pendingCount", { count: data.stats.pending_edges })}`}
            {data.stats.truncated && ` · ${t("graph.truncated")}`}
            {view === "mappings" && ` · ${t("graph.gapCount", { count: data.nodes.filter((node) => node.is_gap).length })}`}
          </p>
          <div style={{ display: "flex", gap: 8, margin: "8px 0" }}>
            <button type="button" className="kn-button kn-button-ghost" onClick={() => exportGraph("svg")}>
              {t("graph.exportSvg")}
            </button>
            <button type="button" className="kn-button kn-button-ghost" onClick={() => exportGraph("png")}>
              {t("graph.exportPng")}
            </button>
            {exportError && (
              <p role="alert" style={{ margin: 0, alignSelf: "center", color: "var(--accent-ruby)", fontSize: "0.8125rem" }}>
                {t(exportError, { defaultValue: t("graph.exportFailed") })}
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
            <div ref={canvasWrapper} style={{ flex: 1, minWidth: 0, overflow: "auto", maxHeight: MIN_CANVAS_HEIGHT }}>
              <Canvas
                data={data}
                layoutKind={activeLayout}
                width={WIDTH}
                height={height}
                labelLimit={thinLabels ? Math.max(1, Math.round(data.nodes.length * 0.15)) : undefined}
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
