"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  LayoutDashboard,
  Users,
  Building2,
  FileSignature,
  CalendarDays,
  MapPin,
  Award,
  Wallet,
  Package,
  Truck,
  ShoppingCart,
  ArrowDownUp,
  Monitor,
  Handshake,
  ChartNoAxesCombined,
  ContactRound,
  CodeXml,
  FileText,
  Receipt,
  CircleDollarSign,
  ShieldCheck,
  History,
  Settings as SettingsIcon,
  LogOut,
  Menu,
  X,
  ChevronLeft,
  Sprout,
  ArrowUpLeft,
} from "lucide-react";
import { apiBase, configureApi, request, uiPorts } from "@/lib/api";
import { labels } from "@/lib/format";
import { systemResources, systems } from "@/lib/resources";
import type { System, User } from "@/lib/types";
import { session } from "@/lib/session";
import { Dashboard } from "./Dashboard";
import { Login } from "./Login";
import { ResourceTable } from "./ResourceTable";
import { Settings } from "./Settings";
import { ErrorBox } from "./Shared";

const icons: Record<string, typeof Users> = {
  employees: Users,
  departments: Building2,
  "employment-contracts": FileSignature,
  leaves: CalendarDays,
  missions: MapPin,
  adjustments: Award,
  payrolls: Wallet,
  items: Package,
  suppliers: Truck,
  purchases: ShoppingCart,
  movements: ArrowDownUp,
  assets: Monitor,
  assignments: Handshake,
  stock: ChartNoAxesCombined,
  customers: ContactRound,
  offerings: CodeXml,
  quotations: FileText,
  contracts: FileSignature,
  invoices: Receipt,
  payments: CircleDollarSign,
  receivables: ChartNoAxesCombined,
  users: ShieldCheck,
  "audit-logs": History,
};
export function App({ system, apiUrl }: { system: System; apiUrl?: string }) {
  configureApi(system, apiUrl);
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [route, setRoute] = useState("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [demo, setDemo] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const sessionKey = `royesh.${system}.token`;
  const [sessionNotice, setSessionNotice] = useState("");
  const [sessionError, setSessionError] = useState("");
  const tokenRef = useRef("");
  const sidebarRef = useRef<HTMLElement>(null);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 980px)");
    const update = () => {
      setCompact(media.matches);
      if (!media.matches) setMobileOpen(false);
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!compact || !mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () =>
      Array.from(
        sidebarRef.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), a[href], summary",
        ) || [],
      ).filter((element) => element.getClientRects().length > 0);
    controls()[0]?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobileOpen(false);
      }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = oldOverflow;
      window.removeEventListener("keydown", onKeyDown);
      if (previous?.isConnected) previous.focus();
    };
  }, [compact, mobileOpen]);
  const expire = useCallback(() => {
    session.remove(sessionKey);
    tokenRef.current = "";
    setToken("");
    setUser(null);
  }, [sessionKey]);
  useEffect(() => {
    let alive = true;
    const stored = session.read(sessionKey);
    tokenRef.current = stored || "";
    if (stored)
      request<User>(system, stored, "/auth/me")
        .then((result) => {
          if (alive) {
            setToken(stored);
            setUser(result);
          }
        })
        .catch((reason) => {
          if (!alive) return;
          if (reason.status === 401) session.remove(sessionKey);
          else setSessionError(reason.message);
        })
        .finally(() => {
          if (alive) setRestoring(false);
        });
    else setRestoring(false);
    fetch(apiBase(system).replace(/\/api\/v1$/, "/health"), { signal: AbortSignal.timeout(5000) })
      .then((response) => response.json())
      .then((body) => {
        if (alive) setDemo(body.demo === true);
      })
      .catch(() => {});
    const hashChange = () => {
      setRoute(window.location.hash.slice(1) || "dashboard");
      setMobileOpen(false);
    };
    hashChange();
    window.addEventListener("hashchange", hashChange);
    const sessionExpired = (event: Event) => {
      const detail = (event as CustomEvent<{ system: System; token: string }>).detail;
      if (detail?.system === system && detail.token === tokenRef.current) expire();
    };
    window.addEventListener("royesh-session-expired", sessionExpired);
    return () => {
      alive = false;
      window.removeEventListener("hashchange", hashChange);
      window.removeEventListener("royesh-session-expired", sessionExpired);
    };
  }, [system, sessionKey, expire]);
  function navigate(key: string) {
    window.location.hash = key;
    setRoute(key);
    setMobileOpen(false);
    requestAnimationFrame(() => document.getElementById("main-content")?.focus());
  }
  async function logout() {
    setLoggingOut(true);
    setLogoutError("");
    try {
      await request(system, token, "/auth/logout", { method: "POST" });
      expire();
    } catch (reason) {
      setLogoutError((reason as Error).message);
    } finally {
      setLoggingOut(false);
    }
  }
  const refreshProfile = useCallback(() => {
    const activeToken = tokenRef.current;
    if (!activeToken) return;
    request<User>(system, activeToken, "/auth/me")
      .then((profile) => {
        if (tokenRef.current === activeToken) setUser(profile);
      })
      .catch(() => {});
  }, [system]);
  const allResources = systemResources(system);
  const available = allResources.filter(
    (resource) =>
      (!resource.adminOnly || user?.role === "admin") &&
      (!resource.managerOnly || user?.role !== "staff"),
  );
  const resource = available.find((item) => item.key === route);
  if (restoring)
    return (
      <div className="boot-screen" role="status">
        <Sprout size={38} />
        <strong>رویش</strong>
        <span>در حال آماده‌سازی فضای کاری…</span>
      </div>
    );
  if (!user || !token)
    return (
      <Login
        system={system}
        notice={sessionNotice}
        initialError={sessionError}
        onLogin={(newToken, newUser, isDemo) => {
          session.write(sessionKey, newToken);
          tokenRef.current = newToken;
          setToken(newToken);
          setUser(newUser);
          setDemo(isDemo);
          setSessionNotice("");
          setSessionError("");
          setLogoutError("");
          setRoute("dashboard");
          window.location.hash = "dashboard";
        }}
      />
    );
  const business = available.filter((item) => !["users", "audit-logs"].includes(item.key));
  const management = available.filter((item) => ["users", "audit-logs"].includes(item.key));
  const nav = (key: string, title: string, Icon: typeof Users) => (
    <button
      key={key}
      onClick={() => navigate(key)}
      className={`nav-item ${route === key ? "active" : ""}`}
      aria-current={route === key ? "page" : undefined}
    >
      <Icon size={19} />
      <span>{title}</span>
      {route === key && <ChevronLeft size={16} />}
    </button>
  );
  function systemUrl(other: System) {
    const configured = {
      personnel: process.env.NEXT_PUBLIC_PERSONNEL_URL,
      inventory: process.env.NEXT_PUBLIC_INVENTORY_URL,
      commerce: process.env.NEXT_PUBLIC_COMMERCE_URL,
    }[other];
    return (
      configured || `${window.location.protocol}//${window.location.hostname}:${uiPorts[other]}`
    );
  }
  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        رفتن به محتوای اصلی
      </a>
      {mobileOpen && (
        <button
          className="nav-scrim"
          aria-label="بستن فهرست"
          tabIndex={-1}
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside
        id="main-navigation"
        ref={sidebarRef}
        className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}
        inert={compact && !mobileOpen}
        role={compact && mobileOpen ? "dialog" : undefined}
        aria-modal={compact && mobileOpen ? true : undefined}
        aria-label="فهرست اصلی"
      >
        <div className="sidebar-brand">
          <div className="brand">
            <div className="brand-symbol">
              <Sprout size={27} />
            </div>
            <div>
              <strong>رویش</strong>
              <span>شرکت توسعه نرم‌افزار</span>
            </div>
          </div>
          <button
            className="icon-button mobile-close"
            aria-label="بستن فهرست"
            onClick={() => setMobileOpen(false)}
          >
            <X size={21} />
          </button>
        </div>
        <div className="system-identity">
          <span className="system-dot" />
          {systems[system].title}
        </div>
        <nav>
          {nav("dashboard", "نمای کلی", LayoutDashboard)}
          <span className="nav-label">مدیریت عملیات</span>
          {business.map((item) => nav(item.key, item.title, icons[item.key] || FileText))}
          <span className="nav-label">حساب و مدیریت</span>
          {management.map((item) => nav(item.key, item.title, icons[item.key] || ShieldCheck))}
          {nav("settings", "حساب کاربری", SettingsIcon)}
        </nav>
        <div className="sidebar-bottom">
          <details className="system-switch">
            <summary>
              سامانه‌های مستقل
              <ArrowUpLeft size={16} />
            </summary>
            <div>
              {(Object.keys(systems) as System[])
                .filter((key) => key !== system)
                .map((key) => (
                  <a key={key} href={systemUrl(key)}>
                    {systems[key].title}
                    <ArrowUpLeft size={15} />
                  </a>
                ))}
            </div>
            <small>هر سامانه ورود و داده‌های مستقل دارد.</small>
          </details>
          <div className="sidebar-user">
            <div className="avatar">{user.full_name.slice(0, 1)}</div>
            <div>
              <strong>{user.full_name}</strong>
              <span>{labels[user.role]}</span>
            </div>
            <button
              className="icon-button"
              aria-label="خروج از حساب"
              title="خروج از حساب"
              onClick={logout}
              disabled={loggingOut}
            >
              <LogOut size={19} />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace" inert={compact && mobileOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              aria-label="بازکردن فهرست"
              aria-expanded={mobileOpen}
              aria-controls="main-navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={23} />
            </button>
            <span>فضای کاری رویش</span>
            <ChevronLeft size={14} />
            <strong>
              {resource?.title || (route === "settings" ? "حساب کاربری" : "نمای کلی")}
            </strong>
          </div>
          <div className="topbar-info">
            {demo && <span className="demo-tag">محیط نمونه · اطلاعات ساختگی</span>}
            <time>
              {new Intl.DateTimeFormat("fa-IR", {
                weekday: "long",
                day: "numeric",
                month: "long",
              }).format(new Date())}
            </time>
          </div>
        </header>
        <main id="main-content" tabIndex={-1} className="main-content">
          {logoutError && <ErrorBox message={logoutError} retry={logout} />}
          {route === "settings" ? (
            <Settings
              system={system}
              token={token}
              user={user}
              onPasswordChanged={() => {
                if (tokenRef.current !== token) return;
                setSessionNotice("گذرواژه تغییر کرد. با گذرواژه جدید وارد شوید.");
                expire();
              }}
            />
          ) : resource ? (
            <ResourceTable
              key={resource.key}
              system={system}
              token={token}
              user={user}
              resource={resource}
              onExpired={expire}
              onAccountChanged={refreshProfile}
            />
          ) : (
            <Dashboard system={system} token={token} user={user} navigate={navigate} />
          )}
        </main>
        <footer className="workspace-footer">
          <span>رویش · {systems[system].title}</span>
          <span>هر تغییر، یک سابقه قابل پیگیری</span>
        </footer>
      </div>
    </div>
  );
}
