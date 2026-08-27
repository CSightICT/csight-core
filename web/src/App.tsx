import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { AppShell } from "./components/AppShell";
import { CaseWorkspacePage } from "./pages/CaseWorkspacePage";
import { CasesPage } from "./pages/CasesPage";
import { LoginPage } from "./pages/LoginPage";
import { MetricsPage } from "./pages/MetricsPage";
import { NewCasePage } from "./pages/NewCasePage";
import { ReportPage } from "./pages/ReportPage";
import { ReviewDetailPage } from "./pages/ReviewDetailPage";
import { ReviewsPage } from "./pages/ReviewsPage";

function ProtectedLayout() {
  const { user } = useAuth();
  const location = useLocation();
  return user ? <AppShell /> : <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
}

export function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route element={<ProtectedLayout />}>
      <Route index element={<Navigate to="/cases" replace />} />
      <Route path="/cases" element={<CasesPage />} />
      <Route path="/cases/new" element={<NewCasePage />} />
      <Route path="/cases/:caseId" element={<CaseWorkspacePage />} />
      <Route path="/reviews" element={<ReviewsPage />} />
      <Route path="/reviews/:taskId" element={<ReviewDetailPage />} />
      <Route path="/metrics" element={<MetricsPage />} />
      <Route path="/cases/:caseId/report" element={<ReportPage />} />
      <Route path="/cases/:caseId/report/print" element={<ReportPage print />} />
    </Route>
    <Route path="*" element={<Navigate to="/cases" replace />} />
  </Routes>;
}
