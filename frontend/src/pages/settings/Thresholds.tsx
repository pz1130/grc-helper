import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";

interface Thresholds {
  auto_accept_threshold: number;
  force_manual_threshold: number;
  monthly_budget_usd: number;
}

export function ThresholdsPage() {
  const { t } = useTranslation();
  const [form, setForm] = useState<Thresholds>({
    auto_accept_threshold: 0.9,
    force_manual_threshold: 0.6,
    monthly_budget_usd: 200,
  });
  const [error, setError] = useState("");

  const query = useQuery({
    queryKey: ["thresholds"],
    queryFn: () => request<Thresholds>("/api/settings/thresholds"),
  });

  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);

  const save = useMutation({
    mutationFn: () =>
      request<Thresholds>("/api/settings/thresholds", {
        method: "PUT",
        body: JSON.stringify(form),
      }),
    onError: (e: Error) => setError(e.message),
    onSuccess: () => setError(""),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (form.auto_accept_threshold <= form.force_manual_threshold) {
      setError("自动接受阈值必须高于强制人工阈值");
      return;
    }
    save.mutate();
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 12, maxWidth: 420 }}>
      <h3>{t("settings.thresholds")}</h3>
      <label>
        自动接受阈值（高于此值允许批量接受）
        <input
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={form.auto_accept_threshold}
          onChange={(e) => setForm({ ...form, auto_accept_threshold: Number(e.target.value) })}
        />
      </label>
      <label>
        强制人工阈值（低于此值必须逐条确认）
        <input
          type="number"
          step="0.01"
          min="0"
          max="1"
          value={form.force_manual_threshold}
          onChange={(e) => setForm({ ...form, force_manual_threshold: Number(e.target.value) })}
        />
      </label>
      <label>
        月度预算（USD）
        <input
          type="number"
          step="1"
          min="0"
          value={form.monthly_budget_usd}
          onChange={(e) => setForm({ ...form, monthly_budget_usd: Number(e.target.value) })}
        />
      </label>
      {error && (
        <p role="alert" style={{ color: "#c00" }}>
          {error}
        </p>
      )}
      <button type="submit">{t("common.save")}</button>
    </form>
  );
}
