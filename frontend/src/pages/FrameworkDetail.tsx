import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { request } from "../api";
import { useAuth } from "../auth";

interface Framework {
  id: number; key: string; name_zh: string; name_en: string;
  version: string; source: string; item_count: number; imported_at: string;
}
interface FrameworkItem {
  id: number; parent_id: number | null; code: string; title: string;
  description: string; level: number; order_index: number; attributes: Record<string, unknown> | null;
}
interface CoverageRow {
  item_id: number; code: string; title: string; level: number;
  parent_id: number | null; requirements: number; covered: number;
}
interface GapRow { item_id: number; code: string; title: string; has_supporting: boolean; }

export function FrameworkDetail() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const [baseline, setBaseline] = useState("");
  const canWrite = user?.role === "admin" || user?.role === "grc_lead";
  const suffix = baseline ? `?baseline=${encodeURIComponent(baseline)}` : "";
  const framework = useQuery({
    queryKey: ["frameworks"], queryFn: () => request<Framework[]>("/api/frameworks"),
  });
  const tree = useQuery({
    queryKey: ["framework-tree", id], queryFn: () => request<FrameworkItem[]>(`/api/frameworks/${id}/tree`),
    enabled: Boolean(id),
  });
  const coverage = useQuery({
    queryKey: ["framework-coverage", id, baseline],
    queryFn: () => request<CoverageRow[]>(`/api/frameworks/${id}/coverage${suffix}`),
    enabled: Boolean(id),
  });
  const gaps = useQuery({
    queryKey: ["framework-gaps", id, baseline],
    queryFn: () => request<GapRow[]>(`/api/frameworks/${id}/gaps${suffix}`),
    enabled: Boolean(id),
  });
  const runMapping = useMutation({
    mutationFn: () => request<{ job_id: string }>(`/api/mapping/frameworks/${id}`, { method: "POST" }),
  });
  const current = framework.data?.find((item) => String(item.id) === id);

  return <section>
    <p><Link to="/frameworks">← {t("frameworks.title")}</Link></p>
    <h2>{current?.name_zh ?? id} {current && <small>· {current.version}</small>}</h2>
    {canWrite && <button disabled={runMapping.isPending} onClick={() => runMapping.mutate()}>{t("frameworks.runMapping")}</button>}
    {runMapping.isPending && <p role="status">{t("common.loading")}</p>}
    {runMapping.error && <p role="alert">{runMapping.error.message}</p>}
    {runMapping.data && <p role="status">{t("frameworks.mappingQueued", { id: runMapping.data.job_id })}</p>}

    <h3>{t("frameworks.tree")}</h3>
    {tree.isPending && <p role="status">{t("common.loading")}</p>}
    {tree.error && <p role="alert">{tree.error.message}</p>}
    <ul>{tree.data?.map((item) => <li key={item.id} style={{ marginLeft: Math.max(0, item.level - 1) * 20 }}>
      <code>{item.code}</code> {item.title}
      {item.description && <span style={{ color: "#666" }}> — {item.description}</span>}
    </li>)}</ul>

    <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 24 }}>
      <h3 style={{ margin: 0 }}>{t("frameworks.coverage")}</h3>
      <label>{t("frameworks.baseline")} <select value={baseline} onChange={(event) => setBaseline(event.target.value)}>
        <option value="">{t("frameworks.baselineAll")}</option>
        <option value="low">low</option><option value="moderate">moderate</option><option value="high">high</option>
      </select></label>
    </div>
    {coverage.isPending && <p role="status">{t("common.loading")}</p>}
    {coverage.error && <p role="alert">{coverage.error.message}</p>}
    <div style={{ overflowX: "auto" }}><table>
      <thead><tr><th>{t("frameworks.item")}</th><th>{t("frameworks.coverage")}</th></tr></thead>
      <tbody>{coverage.data?.map((row) => {
        const ratio = row.requirements ? row.covered / row.requirements : null;
        const color = ratio === null ? undefined : ratio >= 1 ? "#d8f3dc" : ratio > 0 ? "#fff3bf" : "#ffd6d6";
        return <tr key={row.item_id}><td style={{ paddingLeft: Math.max(0, row.level - 1) * 16 }}><code>{row.code}</code> {row.title}</td><td style={{ background: color }}>{row.covered} / {row.requirements}</td></tr>;
      })}</tbody>
    </table></div>

    <h3 style={{ marginTop: 24 }}>{t("frameworks.gaps")}</h3>
    {gaps.isPending && <p role="status">{t("common.loading")}</p>}
    {gaps.error && <p role="alert">{gaps.error.message}</p>}
    {gaps.data?.length === 0 && <p>{t("common.empty")}</p>}
    <ul>{gaps.data?.map((gap) => <li key={gap.item_id}>
      <code>{gap.code}</code> {gap.title}
      {gap.has_supporting && <small style={{ marginLeft: 8, color: "#946000" }}>{t("frameworks.hasSupporting")}</small>}
    </li>)}</ul>
  </section>;
}
