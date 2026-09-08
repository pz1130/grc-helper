import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { getToken, request } from "../api";

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

export function Documents() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [pasting, setPasting] = useState<number | null>(null);
  const [pasted, setPasted] = useState("");

  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => request<Doc[]>("/api/documents"),
    refetchInterval: (query) =>
      (query.state.data ?? []).some((document) => IN_FLIGHT.has(document.status))
        ? 3000
        : false,
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

  return (
    <section>
      <h2>{t("documents.title")}</h2>

      <div
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (event.dataTransfer.files.length) void uploadAll(event.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        style={{
          border: "2px dashed #bbb",
          borderRadius: 6,
          padding: 24,
          textAlign: "center",
          cursor: "pointer",
          color: "#666",
          marginBottom: 16,
        }}
      >
        {t("documents.dropHint")}
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

      {busy.length > 0 && <p>⏳ {busy.join(", ")}</p>}
      {error && (
        <p role="alert" style={{ color: "#c00" }}>
          {error}
        </p>
      )}

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
            <th />
          </tr>
        </thead>
        <tbody>
          {documents.data?.map((document) => (
            <tr key={document.id}>
              <td>
                <Link to={`/documents/${document.id}`}>{document.title}</Link>
                {document.parse_warnings && (
                  <span title={document.parse_warnings} style={{ marginLeft: 6 }}>
                    ⚠️
                  </span>
                )}
                {document.ocr_quality_flag && <span title="OCR 质量存疑"> 🔍</span>}
              </td>
              <td>{document.doc_type}</td>
              <td>
                {IN_FLIGHT.has(document.status) ? "⏳ " : ""}
                {document.status}
                {document.status === "parse_failed" && (
                  <div style={{ color: "#c00", fontSize: 12 }}>{document.parse_error}</div>
                )}
              </td>
              <td>{document.version ?? "—"}</td>
              <td>{document.owner ?? "—"}</td>
              <td>{document.effective_date ?? "—"}</td>
              <td
                style={{
                  color:
                    document.review_due_date && document.review_due_date < today
                      ? "#c00"
                      : undefined,
                }}
              >
                {document.review_due_date ?? "—"}
              </td>
              <td>
                <button onClick={() => reparse.mutate(document.id)}>
                  {t("documents.reparse")}
                </button>
                {document.status === "parse_failed" && (
                  <button onClick={() => setPasting(document.id)}>
                    {t("documents.pasteText")}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {pasting !== null && (
        <div style={{ marginTop: 16 }}>
          <h4>{t("documents.pasteText")}</h4>
          <p style={{ color: "#666", fontSize: 13 }}>{t("documents.pasteHint")}</p>
          <textarea
            aria-label={t("documents.pasteText")}
            rows={10}
            style={{ width: "100%", maxWidth: 720 }}
            value={pasted}
            onChange={(event) => setPasted(event.target.value)}
          />
          <div>
            <button onClick={() => submitPlainText.mutate(pasting)}>{t("common.save")}</button>
            <button onClick={() => setPasting(null)}>{t("common.cancel")}</button>
          </div>
        </div>
      )}
    </section>
  );
}
