import test from "node:test";
import assert from "node:assert/strict";

const pagePaths = {
  Dashboard: "/dashboard",
  "Dataset Upload": "/dataset-upload",
  "Activity Explorer": "/activity-explorer",
  "Behaviour Profiles": "/behaviour-profiles",
  "Anomaly Detection": "/anomaly-detection",
  Alerts: "/alerts",
  Evaluation: "/evaluation",
};

const routePaths = new Map([
  ...Object.entries(pagePaths).map(([page, path]) => [path, { kind: "page", page }]),
  ["/login", { kind: "login" }],
  ["/register", { kind: "register" }],
]);

function routeForPath(path) {
  const clean = path.replace(/\/+$/, "") || "/";
  if (clean === "/") return null;
  return routePaths.get(clean) ?? null;
}

function defaultRoute(isBypass) {
  return isBypass ? { kind: "page", page: "Dashboard" } : { kind: "login" };
}

test("1. Opening / with bypass defaults directly to Dashboard", () => {
  const route = routeForPath("/") ?? defaultRoute(true);
  assert.deepEqual(route, { kind: "page", page: "Dashboard" });
});

test("2. Navigating to /login (e.g. via Logout) resolves to login screen", () => {
  const route = routeForPath("/login");
  assert.deepEqual(route, { kind: "login" });
});

test("3. Navigating to /register resolves to register screen", () => {
  const route = routeForPath("/register");
  assert.deepEqual(route, { kind: "register" });
});

test("4. All seven primary dashboard routes resolve cleanly", () => {
  const expectedPages = [
    ["/dashboard", "Dashboard"],
    ["/dataset-upload", "Dataset Upload"],
    ["/activity-explorer", "Activity Explorer"],
    ["/behaviour-profiles", "Behaviour Profiles"],
    ["/anomaly-detection", "Anomaly Detection"],
    ["/alerts", "Alerts"],
    ["/evaluation", "Evaluation"],
  ];

  for (const [path, expectedPage] of expectedPages) {
    const route = routeForPath(path);
    assert.deepEqual(route, { kind: "page", page: expectedPage });
  }
});
