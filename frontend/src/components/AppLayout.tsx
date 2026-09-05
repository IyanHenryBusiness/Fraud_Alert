import { NavLink, Outlet } from "react-router-dom"

const navigation = [
  { to: "/", label: "Overview", end: true },
  { to: "/alerts", label: "Alerts", end: false },
  { to: "/analytics", label: "Fraud Analytics", end: false },
]

export function AppLayout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark" aria-label="Fraud analysis workspace">
          <span className="brand-symbol">FA</span>
          <span>
            <strong>Fraud Atlas</strong>
            <small>Analyst workspace</small>
          </span>
        </div>
        <nav className="main-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              <span className="nav-dot" aria-hidden="true" />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-pip" />
          <span>FastAPI connected</span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span className="eyebrow">Risk operations / 06 Sep 2026</span>
          <span className="topbar-note">Decision support for human review</span>
        </header>
        <main className="page-content"><Outlet /></main>
      </div>
    </div>
  )
}
