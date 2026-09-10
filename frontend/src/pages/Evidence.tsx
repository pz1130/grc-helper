import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { request } from "../api";
import { useAuth } from "../auth";

interface EvidenceType {
  id: number;
  name_zh: string;
  name_en: string;
  format: string;
  cadence: string;
  typical_source: string;
  description: string;
}

interface EvidenceItem {
  id: number;
  evidence_type_id: number;
  control_id: number;
  tech_asset_id: number | null;
  title: string;
  owner_user_id: number | null;
  location_hint: string;
  last_collected_at: string | null;
  valid_until: string | null;
  file_path: string | null;
  status: string;
  intent_status: string;
  display_status: string;
  created_at: string;
  evidence_type_name: string | null;
  control_code: string | null;
  control_title: string | null;
  tech_asset_name: string | null;
}

interface ControlOption { id: number; code: string; title: string }

interface EvidenceForm {
  evidence_type_id: string;
  control_id: string;
  tech_asset_id: string;
  title: string;
  owner_user_id: string;
  location_hint: string;
  last_collected_at: string;
  valid_until: string;
  file_path: string;
  status: string;
}

const emptyForm: EvidenceForm = {
  evidence_type_id: "",
  control_id: "",
  tech_asset_id: "",
  title: "",
  owner_user_id: "",
  location_hint: "",
  last_collected_at: "",
  valid_until: "",
  file_path: "",
  status: "planned",
};

const evidenceStatuses = ["planned", "collected", "missing"];

function withParam(current: URLSearchParams, key: string, value: string): URLSearchParams {
  const next = new URLSearchParams(current);
  if (value) next.set(key, value);
  else next.delete(key);
  return next;
}

