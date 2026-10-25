// Next's standalone server needs its static files beside server.js.
import { spawn } from "node:child_process";
import { cp, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const next = fileURLToPath(new URL("../node_modules/next/dist/bin/next", import.meta.url));
const code = await new Promise((resolve) => {
  const child = spawn(process.execPath, [next, "build"], {
    stdio: "inherit",
    env: { ...process.env, ROYESH_DEV: "false", NEXT_TELEMETRY_DISABLED: "1" },
  });
  child.on("exit", resolve);
  child.on("error", () => resolve(1));
});
if (code !== 0) process.exit(Number(code) || 1);
await cp(
  new URL("../.next/static", import.meta.url),
  new URL("../.next/standalone/.next/static", import.meta.url),
  { recursive: true },
);
const publicDirectory = new URL("../public", import.meta.url);
try {
  await access(publicDirectory);
  await cp(publicDirectory, new URL("../.next/standalone/public", import.meta.url), {
    recursive: true,
  });
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
