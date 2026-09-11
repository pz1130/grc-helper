import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { download, request } from "../api";
import { useAuth } from "../auth";

interface Engagement { id: number; name: string; audit_type: string; status: string }
interface Question { id: number; seq: number; question_text: string; language: string; status: string }
interface Answer {
  id: number; question_id: number; body: string; language: string; gap_notes: string;
  cited_clause_ids: number[]; cited_control_ids: number[]; suggested_evidence_ids: number[];
  confidence: number | null; final_body: string | null; finalized_at: string | null;
}
interface HistoryAnswer extends Answer { question_text: string; engagement_name: string }

export function AuditAssistant() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const client = useQueryClient();
  const canDraft = user?.role !== "viewer";
  const canFinalize = user?.role === "admin" || user?.role === "grc_lead";
  const [engagementId, setEngagementId] = useState<number | null>(null);
  const [questionId, setQuestionId] = useState<number | null>(null);
  const [engagementName, setEngagementName] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [xlsxFile, setXlsxFile] = useState<File | null>(null);
  const [xlsxInputKey, setXlsxInputKey] = useState(0);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const engagements = useQuery({
    queryKey: ["audit-engagements"],
    queryFn: () => request<Engagement[]>("/api/audit/engagements"),
  });
  useEffect(() => {
    if (!engagementId && engagements.data?.length) setEngagementId(engagements.data[0].id);
  }, [engagementId, engagements.data]);

  const questions = useQuery({
    queryKey: ["audit-questions", engagementId],
    queryFn: () => request<Question[]>(`/api/audit/engagements/${engagementId}/questions`),
    enabled: engagementId != null,
    refetchInterval: 10000,
  });
  useEffect(() => {
    if (questions.data?.length && !questions.data.some((row) => row.id === questionId)) {
      setQuestionId(questions.data[0].id);
    }
  }, [questionId, questions.data]);

  const answer = useQuery({
    queryKey: ["audit-answer", questionId],
    queryFn: () => request<Answer | null>(`/api/audit/questions/${questionId}/answer`),
    enabled: questionId != null,
    refetchInterval: 10000,
  });
  useEffect(() => { if (answer.data) setDraft(answer.data.body); else setDraft(""); }, [answer.data]);

  const history = useQuery({
    queryKey: ["audit-history"],
    queryFn: () => request<HistoryAnswer[]>("/api/audit/history"),
  });
  const fail = (value: Error) => setError(value.message);
  const refresh = async () => {
    await Promise.all(["audit-engagements", "audit-questions", "audit-answer", "audit-history", "proposals", "proposal-stats"].map((key) => client.invalidateQueries({ queryKey: [key] })));
  };

  const createEngagement = useMutation({
    mutationFn: () => request<Engagement>("/api/audit/engagements", { method: "POST", body: JSON.stringify({ name: engagementName, audit_type: "external", status: "preparing" }) }),
    onError: fail,
    onSuccess: async (row) => { setError(""); setEngagementName(""); setEngagementId(row.id); setQuestionId(null); setNotice(t("audit.created")); await refresh(); },
  });
  const importQuestions = useMutation({
    mutationFn: () => request<Question[]>(`/api/audit/engagements/${engagementId}/questions`, { method: "POST", body: JSON.stringify({ text: questionsText, language: "en" }) }),
    onError: fail,
    onSuccess: async (rows) => { setError(""); setQuestionsText(""); setQuestionId(rows[0]?.id ?? null); setNotice(t("audit.imported", { count: rows.length })); await refresh(); },
  });
  const importXlsx = useMutation({
    mutationFn: () => {
      const form = new FormData();
      if (xlsxFile) form.append("file", xlsxFile);
      return request<Question[]>(`/api/audit/engagements/${engagementId}/questions/xlsx`, { method: "POST", body: form });
    },
    onError: fail,
    onSuccess: async (rows) => { setError(""); setXlsxFile(null); setXlsxInputKey((value) => value + 1); setQuestionId(rows[0]?.id ?? null); setNotice(t("audit.xlsxImported", { count: rows.length })); await refresh(); },
  });
  const exportWord = useMutation({
    mutationFn: () => download(`/api/audit/engagements/${engagementId}/export.docx?language=${i18n.language.startsWith("zh") ? "zh" : "en"}`),
    onError: fail,
    onSuccess: (blob) => {
      setError("");
      const selectedEngagement = engagements.data?.find((row) => row.id === engagementId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${selectedEngagement?.name ?? "audit"}-audit-responses.docx`;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(t("audit.exported"));
    },
  });
  const generate = useMutation({
    mutationFn: (language: string) => request<{ proposal_id: number }>(`/api/audit/questions/${questionId}/generate`, { method: "POST", body: JSON.stringify({ language }) }),
    onError: fail,
    onSuccess: async (row) => { setError(""); setNotice(t("audit.generated", { id: row.proposal_id })); await refresh(); },
  });
  const save = useMutation({
    mutationFn: () => request<Answer>(`/api/audit/answers/${answer.data?.id}`, { method: "PATCH", body: JSON.stringify({ body: draft }) }),
    onError: fail,
    onSuccess: async () => { setError(""); setNotice(t("audit.saved")); await refresh(); },
  });
  const finalize = useMutation({
    mutationFn: () => request<Answer>(`/api/audit/answers/${answer.data?.id}/finalize`, { method: "POST" }),
    onError: fail,
    onSuccess: async () => { setError(""); setNotice(t("audit.finalized")); await refresh(); },
  });
  const busy = createEngagement.isPending || importQuestions.isPending || importXlsx.isPending || exportWord.isPending || generate.isPending || save.isPending || finalize.isPending;
  const selected = questions.data?.find((row) => row.id === questionId);

  return (
    <section>
      <h2>{t("audit.title")}</h2>
      <p style={{ color: "var(--text-secondary)" }}>{t("audit.subtitle")}</p>
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">⚠️ {error}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, .8fr) minmax(260px, 1fr) minmax(360px, 1.5fr)", gap: 16, alignItems: "start" }}>
        <aside className="kn-card">
          <h3>{t("audit.engagements")}</h3>
          {engagements.data?.map((row) => (
            <button key={row.id} className={row.id === engagementId ? "kn-btn-primary" : "kn-btn-secondary"} style={{ display: "block", width: "100%", marginBottom: 8, textAlign: "left" }} onClick={() => { setEngagementId(row.id); setQuestionId(null); }}>
              {row.name}<br /><small>{t(`audit.types.${row.audit_type}`)}</small>
            </button>
          ))}
          {canDraft && <div style={{ borderTop: "1px solid var(--stage-border)", marginTop: 16, paddingTop: 16 }}>
            <input aria-label={t("audit.newEngagement")} placeholder={t("audit.newEngagement")} value={engagementName} onChange={(event) => setEngagementName(event.target.value)} />
            <button className="kn-btn-primary" disabled={busy || !engagementName.trim()} style={{ marginTop: 8 }} onClick={() => createEngagement.mutate()}>{t("common.create", { defaultValue: "Create" })}</button>
          </div>}
          {engagementId && <button className="kn-btn-secondary" disabled={busy} style={{ width: "100%", marginTop: 12 }} onClick={() => exportWord.mutate()}>{t("audit.exportWord")}</button>}
        </aside>

        <div className="kn-card">
          <h3>{t("audit.questions")}</h3>
          {questions.data?.map((row) => (
            <button key={row.id} className={row.id === questionId ? "kn-btn-primary" : "kn-btn-secondary"} style={{ display: "block", width: "100%", marginBottom: 8, textAlign: "left" }} onClick={() => setQuestionId(row.id)}>
              {row.seq}. {row.question_text}<br /><small>{t(`audit.status.${row.status}`)}</small>
            </button>
          ))}
          {engagementId && canDraft && <div style={{ borderTop: "1px solid var(--stage-border)", marginTop: 16, paddingTop: 16 }}>
            <textarea aria-label={t("audit.pasteQuestions")} placeholder={t("audit.pasteQuestions")} rows={6} style={{ width: "100%", boxSizing: "border-box" }} value={questionsText} onChange={(event) => setQuestionsText(event.target.value)} />
            <button className="kn-btn-primary" disabled={busy || !questionsText.trim()} onClick={() => importQuestions.mutate()}>{t("audit.import")}</button>
            <div style={{ borderTop: "1px solid var(--stage-border)", marginTop: 16, paddingTop: 16 }}>
              <label>
                {t("audit.xlsxFile")}
                <input key={xlsxInputKey} aria-label={t("audit.xlsxFile")} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => setXlsxFile(event.target.files?.[0] ?? null)} />
              </label>
              <p style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>{t("audit.xlsxHint")}</p>
              <button className="kn-btn-secondary" disabled={busy || !xlsxFile} onClick={() => importXlsx.mutate()}>{t("audit.importXlsx")}</button>
            </div>
          </div>}
        </div>

        <main className="kn-card">
          <h3>{selected?.question_text ?? t("audit.selectQuestion")}</h3>
          {selected && !answer.data && <>
            <p style={{ color: "var(--text-secondary)" }}>{t("audit.noDraft")}</p>
            {canDraft && <div style={{ display: "flex", gap: 8 }}>
              <button className="kn-btn-primary" disabled={busy} onClick={() => generate.mutate("en")}>{t("audit.generateEn")}</button>
              <button className="kn-btn-secondary" disabled={busy} onClick={() => generate.mutate("zh")}>{t("audit.generateZh")}</button>
            </div>}
            {generate.isSuccess && <p><Link to="/review?kind=answer">{t("audit.reviewProposal")}</Link></p>}
          </>}
          {answer.data && <>
            <textarea aria-label={t("audit.answer")} rows={16} style={{ width: "100%", boxSizing: "border-box" }} value={draft} disabled={!!answer.data.finalized_at || !canDraft} onChange={(event) => setDraft(event.target.value)} />
            {answer.data.gap_notes && <p style={{ color: "var(--accent-amber)" }}>⚠️ {answer.data.gap_notes}</p>}
            <p style={{ fontSize: "0.8125rem", color: "var(--text-tertiary)" }}>{t("audit.references", { clauses: answer.data.cited_clause_ids.length, controls: answer.data.cited_control_ids.length, evidence: answer.data.suggested_evidence_ids.length })}</p>
            {!answer.data.finalized_at && canDraft && <button className="kn-btn-secondary" disabled={busy || !draft.trim()} onClick={() => save.mutate()}>{t("common.save")}</button>}
            {!answer.data.finalized_at && canFinalize && <button className="kn-btn-primary" disabled={busy || !draft.trim()} style={{ marginLeft: 8 }} onClick={() => finalize.mutate()}>{t("audit.finalize")}</button>}
            {answer.data.finalized_at && <span className="kn-badge kn-badge-emerald">{t("audit.finalized")}</span>}
          </>}
        </main>
      </div>
      <div className="kn-card" style={{ marginTop: 20 }}>
        <h3>{t("audit.history")}</h3>
        {history.data?.map((row) => <div key={row.id} style={{ borderTop: "1px solid var(--stage-border)", padding: "12px 0" }}><strong>{row.question_text}</strong><div style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>{row.engagement_name}</div><p>{row.final_body}</p></div>)}
        {history.data?.length === 0 && <p style={{ color: "var(--text-tertiary)" }}>{t("audit.noHistory")}</p>}
      </div>
    </section>
  );
}
