import { ApiError, request } from "/assets/shared/api.js";
import { el } from "/assets/shared/dom.js";
import { errorState, loadingState } from "/assets/shared/ui.js";

const ROLE_LABELS = {
  WORKSPACE_MANAGER: "مدير مساحة العمل",
  MEMBER: "عضو",
};

function formatDate(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
    dateStyle: "long",
    timeStyle: "short",
  }).format(date);
}

function field(label, value) {
  return el(
    "div",
    { className: "activation-field" },
    el("dt", {}, label),
    el("dd", {}, value || "—"),
  );
}

function activationError(error) {
  const code = error instanceof ApiError ? error.code : "REQUEST_FAILED";
  const messages = {
    INVITATION_INVALID: ["رابط التفعيل غير صالح", "تحقق من رابط التفعيل الكامل أو تواصل مع مسؤول النظام."],
    INVITATION_NOT_ACTIVATABLE: ["الدعوة غير قابلة للتفعيل", "هذه دعوة تاريخية لا ترتبط بحساب جرى تجهيزه مسبقًا."],
    INVITATION_EXPIRED: ["انتهت صلاحية الدعوة", "اطلب من مسؤول النظام إنشاء دعوة تفعيل جديدة."],
    INVITATION_REVOKED: ["أُلغيت الدعوة", "تواصل مع مسؤول النظام إذا كنت ما تزال تحتاج إلى الوصول."],
    INVITATION_ALREADY_ACCEPTED: ["استُخدم رابط التفعيل", "تم استهلاك هذا الرابط من قبل ولا يمكن استخدامه مرة أخرى."],
    MEMBERSHIP_ALREADY_EXISTS: ["العضوية موجودة مسبقًا", "لن ينشئ التفعيل عضوية مكررة."],
    PROVISIONED_IDENTITY_MISSING: ["تعذر العثور على الحساب المجهّز", "تواصل مع مسؤول النظام لمراجعة الدعوة."],
    IDENTITY_ADMIN_NOT_CONFIGURED: ["خدمة التفعيل غير متاحة", "لم تُفعّل خدمة إدارة الهوية في بيئة التشغيل."],
    IDENTITY_PROVIDER_FAILURE: ["تعذر إكمال التفعيل", "تعذر الاتصال بخدمة الهوية. حاول مرة أخرى لاحقًا."],
  };
  const message = messages[code] || ["تعذر إكمال التفعيل", "حاول مرة أخرى لاحقًا أو تواصل مع مسؤول النظام."];
  return errorState(message[0], message[1]);
}

function tokenFromFragment() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("token");
  window.history.replaceState(null, "", "/app/invitations/accept");
  return token;
}

export function start() {
  document.documentElement.dataset.surface = "activation";
  document.title = "تفعيل الحساب";
  const root = document.querySelector("#frontend-root");
  const content = el("section", { className: "activation-card" }, loadingState("جاري التحقق من دعوة التفعيل…"));
  root.replaceChildren(
    el(
      "main",
      { className: "activation-shell" },
      el("div", { className: "activation-brand" }, "منصة المعرفة"),
      content,
    ),
  );
  let token = tokenFromFragment();
  if (!token) {
    content.replaceChildren(activationError(new ApiError(404, "INVITATION_INVALID")));
    return;
  }

  request("/api/auth/invitations/activation/preview", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token }),
  }).then((invitation) => {
    const activate = el("button", { className: "button", type: "button" }, "تفعيل الحساب");
    const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
    activate.addEventListener("click", async () => {
      activate.disabled = true;
      feedback.replaceChildren();
      try {
        const result = await request("/api/auth/invitations/activation", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ token }),
        });
        token = null;
        await request("/api/auth/sign-out", { method: "POST" });
        window.location.replace(result.login_path || "/login");
        return;
        content.replaceChildren(
          el("div", { className: "activation-success", role: "status" },
            el("h1", {}, "تم تفعيل الحساب"),
            el("p", {}, result.message),
            el("a", { className: "button", href: "/login" }, "الانتقال إلى تسجيل الدخول"),
          ),
        );
      } catch (error) {
        activate.disabled = false;
        feedback.replaceChildren(activationError(error));
      }
    });
    content.replaceChildren(
      el("header", { className: "activation-heading" },
        el("p", { className: "eyebrow" }, "دعوة تفعيل"),
        el("h1", {}, "تفعيل حسابك"),
        el("p", {}, "راجع بيانات الوصول ثم فعّل الحساب. لن يؤدي التفعيل إلى تسجيل دخولك."),
      ),
      el("dl", { className: "activation-details" },
        field("مساحة العمل", invitation.workspace_name),
        field("اسم المستخدم", invitation.username),
        field("البريد الإلكتروني", invitation.email),
        field("الدور", ROLE_LABELS[invitation.role_name] || invitation.role_name),
        invitation.team_name ? field("الفريق", invitation.team_name) : null,
        field("تنتهي الدعوة", formatDate(invitation.expires_at)),
      ),
      feedback,
      el("div", { className: "form-actions" }, activate),
    );
    activate.focus();
  }).catch((error) => {
    token = null;
    content.replaceChildren(activationError(error));
  });
}
