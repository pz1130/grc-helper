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
  citations: { clause_id: number; quote: string; document_id?: number; citation_label?: string; document_title?: string; heading_path?: string }[];
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
    item_coverage?: {
      closed: boolean;
      confirmed: { control_code: string; strength: string }[];
    };
  } | null;
  relation_context?: {
    relation_type?: string;
    from: { id: number; code: string; title: string; statement: string };
    to: { id: number; code: string; title: string; statement: string };
  } | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

type Citation = Proposal["citations"][number];

/** 同一条款的多条引文归到一个来源块下——条款是引用原子，落库时也按 clause_id 去重。 */
function groupByClause(citations: Citation[]): [number, Citation[]][] {
  const groups = new Map<number, Citation[]>();
  for (const citation of citations) {
    const bucket = groups.get(citation.clause_id);
    if (bucket) bucket.push(citation);
    else groups.set(citation.clause_id, [citation]);
  }
  return [...groups.entries()];
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
  const quote = typeof payload.framework_item_quote === "string" ? payload.framework_item_quote : "";
  const strength = typeof payload.strength === "string" ? payload.strength : "partial";
  // 目标项已被已确认的 full/partial 关掉时，这条确认了也不改变覆盖度；若它本身
  // 是 supporting，连差距清单上的标记都不会新增——审之前就该看见这件事。
  const coverage = proposal.mapping_context?.item_coverage;
  const covered = coverage?.closed === true;
  const coveredBy = (coverage?.confirmed ?? [])
    .filter((row) => row.strength === "full" || row.strength === "partial")
    .map((row) => `${row.control_code} (${t(`mapping.strength.${row.strength}`, { defaultValue: row.strength })})`)
    .join("、");

  return (
    <div style={{ marginTop: 16 }}>
      {covered && (
        <p
          role="note"
          style={{
            margin: "0 0 16px",
            padding: "10px 14px",
            fontSize: "0.875rem",
            lineHeight: 1.6,
            color: "var(--accent-amber)",
            background: "var(--accent-amber-bg)",
            border: "1px solid var(--accent-amber-border)",
            borderRadius: "var(--radius-xs)",
          }}
        >
          {t("mapping.alreadyCovered", { controls: coveredBy })}
          {strength === "supporting" && <> {t("mapping.supportingNoEffect")}</>}
        </p>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 16, marginBottom: 16 }}>
        <div className="kn-card" style={{ background: "var(--stage-card-subtle)" }}>
          <h3 style={{ fontSize: "1.0625rem" }}>
            {t("mapping.frameworkItem")} · <code>{itemCode}</code> {itemTitle}
          </h3>
          <p style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
            <HighlightQuote text={itemDescription} quote={quote} />
          </p>
          <div style={{ marginTop: 12, padding: "8px 12px", background: "rgba(255, 214, 10, 0.08)", borderRadius: "var(--radius-xs)", border: "1px solid rgba(255, 214, 10, 0.2)" }}>
            <strong style={{ fontSize: "0.8125rem", color: "var(--accent-amber)" }}>{t("mapping.quote")}: </strong>
            <mark>{quote}</mark>
          </div>
        </div>
        <aside className="kn-card" style={{ background: "var(--stage-card-subtle)" }}>
          <h3 style={{ fontSize: "1.0625rem" }}>
            {t("mapping.control")} · <code>{controlCode}</code> {controlTitle}
          </h3>
          <p style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
            {controlStatement}
          </p>
        </aside>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <label style={{ flexDirection: "row", alignItems: "center" }}>
          <span>{t("mapping.strength.label")}</span>
          <select
            aria-label={t("mapping.strength.label")}
            value={strength}
            disabled={busy}
            onChange={(event) => onStrengthChange(event.target.value)}
            style={{ padding: "6px 28px 6px 12px" }}
          >
            <option value="full">{t("mapping.strength.full")}</option>
            <option value="partial">{t("mapping.strength.partial")}</option>
            <option value="supporting">{t("mapping.strength.supporting")}</option>
          </select>
        </label>
      </div>

      {editing && (
        <label style={{ display: "block", marginTop: 16 }}>
          {t("review.payload")}
          <textarea
            aria-label={t("review.payload")}
            rows={8}
            style={{ width: "100%", boxSizing: "border-box" }}
            value={draft}
            disabled={busy}
            onChange={(event) => onDraftChange(event.target.value)}
          />
        </label>
      )}
    </div>
  );
}

