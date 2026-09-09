import { el } from "/assets/shared/dom.js?v=stage4-auth-footer-2";
import { errorState } from "/assets/shared/ui.js?v=stage4-auth-footer-2";
import { logoutCurrentBrowser } from "/assets/shared/session.js?v=stage4-auth-footer-2";

export function createShell(surface, routes) {
  const root = document.querySelector("#frontend-root");
  root.replaceChildren();
  const nav = el("nav", { className: "primary-nav", "aria-label": surface === "system" ? "إدارة النظام" : "مساحة العمل" });
  routes.forEach((route) => nav.append(el("a", {
    href: route.path,
    className: "nav-link",
    dataset: { route: route.path, scope: route.scope || "", permission: route.requiredPermission || "" },
  }, route.label)));
  const footerWorkspaceValue = surface === "system"
    ? null
    : el("strong", { className: "sidebar-footer-value" }, "جارٍ تحديد النطاق…");
  const footerContext = surface === "system"
    ? el("strong", { className: "sidebar-footer-context" }, "إدارة النظام")
    : el("div", { className: "sidebar-footer-context sidebar-footer-line" },
      el("span", { className: "sidebar-footer-label" }, "مساحة العمل:"),
      footerWorkspaceValue);
  const footerIdentityValue = el("span", { className: "sidebar-footer-value" }, "هوية غير متاحة");
  const footerIdentity = el("div", { className: "sidebar-footer-identity sidebar-footer-line" },
    el("span", { className: "sidebar-footer-label" }, "المستخدم:"),
    footerIdentityValue);
  const footerError = el("span", { className: "sidebar-footer-error", role: "alert", hidden: "true" });
  const logout = el("button", { className: "sidebar-footer-logout", type: "button" }, "تسجيل الخروج");
  const footer = el("div", { className: "sidebar-footer" }, footerContext, footerIdentity, logout, footerError);
  let logoutPending = false;
  logout.addEventListener("click", async () => {
    if (logoutPending) return;
    logoutPending = true;
    logout.disabled = true;
    footerError.hidden = true;
    try {
      await logoutCurrentBrowser();
    } catch {
      logoutPending = false;
      logout.disabled = false;
      footerError.textContent = "تعذر تسجيل الخروج. حاول مرة أخرى.";
      footerError.hidden = false;
    }
  });
  const shell = el("div", { className: `control-shell ${surface}-shell`, dir: "rtl" },
    el("aside", { className: "sidebar" },
      el("a", { href: `/${surface}`, className: "brand" }, "منصة المعرفة"),
      nav,
      footer),
    el("main", { className: "shell-main" },
      el("header", { className: "topbar" },
        el("div", { className: "topbar-copy" }, el("p", { className: "eyebrow" }, "لوحة التحكم"), el("h1", { id: "route-title" }, "الرئيسية")),
        el("span", { className: "workspace-context" }, surface === "system" ? "نطاق النظام" : "مساحة العمل الحالية")),
      el("section", { className: "route-host", id: "route-host", tabindex: "-1" })),
  );
  root.append(shell);
  return {
    root,
    host: shell.querySelector("#route-host"),
    title: shell.querySelector("#route-title"),
    setIdentity(identity) {
      footerIdentityValue.textContent = identity?.display_name || identity?.username || identity?.name || "هوية غير متاحة";
    },
    setWorkspaceName(name) {
      if (footerWorkspaceValue) footerWorkspaceValue.textContent = name || "تعذر تحديد النطاق";
    },
    render({ route, path }) {
      const permissions = window.__controlPlanePermissions;
      shell.querySelectorAll(".nav-link").forEach((item) => {
        item.hidden = Array.isArray(permissions) && item.dataset.permission && !permissions.includes(item.dataset.permission);
        item.classList.toggle("active", item.dataset.route === (route?.path || path));
      });
      this.title.textContent = route?.label || "المسار غير متاح";
      const unavailable = Array.isArray(permissions) && route?.requiredPermission && !permissions.includes(route.requiredPermission);
      this.host.replaceChildren(unavailable
        ? errorState("الوصول غير متاح", "لا تتوفر صلاحية هذا النطاق للحساب الحالي.")
        : (route?.render?.() || errorState("المسار غير متاح", "هذا المسار الهيكلي غير مسجل بعد.")));
      this.host.focus({ preventScroll: true });
    },
  };
}
