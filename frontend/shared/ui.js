import { el, safeHref } from "/assets/shared/dom.js";

export function loadingState(label = "جارٍ التحميل…") {
  return el("div", { className: "state loading-state", role: "status", "aria-live": "polite" }, label);
}

export function emptyState(title = "لا توجد بيانات", description = "لا توجد عناصر متاحة حاليًا.") {
  return el("section", { className: "state empty-state" }, el("h2", {}, title), el("p", {}, description));
}

export function errorState(title = "تعذر تحميل الواجهة", description = "حاول مرة أخرى لاحقًا.") {
  return el("section", { className: "state error-state", role: "alert" }, el("h2", {}, title), el("p", {}, description));
}

export function toastRegion(root) {
  const region = el("div", { className: "toast-region", "aria-live": "polite", "aria-atomic": "true" });
  root.append(region);
  return region;
}

export function toast(region, message, { timeout = 4500 } = {}) {
  const item = el("div", { className: "toast" }, message);
  region.append(item);
  window.setTimeout(() => item.remove(), timeout);
}

export function statusBadge(state) {
  const labels = {
    ACTIVE: "نشط",
    ARCHIVED: "مؤرشف",
    SUSPENDED: "معلّق",
    READY: "جاهز",
    CREATED: "تم الإنشاء",
    RUNNING: "قيد التشغيل",
    COMPLETED: "مكتمل",
    FAILED: "فشل",
    PENDING: "قيد الانتظار",
    REVOKED: "ملغى",
    ACCEPTED: "مقبول",
    EXPIRED: "منتهي",
    REGISTERED: "مسجّل",
    CONFIGURED: "مهيأ",
    DEGRADED: "متدهور",
    INVALID: "غير صالح",
    PREPARING: "قيد التجهيز",
    DISABLED: "معطّل",
    REMOVING: "قيد الإزالة",
    REMOVED: "مزال",
    STORED: "الملف الأصلي محفوظ",
    AWAITING_UPLOAD: "بانتظار رفع الملف الأصلي",
    LEGACY_UNAVAILABLE: "الملف الأصلي غير متوفر — مصدر تاريخي",
    UNAVAILABLE: "الملف الأصلي غير متوفر",
  };
  const normalized = String(state || "").toUpperCase();
  if (!Object.hasOwn(labels, normalized)) throw new Error("Unsupported backend status");
  return el("span", {
    className: `status-badge status-${normalized.toLowerCase()}`,
    dataset: { status: normalized },
    title: normalized,
  }, labels[normalized]);
}

export function drawer(title, content) {
  const previous = document.activeElement;
  const close = el("button", { className: "button secondary", type: "button", "aria-label": "إغلاق" }, "إغلاق");
  const panel = el("aside", { className: "drawer", role: "dialog", "aria-modal": "true", "aria-label": title },
    el("div", { className: "drawer-head" }, el("h2", {}, title), close),
    el("div", { className: "drawer-content" }, content));
  const dismiss = () => {
    panel.remove();
    document.removeEventListener("keydown", onKeyDown);
    if (previous instanceof HTMLElement) previous.focus();
  };
  const onKeyDown = (event) => { if (event.key === "Escape") dismiss(); };
  close.addEventListener("click", dismiss);
  document.addEventListener("keydown", onKeyDown);
  document.body.append(panel);
  close.focus();
  return { panel, close: dismiss };
}

export function link(href, label, className = "nav-link") {
  return el("a", { href: safeHref(href), className }, label);
}
