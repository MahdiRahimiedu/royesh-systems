// Same readable UI source, three separate applications and API sessions.
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ports = { personnel: 3001, inventory: 3002, commerce: 3003 };
const system = process.argv[2] || "personnel";
const mode = process.argv[3] || "dev";
if (!(system in ports)) throw new Error(`Unknown system: ${system}`);
const production = mode === "start";
const executable = fileURLToPath(
  new URL(
    production ? "../.next/standalone/server.js" : "../node_modules/next/dist/bin/next",
    import.meta.url,
  ),
);
const child = spawn(
  process.execPath,
  production
    ? [executable]
    : [
        executable,
        mode,
        "--port",
        process.env.PORT || String(ports[system]),
        "--hostname",
        process.env.HOST || "127.0.0.1",
      ],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      ROYESH_SYSTEM: system,
      NEXT_PUBLIC_SYSTEM: system,
      ROYESH_DEV: mode === "dev" ? "true" : "false",
      HOSTNAME: process.env.HOST || "127.0.0.1",
      PORT: process.env.PORT || String(ports[system]),
    },
  },
);
child.on("exit", (code) => process.exit(code || 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
