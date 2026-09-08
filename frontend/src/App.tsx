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

export function App() {
  const { user, loading } = useAuth();

  if (loading) return <p style={{ padding: 24 }}>…</p>;
  if (!user) return <Login />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/documents" element={<Documents />} />
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
