import { createContext, useContext, useEffect, useState } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import { AllocationTab } from "./components/AllocationTab";
import { Dashboard } from "./components/Dashboard";
import { EventsTab } from "./components/EventsTab";
import { IntelTab } from "./components/IntelTab";
import { ReportsTab } from "./components/ReportsTab";
import { TenantTab } from "./components/TenantTab";
import { FormModals } from "./components/modals/FormModals";
import { DataProvider, useData } from "./context/DataContext";
import { UserScorePage } from "./pages/UserScorePage";

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/events", label: "Events" },
  { to: "/allocation", label: "Parking" },
  { to: "/intel", label: "Explain & AI" },
  { to: "/reports", label: "Reports" },
  { to: "/admin", label: "Tenant admin" },
] as const;

type ShellModalCtx = {
  openGroupModal: () => void;
  openUserModal: () => void;
};

const ShellModalContext = createContext<ShellModalCtx | null>(null);

export function useShellModals() {
  const c = useContext(ShellModalContext);
  if (!c) throw new Error("useShellModals outside ShellModalContext");
  return c;
}

function Layout() {
  const { health, reloadAll, resetAll } = useData();
  const [groupOpen, setGroupOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);

  const shellModals: ShellModalCtx = {
    openGroupModal: () => {
      setUserOpen(false);
      setGroupOpen(true);
    },
    openUserModal: () => {
      setGroupOpen(false);
      setUserOpen(true);
    },
  };

  useEffect(() => {
    reloadAll().catch(console.error);
  }, [reloadAll]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (userOpen) setUserOpen(false);
      else if (groupOpen) setGroupOpen(false);
    };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [userOpen, groupOpen]);

  async function handleReset() {
    setResetBusy(true);
    try {
      await resetAll();
    } finally {
      setResetBusy(false);
    }
  }

  const featureRows: [string, boolean][] = health
    ? [
        ["SQLite / store", health.store === "SqliteStore"],
        ["Groups registry", !!health.features?.groups_registry],
        ["Score history", !!health.features?.score_history],
        ["Tenant weights", !!health.features?.tenant_weights],
        ["Shadow mode", !!health.features?.shadow_mode],
        [
          (() => {
            const b = String(health.features?.llm_backend ?? "off");
            const auto =
              !!health.features?.llm_auto_ollama && health.features?.llm_backend === "ollama";
            return `LLM (${b}${auto ? ", auto" : ""})`;
          })(),
          !!health.features?.llm_explain_env,
        ],
      ]
    : [];

  return (
    <ShellModalContext.Provider value={shellModals}>
      <header className="top">
        <div>
          <h1>Newton 3.0</h1>
          <p className="muted">React UI · routed URLs · connects to Newton API</p>
        </div>
        <div className="actions">
          <button
            type="button"
            title="Deletes all local users, groups, events, scores, saved allocations, and tenant config, then reloads"
            disabled={resetBusy}
            onClick={() => void handleReset()}
          >
            {resetBusy ? "Working…" : "Reset all data"}
          </button>
          <span
            className="pill"
            style={{ background: health ? "#1f3b2d" : "#4a2323" }}
          >
            {health
              ? `${health.status} · ${health.store}${health.sqlite_path ? " · DB on disk" : ""}`
              : "offline"}
          </span>
        </div>
      </header>

      <div id="feature-badges" className="badges" aria-label="Feature flags">
        {featureRows.map(([label, on]) => (
          <span key={label} className={`badge ${on ? "on" : "off"}`}>
            {label}: {on ? "yes" : "no"}
          </span>
        ))}
      </div>

      <nav className="tabs" role="tablist" aria-label="Sections">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            role="tab"
            className={({ isActive }) => `tab${isActive ? " active" : ""}`}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <section className="panel active" role="tabpanel">
        <Outlet />
      </section>

      <FormModals
        groupOpen={groupOpen}
        userOpen={userOpen}
        onCloseGroup={() => setGroupOpen(false)}
        onCloseUser={() => setUserOpen(false)}
      />

      <footer className="muted page-foot">
        Routes: <code>/dashboard</code>, <code>/events</code>, <code>/allocation</code>,{" "}
        <code>/intel</code>, <code>/reports</code>, <code>/admin</code>,{" "}
        <code>/users/&#123;id&#125;/score</code> · Set{" "}
        <code>VITE_API_BASE_URL</code> when UI and API use different origins (
        <code>ui/.env.example</code>)
      </footer>
    </ShellModalContext.Provider>
  );
}

function DashboardRoute() {
  const { openGroupModal, openUserModal } = useShellModals();
  const navigate = useNavigate();
  return (
    <Dashboard
      onOpenGroup={openGroupModal}
      onOpenUser={openUserModal}
      onScoreUser={(id) => navigate(`/users/${encodeURIComponent(id)}/score`)}
    />
  );
}

export default function App() {
  return (
    <DataProvider>
      <BrowserRouter
        basename={import.meta.env.BASE_URL}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardRoute />} />
            <Route path="events" element={<EventsTab />} />
            <Route path="allocation" element={<AllocationTab />} />
            <Route path="intel" element={<IntelTab />} />
            <Route path="reports" element={<ReportsTab />} />
            <Route path="admin" element={<TenantTab />} />
            <Route path="users/:userId/score" element={<UserScorePage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </DataProvider>
  );
}
