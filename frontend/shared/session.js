import { clearInflight, request } from "/assets/shared/api.js";
import { workspaceCache } from "/assets/shared/cache.js";

let logoutTask = null;
let activeShell = null;

export function registerShell(shell) {
  activeShell = shell;
}

export function setCurrentWorkspaceName(name) {
  activeShell?.setWorkspaceName(name);
}

export function clearClientSessionState() {
  workspaceCache.clear();
  clearInflight();
  ["selected_workspace_id", "last_selected_workspace_id"].forEach((key) => {
    window.localStorage.removeItem(key);
  });
  delete window.__controlPlanePermissions;
  delete window.__controlPlaneIdentity;
  activeShell = null;
}

export function logoutCurrentBrowser() {
  if (logoutTask) return logoutTask;
  logoutTask = request("/api/auth/sign-out", { method: "POST" })
    .then(() => {
      clearClientSessionState();
      window.location.replace("/login");
    })
    .finally(() => {
      logoutTask = null;
    });
  return logoutTask;
}
