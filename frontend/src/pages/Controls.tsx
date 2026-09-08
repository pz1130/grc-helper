import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ApiError, getToken, request, setToken } from "../api";
import { useAuth } from "../auth";
import type { Proposal } from "./ReviewQueue";

export interface Control {
  id: number;
  code: string;
  title: string;
  statement: string;
  category: string | null;
  owner_user_id: number | null;
  status: string;
}

const MAPPING_FIELDS = ["code", "title", "statement", "category", "owner", "framework_refs", "note"] as const;

async function upload<T>(path: string, body: FormData): Promise<T> {
  const token = getToken();
  const response = await fetch(path, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body });
  if (response.status === 401) setToken(null);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, data.code ?? "error", data.message ?? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? response.status)));
  return data as T;
}

function MatrixImport() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [report, setReport] = useState<{ ok: boolean; report: string[]; rows: number } | null>(null);
  const [result, setResult] = useState<{ imported: number; proposal_ids: number[]; mapping_proposal_id: number } | null>(null);
  const [error, setError] = useState("");
  const [resumeId, setResumeId] = useState("");
  function body() {
    if (!file) throw new Error(t("matrix.chooseFile"));
    const form = new FormData(); form.append("file", file); return form;
  }
  async function refresh() {
    await Promise.all(["proposals", "proposal-stats", "controls"].map((key) => client.invalidateQueries({ queryKey: [key] })));
  }
  const propose = useMutation({
    mutationFn: () => upload<Proposal>("/api/matrix/propose-mapping", body()),
    onMutate: () => setError(""),
    onError: (e: Error) => setError(e.message),
    onSuccess: async (p) => { setProposal(p); setMapping(p.payload.mapping as Record<string, string>); setReport(null); setResult(null); await refresh(); },
  });
  const validate = useMutation({
    mutationFn: () => { const form = body(); form.append("mapping_json", JSON.stringify(mapping)); return upload<{ ok: boolean; report: string[]; rows: number }>("/api/matrix/validate", form); },
    onMutate: () => { setError(""); setReport(null); },
    onError: (e: Error) => setError(e.message),
    onSuccess: setReport,
  });
  const approve = useMutation({
    mutationFn: () => {
      if (!proposal) throw new Error(t("matrix.chooseFile"));
      const original = proposal.payload.mapping as Record<string, string>;
      const changed = JSON.stringify(Object.entries(original).sort()) !== JSON.stringify(Object.entries(mapping).sort());
      return request<Proposal>(`/api/proposals/${proposal.id}/decide`, { method: "POST", body: JSON.stringify(changed ? { decision: "modify", payload: { ...proposal.payload, mapping } } : { decision: "accept" }) });
    },
    onMutate: () => setError(""),
    onError: (e: Error) => setError(e.message),
    onSuccess: async (p) => { setProposal(p); await refresh(); },
  });
  const importRows = useMutation({
    mutationFn: () => {
      if (!proposal && !resumeId) throw new Error(t("matrix.chooseFile"));
      const form = body(); form.append("proposal_id", proposal ? String(proposal.id) : resumeId);
      return upload<{ imported: number; proposal_ids: number[]; mapping_proposal_id: number }>("/api/matrix/import", form);
    },
    onMutate: () => setError(""),
    onError: (e: Error) => setError(e.message),
    onSuccess: async (data) => { setResult(data); await refresh(); },
  });
  const approved = proposal?.status === "accepted" || proposal?.status === "modified";
  const busy = propose.isPending || validate.isPending || approve.isPending || importRows.isPending;
  const headers = Array.isArray(proposal?.payload.source_headers) ? proposal.payload.source_headers.filter((h): h is string => typeof h === "string") : [];
  return <details style={{ border: "1px solid #e5e5e5", borderRadius: 6, padding: 12, marginBottom: 16 }}>
    <summary>{t("matrix.title")}</summary>
    <p style={{ color: "#666" }}>{t("matrix.flow")}</p>
    <label>{t("matrix.file")} <input type="file" accept=".xlsx" disabled={busy} onChange={(e) => { setFile(e.target.files?.[0] ?? null); setProposal(null); setMapping({}); setReport(null); setResult(null); setError(""); }} /></label>{" "}
    <button disabled={!file || busy || !!proposal} onClick={() => propose.mutate()}>{t("matrix.propose")}</button>
    {!proposal && <div style={{ marginTop: 12 }}>
      <p>{t("matrix.resumeHint")}</p>
      <label>{t("matrix.proposalId")} <input type="number" min="1" step="1" value={resumeId} disabled={busy} onChange={(e) => { setResumeId(e.target.value); setResult(null); }} /></label>{" "}
      <button disabled={busy || !file || !Number.isSafeInteger(Number(resumeId)) || Number(resumeId) < 1 || !!result} onClick={() => importRows.mutate()}>{t("matrix.import")}</button>
    </div>}
    {busy && <p role="status">{t("common.loading")}</p>}
    {error && <p role="alert" style={{ color: "#c00" }}>{error}</p>}
    {proposal && <>
      <p><Link to="/review?kind=matrix_mapping">{t("review.title")} · #{proposal.id}</Link> · {proposal.status}</p>
      {typeof proposal.payload.notes === "string" && <p>{proposal.payload.notes}</p>}
      <p>{t("matrix.rows", { count: typeof proposal.payload.source_rows === "number" ? proposal.payload.source_rows : report?.rows ?? 0 })}</p>
      <div style={{ overflowX: "auto" }}><table><thead><tr><th>{t("matrix.target")}</th><th>{t("matrix.source")}</th></tr></thead><tbody>
        {MAPPING_FIELDS.map((field) => <tr key={field}><td>{t(`matrix.fields.${field}`)}{field === "title" || field === "statement" ? " *" : ""}</td><td>
          <select aria-label={t(`matrix.fields.${field}`)} value={mapping[field] ?? ""} disabled={busy || approved} onChange={(e) => { const next = { ...mapping }; if (e.target.value) next[field] = e.target.value; else delete next[field]; setMapping(next); setReport(null); setError(""); }}>
            <option value="">{t("matrix.unmapped")}</option>
            {[...new Set([...headers, ...Object.values(mapping)])].map((header) => <option key={header} value={header}>{header}</option>)}
          </select>
        </td></tr>)}
      </tbody></table></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <button disabled={busy || !mapping.title || !mapping.statement} onClick={() => validate.mutate()}>{t("matrix.validate")}</button>
        <button disabled={busy || approved || !report?.ok} onClick={() => approve.mutate()}>{t("matrix.approve")}</button>
        <button disabled={busy || !approved || !report?.ok || !!result} onClick={() => importRows.mutate()}>{t("matrix.import")}</button>
      </div>
      {report && <div role={report.ok ? "status" : "alert"}><p>{t(report.ok ? "matrix.valid" : "matrix.invalid", { count: report.rows })}</p><ul>{report.report.map((line, i) => <li key={i}>{line}</li>)}</ul></div>}
      {approved && !result && <p role="status">{t("matrix.approved")}</p>}
    </>}
    {result && <p role="status">{t("matrix.result", { count: result.imported })} <Link to="/review?kind=control_extract">{t("review.title")}</Link></p>}
  </details>;
}

