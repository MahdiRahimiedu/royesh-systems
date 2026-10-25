import type { PageResult, Row, System } from "./types";

export const apiPorts = { personnel: 8001, inventory: 8002, commerce: 8003 };
export const uiPorts = { personnel: 3001, inventory: 3002, commerce: 3003 };
const runtimeOrigins = new Map<System, string>();
export function configureApi(system: System, origin?: string): void {
  if (origin) runtimeOrigins.set(system, origin.replace(/\/$/, ""));
}
export function apiBase(system: System): string {
  if (runtimeOrigins.has(system)) return runtimeOrigins.get(system)!;
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  const hostname = typeof window === "undefined" ? "localhost" : window.location.hostname;
  const protocol = typeof window === "undefined" ? "http:" : window.location.protocol;
  return `${protocol}//${hostname}:${apiPorts[system]}/api/v1`;
}
export class ApiError extends Error {
  public status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

// Keep validation messages useful to the Persian user, without exposing raw JSON.
type ValidationIssue = {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
  ctx?: Record<string, unknown>;
};
const fieldLabels: Record<string, string> = {
  username: "نام کاربری",
  password: "گذرواژه",
  full_name: "نام کامل",
  role: "نقش",
  employee_id: "شناسه کارمند",
  employee_name: "نام کارمند",
  personnel_code: "کد پرسنلی",
  first_name: "نام",
  last_name: "نام خانوادگی",
  email: "ایمیل",
  phone: "تلفن",
  department_id: "واحد سازمانی",
  job_title: "عنوان شغلی",
  employment_type: "نوع همکاری",
  hire_date: "تاریخ استخدام",
  status: "وضعیت",
  base_salary: "حقوق پایه",
  name: "نام",
  description: "توضیحات",
  title: "عنوان",
  start_date: "تاریخ شروع",
  end_date: "تاریخ پایان",
  notes: "توضیحات",
  type: "نوع",
  kind: "نوع ثبت",
  reason: "دلیل",
  destination: "مقصد",
  allowance: "فوق‌العاده مأموریت",
  amount: "مبلغ",
  date: "تاریخ",
  period: "دوره حقوق",
  bonus: "مزایا",
  deduction: "کسورات",
  sku: "کد کالا",
  category: "دسته‌بندی",
  unit: "واحد",
  tracking_type: "روش نگهداری",
  min_stock: "حداقل موجودی",
  contact_name: "نام رابط",
  address: "نشانی",
  supplier_id: "تأمین‌کننده",
  item_id: "کالا",
  quantity: "تعداد",
  unit_price: "قیمت واحد",
  serial_number: "شماره سریال",
  serial_numbers: "شماره سریال‌ها",
  reference: "شماره مرجع",
  asset_id: "دارایی",
  company_name: "نام شرکت",
  customer_id: "مشتری",
  valid_until: "اعتبار پیشنهاد",
  lines: "ردیف‌های پیشنهاد",
  offering_id: "خدمت",
  quotation_id: "پیشنهاد قیمت",
  contract_id: "قرارداد",
  issue_date: "تاریخ صدور",
  due_date: "سررسید",
  invoice_id: "صورتحساب",
  paid_date: "تاریخ دریافت",
  method: "روش پرداخت",
  current_password: "گذرواژه فعلی",
  new_password: "گذرواژه جدید",
  comment: "توضیح تصمیم",
};
function validationMessage(issue: ValidationIssue): string {
  const field =
    issue.loc
      ?.slice(1)
      .map((part) => (typeof part === "number" ? `ردیف ${part + 1}` : fieldLabels[part] || "ورودی"))
      .join(" / ") || "ورودی";
  const messages: Record<string, string> = {
    missing: "این فیلد الزامی است.",
    string_too_short: `حداقل ${issue.ctx?.min_length} نویسه وارد کنید.`,
    string_too_long: `حداکثر ${issue.ctx?.max_length} نویسه مجاز است.`,
    int_type: "یک عدد صحیح وارد کنید.",
    int_parsing: "یک عدد صحیح وارد کنید.",
    greater_than: `عدد باید بیشتر از ${issue.ctx?.gt} باشد.`,
    greater_than_equal: `عدد باید حداقل ${issue.ctx?.ge} باشد.`,
    less_than_equal: `عدد باید حداکثر ${issue.ctx?.le} باشد.`,
    uuid_parsing: "شناسه UUID معتبر وارد کنید.",
    literal_error: "یکی از گزینه‌های مجاز را انتخاب کنید.",
    date_parsing: "تاریخ معتبر با قالب سال-ماه-روز وارد کنید.",
    date_from_datetime_parsing: "تاریخ معتبر با قالب سال-ماه-روز وارد کنید.",
    string_pattern_mismatch: "قالب مقدار واردشده معتبر نیست.",
    extra_forbidden: "فرم با نسخه سرور سازگار نیست. صفحه را تازه‌سازی کنید.",
    bool_type: "مقدار بله یا خیر معتبر وارد کنید.",
  };
  return `${field}: ${messages[issue.type || ""] || issue.msg?.replace(/^Value error, /, "") || "مقدار واردشده معتبر نیست."}`;
}
export async function request<T>(
  system: System,
  token: string,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  try {
    response = await fetch(`${apiBase(system)}${path}`, {
      ...options,
      headers,
      cache: "no-store",
      signal: options.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(20000)])
        : AbortSignal.timeout(20000),
    });
  } catch {
    if (options.signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
    throw new ApiError(
      options.method && options.method !== "GET"
        ? "پاسخ سرور دریافت نشد. پیش از ثبت دوباره، فهرست سوابق را بررسی کنید؛ ممکن است عملیات در سرور ثبت شده باشد."
        : "ارتباط با سرور برقرار نشد. اجرای سرور و اتصال شبکه را بررسی کنید و دوباره تلاش کنید.",
      0,
    );
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && token && typeof window !== "undefined")
      window.dispatchEvent(
        new CustomEvent("royesh-session-expired", { detail: { system, token } }),
      );
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map(validationMessage).join("؛ ")
          : "انجام درخواست ممکن نشد. دوباره تلاش کنید.";
    throw new ApiError(message, response.status);
  }
  return body as T;
}
export async function allRows(
  system: System,
  token: string,
  endpoint: string,
  options: { query?: Record<string, string>; signal?: AbortSignal; pageLimit?: number } = {},
): Promise<Row[]> {
  const items: Row[] = [];
  const pageLimit = options.pageLimit ?? 1000;
  for (let page = 1; page <= pageLimit; page++) {
    const params = new URLSearchParams({ ...options.query, page: String(page), page_size: "100" });
    const result = await request<PageResult>(system, token, `${endpoint}?${params}`, {
      signal: options.signal,
    });
    if (result.total > pageLimit * 100)
      throw new ApiError(
        "تعداد ردیف‌ها بیش از سقف دریافت است. جست‌وجو یا فیلتر را محدود کنید.",
        400,
      );
    items.push(...result.items);
    if (items.length >= result.total || !result.items.length) return items;
  }
  throw new ApiError("تعداد ردیف‌ها بیش از حد مجاز دریافت است. دامنهٔ گزارش را محدود کنید.", 400);
}
