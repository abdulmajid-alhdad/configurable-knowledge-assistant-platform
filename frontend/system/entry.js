import { SYSTEM_ROUTES } from "/assets/system/routes.js?v=stage4-provider-resolution-1";
import { getJSON } from "/assets/shared/api.js?v=stage4-provider-resolution-1";
import { startSurface } from "/assets/shared/surface.js?v=stage4-provider-resolution-1";

export async function start() {
  try {
    window.__controlPlanePermissions = await getJSON("/api/system/me/permissions");
  } catch {
    window.__controlPlanePermissions = [];
  }
  if (!Array.isArray(window.__controlPlanePermissions) || !window.__controlPlanePermissions.length) {
    window.location.replace("/app");
    return null;
  }
  return startSurface("system", SYSTEM_ROUTES);
}
