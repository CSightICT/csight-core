import { lazy, Suspense, useEffect, type ReactElement } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { AppShell } from "./components/AppShell";
import { Loading } from "./components/Ui";

const CaseWorkspacePage = lazy(() => import("./pages/CaseWorkspacePage").then((module) => ({ default: module.CaseWorkspacePage })));
const CasesPage = lazy(() => import("./pages/CasesPage").then((module) => ({ default: module.CasesPage })));
const DataAssetsPage = lazy(() => import("./pages/DataAssetsPage").then((module) => ({ default: module.DataAssetsPage })));
const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const MetricsPage = lazy(() => import("./pages/MetricsPage").then((module) => ({ default: module.MetricsPage })));
const OperationsPage = lazy(() => import("./pages/OperationsPage").then((module) => ({ default: module.OperationsPage })));
const ReportPage = lazy(() => import("./pages/ReportPage").then((module) => ({ default: module.ReportPage })));
const ReviewDetailPage = lazy(() => import("./pages/ReviewDetailPage").then((module) => ({ default: module.ReviewDetailPage })));
const ReviewsPage = lazy(() => import("./pages/ReviewsPage").then((module) => ({ default: module.ReviewsPage })));

function deferredRoute(element: ReactElement) {
  return <Suspense fallback={<div className="page"><Loading label="화면을 준비하는 중" /></div>}>{element}</Suspense>;
}

function ProtectedLayout() {
  const { user } = useAuth();
  const location = useLocation();
  return user ? <AppShell /> : <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
}

const routeTitles: ReadonlyArray<readonly [RegExp, string]> = [
  [/^\/cases\/[^/]+\/report(?:\/print)?$/, "처리 확인 문서"],
  [/^\/cases\/[^/]+$/, "케이스 업무 공간"],
  [/^\/cases$/, "상담 케이스"],
  [/^\/reviews\/[^/]+$/, "검토 상세"],
  [/^\/reviews$/, "검토함"],
  [/^\/metrics$/, "운영 지표"],
  [/^\/data-assets$/, "데이터 자산"],
  [/^\/operations$/, "운영 상태"],
  [/^\/login$/, "로그인"],
];

function RouteAccessibility() {
  const location = useLocation();

  useEffect(() => {
    const routeTitle = routeTitles.find(([pattern]) => pattern.test(location.pathname))?.[1]
      ?? "상담원 콘솔";
    document.title = `${routeTitle} | CSight`;
    const focusTimer = window.setTimeout(() => {
      document.getElementById("main-content")?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(focusTimer);
  }, [location.pathname]);

  return null;
}

export function App() {
  return <>
    <RouteAccessibility />
    <Routes>
    <Route path="/login" element={deferredRoute(<LoginPage />)} />
    <Route element={<ProtectedLayout />}>
      <Route index element={<Navigate to="/cases" replace />} />
      <Route path="/cases" element={deferredRoute(<CasesPage />)} />
      <Route path="/cases/new" element={<Navigate to="/cases" replace />} />
      <Route path="/cases/:caseId" element={deferredRoute(<CaseWorkspacePage />)} />
      <Route path="/reviews" element={deferredRoute(<ReviewsPage />)} />
      <Route path="/reviews/:taskId" element={deferredRoute(<ReviewDetailPage />)} />
      <Route path="/metrics" element={deferredRoute(<MetricsPage />)} />
      <Route path="/data-assets" element={deferredRoute(<DataAssetsPage />)} />
      <Route path="/operations" element={deferredRoute(<OperationsPage />)} />
      <Route path="/cases/:caseId/report" element={deferredRoute(<ReportPage />)} />
      <Route path="/cases/:caseId/report/print" element={deferredRoute(<ReportPage print />)} />
    </Route>
    <Route path="*" element={<Navigate to="/cases" replace />} />
    </Routes>
  </>;
}
