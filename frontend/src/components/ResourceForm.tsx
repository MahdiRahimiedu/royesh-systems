"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Plus, Trash2, Save } from "lucide-react";
import { allRows, request } from "@/lib/api";
import { labels, number, todayISO } from "@/lib/format";
import {
  editableFields,
  initialValues,
  preparePayload,
  referenceOptions,
  type Values,
  type QuotationLine,
} from "@/lib/forms";
import type { Field, Resource, Row, System, User } from "@/lib/types";
import { ErrorBox } from "./Shared";

export function ResourceForm({
  system,
  token,
  user,
  resource,
  row,
  onSaved,
  onCancel,
  onBusyChange,
}: {
  system: System;
  token: string;
  user: User;
  resource: Resource;
  row?: Row;
  onSaved: () => void;
  onCancel: () => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const fields = editableFields(resource, user, row);
  const [values, setValues] = useState<Values>(() => initialValues(fields, row));
  const [references, setReferences] = useState<Record<string, Row[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [referenceError, setReferenceError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmingStatus, setConfirmingStatus] = useState(false);
  const [retry, setRetry] = useState(0);
  const inFlight = useRef(false);
  const [lines, setLines] = useState<QuotationLine[]>(() =>
    Array.isArray(row?.lines)
      ? (row.lines as Record<string, unknown>[]).map((line) => ({
          offering_id: String(line.offering_id || ""),
          description: String(line.description || ""),
          quantity: Number(line.quantity),
          unit_price: Number(line.unit_price),
        }))
      : [{ offering_id: "", description: "", quantity: 1, unit_price: 0 }],
  );
  const set = (key: string, value: string | number | boolean) => {
    setConfirmingStatus(false);
    setValues((previous) => {
      const next = { ...previous, [key]: value };
      if (resource.key === "contracts" && key === "customer_id") next.quotation_id = "";
      if (resource.key === "assignments" && key === "asset_id" && value) next.quantity = 1;
      if (resource.key === "movements" && key === "type" && value === "out")
        next.serial_numbers = "";
      if (resource.key === "contracts" && key === "quotation_id" && value) {
        const quote = references["/quotations"]?.find((item) => item.id === value);
        if (quote) {
          next.amount = Number(quote.total);
          next.customer_id = String(quote.customer_id);
        }
      }
      return next;
    });
  };
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true);
    setReferenceError("");
    const endpoints = Array.from(
      new Set([
        ...(fields.map((field) => field.reference).filter(Boolean) as string[]),
        ...(resource.key === "quotations" ? ["/offerings"] : []),
      ]),
    );
    Promise.all(
      endpoints.map(
        async (endpoint) =>
          [
            endpoint,
            await allRows(system, token, endpoint, { signal: controller.signal }),
          ] as const,
      ),
    )
      .then((data) => {
        if (alive) setReferences(Object.fromEntries(data));
      })
      .catch((reason) => {
        if (alive) setReferenceError(reason.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      controller.abort();
    };
    // Fields derive from a resource that remains fixed while this drawer is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [system, token, resource.key, retry]);

  const selectedItem = references["/items"]?.find((item) => item.id === values.item_id);
  const isSerialized = selectedItem?.tracking_type === "serialized";
  function availableOptions(field: Field): Row[] {
    return referenceOptions(field, references[field.reference || ""] || [], resource, values, row);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || loading || referenceError) return;
    setError("");
    if (resource.staffCreate && user.role === "staff" && !user.employee_id) {
      setError(
        "حساب شما به پرونده پرسنلی متصل نشده است. مدیر سامانه باید شناسه کارمند را برای این حساب تنظیم کند.",
      );
      return;
    }
    if (
      values.start_date &&
      values.end_date &&
      String(values.end_date) < String(values.start_date)
    ) {
      setError("تاریخ پایان باید برابر یا بعد از تاریخ شروع باشد.");
      return;
    }
    if (
      values.issue_date &&
      values.due_date &&
      String(values.due_date) < String(values.issue_date)
    ) {
      setError("سررسید باید برابر یا بعد از تاریخ صدور باشد.");
      return;
    }
    if (resource.key === "assignments" && Boolean(values.asset_id) === Boolean(values.item_id)) {
      setError("یک دارایی سریال‌دار یا یک کالای تعدادی انتخاب کنید.");
      return;
    }
    if (resource.key === "movements" && isSerialized && values.type === "out") {
      setError("خروج تجهیز سریال‌دار باید از بخش تحویل و بازگشت ثبت شود.");
      return;
    }
    if (
      resource.key === "contracts" &&
      Boolean(values.employee_id) !== Boolean(values.employee_name)
    ) {
      setError("شناسه و نام مسئول قرارداد باید با هم وارد شوند یا هر دو خالی باشند.");
      return;
    }
    let payload: Record<string, unknown>;
    try {
      payload = preparePayload(resource, fields, values, user, row, lines);
    } catch (reason) {
      setError((reason as Error).message);
      return;
    }
    if (row && payload.status && !confirmingStatus) {
      setConfirmingStatus(true);
      return;
    }
    setBusy(true);
    inFlight.current = true;
    onBusyChange(true);
    try {
      await request(system, token, resource.endpoint + (row ? `/${row.id}` : ""), {
        method: row ? "PATCH" : "POST",
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
        <div className="form-note">
          فیلدهای دارای <span className="required">*</span> الزامی‌اند. تاریخ ورودی با تقویم میلادی
          و نمایش تاریخ در فهرست‌ها شمسی است.
        </div>
        {user.role === "staff" && resource.staffCreate && (
          <div className="info-box">درخواست برای پرونده پرسنلی خود شما ثبت می‌شود.</div>
        )}
        {resource.key === "assignments" && (
          <div className="info-box">
            یکی از دو نوع دارایی یا کالای تعدادی را انتخاب کنید. شناسه کارمند، مرجع سامانه پرسنلی
            است.
          </div>
        )}
        {row && resource.key === "contracts" && row.status !== "draft" && (
          <div className="info-box">
            مشتری، مبلغ و تاریخ‌های قرارداد فعال قابل تغییر نیستند؛ اطلاعات پیگیری و توضیحات را
            می‌توانید اصلاح کنید.
          </div>
        )}
        {loading && (
          <p className="muted" role="status">
            در حال دریافت گزینه‌های فرم…
          </p>
        )}
        {referenceError && (
          <ErrorBox message={referenceError} retry={() => setRetry((count) => count + 1)} />
        )}
        <div className="form-grid">
          {fields.map((field) => {
            const inputId = `field-${field.key}`;
            const isWide = field.type === "textarea" || field.key === "employee_id";
            const disabled =
              busy ||
              loading ||
              (resource.key === "contracts" && !!values.quotation_id && field.key === "amount") ||
              (resource.key === "assets" && !row && field.key === "status") ||
              (resource.key === "assignments" &&
                ((field.key === "quantity" && !!values.asset_id) ||
                  (field.key === "item_id" && !!values.asset_id) ||
                  (field.key === "asset_id" && !!values.item_id)));
            return (
              <div
                key={field.key}
                className={`form-field ${isWide ? "wide" : ""} ${field.type === "checkbox" ? "check-field" : ""}`}
              >
                {field.type === "checkbox" ? (
                  <label className="check-label" htmlFor={inputId}>
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={Boolean(values[field.key])}
                      disabled={disabled}
                      onChange={(event) => set(field.key, event.target.checked)}
                    />
                    {field.label}
                  </label>
                ) : (
                  <>
                    <label htmlFor={inputId}>
                      {field.label}{" "}
                      {field.required && (
                        <span className="required" aria-label="الزامی">
                          *
                        </span>
                      )}
                    </label>
                    {field.type === "textarea" ? (
                      <textarea
                        id={inputId}
                        value={String(values[field.key] ?? "")}
                        onChange={(event) => set(field.key, event.target.value)}
                        required={field.required}
                        disabled={disabled}
                        rows={3}
                        maxLength={2000}
                        aria-describedby={field.hint ? `${inputId}-hint` : undefined}
                      />
                    ) : field.type === "select" ? (
                      <select
                        id={inputId}
                        value={String(values[field.key] ?? "")}
                        onChange={(event) => set(field.key, event.target.value)}
                        required={field.required}
                        disabled={disabled}
                      >
                        <option value="">انتخاب کنید</option>
                        {resource.key === "assets" &&
                          field.key === "status" &&
                          row?.status === "assigned" && <option value="assigned">تحویل شده</option>}
                        {field.reference
                          ? availableOptions(field).map((item) => (
                              <option value={item.id} key={item.id}>
                                {field.key === "invoice_id"
                                  ? [item.customer_name, item.contract_title, item.description]
                                      .filter(Boolean)
                                      .join(" · ") || item.id
                                  : [
                                      item[field.display || "name"] || item.name || item.id,
                                      item.customer_name,
                                    ]
                                      .filter(Boolean)
                                      .join(" · ")}
                                {item.balance !== undefined
                                  ? ` — مانده ${number(item.balance)} تومان`
                                  : ""}
                              </option>
                            ))
                          : field.options?.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                      </select>
                    ) : (
                      <input
                        id={inputId}
                        type={field.type || "text"}
                        dir={
                          ["email", "tel", "number", "date", "month", "password"].includes(
                            field.type || "",
                          ) ||
                          [
                            "employee_id",
                            "personnel_code",
                            "sku",
                            "serial_number",
                            "username",
                          ].includes(field.key)
                            ? "ltr"
                            : undefined
                        }
                        value={String(values[field.key] ?? "")}
                        min={field.min}
                        max={
                          field.type === "date" && ["issue_date", "paid_date"].includes(field.key)
                            ? todayISO()
                            : undefined
                        }
                        step={field.step}
                        required={field.required}
                        disabled={disabled}
                        minLength={field.type === "password" ? 10 : undefined}
                        maxLength={field.type === "text" || !field.type ? 255 : undefined}
                        onChange={(event) => set(field.key, event.target.value)}
                        autoComplete={field.type === "password" ? "new-password" : "off"}
                        aria-describedby={field.hint ? `${inputId}-hint` : undefined}
                      />
                    )}
                  </>
                )}
                {field.hint && <small id={`${inputId}-hint`}>{field.hint}</small>}
                {field.reference && !loading && !availableOptions(field).length && (
                  <small className="warning-text">
                    گزینه واجد شرایطی موجود نیست. ابتدا اطلاعات بخش مربوط را ثبت کنید.
                  </small>
                )}
              </div>
            );
          })}
        </div>
        {resource.key === "movements" && isSerialized && (
          <div className="info-box">
            این کالا سریال‌دار است. برای ورود، همه سریال‌ها را وارد کنید؛ برای خروج از بخش تحویل و
            بازگشت استفاده کنید.
          </div>
        )}
        {confirmingStatus && (
          <div className="info-box" role="alert">
            وضعیت این مورد از «{labels[String(row?.status)] || String(row?.status)}» به «
            {labels[String(values.status)] || String(values.status)}» تغییر خواهد کرد. برای ثبت
            نهایی، دکمه تأیید تغییر وضعیت را بزنید.
          </div>
        )}
        {resource.key === "quotations" && (
          <section className="line-editor">
            <div className="section-heading">
              <h3>ردیف‌های پیشنهاد</h3>
              <button
                className="button secondary small"
                type="button"
                disabled={busy || loading || lines.length >= 100}
                onClick={() =>
                  setLines([
                    ...lines,
                    { offering_id: "", description: "", quantity: 1, unit_price: 0 },
                  ])
                }
              >
                <Plus size={16} />
                افزودن ردیف
              </button>
            </div>
            {lines.map((line, index) => (
              <fieldset key={index} className="quote-line" disabled={busy || loading}>
                <legend>ردیف {number(index + 1)}</legend>
                <label>
                  انتخاب خدمت
                  <select
                    value={line.offering_id}
                    onChange={(event) => {
                      const offering = references["/offerings"]?.find(
                        (item) => item.id === event.target.value,
                      );
                      setLines(
                        lines.map((item, i) =>
                          i === index
                            ? {
                                ...item,
                                offering_id: event.target.value,
                                description: String(offering?.name || item.description),
                                unit_price: Number(offering?.unit_price ?? item.unit_price),
                              }
                            : item,
                        ),
                      );
                    }}
                  >
                    <option value="">شرح آزاد</option>
                    {references["/offerings"]
                      ?.filter((item) => item.is_active || item.id === line.offering_id)
                      .map((item) => (
                        <option value={item.id} key={item.id}>
                          {String(item.name)}
                          {!item.is_active
                            ? " (غیرفعال؛ برای تغییر ردیف خدمت دیگری انتخاب کنید)"
                            : ""}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  شرح خدمت
                  <input
                    required
                    value={line.description}
                    maxLength={500}
                    onChange={(event) =>
                      setLines(
                        lines.map((item, i) =>
                          i === index ? { ...item, description: event.target.value } : item,
                        ),
                      )
                    }
                  />
                </label>
                <div className="line-amounts">
                  <label>
                    تعداد
                    <input
                      type="number"
                      required
                      min="1"
                      step="1"
                      value={line.quantity}
                      onChange={(event) =>
                        setLines(
                          lines.map((item, i) =>
                            i === index ? { ...item, quantity: Number(event.target.value) } : item,
                          ),
                        )
                      }
                    />
                  </label>
                  <label>
                    قیمت واحد (تومان)
                    <input
                      type="number"
                      required
                      min="1"
                      step="1"
                      value={line.unit_price}
                      onChange={(event) =>
                        setLines(
                          lines.map((item, i) =>
                            i === index
                              ? { ...item, unit_price: Number(event.target.value) }
                              : item,
                          ),
                        )
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="icon-button danger-text"
                    disabled={lines.length === 1}
                    aria-label={`حذف ردیف ${index + 1}`}
                    onClick={() => setLines(lines.filter((_, i) => i !== index))}
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </fieldset>
            ))}
            <p className="quote-total">
              جمع پیشنهاد{" "}
              <strong>
                {number(lines.reduce((sum, line) => sum + line.quantity * line.unit_price, 0))}{" "}
                تومان
              </strong>
            </p>
          </section>
        )}
        {error && <ErrorBox message={error} />}
      </div>
      <footer className="drawer-footer">
        <button
          className="button primary"
          type="submit"
          disabled={busy || loading || !!referenceError}
        >
          <Save size={18} />
          {busy
            ? "در حال ذخیره…"
            : confirmingStatus
              ? "تأیید تغییر وضعیت و ذخیره"
              : row
                ? "ذخیره تغییرات"
                : `ثبت ${resource.singular}`}
        </button>
        <button className="button secondary" type="button" disabled={busy} onClick={onCancel}>
          انصراف
        </button>
      </footer>
    </form>
  );
}
