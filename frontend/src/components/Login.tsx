"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  Sprout,
  ShieldCheck,
  ArrowUpLeft,
  Users,
  Package,
  BriefcaseBusiness,
  Eye,
  EyeOff,
} from "lucide-react";
import { apiBase, request } from "@/lib/api";
import { systems } from "@/lib/resources";
import type { System, User } from "@/lib/types";
import { ErrorBox, Success } from "./Shared";

export function Login({
  system,
  onLogin,
  notice,
  initialError,
}: {
  system: System;
  onLogin: (token: string, user: User, demo: boolean) => void;
  notice?: string;
  initialError?: string;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError || "");
  const interacted = useRef(false);
  const inFlight = useRef(false);
  useEffect(() => {
    let alive = true;
    if (!["localhost", "127.0.0.1", "::1", "[::1]"].includes(window.location.hostname)) return;
    fetch(apiBase(system).replace(/\/api\/v1$/, "/health"), { signal: AbortSignal.timeout(5000) })
      .then((response) => response.json())
      .then((body) => {
        if (alive && body.demo === true) {
          setDemo(true);
          if (!interacted.current && !notice) {
            setUsername("admin");
            setPassword("admin12345");
          }
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [system]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await request<{ access_token: string; user: User }>(
        system,
        "",
        "/auth/login",
        { method: "POST", body: JSON.stringify({ username, password }) },
      );
      onLogin(result.access_token, result.user, demo);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  }
  return (
    <main className="login-layout">
      <section className="login-brand">
        <div className="brand">
          <div className="brand-symbol">
            <Sprout size={28} />
          </div>
          <div>
            <strong>رویش</strong>
            <span>شرکت توسعه نرم‌افزار</span>
          </div>
        </div>
        <div className="login-statement">
          <span className="brand-rule" />
          <h1>
            همه‌چیز برای
            <br />
            یک روز کاری منظم.
          </h1>
          <p>
            اطلاعات روشن، مسئولیت مشخص
            <br />و سابقه‌ای که همیشه در دسترس است.
          </p>
        </div>
        <div className="login-systems">
          <div className={system === "personnel" ? "selected" : ""}>
            <Users size={20} />
            <span>پرسنلی</span>
          </div>
          <div className={system === "inventory" ? "selected" : ""}>
            <Package size={20} />
            <span>انبار و تجهیزات</span>
          </div>
          <div className={system === "commerce" ? "selected" : ""}>
            <BriefcaseBusiness size={20} />
            <span>بازرگانی</span>
          </div>
        </div>
        <p className="brand-bottom">سامانه‌های مدیریت شرکت رویش</p>
      </section>
      <section className="login-main">
        <div className="login-form-wrap">
          <div className="login-title">
            <div className="login-icon">
              {system === "personnel" ? (
                <Users size={28} />
              ) : system === "inventory" ? (
                <Package size={28} />
              ) : (
                <BriefcaseBusiness size={28} />
              )}
            </div>
            <h2>ورود به {systems[system].title}</h2>
            <p>برای دسترسی به فضای کاری، وارد حساب خود شوید.</p>
          </div>
          {notice && <Success message={notice} />}
          <form onSubmit={submit} className="login-form">
            <div className="form-field">
              <label htmlFor="username">نام کاربری</label>
              <input
                id="username"
                dir="ltr"
                autoComplete="username"
                required
                maxLength={100}
                value={username}
                disabled={busy}
                onChange={(event) => {
                  interacted.current = true;
                  setUsername(event.target.value);
                }}
                placeholder="نام کاربری خود را وارد کنید"
              />
            </div>
            <div className="form-field">
              <label htmlFor="password">گذرواژه</label>
              <div className="password-input">
                <input
                  id="password"
                  type={visible ? "text" : "password"}
                  dir="ltr"
                  autoComplete="current-password"
                  required
                  maxLength={256}
                  value={password}
                  disabled={busy}
                  onChange={(event) => {
                    interacted.current = true;
                    setPassword(event.target.value);
                  }}
                  placeholder="گذرواژه خود را وارد کنید"
                />
                <button
                  className="icon-button"
                  type="button"
                  aria-label={visible ? "پنهان‌کردن گذرواژه" : "نمایش گذرواژه"}
                  onClick={() => setVisible((value) => !value)}
                >
                  {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
            {error && <ErrorBox message={error} />}
            <button className="button primary login-submit" disabled={busy} type="submit">
              {busy ? "در حال ورود…" : "ورود به فضای کاری"}
              <ArrowLeft size={19} />
            </button>
          </form>
          {demo && (
            <div className="demo-accounts">
              <div>
                <ShieldCheck size={19} />
                <strong>محیط نمونه دانشگاهی</strong>
              </div>
              <p>اطلاعات این محیط ساختگی است. یک حساب نمونه انتخاب کنید:</p>
              <div className="demo-choices">
                {[
                  { username: "admin", title: "مدیر سامانه" },
                  { username: "manager", title: "مدیر واحد" },
                  { username: "staff", title: "کارمند" },
                ].map((account) => (
                  <button
                    type="button"
                    disabled={busy}
                    key={account.username}
                    className={username === account.username ? "selected" : ""}
                    onClick={() => {
                      interacted.current = true;
                      setUsername(account.username);
                      setPassword(`${account.username}12345`);
                    }}
                  >
                    <span>{account.title}</span>
                    <code>{account.username}</code>
                  </button>
                ))}
              </div>
              <small>
                گذرواژه: نام کاربری + <code>12345</code>
              </small>
            </div>
          )}
          <div className="login-support">
            <ShieldCheck size={16} />
            <span>دسترسی‌ها بر اساس نقش حساب کاربری تعیین می‌شوند.</span>
          </div>
          <a
            className="login-api"
            href={`${apiBase(system).replace(/\/api\/v1$/, "")}/docs`}
            target="_blank"
            rel="noreferrer"
          >
            راهنمای API برای تیم ادغام
            <ArrowUpLeft size={15} />
          </a>
        </div>
      </section>
    </main>
  );
}
