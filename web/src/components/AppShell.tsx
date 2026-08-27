import { BarChart3, BriefcaseBusiness, ClipboardCheck, LogOut, Menu, Plus, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

const navItems = [
  { to: "/cases", label: "상담 케이스", icon: BriefcaseBusiness },
  { to: "/cases/new", label: "새 케이스", icon: Plus },
  { to: "/reviews", label: "검토함", icon: ClipboardCheck },
  { to: "/metrics", label: "PoC 지표", icon: BarChart3 },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">본문으로 이동</a>
    <header className="mobile-topbar">
      <button className="icon-button" type="button" aria-label="메뉴 열기" onClick={() => setOpen(true)}><Menu /></button>
      <Brand />
    </header>
    {open && <button className="nav-scrim" type="button" aria-label="메뉴 닫기" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`} aria-label="주 메뉴">
      <div className="sidebar-brand"><Brand /><button className="icon-button mobile-only" type="button" aria-label="메뉴 닫기" onClick={() => setOpen(false)}><X /></button></div>
      <nav>{navItems.map(({ to, label, icon: Icon }) => <NavLink
        key={to} to={to} onClick={() => setOpen(false)}
        className={({ isActive }) => isActive ? "nav-link nav-link-active" : "nav-link"}
      ><Icon aria-hidden="true" size={20} /><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-foot">
        <div className="user-chip"><span className="avatar">{user?.display_name?.slice(0, 1) || "C"}</span><div><strong>{user?.display_name}</strong><small>{user?.roles.join(" · ")}</small></div></div>
        <button className="nav-link logout-button" type="button" onClick={logout}><LogOut aria-hidden="true" size={19} />로그아웃</button>
      </div>
    </aside>
    <main id="main-content" className="main-content"><Outlet /></main>
  </div>;
}

function Brand() {
  return <div className="brand"><span className="brand-mark"><ShieldCheck size={20} /></span><span><strong>CSight</strong><small>상담원 콘솔</small></span></div>;
}