function RelationBody({
  proposal, editing, draft, busy, onDraftChange,
}: {
  proposal: Proposal;
  editing: boolean;
  draft: string;
  busy: boolean;
  onDraftChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const context = proposal.relation_context;
  const payload = proposal.payload as Record<string, unknown>;
  const fromQuote = typeof payload.from_quote === "string" ? payload.from_quote : "";
  const toQuote = typeof payload.to_quote === "string" ? payload.to_quote : "";
  const relationType = context?.relation_type
    ?? (typeof payload.relation_type === "string" ? payload.relation_type : "");
  const label = relationType === "duplicates"
    ? t("relations.duplicates")
    : t("relations.dependsOn");
  const editor = editing && (
    <label style={{ display: "block", marginTop: 16 }}>
      {t("review.payload")}
      <textarea
        aria-label={t("review.payload")}
        rows={8}
        style={{ width: "100%", boxSizing: "border-box" }}
        value={draft}
        disabled={busy}
        onChange={(event) => onDraftChange(event.target.value)}
      />
    </label>
  );

  if (!context) {
    return (
      <div style={{ marginTop: 14 }}>
        <p><strong style={{ color: "var(--accent-blue)" }}>{label}</strong></p>
        <p role="note" style={{ color: "var(--accent-amber)" }}>{t("relations.contextMissing")}</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 13 }}>
          {JSON.stringify(proposal.payload, null, 2)}
        </pre>
        {editor}
      </div>
    );
  }

  return (
    <div style={{ marginTop: 14 }}>
      <p><strong style={{ color: "var(--accent-blue)" }}>{label}</strong></p>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <section className="kn-card" style={{ background: "var(--stage-card-subtle)" }}>
          <h3 style={{ fontSize: "1rem" }}>
            {t("relations.from")} · <code>{context.from.code}</code> {context.from.title}
          </h3>
          <p style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
            <HighlightQuote text={context.from.statement} quote={fromQuote} />
          </p>
        </section>
        <section className="kn-card" style={{ background: "var(--stage-card-subtle)" }}>
          <h3 style={{ fontSize: "1rem" }}>
            {t("relations.to")} · <code>{context.to.code}</code> {context.to.title}
          </h3>
          <p style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
            <HighlightQuote text={context.to.statement} quote={toQuote} />
          </p>
        </section>
      </div>
      {editor}
    </div>
  );
}

