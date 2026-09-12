import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { request } from "../api";

interface Usage {
  month_to_date_cost: number;
  budget: number | null;
  by_task: { task_key: string; cost: number; calls: number }[];
}

interface EvidenceStats {
  expired: number;
}

interface ReviewDocument {
  id: number;
  review_due_date: string | null;
}

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function isoSoonUntil(today: string): string {
  return new Date(
    Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)) - 1, Number(today.slice(8, 10)) + 30),
  ).toISOString().slice(0, 10);
}

export function Overview() {
  const { t } = useTranslation();
  const [dlpEnabled, setDlpEnabled] = useState(true);
  const [activePipeline, setActivePipeline] = useState("SOC2-CC6.1-Inference");

  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: () => request<Usage>("/api/settings/usage"),
  });
  const evidenceStats = useQuery({
    queryKey: ["evidence-stats"],
    queryFn: () => request<EvidenceStats>("/api/evidence/stats"),
  });
  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => request<ReviewDocument[]>("/api/documents"),
  });

  const today = isoToday();
  const soonUntil = isoSoonUntil(today);
  const overdue = (documents.data ?? []).filter((doc) => doc.review_due_date && doc.review_due_date < today).length;
  const soon = (documents.data ?? []).filter(
    (doc) => doc.review_due_date && doc.review_due_date >= today && doc.review_due_date <= soonUntil,
  ).length;

  const cost = data?.month_to_date_cost ?? 0;
  const budget = data?.budget;
  const budgetRatio = budget && budget > 0 ? Math.min(Math.round((cost / budget) * 100), 100) : null;
  const totalCalls = data?.by_task.reduce((sum, r) => sum + r.calls, 0) ?? 0;
  const maxTaskCost = Math.max(...(data?.by_task.map((r) => r.cost) ?? [1]), 0.0001);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Oceanic Cyber-Teal Window Frame */}
      <div className="kn-window-frame">
        {/* macOS Style Traffic Lights Window Header */}
        <div className="kn-window-header">
          <div className="kn-traffic-lights">
            <div className="kn-traffic-light red" />
            <div className="kn-traffic-light yellow" />
            <div className="kn-traffic-light green" />
          </div>
          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 8, fontWeight: 500 }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            <span>GRC Helper · Governance Platform</span>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span className="kn-badge kn-badge-emerald" style={{ fontSize: "0.6875rem", padding: "2px 7px" }}>
              <span className="kn-dot kn-dot-emerald" /> Live Telemetry
            </span>
          </div>
        </div>

        <div style={{ padding: "28px" }}>
          {/* Hero Section Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16, marginBottom: 26 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: "1.625rem", letterSpacing: "-0.025em" }}>
                {t("overview.title")}
              </h2>
              <p style={{ margin: "6px 0 0", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                Enterprise AI Governance & Inference Consumption Dashboard
              </p>
            </div>
            {/* Glowing Mint Pill Button (from reference image) */}
            <button
              type="button"
              className="kn-btn-mint-pill"
              onClick={() => alert("Pipeline telemetry scan triggered")}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span>Run Pipeline</span>
            </button>
          </div>

          {/* Bento Grid Metrics */}
          <div className="kn-bento-grid">
            {/* Month Cost & Budget Card */}
            <div className="kn-card kn-stat-card">
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span className="kn-stat-label">{t("overview.monthCost")}</span>
                  {budgetRatio !== null && (
                    <span className={`kn-badge ${budgetRatio > 90 ? "kn-badge-ruby" : budgetRatio > 70 ? "kn-badge-amber" : "kn-badge-emerald"}`}>
                      {budgetRatio}%
                    </span>
                  )}
                </div>
                <div className="kn-stat-number" style={{ color: "var(--text-primary)" }}>
                  ${data ? data.month_to_date_cost.toFixed(2) : "—"}
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "4px 0 8px" }}>
                  {t("overview.monthCost")}: ${data?.month_to_date_cost.toFixed(2) ?? "—"}
                  {data?.budget != null && ` / $${data.budget.toFixed(2)}`}
                </p>
              </div>
              {budget != null && budgetRatio !== null && (
                <div style={{ marginTop: 8 }}>
                  <div className="kn-progress-bar" style={{ height: 6, borderRadius: 9999 }}>
                    <div
                      className="kn-progress-fill"
                      style={{
                        width: `${budgetRatio}%`,
                        background: budgetRatio > 90 ? "var(--accent-ruby)" : budgetRatio > 70 ? "var(--accent-amber)" : "linear-gradient(90deg, #059669, #10b981)",
                        boxShadow: budgetRatio > 90 ? "0 0 10px rgba(255, 69, 58, 0.4)" : budgetRatio > 70 ? "0 0 10px rgba(255, 159, 10, 0.4)" : "0 0 10px rgba(16, 185, 129, 0.4)",
                      }}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Expired Evidence Card */}
            <div className="kn-card kn-stat-card">
              <div>
                <span className="kn-stat-label">{t("overview.expiredEvidence")}</span>
                <div className="kn-stat-number" style={{ color: evidenceStats.data?.expired ? "var(--accent-ruby)" : undefined }}>
                  {evidenceStats.data?.expired ?? "—"}
                </div>
                <div className="kn-stat-sub">{t("overview.expiredEvidenceHint")}</div>
              </div>
              <span className={`kn-badge ${evidenceStats.data?.expired ? "kn-badge-ruby" : "kn-badge-emerald"}`}>
                {evidenceStats.data?.expired ? t("overview.needsAttention") : t("overview.upToDate")}
              </span>
            </div>

            {/* Review Due Card */}
            <div className="kn-card kn-stat-card" data-card="review-due">
              <div>
                <span className="kn-stat-label">{t("documents.reviewDue")}</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                  <Link
                    to="/documents?review=overdue"
                    style={{ color: overdue ? "var(--accent-ruby)" : "var(--text-primary)", fontWeight: 600, textDecoration: "none" }}
                  >
                    {t("documents.reviewOverdue", { count: overdue })}
                  </Link>
                  <Link
                    to="/documents?review=soon"
                    style={{ color: soon ? "var(--accent-amber)" : "var(--text-primary)", fontWeight: 600, textDecoration: "none" }}
                  >
                    {t("documents.reviewSoon", { count: soon })}
                  </Link>
                </div>
              </div>
              <span className={`kn-badge ${overdue || soon ? "kn-badge-ruby" : "kn-badge-emerald"}`}>
                {overdue || soon ? t("overview.needsAttention") : t("overview.upToDate")}
              </span>
            </div>

            {/* Total Calls Card */}
            <div className="kn-card kn-stat-card">
              <div>
                <span className="kn-stat-label">{t("overview.calls")}</span>
                <div className="kn-stat-number" style={{ color: "var(--text-primary)" }}>
                  {totalCalls.toLocaleString()}
                </div>
                <div className="kn-stat-sub">
                  {data?.by_task.length ?? 0} Active Task Pipelines
                </div>
              </div>
              <div style={{ display: "flex", gap: 6, marginTop: 16 }}>
                <span className="kn-badge kn-badge-emerald">
                  <span className="kn-dot kn-dot-emerald" /> Optimal Flow
                </span>
              </div>
            </div>
          </div>

          {/* Interactive Pipeline Deck & Floating Console (from Reference Image) */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 18, marginTop: 22 }}>
            {/* Control Deck with Toggle & Wireframe Card */}
            <div className="kn-deck-card">
              <div style={{ fontSize: "0.875rem", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="14" width="7" height="7" rx="1" />
                  <rect x="3" y="14" width="7" height="7" rx="1" />
                </svg>
                <span>AI Pipeline Privacy & Governance Guard</span>
              </div>

              {/* Toggle Switch row matching reference image */}
              <div className="kn-deck-row">
                <div>
                  <div style={{ fontSize: "0.8125rem", fontWeight: 500 }}>Active DLP Redaction & Filtering</div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>Automatically sanitizes PII & secrets before inference</div>
                </div>
                <div
                  className={`kn-toggle-switch ${dlpEnabled ? "active" : ""}`}
                  onClick={() => setDlpEnabled(!dlpEnabled)}
                  role="switch"
                  aria-checked={dlpEnabled}
                  tabIndex={0}
                >
                  <div className="kn-toggle-knob" />
                </div>
              </div>

              {/* Wireframe Line Art Preview (from reference image) */}
              <div className="kn-wireframe-card">
                <div className="kn-wireframe-icon-box">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--accent-emerald)" }}>
                    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                    <polyline points="22,6 12,13 2,6" />
                  </svg>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Telemetry Stream · Active Link
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 6 }}>
                    <div style={{ height: 4, borderRadius: 2, background: "var(--accent-emerald)", opacity: 0.45, width: "85%" }} />
                    <div style={{ height: 4, borderRadius: 2, background: "var(--accent-emerald)", opacity: 0.2, width: "55%" }} />
                  </div>
                </div>
              </div>
            </div>

            {/* Floating Shadcn-style Command Dialog (from reference image) */}
            <div className="kn-floating-dialog">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingBottom: 12, borderBottom: "1px solid var(--stage-border)" }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.8125rem", color: "var(--text-primary)", fontWeight: 600 }}>
                  npx grc-pipeline@latest run --live
                </div>
                <span className="kn-badge kn-badge-emerald" style={{ fontSize: "0.625rem" }}>CLI</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                <div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", marginBottom: 4 }}>Active Target Baseline</div>
                  <input
                    className="kn-input"
                    value={activePipeline}
                    onChange={(e) => setActivePipeline(e.target.value)}
                    style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)" }}
                  />
                </div>
                <div>
                  <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)", marginBottom: 4 }}>Default Provider Route</div>
                  <input
                    className="kn-input"
                    value="azure-gpt4o-mini (Fallback: deepseek-r1)"
                    readOnly
                    style={{ fontSize: "0.75rem", fontFamily: "var(--font-mono)", opacity: 0.85 }}
                  />
                </div>
                <button
                  type="button"
                  className="kn-btn-mint-pill"
                  style={{ width: "100%", borderRadius: "var(--radius-sm)", padding: "7px 0", marginTop: 4 }}
                  onClick={() => alert(`Applied config for: ${activePipeline}`)}
                >
                  Apply Configuration
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Task Breakdown Table Card */}
      <div className="kn-card" style={{ padding: 0 }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--stage-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: "1.0625rem" }}>Task Breakdown</h3>
          <span className="kn-badge kn-badge-emerald">{data?.by_task.length ?? 0} Pipelines</span>
        </div>
        <div className="kn-table-container" style={{ margin: 0, border: "none", borderRadius: 0, boxShadow: "none" }}>
          <table>
            <thead>
              <tr>
                <th>task</th>
                <th>{t("overview.calls")}</th>
                <th>cost</th>
              </tr>
            </thead>
            <tbody>
              {data?.by_task.map((row) => (
                <tr key={row.task_key}>
                  <td style={{ fontWeight: 500 }}>
                    <code style={{ fontSize: "0.8125rem", color: "var(--accent-emerald)", background: "rgba(16, 185, 129, 0.08)", padding: "2px 6px", borderRadius: 4, border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                      {row.task_key}
                    </code>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ minWidth: 40, fontVariantNumeric: "tabular-nums" }}>{row.calls.toLocaleString()}</span>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <span style={{ minWidth: 68, fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                        ${row.cost.toFixed(4)}
                      </span>
                      <div style={{ flex: 1, maxWidth: 120 }}>
                        <div className="kn-progress-bar" style={{ height: 4, borderRadius: 9999 }}>
                          <div
                            className="kn-progress-fill"
                            style={{
                              width: `${Math.max((row.cost / maxTaskCost) * 100, 4)}%`,
                              background: "linear-gradient(90deg, #059669, #10b981)",
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

