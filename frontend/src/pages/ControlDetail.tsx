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
  return (
    <section>
      <p style={{ marginBottom: 16 }}>
        <Link to="/controls" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.875rem" }}>
          ← {t("controls.title")}
        </Link>
      </p>

      {detail.isPending && <p role="status">{t("common.loading")}</p>}
      {detail.error && (
        <p role="alert">
          <span>⚠️</span> {detail.error.message}{" "}
          <button className="kn-btn-sm" onClick={() => void detail.refetch()}>{t("common.retry")}</button>
        </p>
      )}

      {data && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <h2>
                <code style={{ fontSize: "1.25rem", marginRight: 10 }}>{data.code}</code>
                {data.title}
              </h2>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 6 }}>
                <span className="kn-badge">
                  {t("controls.category")}: {data.category ?? "—"}
                </span>
                <span className="kn-badge kn-badge-emerald">
                  {t("documents.status")}: {data.status}
                </span>
              </div>
            </div>
          </div>

          {/* Statement & Edit Pane */}
          <div className="kn-card" style={{ marginBottom: 24 }}>
            {form ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (form.title.trim() && form.statement.trim()) save.mutate();
                }}
                style={{ display: "grid", gap: 16, maxWidth: 760 }}
              >
                <label>
                  {t("controls.name")}
                  <input
                    required
                    disabled={save.isPending}
                    value={form.title}
                    onChange={(e) => setForm({ ...form, title: e.target.value })}
                    style={{ width: "100%" }}
                  />
                </label>
                <label>
                  {t("controls.statement")}
                  <textarea
                    required
                    disabled={save.isPending}
                    rows={6}
                    value={form.statement}
                    onChange={(e) => setForm({ ...form, statement: e.target.value })}
                    style={{ width: "100%" }}
                  />
                </label>
                <label>
                  {t("controls.category")}
                  <input
                    disabled={save.isPending}
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                  />
                </label>

                {save.error && <p role="alert"><span>⚠️</span> {save.error.message}</p>}

                <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
                  <button
                    className="kn-btn-primary"
                    disabled={save.isPending || !form.title.trim() || !form.statement.trim()}
                    type="submit"
                  >
                    {t("common.save")}
                  </button>
                  <button
                    type="button"
                    className="kn-btn-secondary"
                    disabled={save.isPending}
                    onClick={() => setForm(null)}
                  >
                    {t("common.cancel")}
                  </button>
                </div>
              </form>
            ) : (
              <div>
                <p style={{ whiteSpace: "pre-wrap", fontSize: "1rem", lineHeight: 1.65, color: "var(--text-primary)", margin: 0 }}>
                  {data.statement}
                </p>
                {canWrite && (
                  <div style={{ marginTop: 16 }}>
                    <button
                      className="kn-btn-secondary kn-btn-sm"
                      onClick={() => {
                        setForm({ title: data.title, statement: data.statement, category: data.category ?? "" });
                        save.reset();
                        setSaved(false);
                      }}
                    >
                      {t("common.edit")}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {saved && <p role="status">{t("common.saved")}</p>}

          {/* Sources Section */}
          <div className="kn-card" style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: "1.0625rem" }}>
              {t("controls.sources")} · {t("controls.backedBy", { count: new Set(data.sources.map((s) => s.document_id)).size })}
            </h3>
            {data.sources.length === 0 && <p style={{ color: "var(--text-tertiary)" }}>{t("controls.noSources")}</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.sources.map((s) => (
                <li
                  key={`${s.document_id}-${s.clause_id}`}
                  style={{
                    padding: "10px 14px",
                    background: "var(--stage-card-subtle)",
                    borderRadius: "var(--radius-sm)",
                    marginBottom: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <Link to={`/documents/${s.document_id}#clause-${s.clause_id}`} style={{ fontWeight: 600 }}>
                    {s.document_title} · <code>{s.citation_label}</code>
                  </Link>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    · <span className="kn-badge">{t(`controls.relationTypes.${s.relation}`, { defaultValue: s.relation })}</span> · {s.heading_path}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Relations Section */}
          <div className="kn-card" style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: "1.0625rem" }}>{t("controls.relations")}</h3>
            {data.relations.length === 0 && <p style={{ color: "var(--text-tertiary)" }}>{t("common.empty")}</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.relations.map((r) => (
                <li
                  key={`${r.from_control_id}-${r.to_control_id}-${r.relation_type}`}
                  style={{
                    padding: "12px 14px",
                    background: "var(--stage-card-subtle)",
                    borderRadius: "var(--radius-sm)",
                    marginBottom: 8,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <Link to={`/controls/${r.from_control_id}`} style={{ fontWeight: 600 }}>
                      #{r.from_control_id}
                    </Link>
                    <span style={{ color: "var(--accent-blue)" }}>→</span>
                    <Link to={`/controls/${r.to_control_id}`} style={{ fontWeight: 600 }}>
                      #{r.to_control_id}
                    </Link>
                    <span className="kn-badge kn-badge-blue">
                      {t(`controls.relationTypes.${r.relation_type}`, { defaultValue: r.relation_type })}
                    </span>
                  </div>
                  {r.rationale && (
                    <p style={{ margin: "6px 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)", whiteSpace: "pre-wrap" }}>
                      {r.rationale}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>

          {/* Framework Mappings Section */}
          <div className="kn-card">
            <h3 style={{ fontSize: "1.0625rem" }}>{t("controls.frameworkMappings")}</h3>
            {(data.mappings ?? []).length === 0 && <p style={{ color: "var(--text-tertiary)" }}>{t("controls.noFrameworkMappings")}</p>}
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {(data.mappings ?? []).map((mapping) => (
                <li
                  key={`${mapping.framework_name}-${mapping.code}`}
                  style={{
                    padding: "10px 14px",
                    background: "var(--stage-card-subtle)",
                    borderRadius: "var(--radius-sm)",
                    marginBottom: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{mapping.framework_name}</span> · <code>{mapping.code}</code> {mapping.title} ·{" "}
                  <span className="kn-badge kn-badge-purple">
                    {t(`mapping.strength.${mapping.strength}`, { defaultValue: mapping.strength })}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  );
}
