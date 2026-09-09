import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { ApiError, getToken, request, setToken } from "../api";
import { useAuth } from "../auth";

interface Framework {
  id: number;
  key: string;
  name_zh: string;
  name_en: string;
  version: string;
  source: string;
  item_count: number;
  imported_at: string;
}

interface ValidationResult {
  ok: boolean;
  report: string[];
  items: number;
}

async function upload<T>(path: string, body: FormData): Promise<T> {
  const token = getToken();
  const response = await fetch(path, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body,
  });
  if (response.status === 401) setToken(null);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, data.code ?? "error", data.message ?? "请求失败");
  }
  return data as T;
}

export function Frameworks() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const client = useQueryClient();
  const canWrite = user?.role === "admin" || user?.role === "grc_lead";
  const [file, setFile] = useState<File | null>(null);
  const [key, setKey] = useState("");
  const [nameZh, setNameZh] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [version, setVersion] = useState("");
  const [source, setSource] = useState("");
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const frameworks = useQuery({
    queryKey: ["frameworks"],
    queryFn: () => request<Framework[]>("/api/frameworks"),
  });

  function formData(): FormData {
    if (!file) throw new Error(t("frameworks.chooseFile"));
    const form = new FormData();
    form.append("file", file);
    return form;
  }

  const validate = useMutation({
    mutationFn: () => upload<ValidationResult>("/api/frameworks/validate", formData()),
    onMutate: () => { setError(""); setNotice(""); setValidation(null); },
    onError: (caught: Error) => setError(caught.message),
    onSuccess: setValidation,
  });

  const importFramework = useMutation({
    mutationFn: () => {
      const form = formData();
      form.append("key", key.trim());
      form.append("name_zh", nameZh.trim());
      form.append("name_en", nameEn.trim());
      form.append("version", version.trim());
      form.append("source", source.trim());
      return upload<Framework>("/api/frameworks/import", form);
    },
    onMutate: () => { setError(""); setNotice(""); },
    onError: (caught: Error) => setError(caught.message),
    onSuccess: async (framework) => {
      setNotice(t("frameworks.imported", { key: framework.key }));
      setValidation(null);
      setFile(null);
      await client.invalidateQueries({ queryKey: ["frameworks"] });
    },
  });

  const busy = validate.isPending || importFramework.isPending;
  const metadataReady = Boolean(file && key.trim() && nameZh.trim() && nameEn.trim() && version.trim());

  return <section>
    <h2>{t("frameworks.title")}</h2>
    {frameworks.isPending && <p role="status">{t("common.loading")}</p>}
    {frameworks.error && <p role="alert">{frameworks.error.message}</p>}
    {frameworks.data && frameworks.data.length === 0 && <p>{t("common.empty")}</p>}
    {!!frameworks.data?.length && <table>
      <thead><tr><th>{t("frameworks.name")}</th><th>{t("frameworks.key")}</th><th>{t("frameworks.version")}</th><th>{t("frameworks.items")}</th></tr></thead>
      <tbody>{frameworks.data.map((framework) => <tr key={framework.id}>
        <td><Link to={`/frameworks/${framework.id}`}>{framework.name_zh}</Link></td>
        <td><code>{framework.key}</code></td>
        <td>{framework.version}</td>
        <td>{framework.item_count}</td>
      </tr>)}</tbody>
    </table>}

    {canWrite && <details open style={{ border: "1px solid #e5e5e5", borderRadius: 6, padding: 12, marginTop: 20 }}>
      <summary>{t("frameworks.import")}</summary>
      <p style={{ color: "#666" }}>{t("frameworks.importHint")}</p>
      <label>{t("frameworks.file")} <input type="file" accept=".xlsx" disabled={busy} onChange={(event) => {
        setFile(event.target.files?.[0] ?? null); setValidation(null); setError(""); setNotice("");
      }} /></label>
      <div style={{ display: "grid", gap: 8, maxWidth: 520, marginTop: 12 }}>
        <label>{t("frameworks.key")} <input value={key} disabled={busy} onChange={(event) => setKey(event.target.value)} /></label>
        <label>{t("frameworks.nameZh")} <input value={nameZh} disabled={busy} onChange={(event) => setNameZh(event.target.value)} /></label>
        <label>{t("frameworks.nameEn")} <input value={nameEn} disabled={busy} onChange={(event) => setNameEn(event.target.value)} /></label>
        <label>{t("frameworks.version")} <input value={version} disabled={busy} onChange={(event) => setVersion(event.target.value)} /></label>
        <label>{t("frameworks.source")} <input value={source} disabled={busy} onChange={(event) => setSource(event.target.value)} /></label>
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button disabled={!file || busy} onClick={() => validate.mutate()}>{t("frameworks.validate")}</button>
        <button disabled={!validation?.ok || !metadataReady || busy} onClick={() => importFramework.mutate()}>{t("frameworks.confirmImport")}</button>
      </div>
      {busy && <p role="status">{t("common.loading")}</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {validation && <div role={validation.ok ? "status" : "alert"}>
        <p>{t("frameworks.report")} · {validation.items} {t("frameworks.items")}</p>
        {validation.report.length > 0 && <ul>{validation.report.map((line, index) => <li key={index}>{line}</li>)}</ul>}
      </div>}
    </details>}
  </section>;
}
