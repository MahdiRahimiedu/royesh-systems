import type { Row } from "./types";

export type WorkflowAction = {
  title: string;
  suffix: string;
  body?: Record<string, unknown>;
  danger?: boolean;
  detail: string;
  field?: "comment" | "serial_numbers";
  allowance?: boolean;
};
export function actionsFor(resource: string, row: Row): WorkflowAction[] {
  const state = String(row.status || "");
  if (["leaves", "missions"].includes(resource) && state === "pending")
    return [
      {
        title: "تأیید درخواست",
        suffix: "decision",
        body: { status: "approved" },
        detail: "این درخواست پس از ثبت تصمیم، تأیید می‌شود.",
        field: "comment",
        allowance: resource === "missions",
      },
      {
        title: "رد درخواست",
        suffix: "decision",
        body: { status: "rejected" },
        danger: true,
        detail: "رد درخواست در سوابق کارمند ثبت خواهد شد.",
        field: "comment",
      },
    ];
  if (resource === "payrolls" && state === "draft")
    return [
      {
        title: "ثبت پرداخت حقوق",
        suffix: "pay",
        detail:
          "با ثبت پرداخت، فیش حقوقی نهایی می‌شود. این عملیات پرداخت بانکی انجام نمی‌دهد و صرفاً ثبت سابقه است.",
      },
    ];
  if (resource === "purchases")
    return [
      ...(state === "pending"
        ? [
            {
              title: "تأیید خرید",
              suffix: "approve",
              detail: "درخواست خرید برای دریافت کالا در انبار آماده می‌شود.",
            },
          ]
        : []),
      ...(state === "approved"
        ? [
            {
              title: "دریافت در انبار",
              suffix: "receive",
              detail:
                "دریافت کالا موجودی انبار را افزایش می‌دهد. برای تجهیزات سریال‌دار، یک سریال در هر خط و به تعداد سفارش وارد کنید.",
              field: "serial_numbers" as const,
            },
          ]
        : []),
      ...(["pending", "approved"].includes(state)
        ? [
            {
              title: "لغو خرید",
              suffix: "cancel",
              danger: true,
              detail: "درخواست خرید لغو می‌شود و قابل دریافت نخواهد بود.",
            },
          ]
        : []),
    ];
  if (resource === "assignments" && state !== "returned" && !row.returned_at && !row.is_returned)
    return [
      {
        title: "ثبت بازگشت",
        suffix: "return",
        detail: "با تأیید بازگشت، کالا یا تجهیز دوباره به موجودی قابل تحویل اضافه می‌شود.",
      },
    ];
  if (resource === "quotations") {
    const targets =
      state === "draft"
        ? [{ status: "sent", title: "ثبت ارسال به مشتری" }]
        : state === "sent"
          ? [
              { status: "accepted", title: "ثبت پذیرش مشتری" },
              { status: "rejected", title: "ثبت رد پیشنهاد" },
            ]
          : [];
    return targets.map((target) => ({
      title: target.title,
      suffix: "status",
      body: { status: target.status },
      danger: target.status === "rejected",
      detail: "وضعیت پیشنهاد قیمت بر اساس نتیجه واقعی مذاکره تغییر می‌کند.",
    }));
  }
  if (resource === "contracts") {
    const targets =
      state === "draft"
        ? [
            { status: "active", title: "فعال‌کردن قرارداد" },
            { status: "cancelled", title: "لغو قرارداد" },
          ]
        : state === "active"
          ? [
              { status: "completed", title: "تکمیل قرارداد" },
              { status: "cancelled", title: "لغو قرارداد" },
            ]
          : [];
    return targets.map((target) => ({
      title: target.title,
      suffix: "status",
      body: { status: target.status },
      danger: target.status === "cancelled",
      detail:
        "تغییر وضعیت قرارداد در سوابق سامانه ثبت می‌شود. وجود تعهدات مالی ممکن است مانع لغو شود.",
    }));
  }
  if (resource === "invoices" && state === "unpaid" && !Number(row.paid_amount))
    return [
      {
        title: "ابطال صورتحساب",
        suffix: "void",
        danger: true,
        detail: "صورتحساب از مطالبات فعال حذف و سابقه آن با وضعیت باطل‌شده حفظ می‌شود.",
      },
    ];
  return [];
}
