import type { Field, Resource, Row, User } from "./types";

export type Values = Record<string, string | number | boolean>;
export type QuotationLine = {
  offering_id: string;
  description: string;
  quantity: number;
  unit_price: number;
};

/** Backend ownership rules also shape the fields offered by the interface. */
export function editableFields(resource: Resource, user: User, row?: Row): Field[] {
  return resource.fields.filter((field) => {
    if (row && field.createOnly) return false;
    if (
      row &&
      resource.key === "employment-contracts" &&
      ["employee_id", "start_date", "base_salary"].includes(field.key)
    )
      return false;
    if (row && resource.key === "payrolls" && !["bonus", "deduction"].includes(field.key))
      return false;
    if (
      row &&
      resource.key === "contracts" &&
      row.status !== "draft" &&
      ["customer_id", "amount", "start_date", "end_date"].includes(field.key)
    )
      return false;
    if (
      row &&
      resource.key === "contracts" &&
      row.quotation_id &&
      ["customer_id", "amount"].includes(field.key)
    )
      return false;
    if (row && resource.key === "assets" && row.status !== "available" && field.key === "status")
      return false;
    if (
      user.role === "staff" &&
      (field.key === "employee_id" || (resource.key === "missions" && field.key === "allowance"))
    )
      return false;
    if (
      !row &&
      ((resource.key === "users" && field.key === "is_active") ||
        (resource.key === "assets" && field.key === "status"))
    )
      return false;
    return true;
  });
}

export function initialValues(fields: Field[], row?: Row): Values {
  return Object.fromEntries(
    fields.map((field) => [
      field.key,
      row?.[field.key] ??
        field.default ??
        (field.type === "checkbox"
          ? false
          : field.type === "number"
            ? 0
            : field.type === "select" && field.required && field.options?.length
              ? field.options[0].value
              : ""),
    ]),
  ) as Values;
}

export function referenceOptions(
  field: Field,
  entries: Row[],
  resource: Resource,
  values: Values,
  row?: Row,
): Row[] {
  return entries.filter((item) => {
    // Preserve a current inactive relation while editing unrelated information.
    if (row && item.id === row[field.key]) return true;
    if (field.key === "employee_id") return item.status === "active";
    if (field.key === "customer_id") return item.status === "active";
    if (field.key === "asset_id") return item.status === "available";
    if (resource.key === "assignments" && field.key === "item_id")
      return item.tracking_type === "quantity" && Number(item.quantity_available) > 0;
    if (resource.key === "assets" && field.key === "item_id")
      return item.tracking_type === "serialized";
    if (field.key === "quotation_id")
      return (
        item.status === "accepted" &&
        (!values.customer_id || item.customer_id === values.customer_id)
      );
    if (field.key === "contract_id")
      return (
        ["active", "completed"].includes(String(item.status)) &&
        Number(item.remaining_amount ?? 1) > 0
      );
    if (field.key === "invoice_id")
      return ["unpaid", "partial"].includes(String(item.status)) && Number(item.balance) > 0;
    return true;
  });
}

function normalized(field: Field, value: Values[string] | null | undefined): unknown {
  if (field.type === "number") {
    if (value === "" || value === null || value === undefined) return 0;
    const amount = Number(value);
    if (!Number.isSafeInteger(amount))
      throw new Error(`${field.label}: عدد صحیح در محدوده مجاز وارد کنید.`);
    if (field.min !== undefined && amount < field.min)
      throw new Error(`${field.label}: مقدار کمتر از حداقل مجاز است.`);
    return amount;
  }
  if (
    (value === "" || value === null || value === undefined) &&
    (field.key.endsWith("_id") || field.type === "date")
  )
    return null;
  if (field.type === "checkbox") return Boolean(value);
  // Passwords deliberately keep leading/trailing whitespace.
  return field.type === "password" ? String(value ?? "") : String(value ?? "").trim();
}

export function preparePayload(
  resource: Resource,
  fields: Field[],
  values: Values,
  user: User,
  row?: Row,
  lines: QuotationLine[] = [],
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.key === "serial_numbers") {
      const serials = String(values[field.key] || "")
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean);
      if (serials.length) payload.serial_numbers = serials;
      continue;
    }
    payload[field.key] = normalized(field, values[field.key]);
    if (field.required && (payload[field.key] === "" || payload[field.key] === null))
      throw new Error(`${field.label}: این فیلد الزامی است.`);
  }
  if (resource.key === "contracts" && payload.employee_name === "") payload.employee_name = null;
  if (resource.staffCreate && user.role === "staff") {
    if (!user.employee_id)
      throw new Error(
        "حساب شما به پرونده پرسنلی متصل نشده است. از مدیر سامانه بخواهید شناسه کارمند را تنظیم کند.",
      );
    payload.employee_id = user.employee_id;
  }
  if (resource.key === "missions" && user.role === "staff") payload.allowance = 0;
  if (resource.key === "assignments" && payload.asset_id) payload.quantity = 1;
  if (resource.key === "quotations") {
    if (!lines.length || lines.length > 100)
      throw new Error("پیشنهاد باید بین یک تا صد ردیف داشته باشد.");
    payload.lines = lines.map((line) => {
      if (
        !line.description.trim() ||
        !Number.isSafeInteger(line.quantity) ||
        line.quantity < 1 ||
        !Number.isSafeInteger(line.unit_price) ||
        line.unit_price < 1 ||
        !Number.isSafeInteger(line.quantity * line.unit_price)
      )
        throw new Error("شرح، تعداد و قیمت صحیح و مثبت برای همه ردیف‌های پیشنهاد وارد کنید.");
      return {
        offering_id: line.offering_id || null,
        description: line.description.trim(),
        quantity: line.quantity,
        unit_price: line.unit_price,
      };
    });
  }
  if (row) {
    for (const field of fields) {
      const previous =
        resource.key === "contracts" && field.key === "employee_name" && !row.employee_name
          ? null
          : normalized(field, row[field.key] as Values[string] | null | undefined);
      if (field.key in payload && JSON.stringify(payload[field.key]) === JSON.stringify(previous))
        delete payload[field.key];
    }
    if (resource.key === "quotations" && Array.isArray(row.lines)) {
      const original = (row.lines as Record<string, unknown>[]).map((line) => ({
        offering_id: line.offering_id || null,
        description: line.description,
        quantity: line.quantity,
        unit_price: line.unit_price,
      }));
      if (JSON.stringify(original) === JSON.stringify(payload.lines)) delete payload.lines;
    }
    if (!Object.keys(payload).length) throw new Error("تغییری در اطلاعات ایجاد نشده است.");
  }
  return payload;
}
