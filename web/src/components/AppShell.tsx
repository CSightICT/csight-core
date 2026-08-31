import { Activity, BarChart3, BriefcaseBusiness, ClipboardCheck, Database, LogOut, Menu, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

const navItems = [
  { to: "/cases", label: "상담 케이스", reviewerLabel: "문의 대기", icon: BriefcaseBusiness },
  { to: "/reviews", label: "검토함", reviewerLabel: "내 문의 처리 현황", icon: ClipboardCheck },
  { to: "/metrics", label: "운영 지표", icon: BarChart3 },
  { to: "/data-assets", label: "데이터 자산", icon: Database, adminOnly: false },
  { to: "/operations", label: "운영 상태", icon: Activity, adminOnly: true },
];

export function AppShell() {
  const { user, logout, sessionExpiresWithinFiveMinutes, startOidcLogin } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const reviewerWorkspace = Boolean(user?.roles.includes("REVIEWER") && !user.roles.includes("ADMIN"));
  async function handleLogout() {
    setLogoutError(false);
    try {
      await logout();
    } catch {
      setLogoutError(true);
    }
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">본문으로 이동</a>
    <header className="mobile-topbar">
      <button className="icon-button" type="button" aria-label="메뉴 열기" onClick={() => setOpen(true)}><Menu /></button>
      <Brand />
    </header>
    {open && <button className="nav-scrim" type="button" aria-label="메뉴 닫기" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="주 메뉴">
      <div className="sidebar-brand"><Brand />{open && <button className="icon-button mobile-only" type="button" aria-label="메뉴 닫기" onClick={() => setOpen(false)}><X /></button>}</div>
      <nav>{navItems.filter((item) => (!item.adminOnly || user?.roles.includes("ADMIN")) && (!reviewerWorkspace || item.to === "/cases" || item.to === "/reviews")).map(({ to, label, reviewerLabel, icon: Icon }) => <NavLink
        key={to} to={to} onClick={() => setOpen(false)}
        className={({ isActive }) => isActive ? "nav-link nav-link-active" : "nav-link"}
      ><Icon aria-hidden="true" size={20} /><span>{reviewerWorkspace ? reviewerLabel ?? label : label}</span></NavLink>)}</nav>
      <div className="sidebar-foot">
        {logoutError && <span className="sidebar-auth-error" role="alert">서버에서 로그아웃을 확인하지 못했습니다. 다시 시도해 주세요.</span>}
        <div className="user-chip"><span className="avatar">{user?.display_name?.slice(0, 1) || "C"}</span><div><strong>{user?.display_name}</strong><small>{user?.roles.join(" · ")}</small></div></div>
        <button className="nav-link logout-button" type="button" onClick={() => void handleLogout()}><LogOut aria-hidden="true" size={19} />로그아웃</button>
      </div>
    </aside>
    <main id="main-content" className="main-content" tabIndex={-1}>
      {sessionExpiresWithinFiveMinutes && <div className="session-warning" role="status"><span>세션이 5분 안에 만료됩니다.</span><button type="button" className="button button-secondary" onClick={() => startOidcLogin(`${location.pathname}${location.search}`)}>다시 인증</button></div>}
      <Outlet />
    </main>
  </div>;
}

function Brand() {
  return <div className="brand"><span className="brand-mark"><ShieldCheck size={20} /></span><span><strong>CSight</strong><small>상담원 콘솔</small></span></div>;
}
