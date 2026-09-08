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
];

export function Providers() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
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
      <h3>{t("settings.providers")}</h3>
      <table>
        <thead>
          <tr>
            <th>name</th>
            <th>kind</th>
            <th>model</th>
            <th>api key</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {providers.data?.map((p) => (
            <tr key={p.id}>
              <td>
                {p.name}
                {p.is_fallback && " (fallback)"}
              </td>
              <td>{p.kind}</td>
              <td>{p.model}</td>
              <td>
                <code>{p.api_key_masked}</code>
              </td>
              <td>
                <button onClick={() => void testConnection(p.id)}>{t("common.test")}</button>
                {probe[p.id]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>{t("common.add")}</h4>
      <form onSubmit={submit} style={{ display: "grid", gap: 8, maxWidth: 420 }}>
        <input
          placeholder="name"
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
          placeholder="model"
          value={form.model}
          required
          onChange={(e) => setForm({ ...form, model: e.target.value })}
        />
        <input
          placeholder="base_url（留空用默认）"
          value={form.base_url}
          onChange={(e) => setForm({ ...form, base_url: e.target.value })}
        />
        <input
          type="password"
          placeholder="api key"
          value={form.api_key}
          required
          onChange={(e) => setForm({ ...form, api_key: e.target.value })}
        />
        <button type="submit">{t("common.save")}</button>
      </form>

      <h3 style={{ marginTop: 32 }}>{t("settings.routing")}</h3>
      <table>
        <tbody>
          {TASK_KEYS.map((key) => {
            const current = routing.data?.find((r) => r.task_key === key);
            return (
              <tr key={key}>
                <td>{key}</td>
                <td>
                  <select
                    aria-label={key}
                    value={current?.provider_config_id ?? ""}
                    onChange={(e) =>
                      route.mutate({ task_key: key, provider_config_id: Number(e.target.value) })
                    }
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
  );
}
