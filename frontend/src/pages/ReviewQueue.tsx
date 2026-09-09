import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "../api";
import { useAuth } from "../auth";

export interface Proposal {
  id: number;
  kind: string;
  payload: Record<string, unknown>;
  citations: { clause_id: number; quote: string; document_id?: number; citation_label?: string }[];
  confidence: number | null;
  document_id: number | null;
  status: string;
  decided_payload?: Record<string, unknown> | null;
  // Optional until the API exposes eligibility to all READ users. Never guess thresholds.
  bulk_acceptable?: boolean;
  ocr_quality_flag?: boolean;
  mapping_context?: {
    framework_item: { id: number; code: string; title: string; description: string };
    control: { id: number; code: string; title: string; statement: string };
  } | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function HighlightQuote({ text, quote }: { text: string; quote: string }) {
  const position = quote ? text.indexOf(quote) : -1;
  if (position < 0) return <>{text}</>;
  return <>{text.slice(0, position)}<mark>{text.slice(position, position + quote.length)}</mark>{text.slice(position + quote.length)}</>;
}

function MappingPreview({
  proposal, editing, draft, busy, onDraftChange, onStrengthChange,
}: {
  proposal: Proposal;
  editing: boolean;
  draft: string;
  busy: boolean;
  onDraftChange: (value: string) => void;
  onStrengthChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const payload = proposal.payload;
  const item = proposal.mapping_context?.framework_item ?? asRecord(payload.framework_item);
  const control = proposal.mapping_context?.control ?? asRecord(payload.control);
  const itemCode = typeof item.code === "string" ? item.code : `#${String(payload.framework_item_id ?? "?")}`;
  const itemTitle = typeof item.title === "string" ? item.title : t("mapping.frameworkItem");
  const itemDescription = typeof item.description === "string" ? item.description : "";
  const controlCode = typeof control.code === "string" ? control.code : `#${String(payload.control_id ?? "?")}`;
  const controlTitle = typeof control.title === "string" ? control.title : t("mapping.control");
  const controlStatement = typeof control.statement === "string" ? control.statement : "";
  const quote = typeof payload.quote === "string" ? payload.quote : "";
  const strength = typeof payload.strength === "string" ? payload.strength : "partial";
  return <div style={{ marginTop: 12 }}>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 16 }}>
      <div>
        <h3>{t("mapping.frameworkItem")} · <code>{itemCode}</code> {itemTitle}</h3>
        <p style={{ whiteSpace: "pre-wrap" }}><HighlightQuote text={itemDescription} quote={quote} /></p>
        <p><strong>{t("mapping.quote")}:</strong> <mark>{quote}</mark></p>
      </div>
      <aside style={{ background: "#f7f7f7", padding: 12 }}>
        <h3>{t("mapping.control")} · <code>{controlCode}</code> {controlTitle}</h3>
        <p style={{ whiteSpace: "pre-wrap" }}>{controlStatement}</p>
      </aside>
    </div>
    <label>{t("mapping.strength.label")} <select aria-label={t("mapping.strength.label")} value={strength} disabled={busy} onChange={(event) => onStrengthChange(event.target.value)}>
      <option value="full">{t("mapping.strength.full")}</option>
      <option value="partial">{t("mapping.strength.partial")}</option>
      <option value="supporting">{t("mapping.strength.supporting")}</option>
    </select></label>
    {editing && <label style={{ display: "block", marginTop: 8 }}>{t("review.payload")}<textarea aria-label={t("review.payload")} rows={8} style={{ width: "100%", boxSizing: "border-box" }} value={draft} disabled={busy} onChange={(event) => onDraftChange(event.target.value)} /></label>}
  </div>;
}

