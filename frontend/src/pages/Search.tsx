import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { request } from "../api";

interface Hit {
  chunk_id: number;
  clause_id: number;
  document_id: number;
  document_title: string;
  citation_label: string;
  heading_path: string;
  text: string;
  score: number;
  rank_fulltext: number | null;
  rank_vector: number | null;
}

interface SearchResponse {
  query: string;
  expanded_terms: string[];
  hits: Hit[];
  vector_used: boolean;
}

interface IndexStatus {
  model: string;
  total: number;
  embedded: number;
  pending: number;
}

export function Search() {
  const { t } = useTranslation();
  const [draft, setDraft] = useState("");
  const [submitted, setSubmitted] = useState("");

  const status = useQuery({
    queryKey: ["index-status"],
    queryFn: () => request<IndexStatus>("/api/index/status"),
  });

  const results = useQuery({
    queryKey: ["search", submitted],
    queryFn: () =>
      request<SearchResponse>(`/api/search?q=${encodeURIComponent(submitted)}&limit=20`),
    enabled: submitted.trim().length > 0,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitted(draft);
  }

  return (
    <section>
      <h2>{t("search.title")}</h2>

      {status.data && status.data.total > 0 && (
        <p style={{ color: "#666", fontSize: 13 }}>
          {t("search.indexing")}: {status.data.embedded} / {status.data.total}
          {status.data.model ? ` · ${status.data.model}` : ""}
          {status.data.pending > 0 ? ` · ${t("search.indexIncomplete")}` : ""}
        </p>
      )}

      <form onSubmit={submit} style={{ display: "flex", gap: 8, maxWidth: 640 }}>
        <input
          aria-label={t("search.title")}
          placeholder={t("search.placeholder")}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          style={{ flex: 1 }}
        />
        <button type="submit">{t("search.run")}</button>
      </form>

      {results.data && !results.data.vector_used && (
        <p role="status" style={{ background: "#fff8e1", padding: 8, fontSize: 13 }}>
          ⚠️ {t("search.keywordOnly")}
        </p>
      )}

      {results.data && results.data.expanded_terms.length > 1 && (
        <p style={{ color: "#666", fontSize: 13 }}>
          {t("search.expanded")}: {results.data.expanded_terms.slice(1).join(" · ")}
        </p>
      )}

      {results.data && results.data.hits.length === 0 && submitted.trim() && (
        <p style={{ color: "#888" }}>{t("search.noResults")}</p>
      )}

      <ol style={{ paddingLeft: 18 }}>
        {results.data?.hits.map((hit) => (
          <li key={hit.chunk_id} style={{ marginBottom: 16 }}>
            <Link to={`/documents/${hit.document_id}#clause-${hit.clause_id}`}>
              <strong>{hit.document_title}</strong>
            </Link>{" "}
            <Link to={`/documents/${hit.document_id}#clause-${hit.clause_id}`}>
              <code>{hit.citation_label}</code>
            </Link>
            <div style={{ color: "#666", fontSize: 12 }}>{hit.heading_path}</div>
            <p style={{ margin: "4px 0", whiteSpace: "pre-wrap" }}>{hit.text}</p>
            <div style={{ color: "#999", fontSize: 11 }}>
              {t("search.matchedBy")}: {[ 
                hit.rank_fulltext !== null
                  ? `${t("search.byKeyword")} #${hit.rank_fulltext}`
                  : null,
                hit.rank_vector !== null ? `${t("search.bySemantic")} #${hit.rank_vector}` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
