import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { request } from "../../api";

interface Entry {
  id: number;
  user_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string;
}

export function AuditLog() {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["audit-log"],
    queryFn: () => request<Entry[]>("/api/audit-log?limit=200"),
  });

  return (
    <div className="kn-card">
      <div style={{ marginBottom: 16 }}>
        <h3 style={{ margin: "0 0 4px 0", fontSize: "1.125rem" }}>{t("settings.auditLog")}</h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: 0 }}>
          {t("settings.auditLogConfig.description")}
        </p>
      </div>

      <div className="kn-table-container" style={{ margin: 0 }}>
        <table>
          <thead>
            <tr>
              <th>{t("settings.auditLogConfig.time")}</th>
              <th>{t("settings.auditLogConfig.user")}</th>
              <th>{t("settings.auditLogConfig.action")}</th>
              <th>{t("settings.auditLogConfig.entity")}</th>
              <th>{t("settings.auditLogConfig.change")}</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((e) => (
              <tr key={e.id}>
                <td style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                  {e.at.replace("T", " ").slice(0, 19)}
                </td>
                <td>
                  <span style={{ fontWeight: 500 }}>{e.user_id ?? "—"}</span>
                </td>
                <td>
                  <span className="kn-badge kn-badge-blue">
                    {e.action}
                  </span>
                </td>
                <td>
                  <code>
                    {e.entity_type}#{e.entity_id}
                  </code>
                </td>
                <td style={{ fontSize: "0.75rem", fontFamily: "monospace" }}>
                  {e.before && (
                    <div style={{ color: "var(--accent-ruby)", marginBottom: 2 }}>
                      − {JSON.stringify(e.before)}
                    </div>
                  )}
                  {e.after && (
                    <div style={{ color: "var(--accent-emerald)" }}>
                      + {JSON.stringify(e.after)}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
