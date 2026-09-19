import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";

interface Provider {
  id: number;
  name: string;
  kind: string;
  model: string;
  base_url: string | null;
  enabled: boolean;
  is_fallback: boolean;
  api_key_masked: string;
}

interface Routing {
  id: number;
  task_key: string;
  provider_config_id: number;
  temperature: number;
  max_tokens: number;
}

const KINDS = [
  "anthropic",
  "openai",
  "azure_openai",
  "gemini",
  "deepseek",
  "qwen",
  "ollama",
  "minimax",
  "openai_compatible",
];

// spec §6.5 的八个推理任务，加上 embedding（spec §6.1）
const TASK_KEYS = [
  "control_extract",
  "framework_mapping",
  "relation_inference",
  "conflict_detection",
  "audit_prediction",
  "answer_generation",
  "maturity_suggestion",
  "evidence_suggestion",
  "embedding",
  "query_expansion",
  "matrix_mapping",
];

export function Providers() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<number | null>(null);
  const [form, setForm] = useState({
    name: "",
    kind: "anthropic",
    model: "claude-opus-5",
    api_key: "",
    base_url: "",
  });
  const [probe, setProbe] = useState<Record<number, string>>({});

  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: () => request<Provider[]>("/api/settings/providers"),
  });
  const routing = useQuery({
    queryKey: ["routing"],
    queryFn: () => request<Routing[]>("/api/settings/routing"),
  });

  const create = useMutation({
    mutationFn: () =>
      request<Provider>("/api/settings/providers", {
        method: "POST",
        body: JSON.stringify({ ...form, base_url: form.base_url || null }),
      }),
    onSuccess: () => {
      setForm({ ...form, name: "", api_key: "" });
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  const route = useMutation({
    mutationFn: (body: { task_key: string; provider_config_id: number }) =>
      request<Routing>("/api/settings/routing", {
        method: "PUT",
        body: JSON.stringify({ ...body, temperature: 0, max_tokens: 4096 }),
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["routing"] }),
  });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      request(`/api/settings/providers/${id}`, { method: "PATCH", body: JSON.stringify({ enabled }) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["providers"] }),
  });
  // 被任务路由指着的会被后端拒掉（409），把那句话原样显示出来——
  // 它写着还有哪几个任务在用它。
  const remove = useMutation({
    mutationFn: (id: number) => request(`/api/settings/providers/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setConfirming(null);
      void queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  async function testConnection(id: number) {
    const result = await request<{ ok: boolean; message: string }>(
      `/api/settings/providers/${id}/test`,
      { method: "POST" },
    );
    setProbe({ ...probe, [id]: result.ok ? "✅ " + result.message : "❌ " + result.message });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <div>
      <div className="kn-card" style={{ marginBottom: 24 }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "1.125rem" }}>{t("settings.providers")}</h3>
        <div className="kn-table-container" style={{ margin: 0 }}>
          <table>
            <thead>
              <tr>
                <th>{t("settings.providersConfig.name")}</th>
                <th>{t("settings.providersConfig.kind")}</th>
                <th>{t("settings.providersConfig.model")}</th>
                <th>{t("settings.providersConfig.apiKey")}</th>
                <th style={{ textAlign: "right" }}>{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {providers.data?.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.name}</span>
                    {p.is_fallback && <span className="kn-badge kn-badge-purple" style={{ marginLeft: 8 }}>{t("settings.providersConfig.fallback")}</span>}
                  </td>
                  <td>
                    <span className="kn-badge">{p.kind}</span>
                  </td>
                  <td>
                    <span style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>{p.model}</span>
                  </td>
                  <td>
                    <code>{p.api_key_masked}</code>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                      <button className="kn-btn-secondary kn-btn-sm" onClick={() => void testConnection(p.id)}>
                        {t("common.test")}
                      </button>
                      <button
                        className="kn-btn-secondary kn-btn-sm"
                        disabled={toggle.isPending}
                        onClick={() => toggle.mutate({ id: p.id, enabled: !p.enabled })}
                      >
                        {t(p.enabled ? "settings.providerDisable" : "settings.providerEnable")}
                      </button>
                      {confirming === p.id ? (
                        <>
                          <button
                            className="kn-btn-danger kn-btn-sm"
                            disabled={remove.isPending}
                            onClick={() => remove.mutate(p.id)}
                          >
                            {t("settings.providerConfirmDelete")}
                          </button>
                          <button className="kn-btn-secondary kn-btn-sm" onClick={() => { setConfirming(null); remove.reset(); }}>
                            {t("common.cancel")}
                          </button>
                        </>
                      ) : (
                        <button
                          className="kn-btn-danger kn-btn-sm"
                          onClick={() => { setConfirming(p.id); remove.reset(); }}
                        >
                          {t("common.delete")}
                        </button>
                      )}
                      {!p.enabled && <span className="kn-badge">{t("settings.providerDisabled")}</span>}
                      {probe[p.id] && (
                        <span style={{ fontSize: "0.8125rem" }}>{probe[p.id]}</span>
                      )}
                      {confirming === p.id && remove.error && (
                        <span role="alert" style={{ fontSize: "0.8125rem", color: "var(--accent-red)" }}>
                          ⚠️ {remove.error.message}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add Provider Card */}
      <div className="kn-card" style={{ marginBottom: 24 }}>
        <h4 style={{ margin: "0 0 14px 0", fontSize: "1rem" }}>{t("common.add")}</h4>
        <form onSubmit={submit} style={{ display: "grid", gap: 12, maxWidth: 520 }}>
          <input
            placeholder={t("settings.providersConfig.name")}
            value={form.name}
            required
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <input
            placeholder={t("settings.providersConfig.model")}
            value={form.model}
            required
            onChange={(e) => setForm({ ...form, model: e.target.value })}
          />
          <input
            placeholder={t("settings.providersConfig.baseUrlPlaceholder")}
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          />
          <input
            type="password"
            placeholder={t("settings.providersConfig.apiKey")}
            value={form.api_key}
            required
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          />
          <div>
            <button type="submit" className="kn-btn-primary" style={{ padding: "8px 24px" }}>
              {t("common.save")}
            </button>
          </div>
        </form>
      </div>

      {/* Routing Matrix Card */}
      <div className="kn-card">
        <h3 style={{ margin: "0 0 16px 0", fontSize: "1.125rem" }}>{t("settings.routing")}</h3>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: 14 }}>
          {t("settings.providersConfig.routingHint")}
        </p>
        <div className="kn-table-container" style={{ margin: 0 }}>
          <table>
            <thead>
              <tr>
                <th>{t("settings.providersConfig.taskPipeline")}</th>
                <th>{t("settings.providersConfig.assignedProvider")}</th>
              </tr>
            </thead>
            <tbody>
              {TASK_KEYS.map((key) => {
                const current = routing.data?.find((r) => r.task_key === key);
                return (
                  <tr key={key}>
                    <td>
                      <span title={key}>{t(`taskNames.${key}`, { defaultValue: key })}</span>
                    </td>
                    <td>
                      <select
                        aria-label={t("settings.providersConfig.routeFor", { task: t(`taskNames.${key}`, { defaultValue: key }) })}
                        value={current?.provider_config_id ?? ""}
                        onChange={(e) =>
                          route.mutate({ task_key: key, provider_config_id: Number(e.target.value) })
                        }
                        style={{ minWidth: 260, padding: "5px 28px 5px 12px" }}
                      >
                        <option value="">—</option>
                        {providers.data?.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} · {p.model}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
