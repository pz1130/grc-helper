import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";

type Ruleset = "generation" | "embedding";

interface Rule {
  id: number;
  ruleset: Ruleset;
  pattern_type: "regex" | "dictionary";
  pattern: string;
  replacement_prefix: string;
  enabled: boolean;
  order_index: number;
  note: string | null;
}

export function Redaction() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [ruleset, setRuleset] = useState<Ruleset>("generation");
  const [sample, setSample] = useState("");
  const [preview, setPreview] = useState<{ redacted: string; hits: Record<string, number> }>();
  const [form, setForm] = useState({
    pattern_type: "regex" as "regex" | "dictionary",
    pattern: "",
    replacement_prefix: "",
    note: "",
  });

  const rules = useQuery({
    queryKey: ["redaction"],
    queryFn: () => request<Rule[]>("/api/settings/redaction"),
  });

  const create = useMutation({
    mutationFn: () =>
      request<Rule>("/api/settings/redaction", {
        method: "POST",
        body: JSON.stringify({ ...form, ruleset, enabled: true, order_index: 100 }),
      }),
    onSuccess: () => {
      setForm({ ...form, pattern: "", replacement_prefix: "", note: "" });
      void queryClient.invalidateQueries({ queryKey: ["redaction"] });
    },
  });

  async function runPreview() {
    setPreview(
      await request("/api/settings/redaction/preview", {
        method: "POST",
        body: JSON.stringify({ ruleset, text: sample }),
      }),
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <div>
      <h3>{t("settings.redaction")}</h3>
      <p style={{ color: "#666", fontSize: 13 }}>
        generation：完整脱敏，用于所有生成任务。
        <br />
        embedding：宽松脱敏，只脱人名/账号/IP，保留业务术语——脱掉术语会伤检索精度。
      </p>
      <label>
        规则集
        <select
          value={ruleset}
          onChange={(e) => setRuleset(e.target.value as Ruleset)}
          style={{ marginLeft: 8 }}
        >
          <option value="generation">generation</option>
          <option value="embedding">embedding</option>
        </select>
      </label>

      <table style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>type</th>
            <th>pattern</th>
            <th>prefix</th>
            <th>enabled</th>
          </tr>
        </thead>
        <tbody>
          {rules.data
            ?.filter((r) => r.ruleset === ruleset)
            .map((r) => (
              <tr key={r.id}>
                <td>{r.pattern_type}</td>
                <td>
                  <code>{r.pattern}</code>
                </td>
                <td>{r.replacement_prefix}</td>
                <td>{r.enabled ? "✅" : "—"}</td>
              </tr>
            ))}
        </tbody>
      </table>

      <h4>{t("common.add")}</h4>
      <form onSubmit={submit} style={{ display: "grid", gap: 8, maxWidth: 480 }}>
        <select
          aria-label="pattern type"
          value={form.pattern_type}
          onChange={(e) =>
            setForm({ ...form, pattern_type: e.target.value as "regex" | "dictionary" })
          }
        >
          <option value="regex">regex</option>
          <option value="dictionary">dictionary（每行一个词）</option>
        </select>
        <textarea
          placeholder="pattern"
          value={form.pattern}
          required
          rows={3}
          onChange={(e) => setForm({ ...form, pattern: e.target.value })}
        />
        <input
          placeholder="replacement prefix，如 ORG"
          value={form.replacement_prefix}
          required
          onChange={(e) => setForm({ ...form, replacement_prefix: e.target.value })}
        />
        <input
          placeholder="备注"
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
        <button type="submit">{t("common.save")}</button>
      </form>

      <h4 style={{ marginTop: 32 }}>发送预览 / Send preview</h4>
      <p style={{ color: "#666", fontSize: 13 }}>粘一段真实文字，看看实际会发出去什么。</p>
      <textarea
        aria-label="发送预览输入"
        rows={4}
        style={{ width: "100%", maxWidth: 640 }}
        value={sample}
        onChange={(e) => setSample(e.target.value)}
      />
      <button onClick={() => void runPreview()}>预览</button>
      {preview && (
        <pre style={{ background: "#f5f5f5", padding: 12, whiteSpace: "pre-wrap" }}>
          {preview.redacted}
          {"\n\n命中: " + JSON.stringify(preview.hits)}
        </pre>
      )}
    </div>
  );
}
