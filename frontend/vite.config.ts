import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const bypass = process.env.VITE_DEV_AUTH_BYPASS ?? env.VITE_DEV_AUTH_BYPASS;
  if (
    (command === "build" || mode === "production")
    && ["true", "1", "yes"].includes(String(bypass ?? "").trim().toLowerCase())
  ) {
    throw new Error("DEV_AUTH_BYPASS is development-only and cannot be enabled for production.");
  }
  return {
    plugins: [react()],
    envPrefix: "VITE_",
  };
});
