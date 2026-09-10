import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Documents } from "./pages/Documents";
import { DocumentDetail } from "./pages/DocumentDetail";
import { AuditLog } from "./pages/settings/AuditLog";
import { Providers } from "./pages/settings/Providers";
import { Redaction } from "./pages/settings/Redaction";
import { SettingsLayout } from "./pages/settings/SettingsLayout";
import { ThresholdsPage } from "./pages/settings/Thresholds";
import { Users } from "./pages/settings/Users";
import { Search } from "./pages/Search";
import { ReviewQueue } from "./pages/ReviewQueue";
import { Controls } from "./pages/Controls";
import { ControlDetail } from "./pages/ControlDetail";
import { Frameworks } from "./pages/Frameworks";
import { FrameworkDetail } from "./pages/FrameworkDetail";
import { TechAssets } from "./pages/TechAssets";
import { Evidence } from "./pages/Evidence";

export function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          gap: 16,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            border: "3px solid rgba(255, 255, 255, 0.1)",
            borderTopColor: "var(--accent-blue)",
            borderRadius: "50%",
            animation: "kn-pulse 1s infinite linear",
          }}
        />
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", letterSpacing: "0.05em" }}>
          GRC HELPER
        </p>
      </div>
    );
  }
  if (!user) return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/search" element={<Search />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="/controls" element={<Controls />} />
        <Route path="/controls/:id" element={<ControlDetail />} />
        <Route path="/frameworks" element={<Frameworks />} />
        <Route path="/frameworks/:id" element={<FrameworkDetail />} />
        <Route path="/tech-assets" element={<TechAssets />} />
        <Route path="/evidence" element={<Evidence />} />
        <Route path="/documents/:id" element={<DocumentDetail />} />
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="providers" replace />} />
          <Route path="providers" element={<Providers />} />
          <Route path="redaction" element={<Redaction />} />
          <Route path="thresholds" element={<ThresholdsPage />} />
          <Route path="users" element={<Users />} />
          <Route path="audit-log" element={<AuditLog />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
