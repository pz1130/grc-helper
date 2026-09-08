import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { canManageLlmConfig, canReadAuditLog, useAuth } from "../../auth";

export function SettingsLayout() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const isAdmin = canManageLlmConfig(user?.role);

  return (
    <section>
      <h2>{t("settings.title")}</h2>
      <nav style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        {isAdmin && <NavLink to="providers">{t("settings.providers")}</NavLink>}
        {isAdmin && <NavLink to="redaction">{t("settings.redaction")}</NavLink>}
        {isAdmin && <NavLink to="thresholds">{t("settings.thresholds")}</NavLink>}
        {isAdmin && <NavLink to="users">{t("settings.users")}</NavLink>}
        {canReadAuditLog(user?.role) && <NavLink to="audit-log">{t("settings.auditLog")}</NavLink>}
      </nav>
      <Outlet />
    </section>
  );
}
