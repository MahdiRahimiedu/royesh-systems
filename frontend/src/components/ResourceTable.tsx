"use client";
import { useEffect, useState } from "react";
import {
  Plus,
  Search,
  Download,
  ChevronRight,
  ChevronLeft,
  ArrowUpLeft,
  Pencil,
  Copy,
  FileText,
  RefreshCw,
} from "lucide-react";
import { ApiError, allRows, request } from "@/lib/api";
import { cell, csv, downloadCsv, labels, number, date } from "@/lib/format";
import { actionsFor, type WorkflowAction } from "@/lib/workflows";
import type { Column, PageResult, Resource, Row, System, User } from "@/lib/types";
import { Drawer } from "./Drawer";
import { ResourceForm } from "./ResourceForm";
import { WorkflowForm } from "./WorkflowForm";
import { Empty, ErrorBox, Loading, Status, Success } from "./Shared";

type Panel =
  | { type: "create" }
  | { type: "edit" | "detail"; row: Row }
  | { type: "workflow"; row: Row; action: WorkflowAction };
function normalizeRow(row: Row, resource: Resource): Row {
  if (resource.key === "assignments" && !row.status)
    return { ...row, status: row.returned_at || row.is_returned ? "returned" : "assigned" };
  return row;
}
export function ResourceTable({
  system,
  token,
  user,
  resource,
  onExpired,
  onAccountChanged,
}: {
  system: System;
  token: string;
  user: User;
  resource: Resource;
  onExpired: () => void;
  onAccountChanged?: () => void;
}) {
  const [data, setData] = useState<PageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [exportError, setExportError] = useState("");
  const [success, setSuccess] = useState("");
  const [revision, setRevision] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [panelBusy, setPanelBusy] = useState(false);
  const canWrite =
    !resource.readOnly &&
    (user.role !== "staff" || !!resource.staffCreate) &&
    (!resource.adminOnly || user.role === "admin");
  const canManage = user.role !== "staff";
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(query);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const parameters = new URLSearchParams({ page: String(page), page_size: "15", q: debounced });
    if (status) parameters.set(resource.filterParam || "status", status);
    request<PageResult>(system, token, `${resource.endpoint}?${parameters}`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (alive) {
          setData({ ...result, items: result.items.map((row) => normalizeRow(row, resource)) });
          const lastPage = Math.max(1, Math.ceil(result.total / 15));
          if (page > lastPage) setPage(lastPage);
        }
      })
      .catch((reason) => {
        if (!alive) return;
        if (reason instanceof ApiError && reason.status === 401) onExpired();
        else setError(reason.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [system, token, resource, page, debounced, status, revision, onExpired]);
  function saved() {
    setPanel(null);
    setPanelBusy(false);
    setRevision((value) => value + 1);
    setSuccess("اطلاعات با موفقیت در سامانه ثبت شد.");
    if (resource.key === "users") onAccountChanged?.();
  }
  async function exportData() {
    setExporting(true);
    setExportError("");
    try {
      const filter: Record<string, string> = { q: debounced };
      if (status) filter[resource.filterParam || "status"] = status;
      const rows = (await allRows(system, token, resource.endpoint, { query: filter })).map((row) =>
        normalizeRow(row, resource),
      );
      downloadCsv(
        csv(
          rows,
          resource.columns.map((column) => ({
            ...column,
            options: column.options || (column.key === "status" ? resource.statuses : undefined),
          })),
        ),
        `royesh-${resource.key}-${new Date().toISOString().slice(0, 10)}.csv`,
      );
      setSuccess(`خروجی ${number(rows.length)} ردیف دریافت شد.`);
    } catch (reason) {
      setExportError((reason as Error).message);
    } finally {
      setExporting(false);
    }
  }
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / 15));
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{resource.title}</h1>
          <p>{resource.description}</p>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            onClick={exportData}
            disabled={exporting || loading || query !== debounced || !!error || !data?.total}
          >
            <Download size={18} />
            {exporting ? "آماده‌سازی…" : "خروجی CSV"}
          </button>
          {canWrite && (
            <button
              className="button primary"
              onClick={() => {
                setSuccess("");
                setPanel({ type: "create" });
              }}
            >
              <Plus size={19} />
              ثبت {resource.singular}
            </button>
          )}
        </div>
      </div>
      {success && <Success message={success} />}
      {exportError && <ErrorBox message={exportError} retry={exportData} />}
      <section className="ledger" aria-label={resource.title}>
        <div className="table-toolbar">
          <div className="search-field">
            <Search size={19} />
            <input
              aria-label={`جست‌وجو در ${resource.title}`}
              maxLength={100}
              placeholder={`جست‌وجو در ${resource.title}…`}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <div className="table-filters">
            {resource.statuses && (
              <select
                aria-label="فیلتر وضعیت"
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                  setPage(1);
                }}
              >
                <option value="">همه وضعیت‌ها</option>
                {resource.statuses.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            )}
            <button
              type="button"
              className="icon-button"
              title="تازه‌سازی اطلاعات"
              aria-label="تازه‌سازی اطلاعات"
              onClick={() => setRevision((value) => value + 1)}
              disabled={loading}
            >
              <RefreshCw size={18} />
            </button>
            <span className="record-count">
              {data ? `${number(data.total)} مورد` : "دریافت اطلاعات…"}
            </span>
          </div>
        </div>
        {loading ? (
          <Loading />
        ) : error ? (
          <div className="table-error">
            <ErrorBox message={error} retry={() => setRevision((value) => value + 1)} />
          </div>
        ) : !data?.items.length ? (
          <Empty
            title={query || status ? "موردی با این شرایط پیدا نشد" : "هنوز موردی ثبت نشده است"}
            detail={
              query || status
                ? "عبارت جست‌وجو یا وضعیت انتخاب‌شده را تغییر دهید."
                : canWrite
                  ? `اولین ${resource.singular} را با دکمه ثبت اضافه کنید.`
                  : "پس از ثبت اطلاعات توسط مدیر، موارد مجاز در این بخش نمایش داده می‌شوند."
            }
          />
        ) : (
          <div
            className="table-scroll"
            tabIndex={0}
            aria-label="جدول اطلاعات؛ برای مشاهده ستون‌های بیشتر پیمایش کنید"
          >
            <table>
              <thead>
                <tr>
                  {resource.columns.map((column) => (
                    <th scope="col" key={column.key}>
                      {column.label}
                    </th>
                  ))}
                  <th scope="col" className="action-cell">
                    عملیات
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row, index) => (
                  <tr key={row.id || index}>
                    {resource.columns.map((column, i) => (
                      <td
                        className={`${i === 0 ? "primary-cell" : ""} ${column.format === "money" || column.format === "number" ? "numeric" : ""}`}
                        key={column.key}
                      >
                        {column.format === "status" ? (
                          <Status
                            value={row[column.key]}
                            label={
                              (
                                column.options ||
                                (column.key === "status" ? resource.statuses : undefined)
                              )?.find((option) => option.value === String(row[column.key]))?.label
                            }
                          />
                        ) : (
                          cell(row, column)
                        )}
                      </td>
                    ))}
                    <td className="action-cell">
                      <button
                        className="row-link"
                        onClick={() => setPanel({ type: "detail", row })}
                      >
                        جزئیات
                        <ArrowUpLeft size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <footer className="table-footer">
          <span>
            {data?.total
              ? `نمایش ${number((page - 1) * 15 + 1)} تا ${number(Math.min(page * 15, data.total))} از ${number(data.total)} مورد`
              : "هیچ ردیفی برای نمایش وجود ندارد"}
          </span>
          <div className="pagination">
            <button
              className="icon-button"
              aria-label="صفحه قبل"
              disabled={page <= 1 || loading}
              onClick={() => setPage((value) => value - 1)}
            >
              <ChevronRight size={18} />
            </button>
            <span>
              صفحه {number(page)} از {number(totalPages)}
            </span>
            <button
              className="icon-button"
              aria-label="صفحه بعد"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((value) => value + 1)}
            >
              <ChevronLeft size={18} />
            </button>
          </div>
        </footer>
      </section>
      {resource.key === "payrolls" && (
        <p className="footnote">
          محاسبات این نسخه آموزشی است. پرداخت بانکی و محاسبات قانونی بیمه و مالیات در این سامانه
          انجام نمی‌شود.
        </p>
      )}
      {panel && (
        <Drawer
          title={
            panel.type === "create"
              ? `ثبت ${resource.singular}`
              : panel.type === "edit"
                ? `ویرایش ${resource.singular}`
                : panel.type === "workflow"
                  ? panel.action.title
                  : `جزئیات ${resource.singular}`
          }
          subtitle={resource.title}
          busy={panelBusy}
          onClose={() => setPanel(null)}
        >
          {panel.type === "create" || panel.type === "edit" ? (
            <ResourceForm
              system={system}
              token={token}
              user={user}
              resource={resource}
              row={panel.type === "edit" ? panel.row : undefined}
              onSaved={saved}
              onCancel={() => setPanel(null)}
              onBusyChange={setPanelBusy}
            />
          ) : panel.type === "workflow" ? (
            <WorkflowForm
              system={system}
              token={token}
              resource={resource}
              row={panel.row}
              action={panel.action}
              onSaved={saved}
              onCancel={() => setPanel(null)}
              onBusyChange={setPanelBusy}
            />
          ) : (
            <Detail
              system={system}
              token={token}
              resource={resource}
              row={panel.row}
              canEdit={
                canWrite &&
                canManage &&
                !resource.noEdit &&
                !(resource.key === "employment-contracts" && panel.row.status === "ended") &&
                !(
                  ["payrolls", "quotations"].includes(resource.key) && panel.row.status !== "draft"
                ) &&
                !(
                  resource.key === "contracts" &&
                  ["completed", "cancelled"].includes(String(panel.row.status))
                )
              }
              canManage={canManage}
              onEdit={() => setPanel({ type: "edit", row: panel.row })}
              onAction={(action) => setPanel({ type: "workflow", row: panel.row, action })}
            />
          )}
        </Drawer>
      )}
    </>
  );
}

