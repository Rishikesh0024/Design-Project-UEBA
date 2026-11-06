import { useCallback, useEffect, useState } from "react";
import type { PageName } from "../components/Layout";

export type RoutePath =
  | "/dashboard"
  | "/dataset-upload"
  | "/activity-explorer"
  | "/behaviour-profiles"
  | "/anomaly-detection"
  | "/alerts"
  | "/evaluation"
  | "/login"
  | "/register";

export const ROUTE_TO_PAGE: Record<string, PageName> = {
  "/dashboard": "Dashboard",
  "/dataset-upload": "Dataset Upload",
  "/activity-explorer": "Activity Explorer",
  "/behaviour-profiles": "Behaviour Profiles",
  "/anomaly-detection": "Anomaly Detection",
  "/alerts": "Alerts",
  "/evaluation": "Evaluation",
};

export const PAGE_TO_ROUTE: Record<PageName, RoutePath> = {
  "Dashboard": "/dashboard",
  "Dataset Upload": "/dataset-upload",
  "Activity Explorer": "/activity-explorer",
  "Behaviour Profiles": "/behaviour-profiles",
  "Anomaly Detection": "/anomaly-detection",
  "Alerts": "/alerts",
  "Evaluation": "/evaluation",
};

export function normalizePath(pathname: string): RoutePath | null {
  const clean = pathname.replace(/\/+$/, "") || "/";
  if (clean === "/login") return "/login";
  if (clean === "/register") return "/register";
  if (clean === "/dashboard") return "/dashboard";
  if (clean === "/dataset-upload") return "/dataset-upload";
  if (clean === "/activity-explorer") return "/activity-explorer";
  if (clean === "/behaviour-profiles") return "/behaviour-profiles";
  if (clean === "/anomaly-detection") return "/anomaly-detection";
  if (clean === "/alerts") return "/alerts";
  if (clean === "/evaluation") return "/evaluation";
  return null;
}

export function useRouter() {
  const [currentPath, setCurrentPath] = useState<string>(() => window.location.pathname);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentPath(window.location.pathname);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const navigate = useCallback((to: string, replace = false) => {
    if (to === window.location.pathname) {
      setCurrentPath(to);
      return;
    }
    if (replace) {
      window.history.replaceState(null, "", to);
    } else {
      window.history.pushState(null, "", to);
    }
    setCurrentPath(to);
  }, []);

  return { currentPath, navigate };
}

