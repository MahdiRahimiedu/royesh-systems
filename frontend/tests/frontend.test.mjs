import assert from "node:assert/strict";
import { test } from "node:test";
import { editableFields, initialValues, preparePayload, referenceOptions } from "../src/lib/forms.ts";
import { resources, userResource, systemResources } from "../src/lib/resources.ts";
import { actionsFor } from "../src/lib/workflows.ts";
import { csv, date, cell } from "../src/lib/format.ts";
import { allRows, configureApi, request, ApiError } from "../src/lib/api.ts";
import { session } from "../src/lib/session.ts";

const admin = { id: "admin", username: "admin", full_name: "مدیر", role: "admin" };
const staff = { ...admin, role: "staff", employee_id: "employee-one" };
const find = (system, key) => resources[system].find(resource => resource.key === key);

test("all twenty-one business resources have unique routes and named fields", () => {
  for (const system of ["personnel", "inventory", "commerce"]) {
    const list = systemResources(system);
    assert.equal(list.length, 9);
    assert.equal(new Set(list.map(resource => resource.key)).size, list.length);
    assert.ok(list.every(resource => resource.endpoint.startsWith("/") && resource.columns.length));
    assert.ok(list.every(resource => resource.fields.every(field => field.key && field.label)));
  }
});
test("staff requests never accept another employee or a self-authored allowance", () => {
  const resource = find("personnel", "missions");
  const fields = editableFields(resource, staff);
  assert.ok(!fields.some(field => ["employee_id", "allowance"].includes(field.key)));
  const payload = preparePayload(resource, fields, { title: "جلسه", destination: "دفتر", start_date: "2026-10-23", end_date: "2026-10-24", reason: "جلسه پروژه", employee_id: "another", allowance: 9000 }, staff);
  assert.equal(payload.employee_id, "employee-one");
  assert.equal(payload.allowance, 0);
  assert.throws(() => preparePayload(resource, fields, { title: "جلسه", destination: "دفتر", start_date: "2026-10-23", end_date: "2026-10-24", reason: "جلسه" }, { ...staff, employee_id: null }), /پرونده/);
});
test("draft payroll permits editing additions and deductions only", () => {
  const resource = find("personnel", "payrolls");
  const row = { id: "p", status: "draft", bonus: 0, deduction: 0, employee_id: "e", period: "2026-10" };
  const fields = editableFields(resource, admin, row);
  assert.deepEqual(fields.map(field => field.key), ["bonus", "deduction"]);
  assert.deepEqual(preparePayload(resource, fields, { bonus: "1500", deduction: "0" }, admin, row), { bonus: 1500 });
});
test("unchanged numbers and nullable relations are excluded from PATCH", () => {
  const resource = find("commerce", "contracts");
  const row = { id: "c", status: "draft", customer_id: "cust", quotation_id: null, title: "قرارداد", employee_id: null, employee_name: null, start_date: "2026-10-23", end_date: null, amount: 2000, notes: "" };
  const fields = editableFields(resource, admin, row);
  const values = initialValues(fields, row);
  assert.throws(() => preparePayload(resource, fields, { ...values, amount: "2000" }, admin, row), /تغییری/);
  assert.deepEqual(preparePayload(resource, fields, { ...values, notes: "توضیح جدید" }, admin, row), { notes: "توضیح جدید" });
});
test("active contracts cannot submit financial fields", () => {
  const fields = editableFields(find("commerce", "contracts"), admin, { id: "c", status: "active" });
  assert.ok(!fields.some(field => ["customer_id", "amount", "start_date", "end_date"].includes(field.key)));
});
test("quote edit preserves unchanged lines and removes database-only line fields", () => {
  const resource = find("commerce", "quotations");
  const row = { id: "q", customer_id: "cust", title: "پیشنهاد", valid_until: "2026-12-01", notes: "", status: "draft", lines: [{ id: "line", quotation_id: "q", offering_id: null, description: "توسعه", quantity: 2, unit_price: 1000, total: 2000 }] };
  const fields = editableFields(resource, admin, row);
  const values = initialValues(fields, row);
  const lines = [{ offering_id: "", description: "توسعه", quantity: 2, unit_price: 1000 }];
  assert.deepEqual(preparePayload(resource, fields, { ...values, notes: "اصلاح" }, admin, row, lines), { notes: "اصلاح" });
  const payload = preparePayload(resource, fields, values, admin, row, [{ ...lines[0], quantity: 3 }]);
  assert.deepEqual(Object.keys(payload), ["lines"]);
  assert.deepEqual(Object.keys(payload.lines[0]), ["offering_id", "description", "quantity", "unit_price"]);
});
test("unsafe or fractional monetary input cannot turn into corrupted JSON", () => {
  const resource = find("commerce", "offerings");
  const fields = editableFields(resource, admin);
  for (const invalid of ["NaN", "Infinity", "1.5", "9007199254740992"]) assert.throws(() => preparePayload(resource, fields, { name: "خدمت", description: "", unit_price: invalid, unit: "project", is_active: true }, admin), /صحیح/);
});
test("password whitespace is preserved while ordinary text is trimmed", () => {
  const fields = editableFields(userResource, admin);
  const payload = preparePayload(userResource, fields, { username: " new-user ", full_name: " کاربر جدید ", password: "  pass123456  ", role: "staff", employee_id: "" }, admin);
  assert.equal(payload.password, "  pass123456  ");
  assert.equal(payload.username, "new-user");
  assert.equal(payload.employee_id, null);
});
test("new references exclude inactive records while edits retain current relation", () => {
  const resource = find("commerce", "quotations"); const field = resource.fields[0];
  const entries = [{ id: "active", status: "active" }, { id: "inactive", status: "inactive" }];
  assert.deepEqual(referenceOptions(field, entries, resource, {}).map(item => item.id), ["active"]);
  assert.deepEqual(referenceOptions(field, entries, resource, {}, { id: "q", customer_id: "inactive" }).map(item => item.id), ["active", "inactive"]);
});
test("invoice and stock selectors exclude unusable balances", () => {
  const resource = find("commerce", "payments"); const field = resource.fields[0];
  assert.deepEqual(referenceOptions(field, [{ id: "paid", status: "paid", balance: 0 }, { id: "open", status: "partial", balance: 50 }], resource, {}).map(item => item.id), ["open"]);
  const inventory = find("inventory", "assignments"); const item = inventory.fields.find(field => field.key === "item_id");
  assert.deepEqual(referenceOptions(item, [{ id: "empty", tracking_type: "quantity", quantity_available: 0 }, { id: "serial", tracking_type: "serialized", quantity_available: 2 }, { id: "usable", tracking_type: "quantity", quantity_available: 3 }], inventory, {}).map(item => item.id), ["usable"]);
});
test("workflow transitions do not offer repeat payment/return or edits to terminal states", () => {
  assert.deepEqual(actionsFor("payrolls", { id: "p", status: "paid" }), []);
  assert.deepEqual(actionsFor("assignments", { id: "a", status: "returned" }), []);
  assert.deepEqual(actionsFor("contracts", { id: "c", status: "completed" }), []);
  assert.deepEqual(actionsFor("quotations", { id: "q", status: "accepted" }), []);
  assert.equal(actionsFor("missions", { id: "m", status: "pending" })[0].allowance, true);
  assert.equal(actionsFor("missions", { id: "m", status: "pending" })[1].allowance, undefined);
});
test("CSV protects formula-like names even after whitespace and escapes quotes", () => {
  const result = csv([{ id: "1", name: '  =HYPERLINK("bad")' }], [{ key: "name", label: "نام" }]);
  assert.ok(result.startsWith("\uFEFF"));
  assert.ok(result.includes("'  =HYPERLINK"));
  assert.ok(result.includes('""bad""'));
  assert.equal(cell({ id: "1", serial_numbers: ["ABC", "DEF"] }, { key: "serial_numbers", label: "سریال" }), "ABC، DEF");
});
test("date-only values keep the calendar day across time zones", () => {
  const previous = process.env.TZ;
  try { process.env.TZ = "America/Los_Angeles"; const west = date("2026-10-23"); process.env.TZ = "Asia/Tehran"; assert.equal(date("2026-10-23"), west); }
  finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});
