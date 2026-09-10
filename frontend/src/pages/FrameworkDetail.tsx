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

  return (
    <section>
      <p style={{ marginBottom: 16 }}>
        <Link to="/frameworks" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.875rem" }}>
          ← {t("frameworks.title")}
        </Link>
      </p>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16, marginBottom: 24 }}>
        <div>
          <h2>
            {current?.name_zh ?? id}
            {current && <small style={{ color: "var(--text-secondary)", fontSize: "1.0625rem", marginLeft: 8 }}>· {current.version}</small>}
          </h2>
          {current?.name_en && (
            <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              {current.name_en} · Source: {current.source}
            </p>
          )}
        </div>

        {canWrite && (
          <button
            className="kn-btn-primary"
            disabled={runMapping.isPending}
            onClick={() => runMapping.mutate()}
          >
            {t("frameworks.runMapping")}
          </button>
        )}
      </div>

      {runMapping.isPending && <p role="status">{t("common.loading")}</p>}
      {runMapping.error && <p role="alert"><span>⚠️</span> {runMapping.error.message}</p>}
      {runMapping.data && <p role="status">{t("frameworks.mappingQueued", { id: runMapping.data.job_id })}</p>}

      {/* Coverage & Gap Analysis Section */}
      <div className="kn-card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>{t("frameworks.coverage")}</h3>
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8, margin: 0 }}>
            <span>{t("frameworks.baseline")}</span>
            <select
              value={baseline}
              onChange={(event) => setBaseline(event.target.value)}
              style={{ padding: "5px 28px 5px 12px" }}
            >
              <option value="">{t("frameworks.baselineAll")}</option>
              <option value="low">low</option>
              <option value="moderate">moderate</option>
              <option value="high">high</option>
            </select>
          </label>
        </div>

        {coverage.isPending && <p role="status">{t("common.loading")}</p>}
        {coverage.error && <p role="alert"><span>⚠️</span> {coverage.error.message}</p>}

        <div className="kn-table-container" style={{ margin: 0 }}>
          <table>
            <thead>
              <tr>
                <th>{t("frameworks.item")}</th>
                <th>{t("frameworks.coverage")}</th>
              </tr>
            </thead>
            <tbody>
              {coverage.data?.map((row) => {
                const ratio = row.requirements ? row.covered / row.requirements : null;
                const badgeClass =
                  ratio === null
                    ? ""
                    : ratio >= 1
                    ? "kn-badge-emerald"
                    : ratio > 0
                    ? "kn-badge-amber"
                    : "kn-badge-ruby";

                return (
                  <tr key={row.item_id}>
                    <td style={{ paddingLeft: 18 + Math.max(0, row.level - 1) * 20 }}>
                      <code style={{ marginRight: 8 }}>{row.code}</code>
                      <span style={{ fontWeight: row.level === 1 ? 600 : 400 }}>{row.title}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className={`kn-badge ${badgeClass}`}>
                          {row.covered} / {row.requirements}
                        </span>
                        {ratio !== null && (
                          <div style={{ width: 90 }}>
                            <div className="kn-progress-bar">
                              <div
                                className="kn-progress-fill"
                                style={{
                                  width: `${Math.round(ratio * 100)}%`,
                                  background:
                                    ratio >= 1
                                      ? "var(--accent-emerald)"
                                      : ratio > 0
                                      ? "var(--accent-amber)"
                                      : "var(--accent-ruby)",
                                }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Gaps Checklist */}
      <div className="kn-card" style={{ marginBottom: 24 }}>
        <h3 style={{ margin: "0 0 14px 0" }}>{t("frameworks.gaps")}</h3>
        {gaps.isPending && <p role="status">{t("common.loading")}</p>}
        {gaps.error && <p role="alert"><span>⚠️</span> {gaps.error.message}</p>}
        {gaps.data?.length === 0 && (
          <p style={{ color: "var(--accent-emerald)", margin: 0 }}>✓ {t("common.empty")}</p>
        )}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {gaps.data?.map((gap) => (
            <li
              key={gap.item_id}
              style={{
                padding: "10px 14px",
                background: "var(--stage-card-subtle)",
                borderRadius: "var(--radius-sm)",
                marginBottom: 8,
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <span className="kn-badge kn-badge-ruby">GAP</span>
              <code>{gap.code}</code>
              <span style={{ color: "var(--text-primary)" }}>{gap.title}</span>
              {gap.has_supporting && (
                <small style={{ marginLeft: "auto", color: "var(--accent-amber)" }}>
                  {t("frameworks.hasSupporting")}
                </small>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* Framework Tree */}
      <div className="kn-card">
        <h3 style={{ margin: "0 0 14px 0" }}>{t("frameworks.tree")}</h3>
        {tree.isPending && <p role="status">{t("common.loading")}</p>}
        {tree.error && <p role="alert"><span>⚠️</span> {tree.error.message}</p>}
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {tree.data?.map((item) => (
            <li
              key={item.id}
              style={{
                paddingLeft: Math.max(0, item.level - 1) * 20,
                paddingTop: 6,
                paddingBottom: 6,
                borderLeft: item.level > 1 ? "1px solid var(--stage-border-subtle)" : undefined,
                marginLeft: item.level > 1 ? 8 : 0,
              }}
            >
              <code style={{ marginRight: 8 }}>{item.code}</code>
              <span style={{ fontWeight: item.level === 1 ? 600 : 400 }}>{item.title}</span>
              {item.description && (
                <span style={{ color: "var(--text-tertiary)", fontSize: "0.8125rem", marginLeft: 8 }}>
                  — {item.description}
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
