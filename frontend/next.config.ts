import type { NextConfig } from "next";

const config: NextConfig = {
  distDir:
    process.env.ROYESH_DEV === "true"
      ? `.next-${process.env.ROYESH_SYSTEM || "personnel"}`
      : ".next",
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  agentRules: false,
};
export default config;
