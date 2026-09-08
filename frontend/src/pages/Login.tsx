import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth";

export function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      await login(email, password);
    } catch {
      setError(t("login.failed"));
    }
  }

  return (
    <form
      onSubmit={submit}
      style={{ maxWidth: 320, margin: "120px auto", fontFamily: "system-ui, sans-serif" }}
    >
      <h1>{t("login.title")}</h1>
      <label style={{ display: "block", marginBottom: 8 }}>
        {t("login.email")}
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{ width: "100%" }}
        />
      </label>
      <label style={{ display: "block", marginBottom: 8 }}>
        {t("login.password")}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={{ width: "100%" }}
        />
      </label>
      {error && (
        <p role="alert" style={{ color: "#c00" }}>
          {error}
        </p>
      )}
      <button type="submit">{t("login.submit")}</button>
    </form>
  );
}
