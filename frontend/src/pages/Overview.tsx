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

  return (
    <section>
      <h2>{t("overview.title")}</h2>
      <p>
        {t("overview.monthCost")}: ${data?.month_to_date_cost.toFixed(2) ?? "—"}
        {data?.budget != null && ` / $${data.budget.toFixed(2)}`}
      </p>
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
              <td>{row.task_key}</td>
              <td>{row.calls}</td>
              <td>${row.cost.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
