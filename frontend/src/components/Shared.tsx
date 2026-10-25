import { AlertCircle, Inbox, RefreshCw, CheckCircle2 } from "lucide-react";
import { labels } from "@/lib/format";

export function Status({ value, label }: { value: unknown; label?: string }) {
  const status = String(value || "");
  return (
    <span className={`status status-${status}`}>{label || labels[status] || status || "—"}</span>
  );
}
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>درخواست انجام نشد</strong>
        <p>{message}</p>
        {retry && (
          <button type="button" className="text-button" onClick={retry}>
            <RefreshCw size={15} /> تلاش دوباره
          </button>
        )}
      </div>
    </div>
  );
}
export function Success({ message }: { message: string }) {
  return (
    <div className="success-box" role="status">
      <CheckCircle2 size={18} />
      {message}
    </div>
  );
}
export function Empty({
  title = "هنوز موردی ثبت نشده است",
  detail = "برای شروع، اولین مورد را از دکمه ثبت جدید اضافه کنید.",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="empty-state">
      <Inbox size={32} strokeWidth={1.4} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
export function Loading({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton-table" aria-label="در حال دریافت اطلاعات" role="status">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
