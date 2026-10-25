export type System = "personnel" | "inventory" | "commerce";
export type Row = Record<string, unknown> & { id: string };
export type User = {
  id: string;
  username: string;
  full_name: string;
  role: "admin" | "manager" | "staff";
  employee_id?: string | null;
};
export type PageResult = { items: Row[]; total: number; page: number; page_size: number };
export type Option = { value: string; label: string };
export type Field = {
  key: string;
  label: string;
  type?:
    | "text"
    | "email"
    | "tel"
    | "number"
    | "date"
    | "month"
    | "textarea"
    | "select"
    | "checkbox"
    | "password";
  required?: boolean;
  options?: Option[];
  reference?: string;
  display?: string;
  hint?: string;
  default?: string | number | boolean;
  min?: number;
  step?: number;
  createOnly?: boolean;
};
export type Column = {
  key: string;
  label: string;
  format?: "money" | "date" | "datetime" | "status" | "number" | "boolean";
  options?: Option[];
};
export type Resource = {
  key: string;
  title: string;
  singular: string;
  description: string;
  endpoint: string;
  fields: Field[];
  columns: Column[];
  readOnly?: boolean;
  noEdit?: boolean;
  staffCreate?: boolean;
  adminOnly?: boolean;
  managerOnly?: boolean;
  statuses?: Option[];
  filterParam?: string;
};
export type Dashboard = {
  metrics: { label: string; value: number | string; unit?: string }[];
  recent: { title: string; subtitle: string; status: string; date: string }[];
  notices: { title: string; detail: string }[];
};