test("CSV collection preserves filters for every page and never silently truncates", async () => {
  const original = globalThis.fetch; const urls = [];
  configureApi("commerce", "https://api.example.com/api/v1");
  try {
    globalThis.fetch = async input => { urls.push(String(input)); const page = Number(new URL(input).searchParams.get("page")); return Response.json({ items: Array.from({ length: page === 1 ? 100 : 1 }, (_, index) => ({ id: `${page}-${index}` })), total: 101 }); };
    const rows = await allRows("commerce", "token", "/invoices", { query: { q: "مشتری", status: "unpaid" } });
    assert.equal(rows.length, 101); assert.equal(urls.length, 2);
    assert.ok(urls.every(url => new URL(url).searchParams.get("q") === "مشتری" && new URL(url).searchParams.get("status") === "unpaid"));
    await assert.rejects(allRows("commerce", "token", "/invoices", { pageLimit: 1 }), /سقف/);
  } finally { globalThis.fetch = original; }
});
test("API401 identifies its originating token and system", async () => {
  const originalFetch = globalThis.fetch; const originalWindow = globalThis.window; const events = [];
  try {
    globalThis.window = { dispatchEvent: event => events.push(event), location: { hostname: "localhost", protocol: "http:" } };
    globalThis.fetch = async () => Response.json({ detail: "نشست منقضی" }, { status: 401 });
    await assert.rejects(request("commerce", "old-token", "/auth/me"), ApiError);
    assert.deepEqual(events[0].detail, { system: "commerce", token: "old-token" });
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow; }
});
test("denied sessionStorage does not prevent in-tab authentication", () => {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage");
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, get() { throw new Error("blocked"); } });
  try { assert.equal(session.read("test"), null); assert.doesNotThrow(() => session.write("test", "token")); assert.doesNotThrow(() => session.remove("test")); }
  finally { if (previous) Object.defineProperty(globalThis, "sessionStorage", previous); else delete globalThis.sessionStorage; }
});
