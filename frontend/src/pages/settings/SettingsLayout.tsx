import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { canManageLlmConfig, canReadAuditLog, useAuth } from "../../auth";

export function SettingsLayout() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = canManageLlmConfig(user?.role);

  return (
    <section>
      <div style={{ marginBottom: 20 }}>
        <h2>{t("settings.title")}</h2>
        <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)" }}>
          {t("settings.subtitle")}
        </p>
      </div>

      <nav
        className="kn-segmented"
        style={{
          marginBottom: 24,
          flexWrap: "wrap",
          padding: 5,
        }}
      >
        {isAdmin && (
          <NavLink
            to="providers"
            className={({ isActive }) => `kn-segmented-item ${isActive ? "active" : ""}`}
          >
            {t("settings.providers")}
          </NavLink>
        )}
        {isAdmin && (
          <NavLink
            to="redaction"
            className={({ isActive }) => `kn-segmented-item ${isActive ? "active" : ""}`}
          >
            {t("settings.redaction")}
          </NavLink>
        )}
        {isAdmin && (
          <NavLink
            to="thresholds"
            className={({ isActive }) => `kn-segmented-item ${isActive ? "active" : ""}`}
          >
            {t("settings.thresholds")}
          </NavLink>
        )}
        {isAdmin && (
          <NavLink
            to="users"
            className={({ isActive }) => `kn-segmented-item ${isActive ? "active" : ""}`}
          >
            {t("settings.users")}
          </NavLink>
        )}
        {canReadAuditLog(user?.role) && (
          <NavLink
            to="audit-log"
            className={({ isActive }) => `kn-segmented-item ${isActive ? "active" : ""}`}
          >
            {t("settings.auditLog")}
          </NavLink>
        )}
      </nav>

      <Outlet />
    </section>
  );
}
