import { APP_ROUTES } from "/assets/app/routes.js?v=stage4-auth-footer-2";
import { startSurface } from "/assets/shared/surface.js?v=stage4-auth-footer-2";

export function start() {
  startSurface("app", APP_ROUTES);
}