function Detail({
  system,
  token,
  resource,
  row,
  canEdit,
  canManage,
  onEdit,
  onAction,
}: {
  system: System;
  token: string;
  resource: Resource;
  row: Row;
  canEdit: boolean;
  canManage: boolean;
  onEdit: () => void;
  onAction: (action: WorkflowAction) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [details, setDetails] = useState(row);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    if (resource.key === "quotations" && !row.lines)
      request<Row>(system, token, `${resource.endpoint}/${row.id}`, { signal: controller.signal })
        .then((result) => {
          if (alive) setDetails(result);
        })
        .catch((reason) => {
          if (alive) setError(reason.message);
        });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [system, token, row, resource]);
  const common: Record<string, string> = {
    id: "شناسه مرجع",
    created_at: "زمان ثبت",
    updated_at: "آخرین ویرایش",
    employee_id: "شناسه کارمند",
    customer_id: "شناسه مشتری",
    item_id: "شناسه کالا",
    supplier_id: "شناسه تأمین‌کننده",
    asset_id: "شناسه دارایی",
    contract_id: "شناسه قرارداد",
    invoice_id: "شناسه صورتحساب",
    quotation_id: "شناسه پیشنهاد",
    status: "وضعیت",
    approved_at: "زمان تأیید",
    received_at: "زمان دریافت",
    returned_at: "زمان بازگشت",
    paid_at: "زمان پرداخت",
    total: "جمع کل",
    paid_amount: "مبلغ دریافت‌شده",
    balance: "مانده",
    decision_comment: "توضیح تصمیم",
    comment: "توضیح تصمیم",
    full_name: "نام کامل",
    employee_name: "نام کارمند",
    serial_number: "شماره سریال",
    serial_numbers: "شماره سریال‌های گردش",
    quantity_total: "موجودی کل",
    quantity_available: "موجودی قابل تحویل",
    rewards: "تشویقی دوره",
    penalties: "جریمه دوره",
    mission_allowance: "فوق‌العاده مأموریت دوره",
    total_amount: "مبلغ کل خرید",
    invoiced_amount: "جمع صورتحساب‌های صادرشده",
    remaining_amount: "مبلغ قابل صدور صورتحساب",
    invoice_balance: "مانده صورتحساب",
    invoice_status: "وضعیت صورتحساب",
    entity_id: "شناسه رکورد",
    user_id: "شناسه کاربر",
  };
  const fieldLabels: Record<string, string> = {
    ...common,
    ...Object.fromEntries(resource.fields.map((field) => [field.key, field.label])),
    ...Object.fromEntries(resource.columns.map((column) => [column.key, column.label])),
  };
  const columns: Column[] = [...resource.columns];
  for (const key of Object.keys(details)) {
    if (!columns.some((column) => column.key === key) && fieldLabels[key] && key !== "id")
      columns.push({
        key,
        label: fieldLabels[key],
        format: /_at$/.test(key)
          ? "datetime"
          : /_date$/.test(key)
            ? "date"
            : ["status", "employment_type", "role", "tracking_type"].includes(key)
              ? "status"
              : [
                    "total",
                    "base_salary",
                    "amount",
                    "allowance",
                    "unit_price",
                    "paid_amount",
                    "balance",
                    "bonus",
                    "deduction",
                    "rewards",
                    "penalties",
                    "mission_allowance",
                    "total_amount",
                    "invoiced_amount",
                    "remaining_amount",
                    "invoice_balance",
                  ].includes(key)
                ? "money"
                : undefined,
      });
  }
  const workflow = canManage ? actionsFor(resource.key, row) : [];
  return (
    <>
      <div className="drawer-body">
        <div className="detail-heading">
          <FileText size={24} />
          <div>
            <h3>
              {String(
                details.full_name ||
                  details.title ||
                  details.name ||
                  details.employee_name ||
                  resource.singular,
              )}
            </h3>
            {!!details.status && (
              <Status
                value={details.status}
                label={resource.statuses?.find((option) => option.value === details.status)?.label}
              />
            )}
          </div>
        </div>
        <dl className="detail-list">
          {columns
            .filter((column) => details[column.key] !== null && details[column.key] !== undefined)
            .map((column) => (
              <div key={column.key}>
                <dt>{column.label}</dt>
                <dd>
                  {column.format === "status" ? (
                    <Status
                      value={details[column.key]}
                      label={
                        (
                          column.options ||
                          (column.key === "status" ? resource.statuses : undefined)
                        )?.find((option) => option.value === String(details[column.key]))?.label
                      }
                    />
                  ) : (
                    cell(details, column)
                  )}
                </dd>
              </div>
            ))}
        </dl>
        {Array.isArray(details.lines) && (
          <section className="detail-lines">
            <h3>ردیف‌های پیشنهاد</h3>
            {(details.lines as Record<string, unknown>[]).map((line, i) => (
              <div className="detail-line" key={i}>
                <strong>{String(line.description)}</strong>
                <span>
                  {number(line.quantity)} × {number(line.unit_price)} تومان
                </span>
                <b>{number(Number(line.quantity) * Number(line.unit_price))} تومان</b>
              </div>
            ))}
          </section>
        )}
        <div className="reference-copy">
          <span>شناسه مرجع برای استفاده در API و ارتباط سامانه‌ها</span>
          <div>
            <code>{row.id}</code>
            <button
              className="icon-button"
              aria-label="کپی شناسه"
              title="کپی شناسه"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(row.id);
                  setCopied(true);
                } catch {
                  setError("امکان کپی خودکار نیست. شناسه را انتخاب و کپی کنید.");
                }
              }}
            >
              <Copy size={17} />
            </button>
          </div>
          {copied && <small role="status">شناسه کپی شد.</small>}
        </div>
        {error && <ErrorBox message={error} />}
      </div>
      {(canEdit || workflow.length > 0) && (
        <footer className="drawer-footer workflow-footer">
          {canEdit && (
            <button className="button secondary" onClick={onEdit}>
              <Pencil size={17} />
              ویرایش اطلاعات
            </button>
          )}
          {workflow.map((action) => (
            <button
              key={action.title}
              className={`button ${action.danger ? "danger-outline" : "primary"}`}
              onClick={() => onAction(action)}
            >
              {action.title}
            </button>
          ))}
        </footer>
      )}
    </>
  );
}
