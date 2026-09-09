import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";
import type { Control } from "./Controls";

interface Detail extends Control {
  sources: { clause_id: number; document_id: number; document_title: string; citation_label: string; heading_path: string; relation: string }[];
  relations: { from_control_id: number; to_control_id: number; relation_type: string; rationale: string }[];
  mappings?: { framework_name: string; code: string; title: string; strength: string }[];
}

export function ControlDetail() {
  const { id } = useParams();
  return <ControlContent key={id} id={id!} />;
}

function ControlContent({ id }: { id: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role === "admin" || user?.role === "grc_lead";
  const client = useQueryClient();
  const [form, setForm] = useState<{ title: string; statement: string; category: string } | null>(null);
  const [saved, setSaved] = useState(false);
  const detail = useQuery({ queryKey: ["control", id], queryFn: () => request<Detail>(`/api/controls/${id}`) });
  const save = useMutation({
    mutationFn: () => request<Control>(`/api/controls/${id}`, { method: "PATCH", body: JSON.stringify({ ...form, category: form?.category.trim() || null }) }),
    onSuccess: async () => { setForm(null); setSaved(true); await Promise.all([client.invalidateQueries({ queryKey: ["control", id] }), client.invalidateQueries({ queryKey: ["controls"] })]); },
  });
  const data = detail.data;
  return <section>
    <p><Link to="/controls">← {t("controls.title")}</Link></p>
    {detail.isPending && <p role="status">{t("common.loading")}</p>}
    {detail.error && <p role="alert">{detail.error.message} <button onClick={() => void detail.refetch()}>{t("common.retry")}</button></p>}
    {data && <>
      <h2><code>{data.code}</code> {data.title}</h2>
      <p style={{ color: "#666" }}>{t("controls.category")}: {data.category ?? "—"} · {t("documents.status")}: {data.status}</p>
      {form ? <form onSubmit={(e) => { e.preventDefault(); if (form.title.trim() && form.statement.trim()) save.mutate(); }} style={{ display: "grid", gap: 12, maxWidth: 720 }}>
        <label>{t("controls.name")}<input required disabled={save.isPending} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} style={{ display: "block", width: "100%" }} /></label>
        <label>{t("controls.statement")}<textarea required disabled={save.isPending} rows={6} value={form.statement} onChange={(e) => setForm({ ...form, statement: e.target.value })} style={{ display: "block", width: "100%" }} /></label>
        <label>{t("controls.category")}<input disabled={save.isPending} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></label>
        {save.error && <p role="alert">{save.error.message}</p>}
        <div><button disabled={save.isPending || !form.title.trim() || !form.statement.trim()} type="submit">{t("common.save")}</button>{" "}<button type="button" disabled={save.isPending} onClick={() => setForm(null)}>{t("common.cancel")}</button></div>
      </form> : <>
        <p style={{ whiteSpace: "pre-wrap" }}>{data.statement}</p>
        {canWrite && <button onClick={() => { setForm({ title: data.title, statement: data.statement, category: data.category ?? "" }); save.reset(); setSaved(false); }}>{t("common.edit")}</button>}
      </>}
      {saved && <p role="status">{t("common.saved")}</p>}
      <h3>{t("controls.sources")} · {t("controls.backedBy", { count: new Set(data.sources.map((s) => s.document_id)).size })}</h3>
      {data.sources.length === 0 && <p>{t("controls.noSources")}</p>}
      <ul>{data.sources.map((s) => <li key={`${s.document_id}-${s.clause_id}`} style={{ marginBottom: 12 }}>
        <Link to={`/documents/${s.document_id}#clause-${s.clause_id}`}>{s.document_title} · <code>{s.citation_label}</code></Link>
        <span style={{ fontSize: 13, color: "#666" }}> · {t(`controls.relationTypes.${s.relation}`, { defaultValue: s.relation })} · {s.heading_path}</span>
      </li>)}</ul>
      <h3>{t("controls.relations")}</h3>
      {data.relations.length === 0 && <p>{t("common.empty")}</p>}
      <ul>{data.relations.map((r) => <li key={`${r.from_control_id}-${r.to_control_id}-${r.relation_type}`} style={{ marginBottom: 12 }}>
        <Link to={`/controls/${r.from_control_id}`}>#{r.from_control_id}</Link> → <Link to={`/controls/${r.to_control_id}`}>#{r.to_control_id}</Link> · {t(`controls.relationTypes.${r.relation_type}`, { defaultValue: r.relation_type })}
        <p style={{ margin: "4px 0", fontSize: 13, color: "#666", whiteSpace: "pre-wrap" }}>{r.rationale}</p>
      </li>)}</ul>
      <h3>{t("controls.frameworkMappings")}</h3>
      {(data.mappings ?? []).length === 0 && <p>{t("controls.noFrameworkMappings")}</p>}
      <ul>{(data.mappings ?? []).map((mapping) => <li key={`${mapping.framework_name}-${mapping.code}`}>
        {mapping.framework_name} · <code>{mapping.code}</code> {mapping.title} · {t(`mapping.strength.${mapping.strength}`, { defaultValue: mapping.strength })}
      </li>)}</ul>
    </>}
  </section>;
}
