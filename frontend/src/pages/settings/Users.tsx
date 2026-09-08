import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { request } from "../../api";
import type { Role } from "../../auth";

interface UserRow {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  expires_at: string | null;
}

const ROLES: Role[] = ["admin", "grc_lead", "contributor", "viewer"];

export function Users() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    email: "",
    name: "",
    role: "viewer" as Role,
    password: "",
    expires_at: "",
  });

  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => request<UserRow[]>("/api/users"),
  });

  const create = useMutation({
    mutationFn: () =>
      request<UserRow>("/api/users", {
        method: "POST",
        body: JSON.stringify({ ...form, expires_at: form.expires_at || null }),
      }),
    onError: (e: Error) => setError(e.message),
    onSuccess: () => {
      setError("");
      setForm({ ...form, email: "", name: "", password: "", expires_at: "" });
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  const update = useMutation({
    mutationFn: (body: { id: number; patch: Partial<UserRow> }) =>
      request<UserRow>(`/api/users/${body.id}`, {
        method: "PATCH",
        body: JSON.stringify(body.patch),
      }),
    onError: (e: Error) => setError(e.message),
    onSuccess: () => {
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <div>
      <h3>{t("settings.users")}</h3>
      {error && (
        <p role="alert" style={{ color: "#c00" }}>
          {error}
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>email</th>
            <th>name</th>
            <th>role</th>
            <th>active</th>
            <th>expires</th>
          </tr>
        </thead>
        <tbody>
          {users.data?.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.name}</td>
              <td>
                <select
                  aria-label={`role of ${u.email}`}
                  value={u.role}
                  onChange={(e) =>
                    update.mutate({ id: u.id, patch: { role: e.target.value as Role } })
                  }
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`active of ${u.email}`}
                  checked={u.is_active}
                  onChange={(e) => update.mutate({ id: u.id, patch: { is_active: e.target.checked } })}
                />
              </td>
              <td>{u.expires_at?.slice(0, 10) ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4>{t("common.add")}</h4>
      <p style={{ color: "#666", fontSize: 13 }}>外部审计员：角色选 viewer，并填有效期。</p>
      <form onSubmit={submit} style={{ display: "grid", gap: 8, maxWidth: 420 }}>
        <input
          type="email"
          placeholder="email"
          value={form.email}
          required
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <input
          placeholder="name"
          value={form.name}
          required
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <select
          aria-label="new user role"
          value={form.role}
          onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <input
          type="password"
          placeholder="初始密码（至少 8 位）"
          value={form.password}
          required
          minLength={8}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <input
          type="date"
          aria-label="有效期"
          value={form.expires_at}
          onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
        />
        <button type="submit">{t("common.save")}</button>
      </form>
    </div>
  );
}
