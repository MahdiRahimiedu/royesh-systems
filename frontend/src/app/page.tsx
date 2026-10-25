import { App } from "@/components/App";
import type { System } from "@/lib/types";

export const dynamic = "force-dynamic";
export default function Page() {
  const configured = process.env.ROYESH_SYSTEM || process.env.NEXT_PUBLIC_SYSTEM || "personnel";
  const system: System =
    configured === "inventory" || configured === "commerce" ? configured : "personnel";
  return (
    <App
      system={system}
      apiUrl={process.env.API_URL || process.env.API_BASE || process.env.NEXT_PUBLIC_API_URL}
    />
  );
}
