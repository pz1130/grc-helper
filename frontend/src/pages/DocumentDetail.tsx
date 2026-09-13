import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { getToken, request } from "../api";
import { useAuth } from "../auth";

interface ClauseNode {
  id: number;
  number: string | null;
  heading: string;
  heading_path: string;
  citation_label: string;
  text: string;
  level: number;
  page_ref: number | null;
  kind: string;
  children: ClauseNode[];
}

interface Doc {
  id: number;
  title: string;
  doc_type: string;
  status: string;
  version: string | null;
  owner: string | null;
  parse_warnings: string | null;
  supersedes_id: number | null;
}

function flatten(nodes: ClauseNode[]): ClauseNode[] {
  return nodes.flatMap((node) => [node, ...flatten(node.children)]);
}

function Tree({
  nodes,
  onSelect,
  selected,
}: {
  nodes: ClauseNode[];
  onSelect: (node: ClauseNode) => void;
  selected: number | null;
}) {
  return (
    <ul style={{ listStyle: "none", paddingLeft: 12, margin: 0 }}>
      {nodes.map((node) => {
        const isSelected = selected === node.id;
        return (
          <li key={node.id} style={{ margin: "2px 0" }}>
            <button
              onClick={() => onSelect(node)}
              title={node.heading_path}
              style={{
                width: "100%",
                background: isSelected ? "rgba(41, 151, 255, 0.16)" : "transparent",
                color: isSelected ? "#ffffff" : "var(--text-secondary)",
                border: isSelected ? "1px solid rgba(41, 151, 255, 0.35)" : "1px solid transparent",
                borderRadius: "var(--radius-sm)",
                padding: "6px 10px",
                cursor: "pointer",
                textAlign: "left",
                font: "inherit",
                fontSize: "0.8125rem",
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontWeight: isSelected ? 600 : 400,
                boxShadow: isSelected ? "0 2px 8px rgba(41, 151, 255, 0.2)" : "none",
              }}
            >
              {node.kind === "table" ? <span style={{ opacity: 0.7 }}>▦</span> : null}
              {node.number ? (
                <code style={{ fontSize: "0.75rem", padding: "1px 5px", background: "var(--code-bg)" }}>
                  {node.number}
                </code>
              ) : null}
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {node.heading}
              </span>
            </button>
            {node.children.length > 0 && (
              <Tree nodes={node.children} onSelect={onSelect} selected={selected} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function DocumentDetail() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const [selected, setSelected] = useState<ClauseNode | null>(null);
  const [importing, setImporting] = useState(false);
  const [mergeInto, setMergeInto] = useState("");
  const canEdit = user?.role !== "viewer";

  const doc = useQuery({
    queryKey: ["document", id],
    queryFn: () => request<Doc>(`/api/documents/${id}`),
  });
  const clauses = useQuery({
    queryKey: ["clauses", id],
    queryFn: () => request<ClauseNode[]>(`/api/documents/${id}/clauses`),
  });
  const flat = clauses.data ? flatten(clauses.data) : [];

  const uploadVersion = useMutation({
    mutationFn: async (file: File) => {
      const current = doc.data;
      if (!current) throw new Error("document not loaded");
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name.replace(/\.(pdf|docx)$/i, ""));
      body.append("doc_type", current.doc_type);
      body.append("supersedes_id", String(id));
      const response = await fetch("/api/documents", {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body,
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.message ?? String(response.status));
      }
      return (await response.json()) as Doc;
    },
    onSuccess: (created) => {
      setImporting(false);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      navigate(`/documents/${created.id}`);
    },
  });

  const split = useMutation({
    mutationFn: (at: number) =>
      request<ClauseNode>(`/api/clauses/${selected?.id}/split`, {
        method: "POST",
        body: JSON.stringify({ at }),
      }),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ["clauses", id] });
      setSelected(created);
    },
  });
  const merge = useMutation({
    mutationFn: (intoId: number) =>
      request<ClauseNode>(`/api/clauses/${selected?.id}/merge`, {
        method: "POST",
        body: JSON.stringify({ into_id: intoId }),
      }),
    onSuccess: async (winner) => {
      await queryClient.invalidateQueries({ queryKey: ["clauses", id] });
      setMergeInto("");
      setSelected(winner);
    },
  });

  const total = flat.length;

  useEffect(() => {
    if (!clauses.data) return;
    const hashClauseId = location.hash.match(/^#clause-(\d+)$/)?.[1];
    if (!hashClauseId) return;
    const hashClause = flatten(clauses.data).find((node) => node.id === Number(hashClauseId));
    if (hashClause) {
      setSelected((current) => (current?.id === hashClause.id ? current : hashClause));
    }
  }, [clauses.data, location.hash]);

  useEffect(() => {
    if (selected) {
      requestAnimationFrame(() =>
        document.getElementById(`clause-${selected.id}`)?.scrollIntoView({ block: "start" }),
      );
    }
  }, [selected]);

  return (
    <section>
      <p style={{ marginBottom: 16 }}>
        <Link to="/documents" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: "0.875rem" }}>
          ← {t("documents.title")}
        </Link>
      </p>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h2>{doc.data?.title}</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginTop: 4 }}>
            <span className="kn-badge kn-badge-emerald">{doc.data?.status}</span>
            <span className="kn-badge">
              {t("documents.version")}: {doc.data?.version ?? "—"}
            </span>
            <span className="kn-badge kn-badge-blue">
              {t("documents.clauses")}: {total}
            </span>
            {doc.data?.owner && <span className="kn-badge">Owner: {doc.data.owner}</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {doc.data?.supersedes_id != null && (
            <Link
              to={`/documents/${id}/change-impact`}
              className="kn-btn-secondary kn-btn-sm"
              style={{ display: "inline-flex", alignItems: "center", textDecoration: "none" }}
            >
              {t("impact.viewImpact")}
            </Link>
          )}
          <button
            type="button"
            className="kn-btn-primary kn-btn-sm"
            onClick={() => setImporting(true)}
          >
            {t("impact.importNewVersion")}
          </button>
        </div>
      </div>

      {importing && (
        <div className="kn-card" style={{ marginBottom: 20, border: "1px solid var(--accent-blue)" }}>
          <h4 style={{ margin: "0 0 8px 0" }}>{t("impact.importNewVersion")}</h4>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginBottom: 12 }}>
            {t("documents.dropHint")}
          </p>
          <input type="hidden" name="supersedes_id" value={id ?? ""} />
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx"
            aria-label={t("documents.upload")}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadVersion.mutate(file);
              event.target.value = "";
            }}
          />
          {uploadVersion.isPending && <p role="status">{t("common.loading")}</p>}
          {uploadVersion.error && (
            <p role="alert">
              <span>⚠️</span> {uploadVersion.error.message}
            </p>
          )}
          <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
            <button type="button" className="kn-btn-secondary" onClick={() => setImporting(false)}>
              {t("common.cancel")}
            </button>
          </div>
        </div>
      )}

      {doc.data?.parse_warnings && (
        <pre
          style={{
            background: "var(--accent-amber-bg)",
            border: "1px solid var(--accent-amber-border)",
            color: "var(--accent-amber)",
            padding: 12,
            whiteSpace: "pre-wrap",
            fontSize: "0.8125rem",
            marginBottom: 20,
          }}
        >
          ⚠️ {doc.data.parse_warnings}
        </pre>
      )}

      {/* Split Inspector Workspace */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* Navigation Tree Pane */}
        <nav
          className="kn-card"
          style={{
            flex: "0 0 320px",
            maxHeight: "75vh",
            overflow: "auto",
            padding: "16px 12px",
          }}
        >
          <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-tertiary)", textTransform: "uppercase", padding: "0 8px 10px 8px", letterSpacing: "0.06em" }}>
            Document Outline
          </div>
          {clauses.data && (
            <Tree nodes={clauses.data} onSelect={setSelected} selected={selected?.id ?? null} />
          )}
        </nav>

        {/* Clause Reader Pane */}
        <article
          id={selected ? `clause-${selected.id}` : undefined}
          className="kn-card"
          style={{
            flex: 1,
            minHeight: 280,
            background: selected ? "var(--stage-card-hover)" : "var(--stage-card)",
            border: selected ? "1px solid var(--accent-blue)" : "1px solid var(--stage-border)",
            boxShadow: selected ? "var(--shadow-md)" : undefined,
          }}
        >
          {selected ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <h3 style={{ margin: 0, fontSize: "1.2rem" }}>{selected.heading}</h3>
                <div style={{ display: "flex", gap: 8 }}>
                  <code style={{ fontSize: "0.8125rem" }}>{selected.citation_label}</code>
                  {selected.page_ref && <span className="kn-badge">p.{selected.page_ref}</span>}
                </div>
              </div>
              <p style={{ color: "var(--text-tertiary)", fontSize: "0.8125rem", marginBottom: 16 }}>
                {selected.heading_path}
              </p>
              {canEdit ? (
                <>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: 8 }}>
                    {t("documents.splitHint")}
                  </p>
                  <textarea
                    ref={bodyRef}
                    readOnly
                    defaultValue={selected.text}
                    key={selected.id + selected.text}
                    aria-label={selected.heading}
                    style={{
                      width: "100%",
                      minHeight: 200,
                      whiteSpace: "pre-wrap",
                      font: "inherit",
                      fontSize: "0.9375rem",
                      lineHeight: 1.6,
                      background: "var(--stage-card-subtle)",
                      border: "1px solid var(--stage-border)",
                      padding: 16,
                      borderRadius: "var(--radius-sm)",
                      color: "var(--text-primary)",
                      resize: "vertical",
                    }}
                  />
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 12, alignItems: "center" }}>
                    <button
                      type="button"
                      className="kn-btn-secondary kn-btn-sm"
                      onClick={() => {
                        const at = bodyRef.current?.selectionStart ?? 0;
                        split.mutate(at);
                      }}
                    >
                      {t("documents.split")}
                    </button>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: "0.8125rem" }}>
                      {t("documents.merge")}
                      <select
                        value={mergeInto}
                        onChange={(event) => setMergeInto(event.target.value)}
                        aria-label={t("documents.mergePick")}
                      >
                        <option value="">{t("documents.mergePick")}</option>
                        {flat
                          .filter((node) => node.id !== selected.id)
                          .map((node) => (
                            <option key={node.id} value={node.id}>
                              {node.citation_label} {node.heading}
                            </option>
                          ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      className="kn-btn-secondary kn-btn-sm"
                      disabled={!mergeInto}
                      onClick={() => merge.mutate(Number(mergeInto))}
                    >
                      {t("documents.merge")}
                    </button>
                  </div>
                  {(split.error || merge.error) && (
                    <p role="alert" style={{ marginTop: 8 }}>
                      {(split.error ?? merge.error)?.message}
                    </p>
                  )}
                </>
              ) : (
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    font: "inherit",
                    fontSize: "0.9375rem",
                    lineHeight: 1.6,
                    background: "var(--stage-card-subtle)",
                    border: "1px solid var(--stage-border)",
                    padding: 16,
                    borderRadius: "var(--radius-sm)",
                    color: "var(--text-primary)",
                  }}
                >
                  {selected.text}
                </pre>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text-tertiary)" }}>
              <div style={{ fontSize: "2rem", marginBottom: 8, opacity: 0.5 }}>📖</div>
              <p style={{ color: "var(--text-secondary)" }}>{t("common.empty")}</p>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
