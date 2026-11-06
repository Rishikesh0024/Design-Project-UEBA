import type { User } from "../api/client";

const bypassSetting = import.meta.env.VITE_DEV_AUTH_BYPASS;
const bypassEnabled = bypassSetting === "true";

if (
  (import.meta.env.PROD || import.meta.env.MODE === "production")
  && bypassSetting === "true"
) {
  throw new Error("VITE_DEV_AUTH_BYPASS cannot be enabled in a production build.");
}

export const DEV_AUTH_BYPASS = Boolean(import.meta.env.DEV && bypassEnabled);

/**
 * Transient development user used strictly when DEV_AUTH_BYPASS is active.
 * This is a frontend-only representation to populate UI profile widgets.
 * No hardcoded database administrator accounts or database credentials are created.
 */
export const DEV_BYPASS_USER: User = {
  id: 0,
  email: "analyst.dev@ueba.local",
  full_name: "Development Analyst",
  role: "analyst",
};