export function ReviewQueue() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canDecide = user?.role === "admin" || user?.role === "grc_lead";
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const documentId = params.get("document_id") ?? "";
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const proposals = useQuery({
    queryKey: ["proposals", kind, documentId],
    queryFn: () => request<Proposal[]>(`/api/proposals?limit=200&${new URLSearchParams({ ...(kind ? { kind } : {}), ...(documentId ? { document_id: documentId } : {}) })}`),
    refetchInterval: 15000,
  });
  const stats = useQuery({ queryKey: ["proposal-stats"], queryFn: () => request<{ pending: number; by_kind: Record<string, number> }>("/api/proposals/stats"), refetchInterval: 15000 });
  async function refresh() {
    await Promise.all(["proposals", "proposal-stats", "controls", "control"].map((key) => client.invalidateQueries({ queryKey: [key] })));
  }
  const decide = useMutation({
    mutationFn: ({ id, ...body }: { id: number; decision: "accept" | "modify" | "reject"; payload?: Record<string, unknown>; reason?: string }) =>
      request<Proposal>(`/api/proposals/${id}/decide`, { method: "POST", body: JSON.stringify(body) }),
    onMutate: () => { setError(""); setNotice(""); },
    onError: (e: Error) => setError(e.message),
    onSuccess: async (_, variables) => {
      setEditing(null); setRejecting(null); setReason("");
      setSelected((ids) => ids.filter((id) => id !== variables.id));
      setNotice(t("review.decided"));
      await refresh();
    },
  });
  const eligibleIds = (proposals.data ?? []).filter((p) => p.status === "pending" && p.bulk_acceptable === true && p.ocr_quality_flag !== true && p.id !== editing && p.id !== rejecting).map((p) => p.id);
  const selectedIds = selected.filter((id) => eligibleIds.includes(id));
  const bulk = useMutation({
    mutationFn: (ids: number[]) => request<{ accepted: number; skipped: number }>("/api/proposals/bulk-accept", { method: "POST", body: JSON.stringify({ ids }) }),
    onMutate: () => { setError(""); setNotice(""); },
    onError: (e: Error) => setError(e.message),
    onSuccess: async (result) => { setNotice(t("review.bulkResult", result)); setSelected([]); await refresh(); },
  });
  const busy = decide.isPending || bulk.isPending;
  function modify(id: number) {
    try {
      const payload: unknown = JSON.parse(draft);
      if (!payload || typeof payload !== "object" || Array.isArray(payload) || !Object.keys(payload).length) throw new Error(t("review.invalidPayload"));
      const proposal = proposals.data?.find((p) => p.id === id);
      if (!proposal) return;
      const edited = payload as Record<string, unknown>;
      const next: Record<string, unknown> = proposal.kind === "matrix_mapping" ? { ...proposal.payload, mapping: edited } : { ...proposal.payload, ...edited };
      if (proposal.payload.origin === "matrix") {
        for (const field of ["origin", "matrix_mapping_proposal_id", "source_sha256", "row_number", "citations"]) next[field] = proposal.payload[field];
      }
      decide.mutate({ id, decision: "modify", payload: next });
    } catch { setError(t("review.invalidPayload")); }
  }
  return <section>
    <h2>{t("review.title")} {stats.data && <small>· {t("review.pending")} {stats.data.pending}</small>}</h2>
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
      <label>{t("review.kind")} <select value={kind} disabled={busy} onChange={(e) => { setSelected([]); setEditing(null); setRejecting(null); setParams({ ...(documentId ? { document_id: documentId } : {}), ...(e.target.value ? { kind: e.target.value } : {}) }); }}>
        <option value="">{t("review.allKinds")}</option>
        {[...new Set(["control_extract", "matrix_mapping", ...Object.keys(stats.data?.by_kind ?? {})])].map((k) => <option key={k} value={k}>{t(`review.kinds.${k}`, { defaultValue: k })}</option>)}
      </select></label>
      <button disabled={busy || proposals.isFetching} onClick={() => void refresh()}>{t("common.refresh")}</button>
      {documentId && <button onClick={() => { setSelected([]); setParams(kind ? { kind } : {}); }}>{t("review.clearDocument")}</button>}
      {canDecide && <button disabled={busy || proposals.isFetching || !selectedIds.length} onClick={() => bulk.mutate(selectedIds)}>{t("review.bulkAccept")} ({selectedIds.length})</button>}
    </div>
    {!canDecide && <p>{t("review.readOnly")}</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <p role="alert" style={{ color: "#c00" }}>{error}</p>}
    {proposals.isPending && <p role="status">{t("common.loading")}</p>}
    {proposals.error && <p role="alert">{proposals.error.message}</p>}
    {stats.error && <p role="alert">{t("review.statsError")} {stats.error.message}</p>}
    {proposals.isSuccess && proposals.data.length === 0 && <p>{t("review.empty")}</p>}
    {proposals.data && proposals.data.length >= 200 && <p>{t("review.limit")}</p>}
    {proposals.data?.map((p) => <article key={p.id} id={`proposal-${p.id}`} style={{ border: "1px solid #e5e5e5", borderRadius: 6, padding: 16, marginBottom: 16 }}>
      <div style={{ display: "flex", gap: 12, justifyContent: "space-between", flexWrap: "wrap" }}>
        <strong>#{p.id} · {t(`review.kinds.${p.kind}`, { defaultValue: p.kind })}</strong>
        <span>{t("review.confidence")} {p.confidence?.toFixed(2) ?? "—"}</span>
        {canDecide && <label><input type="checkbox" aria-label={t("review.select", { id: p.id })} disabled={busy || !eligibleIds.includes(p.id)} checked={selectedIds.includes(p.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, p.id] : selected.filter((id) => id !== p.id))} /> {t("review.batch")}</label>}
      </div>
      {p.ocr_quality_flag && <p style={{ color: "#946000" }}>🔍 {t("review.ocrSuspect")}</p>}
      {canDecide && !p.ocr_quality_flag && p.bulk_acceptable !== true && <p style={{ color: "#666", fontSize: 13 }}>{t(p.bulk_acceptable === false ? "review.manualOnly" : "review.eligibilityUnknown")}</p>}
      {p.kind === "mapping" ? <MappingPreview
        proposal={p}
        editing={editing === p.id}
        draft={draft}
        busy={busy}
        onDraftChange={setDraft}
        onStrengthChange={(strength) => {
          setEditing(p.id);
          setDraft(JSON.stringify({ ...p.payload, strength }, null, 2));
          setError("");
        }}
      /> : <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 16, marginTop: 12 }}>
        <div>
          <h3>{String(p.payload.title ?? t("review.payload"))}</h3>
          {editing === p.id ? <label>{t("review.payload")}<textarea aria-label={t("review.payload")} rows={14} style={{ width: "100%", boxSizing: "border-box" }} value={draft} disabled={busy} onChange={(e) => setDraft(e.target.value)} /></label> : <>
            {typeof p.payload.statement === "string" && <p style={{ whiteSpace: "pre-wrap" }}>{p.payload.statement}</p>}
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 13 }}>{JSON.stringify(p.payload, null, 2)}</pre>
          </>}
        </div>
        <aside style={{ background: "#f7f7f7", padding: 12 }}>
          <h3>{t("review.evidence")}</h3>
          {p.citations.length === 0 && <p>{t(p.kind === "matrix_mapping" ? "review.mappingEvidence" : "review.noEvidence")}</p>}
          {p.citations.map((c, i) => <div key={`${c.clause_id}-${i}`}>
            {(c.document_id ?? p.document_id) != null ? <Link to={`/documents/${c.document_id ?? p.document_id}#clause-${c.clause_id}`}>{c.citation_label ?? `#${c.clause_id}`}</Link> : <code>#{c.clause_id}</code>}
            <blockquote style={{ margin: "8px 0 16px", whiteSpace: "pre-wrap" }}>{c.quote}</blockquote>
          </div>)}
        </aside>
      </div>}
      {canDecide && p.status === "pending" && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        {editing !== p.id && rejecting !== p.id && <>
          <button disabled={busy} onClick={() => decide.mutate({ id: p.id, decision: "accept" })}>{t("review.accept")}</button>
          <button disabled={busy} onClick={() => {
            setEditing(p.id); setRejecting(null);
            const editable = p.kind === "matrix_mapping" ? p.payload.mapping : p.payload.origin === "matrix" ? Object.fromEntries(Object.entries(p.payload).filter(([field]) => !["origin", "matrix_mapping_proposal_id", "source_sha256", "row_number", "citations"].includes(field))) : p.payload;
            setDraft(JSON.stringify(editable, null, 2)); setError("");
          }}>{t("review.modify")}</button>
          <button disabled={busy} onClick={() => { setRejecting(p.id); setEditing(null); setReason(""); setError(""); }}>{t("review.reject")}</button>
        </>}
        {editing === p.id && <><button disabled={busy || !draft.trim()} onClick={() => modify(p.id)}>{t("review.modify")}</button><button disabled={busy} onClick={() => setEditing(null)}>{t("common.cancel")}</button></>}
        {rejecting === p.id && <><input aria-label={t("review.rejectReason")} placeholder={t("review.rejectReason")} value={reason} disabled={busy} onChange={(e) => setReason(e.target.value)} style={{ flex: 1, minWidth: 200 }} /><button disabled={busy || !reason.trim()} onClick={() => decide.mutate({ id: p.id, decision: "reject", reason: reason.trim() })}>{t("review.reject")}</button><button disabled={busy} onClick={() => setRejecting(null)}>{t("common.cancel")}</button></>}
      </div>}
    </article>)}
  </section>;
}
