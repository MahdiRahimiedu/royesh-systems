"use client";
import { useState, type FormEvent } from "react";
import { KeyRound, UserRound } from "lucide-react";
import { request } from "@/lib/api";
import { labels } from "@/lib/format";
import type { System, User } from "@/lib/types";
import { ErrorBox, Success } from "./Shared";

export function Settings({
  system,
  token,
  user,
  onPasswordChanged,
}: {
  system: System;
  token: string;
  user: User;
  onPasswordChanged: () => void;
}) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setSuccess("");
    setError("");
    if (password !== repeat) {
      setError("گذرواژه جدید و تکرار آن یکسان نیستند.");
      return;
    }
    setBusy(true);
    try {
      await request(system, token, "/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: password }),
      });
      setCurrent("");
      setPassword("");
      setRepeat("");
      onPasswordChanged();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>حساب کاربری</h1>
          <p>مشخصات حساب و تنظیمات امنیتی همین سامانه</p>
        </div>
      </div>
      <div className="settings-layout">
        <section className="ledger settings-profile">
          <div className="section-heading">
            <h2>مشخصات حساب</h2>
            <UserRound size={21} />
          </div>
          <dl className="detail-list">
            <div>
              <dt>نام کامل</dt>
              <dd>{user.full_name}</dd>
            </div>
            <div>
              <dt>نام کاربری</dt>
              <dd dir="ltr">{user.username}</dd>
            </div>
            <div>
              <dt>نقش</dt>
              <dd>{labels[user.role]}</dd>
            </div>
            {user.employee_id && (
              <div>
                <dt>شناسه پرونده پرسنلی</dt>
                <dd>
                  <code className="wrap-code">{user.employee_id}</code>
                </dd>
              </div>
            )}
          </dl>
          <p className="muted">برای اصلاح مشخصات یا دسترسی‌ها با مدیر سامانه هماهنگ کنید.</p>
        </section>
        <section className="ledger settings-password">
          <div className="section-heading">
            <h2>تغییر گذرواژه</h2>
            <KeyRound size={21} />
          </div>
          <form onSubmit={submit}>
            {[
              { id: "current", label: "گذرواژه فعلی", value: current, setter: setCurrent },
              { id: "new", label: "گذرواژه جدید", value: password, setter: setPassword },
              { id: "repeat", label: "تکرار گذرواژه جدید", value: repeat, setter: setRepeat },
            ].map((field) => (
              <div className="form-field" key={field.id}>
                <label htmlFor={field.id}>{field.label}</label>
                <input
                  id={field.id}
                  type="password"
                  dir="ltr"
                  required
                  minLength={field.id === "current" ? 1 : 10}
                  maxLength={128}
                  disabled={busy}
                  value={field.value}
                  autoComplete={field.id === "current" ? "current-password" : "new-password"}
                  onChange={(event) => field.setter(event.target.value)}
                />
              </div>
            ))}
            <small>
              گذرواژه جدید باید حداقل ۱۰ نویسه داشته باشد. پس از تغییر، دوباره وارد حساب شوید.
            </small>
            {error && <ErrorBox message={error} />}
            {success && <Success message={success} />}
            <button className="button primary" disabled={busy} type="submit">
              {busy ? "در حال ذخیره…" : "ذخیره گذرواژه جدید"}
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