export function Controls() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const canWrite = user?.role === "admin" || user?.role === "grc_lead";
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [documentId, setDocumentId] = useState("");
  const controls = useQuery({ queryKey: ["controls", search], queryFn: () => request<Control[]>(`/api/controls?limit=100&q=${encodeURIComponent(search)}`) });
  const documents = useQuery({ queryKey: ["documents"], queryFn: () => request<{ id: number; title: string; status: string }[]>("/api/documents"), enabled: canWrite });
  const extract = useMutation({ mutationFn: (id: string) => request<{ job_id: string }>(`/api/extraction/documents/${id}`, { method: "POST" }) });
  return <section>
    <h2>{t("controls.title")}</h2>
    {canWrite && <>
      <details style={{ border: "1px solid #e5e5e5", borderRadius: 6, padding: 12, marginBottom: 16 }}>
        <summary>{t("controls.extract")}</summary>
        <p>{t("controls.extractHint")}</p>
        {documents.isPending && <p role="status">{t("common.loading")}</p>}
        {documents.error && <p role="alert">{documents.error.message} <button onClick={() => void documents.refetch()}>{t("common.retry")}</button></p>}
        <select aria-label={t("controls.document")} disabled={extract.isPending} value={documentId} onChange={(e) => { setDocumentId(e.target.value); extract.reset(); }}>
          <option value="">{t("controls.document")}</option>
          {documents.data?.filter((d) => d.status === "active").map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select>{" "}<button disabled={!documentId || extract.isPending || extract.isSuccess} onClick={() => extract.mutate(documentId)}>{t("controls.extract")}</button>
        {extract.isPending && <p role="status">{t("common.loading")}</p>}
        {extract.error && <p role="alert">{extract.error.message}</p>}
        {extract.data && <p role="status">{t("controls.queued", { id: extract.data.job_id })} <Link to={`/review?document_id=${documentId}`}>{t("review.title")}</Link></p>}
      </details>
      <MatrixImport />
    </>}
    <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); }} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <input aria-label={t("controls.search")} placeholder={t("controls.search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 320, maxWidth: "100%" }} />
      <button type="submit">{t("search.run")}</button><button type="button" disabled={controls.isFetching} onClick={() => void controls.refetch()}>{t("common.refresh")}</button>
    </form>
    {controls.isPending && <p role="status">{t("common.loading")}</p>}
    {controls.error && <p role="alert">{controls.error.message}</p>}
    {controls.isSuccess && !controls.data.length && <p>{t("common.empty")}</p>}
    {controls.data && controls.data.length >= 100 && <p>{t("controls.limit")}</p>}
    {!!controls.data?.length && <div style={{ overflowX: "auto" }}><table style={{ marginTop: 12 }}>
      <thead><tr><th>{t("controls.code")}</th><th>{t("controls.name")}</th><th>{t("controls.statement")}</th><th>{t("controls.category")}</th></tr></thead>
      <tbody>{controls.data.map((c) => <tr key={c.id}><td><Link to={`/controls/${c.id}`}><code>{c.code}</code></Link></td><td><Link to={`/controls/${c.id}`}>{c.title}</Link></td><td style={{ fontSize: 13, color: "#555", maxWidth: 600 }}>{c.statement.slice(0, 150)}{c.statement.length > 150 ? "…" : ""}</td><td>{c.category ?? "—"}</td></tr>)}</tbody>
    </table></div>}
  </section>;
}
