"use client";
import { useRef, useState, type FormEvent } from "react";
import { Check } from "lucide-react";
import { request } from "@/lib/api";
import type { Row, Resource, System } from "@/lib/types";
import type { WorkflowAction } from "@/lib/workflows";
import { ErrorBox } from "./Shared";

export function WorkflowForm({
  system,
  token,
  resource,
  row,
  action,
  onSaved,
  onCancel,
  onBusyChange,
}: {
  system: System;
  token: string;
  resource: Resource;
  row: Row;
  action: WorkflowAction;
  onSaved: () => void;
  onCancel: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [allowance, setAllowance] = useState(String(row.allowance || 0));
  const inFlight = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    setError("");
    if (action.allowance && (!Number.isSafeInteger(Number(allowance)) || Number(allowance) < 0)) {
      setError("مبلغ فوق‌العاده مأموریت باید عدد صحیح صفر یا بیشتر باشد.");
      return;
    }
    setBusy(true);
    inFlight.current = true;
    onBusyChange(true);
    const payload = { ...action.body };
    if (action.allowance) payload.allowance = Number(allowance);
    if (action.field === "comment") payload.comment = value;
    if (action.field === "serial_numbers" && value.trim())
      payload.serial_numbers = value
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean);
    try {
      await request(system, token, `${resource.endpoint}/${row.id}/${action.suffix}`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onSaved();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
      inFlight.current = false;
      onBusyChange(false);
    }
  }
  return (
    <form className="drawer-form" onSubmit={submit}>
      <div className="drawer-body">
        <p className="confirmation-copy">{action.detail}</p>
        <div className="record-reference">
          مورد انتخاب‌شده
          <strong>
            {String(
              row.title || row.name || row.employee_name || row.item_name || resource.singular,
            )}
          </strong>
          <code>{row.id}</code>
        </div>
        {action.field && (
          <div className="form-field">
            <label htmlFor="workflow-value">
              {action.field === "comment"
                ? "توضیح تصمیم (اختیاری)"
                : "شماره سریال‌ها (برای کالای سریال‌دار)"}
            </label>
            <textarea
              id="workflow-value"
              dir={action.field === "serial_numbers" ? "ltr" : "rtl"}
              rows={6}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              maxLength={action.field === "comment" ? 2000 : 12000}
              disabled={busy}
            />
            <small>
              {action.field === "serial_numbers"
                ? "برای کالای تعدادی این فیلد را خالی بگذارید."
                : "توضیح شما همراه با تصمیم ثبت می‌شود."}
            </small>
          </div>
        )}
        {action.allowance && (
          <div className="form-field">
            <label htmlFor="mission-allowance">فوق‌العاده مصوب مأموریت (تومان)</label>
            <input
              id="mission-allowance"
              dir="ltr"
              type="number"
              required
              min="0"
              max="1000000000000"
              step="1"
              value={allowance}
              disabled={busy}
              onChange={(event) => setAllowance(event.target.value)}
            />
            <small>مبلغ نهایی هنگام تأیید ثبت و در حقوق دوره محاسبه می‌شود.</small>
          </div>
        )}
        {error && <ErrorBox message={error} />}
      </div>
      <footer className="drawer-footer">
        <button
          className={`button ${action.danger ? "danger" : "primary"}`}
          disabled={busy}
          type="submit"
        >
          <Check size={18} />
          {busy ? "در حال ثبت…" : action.title}
        </button>
        <button className="button secondary" disabled={busy} type="button" onClick={onCancel}>
          انصراف
        </button>
      </footer>
    </form>
  );
}
