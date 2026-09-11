import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";

import { getToken, request } from "../api";

interface Coverage {
  document_id: number;
  clauses: number;
  normative_clauses: number;
  controls: number;
  proposals: number;
  uncovered_normative: number;
  never_extracted: boolean;
}

interface Doc {
  id: number;
  title: string;
  doc_type: string;
  status: string;
  version: string | null;
  owner: string | null;
  effective_date: string | null;
  review_due_date: string | null;
  original_filename: string;
  parse_error: string | null;
  parse_warnings: string | null;
  ocr_quality_flag: boolean;
}

const IN_FLIGHT = new Set(["uploaded", "parsing"]);

/** 抽取盲区那一格。没有数据时留空，不猜。 */
function ExtractionCell({ row }: { row?: Coverage }) {
  const { t } = useTranslation();
  if (!row) return <td>—</td>;
  if (row.never_extracted) {
    return (
      <td>
        <span className="kn-badge kn-badge-danger" title={t("documents.neverExtractedHint")}>
          {t("documents.neverExtracted")}
        </span>
      </td>
    );
  }
  return (
    <td style={{ fontSize: "0.8125rem" }}>
      <div>{t("documents.controlCount", { count: row.controls })}</div>
      {row.uncovered_normative > 0 && (
        <div style={{ color: "var(--accent-amber)" }}
             title={t("documents.uncoveredHint")}>
          {t("documents.uncovered", { count: row.uncovered_normative })}
        </div>
      )}
    </td>
  );
}

function isoSoonUntil(today: string): string {
  return new Date(
    Date.UTC(Number(today.slice(0, 4)), Number(today.slice(5, 7)) - 1, Number(today.slice(8, 10)) + 30),
  ).toISOString().slice(0, 10);
}

