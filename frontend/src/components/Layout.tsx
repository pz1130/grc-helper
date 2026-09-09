import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth";
import { setLanguage } from "../i18n";

export function Layout() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();

  return (
    <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif" }}>
      <nav style={{ width: 200, padding: 16, borderRight: "1px solid #e5e5e5" }}>
        <h1 style={{ fontSize: 18, marginTop: 0 }}>{t("app.name")}</h1>
        <NavLink to="/" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.overview")}
        </NavLink>
        <NavLink to="/documents" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.documents")}
        </NavLink>
        <NavLink to="/search" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.search")}
        </NavLink>
        <NavLink to="/review" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.review")}
        </NavLink>
        <NavLink to="/controls" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.controls")}
        </NavLink>
        <NavLink to="/frameworks" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.frameworks")}
        </NavLink>
        <NavLink to="/settings" style={{ display: "block", padding: "6px 0" }}>
          {t("nav.settings")}
        </NavLink>
        <hr />
        <div style={{ fontSize: 12, color: "#666" }}>
          {user?.name} · {user?.role}
        </div>
        <button onClick={logout} style={{ marginTop: 8 }}>
          {t("app.logout")}
        </button>
        <div style={{ marginTop: 16 }}>
          <label style={{ fontSize: 12, color: "#666" }}>
            {t("app.language")}
            <select
              value={i18n.language}
              onChange={(e) => setLanguage(e.target.value as "zh" | "en")}
              style={{ display: "block", marginTop: 4 }}
            >
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24 }}>
        <Outlet />
      </main>
    </div>
  );
}
