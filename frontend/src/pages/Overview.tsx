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

  const proposalStats = useQuery({
    queryKey: ["proposal-stats"],
    queryFn: () => request<{ pending: number }>("/api/proposals/stats"),
  });
  const pendingCount = proposalStats.data?.pending ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Executive Hero Cockpit Banner */}
      <div className="kn-cockpit-hero">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span className="kn-pulse-dot" />
              <span className="kn-badge kn-badge-emerald" style={{ fontSize: "0.75rem" }}>
                {t("overview.compliancePosture", { defaultValue: "治理态势概览" })}
              </span>
            </div>
            <h2 style={{ margin: 0, fontSize: "1.75rem", letterSpacing: "-0.03em", fontWeight: 700 }}>
              {t("overview.heroTitle", { defaultValue: "合规与治理态势驾驶舱" })}
            </h2>
            <p style={{ margin: "6px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              {t("overview.heroSubtitle", { defaultValue: "多标准合规映射 · 证据有效性追踪 · AI 成本与审计监控" })}
            </p>
          </div>
          {pendingCount > 0 && (
            <Link to="/review" className="kn-btn-primary kn-btn-sm" style={{ textDecoration: "none" }}>
              <span>{t("overview.pendingReviewQuick", { defaultValue: "待确认任务" })} ({pendingCount})</span>
              <span>→</span>
            </Link>
          )}
        </div>

        <div className="kn-cockpit-metrics-strip">
          <div className="kn-cockpit-metric">
            <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase" }}>
              {t("overview.activeDocuments", { defaultValue: "受控制度文档" })}
            </span>
            <div className="kn-cockpit-metric-num">{documents.data?.length ?? "—"}</div>
          </div>
          <div className="kn-cockpit-metric">
            <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase" }}>
              {t("overview.monthCost")}
            </span>
            <div className="kn-cockpit-metric-num">${data ? data.month_to_date_cost.toFixed(2) : "0.00"}</div>
          </div>
          <div className="kn-cockpit-metric">
            <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase" }}>
              {t("overview.totalCalls", { defaultValue: "累计模型调用" })}
            </span>
            <div className="kn-cockpit-metric-num">{totalCalls.toLocaleString()}</div>
          </div>
          <div className="kn-cockpit-metric">
            <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", fontWeight: 600, textTransform: "uppercase" }}>
              {t("overview.reviewAlerts", { defaultValue: "复审到期告警" })}
            </span>
            <div className="kn-cockpit-metric-num" style={{ color: overdue > 0 ? "var(--accent-ruby)" : soon > 0 ? "var(--accent-amber)" : undefined }}>
              {overdue + soon}
            </div>
          </div>
        </div>
      </div>

      <div className="kn-bento-grid">
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

        <div className="kn-card kn-stat-card">
          <div>
            <span className="kn-stat-label">{t("overview.calls")}</span>
            <div className="kn-stat-number" style={{ color: "var(--text-primary)" }}>
              {totalCalls.toLocaleString()}
            </div>
            <div className="kn-stat-sub">
              {data?.by_task.length ?? 0} {t("overview.calls")}
            </div>
          </div>
        </div>
      </div>

      <div className="kn-card" style={{ padding: 0 }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--stage-border)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0, fontSize: "1.0625rem" }}>{t("overview.calls")}</h3>
          <span className="kn-badge kn-badge-emerald">{data?.by_task.length ?? 0}</span>
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