export function Documents() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [pasting, setPasting] = useState<number | null>(null);
  const [pasted, setPasted] = useState("");
  const reviewFilter = params.get("review") ?? "";

  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => request<Doc[]>("/api/documents"),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((document) => IN_FLIGHT.has(document.status))
        ? 3000
        : false,
  });
  // 语料盲区：文档传了没抽取、规范条款没产出控制点。两者都是静默的——
  // 不显示出来，界面上没有任何地方会提示。
  const coverage = useQuery({
    queryKey: ["document-coverage"],
    queryFn: () => request<Coverage[]>("/api/documents/coverage"),
  });

  async function uploadOne(file: File): Promise<void> {
    const body = new FormData();
    body.append("file", file);
    body.append("title", file.name.replace(/\.(pdf|docx)$/i, ""));
    body.append("doc_type", /guideline/i.test(file.name) ? "guideline" : "procedure");

    const response = await fetch("/api/documents", {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(`${file.name}: ${detail.message ?? response.status}`);
    }
  }

  async function uploadAll(files: FileList): Promise<void> {
    setError("");
    const selected = Array.from(files);
    setBusy(selected.map((file) => file.name));
    const failures: string[] = [];
    for (const file of selected) {
      try {
        await uploadOne(file);
      } catch (caught) {
        failures.push((caught as Error).message);
      }
    }
    setBusy([]);
    if (failures.length) setError(failures.join("；"));
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  }

  const submitPlainText = useMutation({
    mutationFn: (id: number) =>
      request<Doc>(`/api/documents/${id}/plain-text`, {
        method: "POST",
        body: JSON.stringify({ text: pasted }),
      }),
    onSuccess: () => {
      setPasting(null);
      setPasted("");
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const reparse = useMutation({
    mutationFn: (id: number) =>
      request<Doc>(`/api/documents/${id}/reparse`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const today = new Date().toISOString().slice(0, 10);
  const soonUntil = isoSoonUntil(today);
  const allDocs = documents.data ?? [];
  const overdueCount = allDocs.filter((doc) => doc.review_due_date && doc.review_due_date < today).length;
  const soonCount = allDocs.filter(
    (doc) => doc.review_due_date && doc.review_due_date >= today && doc.review_due_date <= soonUntil,
  ).length;
  const visible = allDocs.filter((document) => {
    if (reviewFilter === "overdue") return Boolean(document.review_due_date && document.review_due_date < today);
    if (reviewFilter === "soon") {
      return Boolean(document.review_due_date && document.review_due_date >= today && document.review_due_date <= soonUntil);
    }
    return true;
  });

  return (
    <section>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 20 }}>
        <div>
          <h2>{t("documents.title")}</h2>
          <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Regulatory & Internal Policy Documents Repository
          </p>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.875rem" }}>
            {t("documents.review")}
            <select
              aria-label={t("documents.review")}
              value={reviewFilter === "overdue" || reviewFilter === "soon" ? reviewFilter : ""}
              onChange={(event) => {
                const next = new URLSearchParams(params);
                if (event.target.value) next.set("review", event.target.value);
                else next.delete("review");
                setParams(next, { replace: true });
              }}
            >
              <option value="">{t("documents.filterAll")}</option>
              <option value="overdue">{t("documents.reviewOverdue", { count: overdueCount })}</option>
              <option value="soon">{t("documents.reviewSoon", { count: soonCount })}</option>
            </select>
          </label>
          <span className="kn-badge kn-badge-blue">
            {documents.data?.length ?? 0} Total Documents
          </span>
        </div>
      </div>

      {/* Keynote Dropzone */}
      <div
        className="kn-dropzone"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (event.dataTransfer.files.length) void uploadAll(event.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
      >
        <svg className="kn-dropzone-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <div className="kn-dropzone-title">{t("documents.dropHint")}</div>
        <div className="kn-dropzone-subtitle">PDF, DOCX · Automatic Clause Extraction & OCR Processing</div>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".pdf,.docx"
          aria-label={t("documents.upload")}
          style={{ display: "none" }}
          onClick={(event) => event.stopPropagation()}
          onChange={(event) => event.target.files && void uploadAll(event.target.files)}
        />
      </div>

      {busy.length > 0 && (
        <p role="status">
          <span className="kn-dot kn-dot-blue kn-pulse" /> ⏳ {busy.join(", ")}
        </p>
      )}
      {error && (
        <p role="alert">
          <span>⚠️</span> {error}
        </p>
      )}

      {/* Documents Data Table */}
      <div className="kn-table-container">
        <table>
          <thead>
            <tr>
              <th>{t("documents.title")}</th>
              <th>{t("documents.docType")}</th>
              <th>{t("documents.status")}</th>
              <th>{t("documents.version")}</th>
              <th>{t("documents.owner")}</th>
              <th>{t("documents.effective")}</th>
              <th>{t("documents.review")}</th>
              <th title={t("documents.blindSpotHint")}>{t("documents.extraction")}</th>
              <th style={{ textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((document) => {
              const isFailed = document.status === "parse_failed";
              const isInFlight = IN_FLIGHT.has(document.status);
              const isActive = document.status === "active";
              const isOverdue = Boolean(document.review_due_date && document.review_due_date < today);

              return (
                <tr key={document.id}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Link
                        to={`/documents/${document.id}`}
                        style={{ fontWeight: 600, color: "var(--text-primary)" }}
                      >
                        {document.title}
                      </Link>
                      {document.parse_warnings && (
                        <span
                          title={document.parse_warnings}
                          className="kn-badge kn-badge-amber"
                          style={{ padding: "1px 6px", fontSize: "0.6875rem" }}
                        >
                          ⚠️
                        </span>
                      )}
                      {document.ocr_quality_flag && (
                        <span
                          title="OCR 质量存疑"
                          className="kn-badge kn-badge-purple"
                          style={{ padding: "1px 6px", fontSize: "0.6875rem" }}
                        >
                          🔍 OCR
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className="kn-badge" style={{ textTransform: "capitalize" }}>
                      {document.doc_type}
                    </span>
                  </td>
                  <td>
                    {isInFlight ? (
                      <span className="kn-badge kn-badge-blue kn-pulse">
                        <span className="kn-dot kn-dot-blue" />
                        ⏳ {document.status}
                      </span>
                    ) : isActive ? (
                      <span className="kn-badge kn-badge-emerald">
                        <span className="kn-dot kn-dot-emerald" />
                        {document.status}
                      </span>
                    ) : isFailed ? (
                      <div>
                        <span className="kn-badge kn-badge-ruby">
                          <span className="kn-dot kn-dot-ruby" />
                          {document.status}
                        </span>
                        {document.parse_error && (
                          <div style={{ color: "var(--accent-ruby)", fontSize: "0.75rem", marginTop: 4 }}>
                            {document.parse_error}
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="kn-badge">{document.status}</span>
                    )}
                  </td>
                  <td>{document.version ? <code>{document.version}</code> : "—"}</td>
                  <td>{document.owner ?? "—"}</td>
                  <td>{document.effective_date ?? "—"}</td>
                  <td style={{ color: isOverdue ? "var(--accent-ruby)" : undefined, fontWeight: isOverdue ? 600 : undefined }}>
                    {document.review_due_date ?? "—"}
                  </td>
                  <ExtractionCell row={(coverage.data ?? []).find((c) => c.document_id === document.id)} />
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <button
                        className="kn-btn-sm kn-btn-secondary"
                        onClick={() => reparse.mutate(document.id)}
                      >
                        {t("documents.reparse")}
                      </button>
                      {document.status === "parse_failed" && (
                        <button
                          className="kn-btn-sm kn-btn-primary"
                          onClick={() => setPasting(document.id)}
                        >
                          {t("documents.pasteText")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Plain Text Fallback Drawer Card */}
      {pasting !== null && (
        <div className="kn-card" style={{ marginTop: 24, border: "1px solid var(--accent-blue)" }}>
          <h4 style={{ margin: "0 0 8px 0" }}>{t("documents.pasteText")}</h4>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginBottom: 12 }}>
            {t("documents.pasteHint")}
          </p>
          <textarea
            aria-label={t("documents.pasteText")}
            rows={10}
            style={{ width: "100%", maxWidth: 840, marginBottom: 16 }}
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
          />
          <div style={{ display: "flex", gap: 10 }}>
            <button className="kn-btn-primary" onClick={() => submitPlainText.mutate(pasting)}>
              {t("common.save")}
            </button>
            <button className="kn-btn-secondary" onClick={() => setPasting(null)}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
