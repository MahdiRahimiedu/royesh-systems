import type { Column, Row } from "./types";

export const labels: Record<string, string> = {
  active: "فعال",
  inactive: "غیرفعال",
  terminated: "قطع همکاری",
  full_time: "تمام‌وقت",
  part_time: "پاره‌وقت",
  contract: "قراردادی",
  pending: "در انتظار بررسی",
  approved: "تأیید شده",
  rejected: "رد شده",
  received: "دریافت شده",
  cancelled: "لغو شده",
  draft: "پیش‌نویس",
  paid: "پرداخت شده",
  partial: "پرداخت بخشی",
  unpaid: "پرداخت نشده",
  void: "باطل شده",
  ended: "پایان‌یافته",
  sent: "ارسال شده",
  accepted: "پذیرفته شده",
  completed: "تکمیل شده",
  available: "آماده تحویل",
  assigned: "تحویل شده",
  retired: "اسقاط شده",
  returned: "بازگشت داده شده",
  quantity: "تعدادی",
  serialized: "دارای سریال",
  in: "ورود",
  out: "خروج",
  reward: "تشویق",
  penalty: "جریمه",
  annual: "استحقاقی",
  sick: "استعلاجی",
  unpaid_leave: "بدون حقوق",
  bank: "حواله بانکی",
  cash: "نقدی",
  cheque: "چک",
  project: "پروژه",
  month: "ماه",
  hour: "ساعت",
  admin: "مدیر سامانه",
  manager: "مدیر واحد",
  staff: "کارمند",
  create: "ثبت",
  update: "ویرایش",
  login: "ورود",
  logout: "خروج",
  approve: "تأیید",
  receive: "دریافت",
  cancel: "لغو",
  return: "بازگشت",
  pay: "پرداخت",
  change_password: "تغییر گذرواژه",
  employee: "کارکنان",
  employees: "کارکنان",
  department: "واحد سازمانی",
  employment_contract: "قرارداد استخدام",
  leave: "مرخصی",
  leaves: "مرخصی",
  mission: "مأموریت",
  missions: "مأموریت",
  adjustment: "تشویق و جریمه",
  payroll: "حقوق",
  item: "کالا",
  supplier: "تأمین‌کننده",
  purchase: "خرید",
  movement: "گردش انبار",
  asset: "دارایی",
  assignment: "تحویل تجهیزات",
  customer: "مشتری",
  offering: "خدمت",
  quotation: "پیشنهاد قیمت",
  invoice: "صورتحساب",
  payment: "دریافت وجه",
  user: "کاربر",
  assign: "تحویل",
  retire: "اسقاط",
  status: "تغییر وضعیت",
  hr_leaves: "مرخصی",
  hr_missions: "مأموریت",
  hr_payrolls: "حقوق",
  hr_employees: "کارکنان",
  hr_adjustments: "تشویق و جریمه",
  hr_employment_contracts: "قرارداد استخدام",
  hr_departments: "واحد سازمانی",
};
export const number = (value: unknown): string =>
  new Intl.NumberFormat("fa-IR").format(Number(value || 0));
export function date(value: unknown): string {
  if (!value) return "—";
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("fa-IR", {
        dateStyle: "medium",
        ...(/^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? { timeZone: "UTC" } : {}),
      }).format(parsed);
}
export function dateTime(value: unknown): string {
  if (!value) return "—";
  const input = String(value);
  const parsed = new Date(
    /T/.test(input) && !/(Z|[+-]\d{2}:\d{2})$/.test(input) ? input + "Z" : input,
  );
  return Number.isNaN(parsed.getTime())
    ? input
    : new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}
export function todayISO(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export function cell(row: Row, column: Column): string {
  const value = row[column.key];
  const option = column.options?.find((entry) => entry.value === String(value));
  if (option) return option.label;
  if (value === null || value === undefined || value === "") return "—";
  if (column.format === "money") return `${number(value)} تومان`;
  if (column.format === "number") return number(value);
  if (column.format === "date") return date(value);
  if (column.format === "datetime") return dateTime(value);
  if (column.format === "boolean") return value ? "بله" : "خیر";
  if (column.format === "status") return labels[String(value)] || String(value);
  if (
    Array.isArray(value) &&
    value.every((entry) => typeof entry === "string" || typeof entry === "number")
  )
    return value.join("، ");
  return typeof value === "object" ? "—" : String(value);
}
export function csv(rows: Row[], columns: Column[]): string {
  // Spreadsheet formula injection is neutralized even for user-authored names.
  const escape = (value: string) =>
    `"${(/^\s*[=+@\-\t\r]/.test(value) ? "'" + value : value).replaceAll('"', '""')}"`;
  return (
    "\uFEFF" +
    [
      columns.map((c) => escape(c.label)).join(","),
      ...rows.map((row) => columns.map((c) => escape(cell(row, c))).join(",")),
    ].join("\r\n")
  );
}
export function downloadCsv(content: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8;" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
