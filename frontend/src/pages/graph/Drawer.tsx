import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { request } from "../../api";
import type { GraphEdgeData, GraphNodeData } from "./types";

interface ControlSource {
  clause_id: number;
  document_id: number;
  document_title: string;
  citation_label: string;
  heading_path: string;
  relation: string;
}

interface ControlDetail {
  id: number;
  code: string;
  title: string;
  statement: string;
  sources: ControlSource[];
}

interface ClauseDetail {
  id: number;
  document_id: number;
  citation_label: string;
  heading_path: string;
  text: string;
}

function ClauseText({ clauseId }: { clauseId: number }) {
  const { data } = useQuery({
    queryKey: ["clause", clauseId],
    queryFn: () => request<ClauseDetail>(`/api/clauses/${clauseId}`),
  });
  if (!data) return null;
  return (
    <p style={{ fontSize: "0.8125rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
      {data.text}
    </p>
  );
}

export interface DrawerProps {
  node: GraphNodeData | null;
  edge: GraphEdgeData | null;
  onClose: () => void;
}

export function Drawer({ node, edge, onClose }: DrawerProps) {
  const { t } = useTranslation();
  const controlId =
    node && node.kind === "control" ? Number(node.key.split(":")[1]) : null;
  const { data: control } = useQuery({
    queryKey: ["control", controlId],
    queryFn: () => request<ControlDetail>(`/api/controls/${controlId}`),
    enabled: controlId !== null,
  });

  if (!node && !edge) return null;

  return (
    <aside
      role="complementary"
      aria-label={t("graph.drawer.title")}
      className="kn-card"
      style={{ width: 340, padding: 16, flexShrink: 0 }}
    >
      <button type="button" className="kn-button kn-button-ghost" onClick={onClose}>
        {t("common.close")}
      </button>
      {edge && (
        <div style={{ marginTop: 12 }}>
          <h2 style={{ fontSize: "0.9375rem" }}>{t(`graph.edgeKind.${edge.kind}`, edge.kind)}</h2>
          <p style={{ fontSize: "0.8125rem" }}>{edge.rationale}</p>
          {edge.confidence !== null && <p>{edge.confidence.toFixed(2)}</p>}
          {edge.proposal_id !== null && (
            <Link
              to={
                edge.kind === "full" || edge.kind === "partial" || edge.kind === "supporting"
                  ? `/review?kind=mapping#proposal-${edge.proposal_id}`
                  : `/review?kind=relation#proposal-${edge.proposal_id}`
              }
            >
              {t("graph.drawer.toReview")}
            </Link>
          )}
        </div>
      )}
      {/* 框架项没有 control 可拉。不单独渲染的话抽屉里只剩一个关闭按钮，
          而映射视图里差距节点恰恰是最想点开看的那个。 */}
      {node && node.kind === "framework_item" && (
        <div style={{ marginTop: 12 }}>
          <h2 style={{ fontSize: "0.9375rem" }}>{node.code}</h2>
          <p style={{ fontWeight: 600 }}>{node.title}</p>
          {node.is_gap && (
            <p style={{ fontSize: "0.8125rem", color: "var(--accent-ruby)" }}>
              {t("graph.drawer.notCovered")}
            </p>
          )}
        </div>
      )}
      {node && control && (
        <div style={{ marginTop: 12 }}>
          <h2 style={{ fontSize: "0.9375rem" }}>{control.code}</h2>
          <p style={{ fontWeight: 600 }}>{control.title}</p>
          <p style={{ fontSize: "0.8125rem" }}>{control.statement}</p>
          {control.sources.map((source) => (
            <div key={source.clause_id} style={{ marginTop: 12 }}>
              <strong style={{ fontSize: "0.75rem" }}>{source.citation_label}</strong>
              <ClauseText clauseId={source.clause_id} />
              <Link to={`/documents/${source.document_id}#clause-${source.clause_id}`}>
                {t("graph.drawer.openInDocument")}
              </Link>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
