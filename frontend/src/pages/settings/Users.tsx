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
      {/* Users Table Card */}
      <div className="kn-card" style={{ marginBottom: 24 }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "1.125rem" }}>{t("settings.users")}</h3>
        {error && (
          <p role="alert">
            <span>⚠️</span> {error}
          </p>
        )}
        {users.error && (
          <p role="alert">
            <span>⚠️</span> {users.error.message}{" "}
            <button className="kn-btn-secondary kn-btn-sm" onClick={() => void users.refetch()}>
              {t("common.retry")}
            </button>
          </p>
        )}
        <div className="kn-table-container" style={{ margin: 0 }}>
          <table>
            <thead>
              <tr>
                <th>{t("settings.usersConfig.email")}</th>
                <th>{t("settings.usersConfig.name")}</th>
                <th>{t("settings.usersConfig.role")}</th>
                <th>{t("settings.usersConfig.active")}</th>
                <th>{t("settings.usersConfig.expiresAt")}</th>
              </tr>
            </thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>{u.email}</td>
                  <td>{u.name}</td>
                  <td>
                    <select
                      aria-label={t("settings.usersConfig.roleOf", { email: u.email })}
                      value={u.role}
                      onChange={(e) =>
                        update.mutate({ id: u.id, patch: { role: e.target.value as Role } })
                      }
                      style={{ padding: "4px 28px 4px 10px", fontSize: "0.8125rem" }}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {t(`settings.usersConfig.roles.${r}`)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={t("settings.usersConfig.activeOf", { email: u.email })}
                      checked={u.is_active}
                      onChange={(e) => update.mutate({ id: u.id, patch: { is_active: e.target.checked } })}
                    />
                  </td>
                  <td>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      {u.expires_at?.slice(0, 10) ?? "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add User Card */}
      <div className="kn-card" style={{ maxWidth: 520 }}>
        <h4 style={{ margin: "0 0 4px 0", fontSize: "1rem" }}>{t("common.add")}</h4>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", marginBottom: 16 }}>
          {t("settings.usersConfig.auditorHint")}
        </p>
        <form onSubmit={submit} style={{ display: "grid", gap: 12 }}>
          <input
            type="email"
            placeholder={t("settings.usersConfig.email")}
            value={form.email}
            required
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
          <input
            placeholder={t("settings.usersConfig.name")}
            value={form.name}
            required
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <select
            aria-label={t("settings.usersConfig.newUserRole")}
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`settings.usersConfig.roles.${r}`)}
              </option>
            ))}
          </select>
          <input
            type="password"
            placeholder={t("settings.usersConfig.passwordPlaceholder")}
            value={form.password}
            required
            minLength={8}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <input
            type="date"
            aria-label={t("settings.usersConfig.expiresAt")}
            value={form.expires_at}
            onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
          />
          <div>
            <button type="submit" className="kn-btn-primary" style={{ padding: "8px 24px" }}>
              {t("common.save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