function optionalId(value: string): number | null {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function Evidence() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const canWrite = user?.role !== "viewer";
  const [form, setForm] = useState<EvidenceForm | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const queryString = params.toString();
  const evidence = useQuery({
    queryKey: ["evidence", queryString],
    queryFn: () => request<EvidenceItem[]>(`/api/evidence${queryString ? `?${queryString}` : ""}`),
  });
  const types = useQuery({
    queryKey: ["evidence-types"],
    queryFn: () => request<EvidenceType[]>("/api/evidence-types"),
    enabled: canWrite,
  });
  const controls = useQuery({
    queryKey: ["controls", "evidence-form"],
    queryFn: () => request<ControlOption[]>("/api/controls?limit=500"),
    enabled: canWrite,
  });
  const assets = useQuery({
    queryKey: ["tech-assets", "evidence-form"],
    queryFn: () => request<{ id: number; name: string }[]>("/api/tech-assets"),
    enabled: canWrite,
  });
  const save = useMutation({
    mutationFn: () => {
      if (!form) throw new Error(t("evidence.formRequired"));
      const payload = {
        evidence_type_id: Number(form.evidence_type_id),
        control_id: Number(form.control_id),
        tech_asset_id: optionalId(form.tech_asset_id),
        title: form.title,
        owner_user_id: optionalId(form.owner_user_id),
        location_hint: form.location_hint,
        last_collected_at: form.last_collected_at ? new Date(form.last_collected_at).toISOString() : null,
        valid_until: form.valid_until ? new Date(form.valid_until).toISOString() : null,
        file_path: form.file_path || null,
        status: form.status,
      };
      return request<EvidenceItem>(editingId === null ? "/api/evidence" : `/api/evidence/${editingId}`, {
        method: editingId === null ? "POST" : "PATCH",
        body: JSON.stringify(payload),
      });
    },
    onMutate: () => setError(""),
    onError: (caught: Error) => setError(caught.message),
    onSuccess: async () => {
      setForm(null);
      setEditingId(null);
      await client.invalidateQueries({ queryKey: ["evidence"] });
      await client.invalidateQueries({ queryKey: ["evidence-stats"] });
    },
  });

  const statusFilter = params.get("status") ?? "";
  const ownerFilter = params.get("owner_user_id") ?? "";
  const dueBefore = (params.get("due_before") ?? "").slice(0, 10);
  const dueAfter = (params.get("due_after") ?? "").slice(0, 10);
  const typeName = useMemo(() => {
    const names = new Map((types.data ?? []).map((type) => [type.id, i18n.language.startsWith("zh") ? type.name_zh : type.name_en]));
    return (id: number) => names.get(id) ?? `#${id}`;
  }, [i18n.language, types.data]);

  function beginCreate() {
    setError("");
    save.reset();
    setEditingId(null);
    setForm(emptyForm);
  }

  function beginEdit(item: EvidenceItem) {
    setError("");
    save.reset();
    setEditingId(item.id);
    setForm({
      evidence_type_id: String(item.evidence_type_id),
      control_id: String(item.control_id),
      tech_asset_id: item.tech_asset_id ? String(item.tech_asset_id) : "",
      title: item.title,
      owner_user_id: item.owner_user_id ? String(item.owner_user_id) : "",
      location_hint: item.location_hint,
      last_collected_at: item.last_collected_at?.slice(0, 16) ?? "",
      valid_until: item.valid_until?.slice(0, 16) ?? "",
      file_path: item.file_path ?? "",
      status: item.intent_status,
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form?.title.trim() && form.evidence_type_id && form.control_id) save.mutate();
  }

  function setFilter(key: string, value: string) {
    setParams(withParam(params, key, value));
  }

  function setDateFilter(key: string, value: string) {
    const normalized = value ? `${value}${key === "due_before" ? "T23:59:59Z" : "T00:00:00Z"}` : "";
    setFilter(key, normalized);
  }

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 20 }}>
        <div>
          <h2>{t("evidence.title")}</h2>
          <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>{t("evidence.subtitle")}</p>
        </div>
        {canWrite && <button className="kn-btn-primary kn-btn-sm" onClick={beginCreate}>{t("common.add")}</button>}
      </div>

      <div className="kn-card" style={{ marginBottom: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, alignItems: "end" }}>
          <label>
            {t("evidence.owner")}
            <input type="number" min="1" value={ownerFilter} placeholder={t("evidence.ownerPlaceholder")} onChange={(e) => setFilter("owner_user_id", e.target.value)} />
          </label>
          <label>
            {t("evidence.status")}
            <select value={statusFilter} onChange={(e) => setFilter("status", e.target.value)}>
              <option value="">{t("evidence.allStatuses")}</option>
              {evidenceStatuses.map((value) => <option key={value} value={value}>{t(`evidence.statuses.${value}`)}</option>)}
              <option value="valid">{t("evidence.statuses.valid")}</option>
              <option value="expired">{t("evidence.statuses.expired")}</option>
            </select>
          </label>
          <label>
            {t("evidence.dueAfter")}
            <input type="date" value={dueAfter} onChange={(e) => setDateFilter("due_after", e.target.value)} />
          </label>
          <label>
            {t("evidence.dueBefore")}
            <input type="date" value={dueBefore} onChange={(e) => setDateFilter("due_before", e.target.value)} />
          </label>
          {(statusFilter || ownerFilter || dueBefore || dueAfter) && <button className="kn-btn-secondary kn-btn-sm" onClick={() => setParams(new URLSearchParams())}>{t("evidence.clearFilters")}</button>}
        </div>
      </div>

      {form && canWrite && (
        <form className="kn-card" onSubmit={submit} style={{ marginBottom: 20, maxWidth: 960 }}>
          <h3 style={{ marginBottom: 16 }}>{t(editingId === null ? "evidence.add" : "evidence.edit")}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 14 }}>
            <label>
              {t("evidence.type")}
              <select required value={form.evidence_type_id} disabled={save.isPending} onChange={(e) => setForm({ ...form, evidence_type_id: e.target.value })}>
                <option value="">{t("evidence.chooseType")}</option>
                {types.data?.map((type) => <option key={type.id} value={type.id}>{i18n.language.startsWith("zh") ? type.name_zh : type.name_en}</option>)}
              </select>
            </label>
            <label>
              {t("evidence.control")}
              <select required value={form.control_id} disabled={save.isPending} onChange={(e) => setForm({ ...form, control_id: e.target.value })}>
                <option value="">{t("evidence.chooseControl")}</option>
                {controls.data?.map((control) => <option key={control.id} value={control.id}>{control.code} · {control.title}</option>)}
              </select>
            </label>
            <label>
              {t("evidence.asset")}
              <select value={form.tech_asset_id} disabled={save.isPending} onChange={(e) => setForm({ ...form, tech_asset_id: e.target.value })}>
                <option value="">{t("evidence.noAsset")}</option>
                {assets.data?.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}
              </select>
            </label>
            <label>
              {t("evidence.titleField")}
              <input required value={form.title} disabled={save.isPending} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </label>
            <label>
              {t("evidence.owner")}
              <input type="number" min="1" value={form.owner_user_id} disabled={save.isPending} onChange={(e) => setForm({ ...form, owner_user_id: e.target.value })} />
            </label>
            <label>
              {t("evidence.status")}
              <select value={form.status} disabled={save.isPending} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {evidenceStatuses.map((value) => <option key={value} value={value}>{t(`evidence.statuses.${value}`)}</option>)}
              </select>
            </label>
            <label>
              {t("evidence.lastCollected")}
              <input type="datetime-local" value={form.last_collected_at} disabled={save.isPending} onChange={(e) => setForm({ ...form, last_collected_at: e.target.value })} />
            </label>
            <label>
              {t("evidence.validUntil")}
              <input type="datetime-local" value={form.valid_until} disabled={save.isPending} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} />
            </label>
            <label>
              {t("evidence.location")}
              <input value={form.location_hint} disabled={save.isPending} onChange={(e) => setForm({ ...form, location_hint: e.target.value })} />
            </label>
            <label>
              {t("evidence.filePath")}
              <input value={form.file_path} disabled={save.isPending} onChange={(e) => setForm({ ...form, file_path: e.target.value })} />
            </label>
          </div>
          {error && <p role="alert">⚠️ {error}</p>}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="kn-btn-primary" type="submit" disabled={save.isPending || !form.title.trim() || !form.evidence_type_id || !form.control_id}>{t("common.save")}</button>
            <button type="button" className="kn-btn-secondary" disabled={save.isPending} onClick={() => { setForm(null); setEditingId(null); }}>{t("common.cancel")}</button>
          </div>
        </form>
      )}

      {evidence.isPending && <p role="status">{t("common.loading")}</p>}
      {evidence.error && <p role="alert">⚠️ {evidence.error.message}</p>}
      {evidence.data && evidence.data.length === 0 && !evidence.isPending && <div className="kn-card" style={{ textAlign: "center", padding: "40px 20px" }}><p style={{ margin: 0 }}>{t("common.empty")}</p></div>}
      {!!evidence.data?.length && (
        <div className="kn-table-container">
          <table>
            <thead><tr><th>{t("evidence.titleField")}</th><th>{t("evidence.type")}</th><th>{t("evidence.control")}</th><th>{t("evidence.owner")}</th><th>{t("evidence.validUntil")}</th><th>{t("evidence.status")}</th>{canWrite && <th />}</tr></thead>
            <tbody>
              {evidence.data.map((item) => {
                const isExpired = item.display_status === "expired";
                return <tr key={item.id}>
                  <td><strong>{item.title}</strong><div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{item.location_hint || "—"}</div></td>
                  <td>{item.evidence_type_name ?? typeName(item.evidence_type_id)}</td>
                  <td><code>{item.control_code ?? `#${item.control_id}`}</code>{item.control_title && <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>{item.control_title}</div>}</td>
                  <td>{item.owner_user_id ? `#${item.owner_user_id}` : "—"}</td>
                  <td style={isExpired ? { color: "var(--accent-ruby)", fontWeight: 700 } : undefined}>{item.valid_until ? new Date(item.valid_until).toLocaleDateString() : "—"}</td>
                  <td><span className={`kn-badge ${isExpired ? "kn-badge-ruby" : item.display_status === "valid" ? "kn-badge-emerald" : item.display_status === "missing" ? "kn-badge-amber" : "kn-badge-blue"}`}>{t(`evidence.statuses.${item.display_status}`, { defaultValue: item.display_status })}</span></td>
                  {canWrite && <td><button className="kn-btn-secondary kn-btn-sm" onClick={() => beginEdit(item)}>{t("common.edit")}</button></td>}
                </tr>;
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
