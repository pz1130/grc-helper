import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { request } from "../api";

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
  status: string;
  version: string | null;
  owner: string | null;
  parse_warnings: string | null;
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
      {nodes.map((node) => (
        <li key={node.id}>
          <button
            onClick={() => onSelect(node)}
            title={node.heading_path}
            style={{
              background: selected === node.id ? "#eef" : "transparent",
              border: "none",
              padding: "3px 4px",
              cursor: "pointer",
              textAlign: "left",
              font: "inherit",
            }}
          >
            {node.kind === "table" ? "▦ " : ""}
            {node.number ? <code>{node.number}</code> : null} {node.heading}
          </button>
          {node.children.length > 0 && (
            <Tree nodes={node.children} onSelect={onSelect} selected={selected} />
          )}
        </li>
      ))}
    </ul>
  );
}

export function DocumentDetail() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [selected, setSelected] = useState<ClauseNode | null>(null);

  const doc = useQuery({
    queryKey: ["document", id],
    queryFn: () => request<Doc>(`/api/documents/${id}`),
  });
  const clauses = useQuery({
    queryKey: ["clauses", id],
    queryFn: () => request<ClauseNode[]>(`/api/documents/${id}/clauses`),
  });

  const total = clauses.data ? flatten(clauses.data).length : 0;

  return (
    <section>
      <p>
        <Link to="/documents">← {t("documents.title")}</Link>
      </p>
      <h2>{doc.data?.title}</h2>
      <p style={{ color: "#666", fontSize: 13 }}>
        {doc.data?.status} · {t("documents.version")} {doc.data?.version ?? "—"} ·{" "}
        {t("documents.clauses")} {total}
      </p>
      {doc.data?.parse_warnings && (
        <pre
          style={{
            background: "#fff8e1",
            padding: 10,
            whiteSpace: "pre-wrap",
            fontSize: 13,
          }}
        >
          ⚠️ {doc.data.parse_warnings}
        </pre>
      )}

      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        <nav style={{ flex: "0 0 320px", maxHeight: "70vh", overflow: "auto" }}>
          {clauses.data && (
            <Tree nodes={clauses.data} onSelect={setSelected} selected={selected?.id ?? null} />
          )}
        </nav>
        <article style={{ flex: 1 }}>
          {selected ? (
            <>
              <h3>{selected.heading}</h3>
              <p style={{ color: "#666", fontSize: 12 }}>
                <code>{selected.citation_label}</code>
                {selected.page_ref ? ` · p.${selected.page_ref}` : ""}
              </p>
              <pre style={{ whiteSpace: "pre-wrap", font: "inherit" }}>{selected.text}</pre>
            </>
          ) : (
            <p style={{ color: "#888" }}>{t("common.empty")}</p>
          )}
        </article>
      </div>
    </section>
  );
}
