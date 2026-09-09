import { createRouter } from "/assets/shared/router.js?v=stage4-auth-footer-2";
import { createShell } from "/assets/shared/shell.js?v=stage4-auth-footer-2";
import { toastRegion } from "/assets/shared/ui.js?v=stage4-auth-footer-2";
import { getJSON } from "/assets/shared/api.js?v=stage4-auth-footer-2";
import { registerShell } from "/assets/shared/session.js?v=stage4-auth-footer-2";

export function startSurface(surface, routes) {
  document.documentElement.dataset.surface = surface;
  delete window.__controlPlaneIdentity;
  const shell = createShell(surface, routes);
  registerShell(shell);
  toastRegion(shell.root);
  getJSON("/api/me").then((identity) => {
    window.__controlPlaneIdentity = identity;
    shell.setIdentity(identity);
  }).catch(() => shell.setIdentity(null));
  const router = createRouter({
    surface,
    routes,
    render: (state) => shell.render(state),
  });
  router.start();
  return router;
}