export function ReviewQueue() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canDecide = user?.role === "admin" || user?.role === "grc_lead";
  const canWrite = user?.role === "admin" || user?.role === "grc_lead";
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const kind = params.get("kind") ?? "";
  const documentId = params.get("document_id") ?? "";
  const strength = params.getAll("strength");
  const [selected, setSelected] = useState<number[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [rejecting, setRejecting] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const proposals = useQuery({
    queryKey: ["proposals", kind, documentId, strength.join(",")],
    queryFn: () => {
      const query = new URLSearchParams({ limit: "200", ...(kind ? { kind } : {}), ...(documentId ? { document_id: documentId } : {}) });
      for (const value of strength) query.append("strength", value);
      return request<Proposal[]>(`/api/proposals?${query}`);
    },
    refetchInterval: 15000,
  });

  const stats = useQuery({
    queryKey: ["proposal-stats"],
    queryFn: () => request<{ pending: number; by_kind: Record<string, number> }>("/api/proposals/stats"),
    refetchInterval: 15000,
  });

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

  const infer = useMutation({
    mutationFn: () => request<{ job_id: string }>("/api/relations/infer", { method: "POST" }),
    onMutate: () => { setError(""); setNotice(""); },
    onError: (e: Error) => setError(e.message),
    onSuccess: (result) => setNotice(t("relations.queued", { id: result.job_id })),
  });

  const embedVectors = useMutation({
    mutationFn: () => request<{ embedded: number; pending: number }>("/api/relations/embed", { method: "POST" }),
    onMutate: () => { setError(""); setNotice(""); },
    onError: (e: Error) => setError(e.message),
    onSuccess: (result) => setNotice(t("relations.embedded", { count: result.embedded, pending: result.pending })),
  });

  const busy = decide.isPending || bulk.isPending || infer.isPending || embedVectors.isPending;

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

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 20 }}>
        <div>
          <h2>
            {t("review.title")}
            {stats.data && (
              <span className="kn-badge kn-badge-blue" style={{ marginLeft: 12, verticalAlign: "middle" }}>
                {t("review.pending")} {stats.data.pending}
              </span>
            )}
          </h2>
          <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Autonomous Extraction Verification & Human-in-the-Loop Cockpit
          </p>
        </div>
      </div>

      {/* Control Filter Bar */}
      <div
        className="kn-card"
        style={{
          padding: "14px 18px",
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          marginBottom: 20,
        }}
      >
        <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <span>{t("review.kind")}</span>
          <select
            value={kind}
            disabled={busy}
            onChange={(e) => {
              setSelected([]); setEditing(null); setRejecting(null);
              setParams({ ...(documentId ? { document_id: documentId } : {}), ...(e.target.value ? { kind: e.target.value } : {}) });
            }}
            style={{ padding: "6px 28px 6px 12px" }}
          >
            <option value="">{t("review.allKinds")}</option>
            {[...new Set(["control_extract", "matrix_mapping", ...Object.keys(stats.data?.by_kind ?? {})])].map((k) => (
              <option key={k} value={k}>{t(`review.kinds.${k}`, { defaultValue: k })}</option>
            ))}
          </select>
        </label>

        {kind === "mapping" && (
          <label style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <span>{t("review.strength")}</span>
            <select
              value={strength.join(",")}
              disabled={busy}
              onChange={(e) => {
                setSelected([]); setEditing(null); setRejecting(null);
                const next = new URLSearchParams({ ...(kind ? { kind } : {}), ...(documentId ? { document_id: documentId } : {}) });
                for (const value of e.target.value ? e.target.value.split(",") : []) next.append("strength", value);
                setParams(next);
              }}
              style={{ padding: "6px 28px 6px 12px" }}
            >
              <option value="">{t("review.allStrengths")}</option>
              <option value="full,partial">{t("review.coverageAffecting")}</option>
              <option value="full">{t("mapping.strength.full")}</option>
              <option value="partial">{t("mapping.strength.partial")}</option>
              <option value="supporting">{t("mapping.strength.supporting")}</option>
            </select>
          </label>
        )}

        <button className="kn-btn-secondary kn-btn-sm" disabled={busy || proposals.isFetching} onClick={() => void refresh()}>
          {t("common.refresh")}
        </button>

        {documentId && (
          <button className="kn-btn-secondary kn-btn-sm" onClick={() => { setSelected([]); setParams(kind ? { kind } : {}); }}>
            {t("review.clearDocument")}
          </button>
        )}

        {canDecide && (
          <button
            className="kn-btn-primary kn-btn-sm"
            disabled={busy || proposals.isFetching || !selectedIds.length}
            onClick={() => bulk.mutate(selectedIds)}
          >
            {t("review.bulkAccept")} ({selectedIds.length})
          </button>
        )}

        {canWrite && (
          <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
            <button className="kn-btn-secondary kn-btn-sm" disabled={busy} onClick={() => infer.mutate()}>
              {t("relations.infer")}
            </button>
            <button className="kn-btn-secondary kn-btn-sm" disabled={busy} onClick={() => embedVectors.mutate()}>
              {t("relations.embed")}
            </button>
          </div>
        )}
      </div>

      {!canDecide && <p style={{ color: "var(--text-tertiary)", fontSize: "0.875rem" }}>{t("review.readOnly")}</p>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert"><span>⚠️</span> {error}</p>}
      {proposals.isPending && <p role="status">{t("common.loading")}</p>}
      {proposals.error && <p role="alert"><span>⚠️</span> {proposals.error.message}</p>}
      {stats.error && <p role="alert"><span>⚠️</span> {t("review.statsError")} {stats.error.message}</p>}
      {proposals.isSuccess && proposals.data.length === 0 && (
        <div className="kn-card" style={{ textAlign: "center", padding: "48px 20px" }}>
          <div style={{ fontSize: "2rem", marginBottom: 8, opacity: 0.5 }}>✓</div>
          <p style={{ color: "var(--text-secondary)", margin: 0 }}>{t("review.empty")}</p>
        </div>
      )}
      {proposals.data && proposals.data.length >= 200 && <p style={{ color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>{t("review.limit")}</p>}

      {/* Proposal Cards Stream */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {proposals.data?.map((p) => {
          const confidence = p.confidence ?? 0;
          const confBadgeClass = confidence >= 0.85 ? "kn-badge-emerald" : confidence >= 0.65 ? "kn-badge-amber" : "kn-badge-ruby";

          return (
            <article
              key={p.id}
              id={`proposal-${p.id}`}
              className="kn-card"
              style={{ padding: "20px 24px" }}
            >
              {/* Proposal Header */}
              <div style={{ display: "flex", gap: 12, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", borderBottom: "1px solid var(--stage-border)", paddingBottom: 14 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontSize: "1.0625rem", fontWeight: 700, color: "var(--text-primary)" }}>
                    #{p.id}
                  </span>
                  <span className="kn-badge">
                    {t(`review.kinds.${p.kind}`, { defaultValue: p.kind })}
                  </span>
                  <span className={`kn-badge ${confBadgeClass}`}>
                    <span className={`kn-dot ${confidence >= 0.85 ? "kn-dot-emerald" : confidence >= 0.65 ? "kn-dot-amber" : "kn-dot-ruby"}`} />
                    {t("review.confidence")} {p.confidence?.toFixed(2) ?? "—"}
                  </span>
                </div>

                {canDecide && p.kind !== "relation" && (
                  <label style={{ flexDirection: "row", alignItems: "center", gap: 6, margin: 0 }}>
                    <input
                      type="checkbox"
                      aria-label={t("review.select", { id: p.id })}
                      disabled={busy || !eligibleIds.includes(p.id)}
                      checked={selectedIds.includes(p.id)}
                      onChange={(e) => setSelected(e.target.checked ? [...selected, p.id] : selected.filter((id) => id !== p.id))}
                    />
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{t("review.batch")}</span>
                  </label>
                )}
              </div>

              {p.ocr_quality_flag && (
                <div style={{ marginTop: 10 }}>
                  <span className="kn-badge kn-badge-amber">
                    🔍 {t("review.ocrSuspect")}
                  </span>
                </div>
              )}

              {canDecide && !p.ocr_quality_flag && p.bulk_acceptable !== true && (
                <p style={{ color: "var(--text-tertiary)", fontSize: "0.8125rem", marginTop: 8 }}>
                  {t(p.bulk_acceptable === false ? "review.manualOnly" : "review.eligibilityUnknown")}
                </p>
              )}

              {/* Card Body */}
              {p.kind === "mapping" ? (
                <MappingPreview
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
                />
              ) : p.kind === "relation" ? (
                <RelationBody
                  proposal={p}
                  editing={editing === p.id}
                  draft={draft}
                  busy={busy}
                  onDraftChange={setDraft}
                />
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", gap: 16, marginTop: 16 }}>
                  {/* Left Payload Pane */}
                  <div className="kn-card" style={{ background: "var(--stage-card-subtle)", margin: 0 }}>
                    <h3 style={{ fontSize: "1.0625rem", marginTop: 0 }}>
                      {String(p.payload.title ?? t("review.payload"))}
                    </h3>
                    {editing === p.id ? (
                      <label>
                        {t("review.payload")}
                        <textarea
                          aria-label={t("review.payload")}
                          rows={14}
                          style={{ width: "100%", boxSizing: "border-box" }}
                          value={draft}
                          disabled={busy}
                          onChange={(e) => setDraft(e.target.value)}
                        />
                      </label>
                    ) : (
                      <>
                        {typeof p.payload.statement === "string" && (
                          <p style={{ whiteSpace: "pre-wrap", fontSize: "0.875rem", lineHeight: 1.6, color: "var(--text-secondary)" }}>
                            {p.payload.statement}
                          </p>
                        )}
                        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: "0.75rem", maxHeight: 180, overflowY: "auto" }}>
                          {JSON.stringify(p.payload, null, 2)}
                        </pre>
                      </>
                    )}
                  </div>

                  {/* Right Evidence Pane */}
                  <aside className="kn-card" style={{ background: "var(--stage-card-subtle)", margin: 0 }}>
                    <h3 style={{ fontSize: "1.0625rem", marginTop: 0 }}>{t("review.evidence")}</h3>
                    {p.citations.length === 0 && (
                      <p style={{ color: "var(--text-tertiary)", fontSize: "0.875rem" }}>
                        {t(p.kind === "matrix_mapping" ? "review.mappingEvidence" : "review.noEvidence")}
                      </p>
                    )}
                    {groupByClause(p.citations).map(([clauseId, group]) => (
                      <div key={clauseId} style={{ marginBottom: 14, paddingBottom: 10, borderBottom: "1px solid var(--stage-border-subtle)" }}>
                        {group[0].document_title && (
                          <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                            {group[0].document_title}
                          </div>
                        )}
                        {group[0].heading_path && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", margin: "2px 0 4px 0" }}>
                            {group[0].heading_path}
                          </div>
                        )}
                        {(group[0].document_id ?? p.document_id) != null ? (
                          <Link to={`/documents/${group[0].document_id ?? p.document_id}#clause-${clauseId}`}>
                            <code>{group[0].citation_label ?? `#${clauseId}`}</code>
                          </Link>
                        ) : (
                          <code>#{clauseId}</code>
                        )}
                        {group.map((c, i) => (
                          <blockquote
                            key={i}
                            style={{
                              margin: "8px 0 0 0",
                              whiteSpace: "pre-wrap",
                              fontSize: "0.8125rem",
                              lineHeight: 1.5,
                              color: "var(--text-secondary)",
                              borderLeft: "2px solid var(--accent-blue)",
                              paddingLeft: 10,
                            }}
                          >
                            {c.quote}
                          </blockquote>
                        ))}
                      </div>
                    ))}
                  </aside>
                </div>
              )}

              {/* Action Buttons Bar */}
              {canDecide && p.status === "pending" && (
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--stage-border)" }}>
                  {editing !== p.id && rejecting !== p.id && (
                    <>
                      <button
                        className="kn-btn-primary"
                        disabled={busy}
                        onClick={() => decide.mutate({ id: p.id, decision: "accept" })}
                      >
                        {t("review.accept")}
                      </button>
                      <button
                        className="kn-btn-secondary"
                        disabled={busy}
                        onClick={() => {
                          setEditing(p.id); setRejecting(null);
                          const editable = p.kind === "matrix_mapping" ? p.payload.mapping : p.payload.origin === "matrix" ? Object.fromEntries(Object.entries(p.payload).filter(([field]) => !["origin", "matrix_mapping_proposal_id", "source_sha256", "row_number", "citations"].includes(field))) : p.payload;
                          setDraft(JSON.stringify(editable, null, 2)); setError("");
                        }}
                      >
                        {t("review.modify")}
                      </button>
                      <button
                        className="kn-btn-danger"
                        disabled={busy}
                        onClick={() => { setRejecting(p.id); setEditing(null); setReason(""); setError(""); }}
                      >
                        {t("review.reject")}
                      </button>
                    </>
                  )}
                  {editing === p.id && (
                    <>
                      <button
                        className="kn-btn-primary"
                        disabled={busy || !draft.trim()}
                        onClick={() => modify(p.id)}
                      >
                        {t("review.modify")}
                      </button>
                      <button
                        className="kn-btn-secondary"
                        disabled={busy}
                        onClick={() => setEditing(null)}
                      >
                        {t("common.cancel")}
                      </button>
                    </>
                  )}
                  {rejecting === p.id && (
                    <>
                      <input
                        aria-label={t("review.rejectReason")}
                        placeholder={t("review.rejectReason")}
                        value={reason}
                        disabled={busy}
                        onChange={(e) => setReason(e.target.value)}
                        style={{ flex: 1, minWidth: 220 }}
                      />
                      <button
                        className="kn-btn-danger"
                        disabled={busy || !reason.trim()}
                        onClick={() => decide.mutate({ id: p.id, decision: "reject", reason: reason.trim() })}
                      >
                        {t("review.reject")}
                      </button>
                      <button
                        className="kn-btn-secondary"
                        disabled={busy}
                        onClick={() => setRejecting(null)}
                      >
                        {t("common.cancel")}
                      </button>
                    </>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
