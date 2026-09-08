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
    <div>
      <h3>{t("settings.auditLog")}</h3>
      <p style={{ color: "#666", fontSize: 13 }}>
        本日志只增不删，可作为本系统自身接受审计时的证据。
      </p>
      <table>
        <thead>
          <tr>
            <th>time</th>
            <th>user</th>
            <th>action</th>
            <th>entity</th>
            <th>change</th>
          </tr>
        </thead>
        <tbody>
          {data?.map((e) => (
            <tr key={e.id}>
              <td>{e.at.replace("T", " ").slice(0, 19)}</td>
              <td>{e.user_id ?? "—"}</td>
              <td>{e.action}</td>
              <td>
                {e.entity_type}#{e.entity_id}
              </td>
              <td style={{ fontSize: 12 }}>
                {e.before && <div>− {JSON.stringify(e.before)}</div>}
                {e.after && <div>+ {JSON.stringify(e.after)}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
