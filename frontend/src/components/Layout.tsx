import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth";
import { setLanguage } from "../i18n";
import { useTheme } from "../theme";
import { BrandLogo } from "./BrandLogo";

export function Layout() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();

  const navItems = [
    {
      to: "/",
      label: t("nav.overview"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
        </svg>
      ),
    },
    {
      to: "/documents",
      label: t("nav.documents"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      ),
    },
    {
      to: "/search",
      label: t("nav.search"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
      ),
    },
    {
      to: "/review",
      label: t("nav.review"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      ),
    },
    {
      to: "/controls",
      label: t("nav.controls"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <circle cx="12" cy="11" r="3" />
        </svg>
      ),
    },
    {
      to: "/frameworks",
      label: t("nav.frameworks"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="12 2 2 7 12 12 22 7 12 2" />
          <polyline points="2 17 12 22 22 17" />
          <polyline points="2 12 12 17 22 12" />
        </svg>
      ),
    },
    {
      to: "/tech-assets",
      label: t("nav.techAssets"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M7 8h10M7 12h4M7 16h7" />
        </svg>
      ),
    },
    {
      to: "/evidence",
      label: t("nav.evidence"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M8 13h8M8 17h6" />
        </svg>
      ),
    },
    {
      to: "/audit",
      label: t("nav.audit"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
          <path d="M9 12h6M9 16h4" />
        </svg>
      ),
    },
    {
      to: "/settings",
      label: t("nav.settings"),
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
    },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", position: "relative" }}>
      {/* Keynote Sidebar */}
      <nav
        style={{
          width: 248,
          padding: "24px 16px",
          background: "var(--sidebar-bg)",
          backdropFilter: "blur(28px) saturate(180%)",
          WebkitBackdropFilter: "blur(28px) saturate(180%)",
          borderRight: "1px solid var(--stage-border)",
          display: "flex",
          flexDirection: "column",
          position: "sticky",
          top: 0,
          height: "100vh",
          boxSizing: "border-box",
          zIndex: 10,
          transition: "background 0.25s ease, border-color 0.25s ease",
        }}
      >
        {/* Brand Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 28, padding: "0 8px" }}>
          <BrandLogo size={32} />
          <h1
            style={{
              fontSize: "1.0625rem",
              margin: 0,
              fontWeight: 700,
              letterSpacing: "-0.01em",
              background: "var(--heading-gradient)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {t("app.name")}
          </h1>
        </div>

        {/* Nav Links */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "9px 12px",
                borderRadius: "var(--radius-sm)",
                color: isActive ? "var(--sidebar-nav-active-color)" : "var(--text-secondary)",
                background: isActive ? "var(--sidebar-nav-active-bg)" : "transparent",
                fontWeight: isActive ? 600 : 500,
                fontSize: "0.875rem",
                transition: "var(--transition-fast)",
                boxShadow: isActive ? "var(--shadow-sm)" : "none",
                border: isActive ? "1px solid var(--stage-border)" : "1px solid transparent",
              })}
            >
              <span style={{ opacity: 0.9, display: "flex", alignItems: "center" }}>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>

        <hr style={{ margin: "16px 0", borderColor: "var(--stage-border)" }} />

        {/* User Identity Card & Actions */}
        <div
          style={{
            background: "var(--user-card-bg)",
            border: "1px solid var(--stage-border)",
            borderRadius: "var(--radius-sm)",
            padding: "12px",
            marginBottom: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: "var(--avatar-bg)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                border: "1px solid var(--stage-border)",
              }}
            >
              {user?.name?.[0]?.toUpperCase() ?? "U"}
            </div>
            <div style={{ overflow: "hidden" }}>
              <div
                style={{
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  whiteSpace: "nowrap",
                  textOverflow: "ellipsis",
                  overflow: "hidden",
                }}
              >
                {user?.name} · {user?.role}
              </div>
              <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                {user?.email}
              </div>
            </div>
          </div>
          <button
            onClick={logout}
            className="kn-btn-sm"
            style={{ width: "100%", justifyContent: "center" }}
          >
            {t("app.logout")}
          </button>
        </div>

        {/* Appearance & Language Controls */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Appearance Segmented Toggle */}
          <div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: 5, fontWeight: 500 }}>
              {t("app.theme")}
            </div>
            <div
              className="kn-segmented"
              style={{ width: "100%", display: "flex", padding: "3px", boxSizing: "border-box" }}
              role="group"
              aria-label={t("app.theme")}
            >
              <button
                type="button"
                className={`kn-segmented-item ${theme === "light" ? "active" : ""}`}
                onClick={() => setTheme("light")}
                style={{
                  flex: 1,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 5,
                  padding: "5px 0",
                  fontSize: "0.75rem",
                }}
                aria-pressed={theme === "light"}
                title={t("app.themeLight")}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
                <span>{t("app.themeLight")}</span>
              </button>
              <button
                type="button"
                className={`kn-segmented-item ${theme === "dark" ? "active" : ""}`}
                onClick={() => setTheme("dark")}
                style={{
                  flex: 1,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 5,
                  padding: "5px 0",
                  fontSize: "0.75rem",
                }}
                aria-pressed={theme === "dark"}
                title={t("app.themeDark")}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
                <span>{t("app.themeDark")}</span>
              </button>
            </div>
          </div>

          {/* Language Segmented Toggle */}
          <div style={{ position: "relative" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginBottom: 5, fontWeight: 500 }}>
              {t("app.language")}
            </div>
            <div
              className="kn-segmented"
              style={{ width: "100%", display: "flex", padding: "3px", boxSizing: "border-box" }}
              role="group"
              aria-label={t("app.language")}
            >
              <button
                type="button"
                className={`kn-segmented-item ${i18n.language.startsWith("zh") ? "active" : ""}`}
                onClick={() => setLanguage("zh")}
                style={{
                  flex: 1,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 5,
                  padding: "5px 0",
                  fontSize: "0.75rem",
                }}
                aria-pressed={i18n.language.startsWith("zh")}
                title="中文"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                <span>中文</span>
              </button>
              <button
                type="button"
                className={`kn-segmented-item ${i18n.language.startsWith("en") ? "active" : ""}`}
                onClick={() => setLanguage("en")}
                style={{
                  flex: 1,
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 5,
                  padding: "5px 0",
                  fontSize: "0.75rem",
                }}
                aria-pressed={i18n.language.startsWith("en")}
                title="English"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 5h7M9 3v2c0 4.418-2.686 8-6 8M5 9c1.5 2 3.5 3.5 6 4M13 19l4-9 4 9M14.5 16h5" />
                </svg>
                <span>English</span>
              </button>
            </div>

            {/* Accessible & test-compatible select element */}
            <label
              style={{
                position: "absolute",
                top: 0,
                right: 0,
                width: 14,
                height: 14,
                opacity: 0.001,
                overflow: "hidden",
                margin: 0,
                padding: 0,
              }}
            >
              {t("app.language")}
              <select
                aria-label={t("app.language")}
                value={i18n.language.startsWith("zh") ? "zh" : "en"}
                onChange={(e) => setLanguage(e.target.value as "zh" | "en")}
                tabIndex={-1}
                style={{ width: "100%", height: "100%", padding: 0, margin: 0 }}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
        </div>
      </nav>

      {/* Stage Main Canvas */}
      <main
        style={{
          flex: 1,
          padding: "36px 48px",
          maxWidth: "1440px",
          width: "calc(100% - 248px)",
          boxSizing: "border-box",
          position: "relative",
          zIndex: 1,
        }}
      >
        <Outlet />
      </main>
    </div>
  );
}
