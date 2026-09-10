import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { request } from "../api";

interface Usage {
  month_to_date_cost: number;
  budget: number | null;
  by_task: { task_key: string; cost: number; calls: number }[];
}

export function Overview() {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: () => request<Usage>("/api/settings/usage"),
  });

  const cost = data?.month_to_date_cost ?? 0;
  const budget = data?.budget;
  const budgetRatio = budget && budget > 0 ? Math.min(Math.round((cost / budget) * 100), 100) : null;
  const totalCalls = data?.by_task.reduce((sum, r) => sum + r.calls, 0) ?? 0;
  const maxTaskCost = Math.max(...(data?.by_task.map((r) => r.cost) ?? [1]), 0.0001);

  return (
    <section>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h2>{t("overview.title")}</h2>
          <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Enterprise AI Governance & Inference Consumption Dashboard
          </p>
        </div>
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
            <div className="kn-stat-number kn-gradient">
              ${data ? data.month_to_date_cost.toFixed(2) : "—"}
            </div>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: 12 }}>
              {t("overview.monthCost")}: ${data?.month_to_date_cost.toFixed(2) ?? "—"}
              {data?.budget != null && ` / $${data.budget.toFixed(2)}`}
            </p>
          </div>
          {budget != null && budgetRatio !== null && (
            <div style={{ marginTop: 8 }}>
              <div className="kn-progress-bar">
                <div
                  className="kn-progress-fill"
                  style={{
                    width: `${budgetRatio}%`,
                    background: budgetRatio > 90 ? "var(--accent-ruby)" : budgetRatio > 70 ? "var(--accent-amber)" : "linear-gradient(90deg, #2997ff, #64d2ff)",
                  }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Total Calls Card */}
        <div className="kn-card kn-stat-card">
          <div>
            <span className="kn-stat-label">{t("overview.calls")}</span>
            <div className="kn-stat-number">
              {totalCalls.toLocaleString()}
            </div>
            <div className="kn-stat-sub">
              {data?.by_task.length ?? 0} Active Task Pipelines
            </div>
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 16 }}>
            <span className="kn-badge kn-badge-blue">
              <span className="kn-dot kn-dot-blue" /> Live Telemetry
            </span>
          </div>
        </div>
      </div>

      {/* Task Breakdown Table Card */}
      <div className="kn-card" style={{ padding: 0 }}>
        <div style={{ padding: "18px 24px", borderBottom: "1px solid var(--stage-border)" }}>
          <h3 style={{ margin: 0, fontSize: "1.0625rem" }}>Task Breakdown</h3>
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
                    <code style={{ fontSize: "0.8125rem", color: "var(--accent-blue)" }}>{row.task_key}</code>
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
                        <div className="kn-progress-bar" style={{ height: 4 }}>
                          <div
                            className="kn-progress-fill"
                            style={{ width: `${Math.max((row.cost / maxTaskCost) * 100, 4)}%` }}
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
    </section>
  );
}
