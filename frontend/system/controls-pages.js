import { ApiError, getJSON, request } from "/assets/shared/api.js";
import { workspaceCache, workspaceKey } from "/assets/shared/cache.js";
import { appendContent, el } from "/assets/shared/dom.js";
import {
  drawer,
  emptyState,
  errorState,
  loadingState,
  statusBadge,
  toast,
} from "/assets/shared/ui.js";

const SYSTEM_SCOPE = "SYSTEM";
const POLICY_KEYS = new Set([
  "knowledge_source_addition_enabled",
  "knowledge_processing_enabled",
]);

const POLICY_LABELS = {
  knowledge_source_addition_enabled: {
    label: "إضافة مصادر المعرفة",
    description: "يسمح بتسجيل مصادر معرفة جديدة ضمن مساحة العمل.",
  },
  knowledge_processing_enabled: {
    label: "معالجة مصادر المعرفة",
    description: "يسمح بمعالجة المصادر وإعادة معالجتها.",
  },
};

const ROLE_LABELS = { SYSTEM_ADMIN: "مدير النظام" };

function permissions() {
  return new Set(window.__controlPlanePermissions || []);
}

function can(permission) {
  return permissions().has(permission);
}

function pageHeader(title, description, ...actions) {
  return el(
    "header",
    { className: "page-toolbar" },
    el("div", { className: "page-heading" }, el("h2", {}, title), el("p", { className: "page-intro" }, description)),
    actions.length ? el("div", { className: "toolbar-actions" }, actions) : null,
  );
}

function panel(title, ...children) {
  return el("section", { className: "panel" }, title ? el("h2", { className: "panel-title" }, title) : null, ...children);
}

function action(label, handler, className = "button") {
  return el("button", { type: "button", className, onclick: handler }, label);
}

function field(label, control, hint = null) {
  return el("label", { className: "field" }, el("span", { className: "field-label" }, label), control, hint ? el("span", { className: "field-hint" }, hint) : null);
}

function primary(primaryValue, secondary = null) {
  return el("div", { className: "primary-cell" }, el("strong", {}, primaryValue || "—"), secondary ? el("span", { className: "secondary-meta" }, secondary) : null);
}

function technical(value) {
  return value === null || value === undefined ? null : el("span", { className: "technical-code", dir: "ltr" }, String(value));
}

function info(label, value, technicalValue = false) {
  return el("div", { className: "info-field" }, el("dt", {}, label), el("dd", { className: technicalValue ? "technical-value" : "" }, value ?? "—"));
}

function table(headers, rows) {
  return el(
    "div",
    { className: "table-wrap" },
    el(
      "table",
      { className: "data-table" },
      el("thead", {}, el("tr", {}, ...headers.map((header) => el("th", {}, header)))),
      el("tbody", {}, ...rows.map((row) => el("tr", {}, ...row.map((cell) => el("td", {}, cell))))),
    ),
  );
}

function formatDate(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("ar-SA-u-ca-gregory", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function notify(message) {
  const region = document.querySelector(".toast-region");
  if (region) toast(region, message);
}

function apiError(error, fallback = "تعذر تحميل البيانات") {
  if (error instanceof ApiError && error.status === 401) return errorState("انتهت الجلسة", "سجّل الدخول مرة أخرى للمتابعة.");
  if (error instanceof ApiError && error.status === 403) return errorState("الوصول غير متاح", "لا تتوفر صلاحية النظام اللازمة لهذه الواجهة.");
  if (error instanceof ApiError && error.status === 404) return errorState("العنصر غير موجود", "لم يعد المورد المطلوب متاحًا.");
  if (error instanceof ApiError && error.status === 409) return errorState("تعذر تنفيذ الإجراء", "يتعارض الإجراء مع الحالة الحالية للمورد.");
  return errorState(fallback, "حاول مرة أخرى لاحقًا.");
}

function jsonRequest(path, method, payload) {
  return request(path, { method, headers: { "content-type": "application/json" }, body: JSON.stringify(payload) });
}

function cacheKey(resource) {
  return workspaceKey(SYSTEM_SCOPE, `controls:${resource}`);
}

function invalidate(...resources) {
  resources.forEach((resource) => workspaceCache.invalidate(cacheKey(resource)));
}

function load(resource, loader, host, paint, unavailable = null) {
  const key = cacheKey(resource);
  const cached = workspaceCache.get(key);
  if (cached !== undefined) paint(cached);
  else host.replaceChildren(loadingState("جاري تحميل البيانات…"));
  const result = workspaceCache.staleWhileRevalidate(key, loader, {
    isCurrent: () => host.isConnected,
    onFresh: paint,
    onError: (error) => {
      if (cached === undefined && host.isConnected) {
        host.replaceChildren(unavailable?.(error) || apiError(error));
      }
    },
  });
  result.refresh.catch(() => {});
}

async function systemWorkspaces() {
  return getJSON("/api/system/workspaces");
}

function workspaceSelect(items, selectedId, onChange) {
  const select = el(
    "select",
    { onchange: () => onChange(select.value), "aria-label": "مساحة العمل" },
    ...items.map((item) => el("option", { value: item.id, selected: item.id === selectedId ? "selected" : null }, item.name)),
  );
  return field("مساحة العمل", select);
}

function booleanControl(label, description, value) {
  const checkbox = el("input", { type: "checkbox", checked: value ? "checked" : null });
  return { checkbox, node: el("label", { className: "toggle-field" }, checkbox, el("span", {}, label), el("small", {}, description)) };
}

function knownStatus(value) {
  try {
    return statusBadge(value);
  } catch {
    return technical(value);
  }
}

export function policiesPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaces = await systemWorkspaces();
      selectedWorkspace = selectedWorkspace || workspaces[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("الضوابط والسياسات", "إدارة الضوابط التشغيلية والأمنية لمساحات العمل."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const resource = `policies:${selectedWorkspace}`;
      load(resource, async () => {
        const [governance, security] = await Promise.allSettled([
          getJSON(`/api/system/workspaces/${selectedWorkspace}/governance`),
          can("security.read") ? getJSON(`/api/system/workspaces/${selectedWorkspace}/security`) : Promise.resolve(null),
        ]);
        return {
          governance: governance.status === "fulfilled" ? governance.value : null,
          governanceError: governance.status === "rejected" ? governance.reason : null,
          security: security.status === "fulfilled" ? security.value : null,
          securityError: security.status === "rejected" ? security.reason : null,
        };
      }, host, (data) => {
        const policyContent = el("div", { className: "control-list" });
        const policyRows = (data.governance || []).filter((item) => POLICY_KEYS.has(item.setting_key));
        if (data.governanceError) {
          policyContent.append(apiError(data.governanceError, "تعذر تحميل السياسات التشغيلية."));
        }
        policyRows.forEach((item) => {
          const definition = POLICY_LABELS[item.setting_key];
          const control = booleanControl(definition.label, definition.description, item.enabled);
          const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
          control.checkbox.disabled = !can("governance.manage");
          const save = can("governance.manage") ? action("حفظ", async () => {
            save.disabled = true;
            feedback.replaceChildren();
            try {
              const enabled = control.checkbox.checked;
              await jsonRequest(`/api/system/workspaces/${selectedWorkspace}/governance/${item.setting_key}`, "PATCH", { enabled });
              item.enabled = enabled;
              workspaceCache.set(cacheKey(resource), data);
              notify("تم حفظ التغييرات.");
            } catch (error) {
              feedback.replaceChildren(apiError(error, "تعذر حفظ التغييرات."));
            } finally {
              save.disabled = false;
            }
          }, "button small") : null;
          policyContent.append(el("div", { className: "stack" },
            el("article", { className: "control-row" }, el("div", {}, control.node, technical(item.setting_key), el("span", { className: "secondary-meta" }, `آخر تحديث: ${formatDate(item.updated_at)}`)), save),
            feedback));
        });

        let securityPanel = null;
        if (data.securityError) {
          securityPanel = panel("ضوابط الأمان والوصول", apiError(data.securityError, "تعذر تحميل ضوابط الأمان."));
        } else if (data.security) {
          const invitations = booleanControl("السماح بالدعوات", "يتحكم في إنشاء دعوات العضوية.", data.security.invitations_enabled);
          const apiKeys = booleanControl("السماح بمفاتيح API", "يتحكم في إنشاء مفاتيح API على مستوى مساحة العمل.", data.security.api_keys_enabled);
          const expiry = el("input", { type: "number", min: "1", max: "90", value: data.security.max_invitation_expiry_days });
          const securityFeedback = el("div", { className: "form-feedback", "aria-live": "polite" });
          [invitations.checkbox, apiKeys.checkbox, expiry].forEach((control) => { control.disabled = !can("security.manage"); });
          const saveSecurity = can("security.manage") ? action("حفظ ضوابط الأمان", async () => {
            saveSecurity.disabled = true;
            securityFeedback.replaceChildren();
            try {
              const expiryDays = Number(expiry.value);
              if (!Number.isInteger(expiryDays) || expiryDays < 1 || expiryDays > 90) {
                securityFeedback.replaceChildren(errorState("تعذر حفظ التغييرات.", "أدخل مدة صحيحة بين يوم واحد و90 يومًا."));
                return;
              }
              await jsonRequest(`/api/system/workspaces/${selectedWorkspace}/security`, "PATCH", {
                invitations_enabled: invitations.checkbox.checked,
                api_keys_enabled: apiKeys.checkbox.checked,
                max_invitation_expiry_days: expiryDays,
              });
              data.security = {
                ...data.security,
                invitations_enabled: invitations.checkbox.checked,
                api_keys_enabled: apiKeys.checkbox.checked,
                max_invitation_expiry_days: expiryDays,
              };
              workspaceCache.set(cacheKey(resource), data);
              notify("تم حفظ التغييرات.");
            } catch (error) {
              securityFeedback.replaceChildren(apiError(error, "تعذر حفظ التغييرات."));
            } finally {
              saveSecurity.disabled = false;
            }
          }) : null;
          const securityContent = el("div", { className: "stack" }, invitations.node, apiKeys.node, field("الحد الأقصى لأيام صلاحية الدعوة", expiry), saveSecurity, securityFeedback, el("span", { className: "secondary-meta" }, `آخر تحديث: ${formatDate(data.security.updated_at)}`));
          securityPanel = panel("ضوابط الأمان والوصول", securityContent);
        }
        host.replaceChildren(
          pageHeader("الضوابط والسياسات", "ضوابط حقيقية قابلة للتنفيذ ضمن مساحة العمل المحددة."),
          panel("نطاق الإدارة", workspaceSelect(workspaces, selectedWorkspace, (value) => { selectedWorkspace = value; render(); })),
          panel("السياسات التشغيلية", policyContent.childElementCount ? policyContent : emptyState("لا توجد سياسات تشغيلية نشطة")),
          securityPanel,
        );
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function money(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const formatted = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 20,
    useGrouping: true,
  }).format(value);
  return el(
    "bdi",
    { className: "currency-value", dir: "ltr" },
    el("span", { className: "currency-amount" }, formatted),
    el("span", { className: "currency-code" }, "US$"),
  );
}

function limitResetLabel(value) {
  return {
    daily: "يومي (منتصف الليل بتوقيت UTC)",
    weekly: "أسبوعي (الاثنين إلى الأحد، UTC)",
    monthly: "شهري (منتصف الليل بتوقيت UTC)",
  }[value] || null;
}

export function usagePage() {
  const host = el("div", { className: "route-panel" });
  load("provider-usage", () => getJSON("/api/system/usage/provider"), host, (data) => {
    const metrics = [
      ["الإنفاق الإجمالي للمفتاح", data.usage],
      ["إنفاق المفتاح اليوم", data.usage_daily],
      ["إنفاق المفتاح هذا الأسبوع", data.usage_weekly],
      ["إنفاق المفتاح هذا الشهر", data.usage_monthly],
    ].filter(([, value]) => typeof value === "number" && Number.isFinite(value));
    const cards = el(
      "div",
      { className: "metrics-grid system-metrics usage-metrics" },
      ...metrics.map(([label, value]) => el(
        "article",
        { className: "metric-card" },
        el("span", { className: "metric-label" }, label),
        el("strong", { className: "metric-value" }, money(value)),
        el("span", { className: "metric-note" }, "إنفاق بالدولار الأمريكي كما يعيده OpenRouter"),
      )),
    );
    const providerFacts = el("dl", { className: "info-grid" },
      info("المزود", data.provider === "openrouter" ? "OpenRouter" : data.provider, true),
      info("وقت جلب البيانات", formatDate(data.retrieved_at)),
      typeof data.is_free_tier === "boolean"
        ? info("المفتاح ضمن الفئة المجانية", data.is_free_tier ? "نعم" : "لا")
        : null,
    );
    const limitFacts = [];
    if (typeof data.limit === "number" && Number.isFinite(data.limit)) limitFacts.push(info("حد إنفاق المفتاح", money(data.limit)));
    if (typeof data.limit_remaining === "number" && Number.isFinite(data.limit_remaining)) limitFacts.push(info("الرصيد المتبقي ضمن الحد", money(data.limit_remaining)));
    const resetLabel = limitResetLabel(data.limit_reset);
    if (resetLabel) limitFacts.push(info("وتيرة إعادة ضبط الحد", resetLabel));
    const sections = [
      pageHeader("الاستخدام", "إنفاق مفتاح OpenRouter كما يعيده مصدر بيانات المزود المعتمد، دون تقدير محلي."),
      metrics.length ? cards : emptyState("لا توجد بيانات استخدام للفترة المحددة."),
      panel("مصدر البيانات", providerFacts),
    ];
    if (limitFacts.length) {
      sections.push(panel("حد إنفاق المفتاح", el("dl", { className: "info-grid" }, ...limitFacts)));
    }
    host.replaceChildren(...sections);
  }, (error) => error instanceof ApiError && error.status === 503
    ? error.code === "provider usage credential unavailable"
      ? errorState("إعداد بيانات الاستخدام غير متاح", "مرجع اعتماد OpenRouter غير مهيأ في الخادم.")
      : errorState("تعذر جلب بيانات الاستخدام من المزود.", "لم يتمكن الخادم من قراءة واجهة استخدام OpenRouter حاليًا.")
    : apiError(error));
  return host;
}

function providerEditor(workspaceId, provider, onSaved) {
  const enabled = booleanControl("مسموح إداريًا في هذه المساحة", "قيمة إدارية محفوظة للمساحة؛ لا تمثل اختبار اتصال بالمزود.", provider.enabled);
  const status = el(
    "select",
    {},
    el("option", { value: "configured" }, "مهيأ إداريًا"),
    el("option", { value: "disabled" }, "معطّل إداريًا"),
    el("option", { value: "degraded" }, "متدهور إداريًا"),
  );
  status.value = provider.administrative_status;
  const baseUrl = el("input", { type: "url", value: provider.base_url_override || "", dir: "ltr", placeholder: provider.default_base_url || "https://…" });
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    el("p", { className: "provider-warning" }, "هذه بيانات إدارية محفوظة للمساحة. تهيئة التنفيذ الفعلية معروضة بصورة مستقلة ولا تتغير من هذا النموذج."),
    enabled.node,
    field("الحالة التشغيلية", status),
    field("عنوان إداري بديل", baseUrl, "قيمة وصفية محفوظة حاليًا؛ لا تغيّر عنوان runtime الفعلي."),
    feedback,
  );
  const save = action("حفظ البيانات الإدارية", async () => {
    save.disabled = true;
    feedback.replaceChildren();
    try {
      await jsonRequest(`/api/system/workspaces/${workspaceId}/providers/${provider.code}`, "PATCH", {
        enabled: enabled.checkbox.checked,
        administrative_status: status.value,
        base_url_override: baseUrl.value.trim() || null,
      });
      invalidate(`providers:${workspaceId}`);
      notify("تم حفظ البيانات الإدارية للمزود.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error));
    }
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); save.click(); });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(`بيانات المزود الإدارية — ${provider.display_name}`, form);
}

function providerDetails(workspaceId, provider, onSaved) {
  const content = el(
    "div",
    { className: "stack" },
    el("p", { className: "detail-lead" }, "تعريف المزود عام في سجل المنصة، بينما السماح والحالة والعنوان البديل بيانات إدارية تخص مساحة العمل المحددة. لا تمثل هذه القيم تحققًا حيًا من اتصال المزود."),
    el("dl", { className: "info-grid" },
      info("الاسم", provider.display_name),
      info("القدرة المسجلة", providerTypeLabel(provider.provider_type)),
      info("الحالة الإدارية", providerStatusLabel(provider.administrative_status)),
      info("سماح المساحة", provider.enabled ? "مسموح إداريًا" : "موقوف إداريًا"),
      info("العنوان الإداري المسجل", provider.base_url || "غير محدد", true),
      info("آخر تحديث", formatDate(provider.updated_at)),
    ),
    technical(provider.code),
  );
  const details = drawer(provider.display_name, content);
  if (can("providers.manage")) {
    content.append(action("تعديل البيانات الإدارية", () => { details.close(); providerEditor(workspaceId, provider, onSaved); }));
  }
}

const PROVIDER_TYPE_LABELS = {
  generation: "توليد",
  embeddings: "تمثيلات متجهية",
  multi: "متعدد القدرات",
};

const PROVIDER_STATUS_LABELS = {
  configured: "مهيأ إداريًا",
  disabled: "معطّل إداريًا",
  degraded: "متدهور إداريًا",
};

function providerTypeLabel(value) {
  return PROVIDER_TYPE_LABELS[value] || value || "غير محدد";
}

function providerStatusLabel(value) {
  return PROVIDER_STATUS_LABELS[value] || value || "غير محدد";
}

function providerDisplayName(value) {
  return value === "openrouter" ? "OpenRouter" : "مزود بعيد";
}

function configurationSourceLabel(source) {
  return source === "PERSISTED" ? "تهيئة النظام المحفوظة" : "تهيئة البيئة الاحتياطية";
}

function runtimeConfigurationCard(title, configuration, dimensions = false, actions = []) {
  const facts = [
    info("المزود", primary(providerDisplayName(configuration.provider), configuration.provider)),
    info("معرّف النموذج لدى المزود", technical(configuration.model_id)),
    info("عنوان المزود", technical(configuration.endpoint)),
    info("مرجع بيانات الاعتماد", technical(configuration.credential_reference)),
    info("مصدر التهيئة", configurationSourceLabel(configuration.source)),
    info("النطاق", "عام للنظام"),
    info("الجاهزية", configuration.structurally_ready === false ? "غير مكتملة" : "مكتملة بنيويًا؛ الاتصال غير مختبر"),
  ];
  if (dimensions && Number.isInteger(configuration.dimensions)) {
    facts.splice(2, 0, info("أبعاد التمثيل", String(configuration.dimensions)));
  }
  return el(
    "article",
    { className: "provider-config-card" },
    el("h3", {}, title),
    el("dl", { className: "info-grid" }, ...facts),
    actions.length ? el("div", { className: "form-actions" }, ...actions) : null,
  );
}

function persistedConfigurationCard(title, capability, configuration, fallback, providers, onSaved) {
  const edit = can("providers.manage")
    ? action(configuration ? "تعديل التهيئة المحفوظة" : "إنشاء تهيئة محفوظة", () => {
      runtimeConfigurationEditor(capability, configuration || fallback, providers, onSaved);
    }, "button secondary small")
    : null;
  if (!configuration) {
    return el(
      "article",
      { className: "provider-config-card" },
      el("h3", {}, title),
      el("p", { className: "detail-lead" }, "لا توجد تهيئة محفوظة. تهيئة البيئة الاحتياطية هي الفعالة."),
      edit,
    );
  }
  const value = { ...configuration, source: "PERSISTED", structurally_ready: true };
  const card = runtimeConfigurationCard(title, value, capability === "embedding", edit ? [edit] : []);
  card.querySelector(".info-grid")?.append(
    info("حالة التفعيل", configuration.active ? "مفعلة" : "غير مفعلة؛ البيئة الاحتياطية فعالة"),
    info("تاريخ الحفظ", formatDate(configuration.created_at)),
  );
  return card;
}

function runtimeConfigurationEditor(capability, initial, providers, onSaved) {
  const allowedTypes = capability === "embedding" ? new Set(["embeddings", "multi"]) : new Set(["generation", "multi"]);
  const provider = el("select", {}, ...providers.filter((item) => allowedTypes.has(item.provider_type)).map((item) => el("option", { value: item.code }, item.display_name)));
  provider.value = initial.provider;
  const model = el("input", { type: "text", required: "required", value: initial.model_id || "", dir: "ltr" });
  const endpoint = el("input", { type: "url", required: "required", value: initial.endpoint || "", dir: "ltr" });
  const credential = el("input", { type: "text", required: "required", value: initial.credential_reference || "", dir: "ltr", pattern: "[A-Z][A-Z0-9_]{1,79}" });
  const dimensions = capability === "embedding" ? el("input", { type: "number", required: "required", min: "1", max: "65536", value: String(initial.dimensions || 1024), dir: "ltr" }) : null;
  const active = booleanControl("تفعيل التهيئة المحفوظة", "عند إيقافها تصبح تهيئة البيئة الاحتياطية هي الفعالة.", initial.active === true || initial.source === "ENVIRONMENT_FALLBACK");
  const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  const form = el(
    "form",
    { className: "source-create-form" },
    el("p", { className: "detail-lead" }, "تُحفظ مراجع بيانات الاعتماد فقط. لا تُخزّن قيمة سرية، ولا يُجرى اختبار اتصال بالمزود عند الحفظ."),
    field("المزود المدعوم", provider),
    field("معرّف النموذج لدى المزود", model),
    field("عنوان المزود البعيد", endpoint),
    field("مرجع بيانات الاعتماد", credential, "اسم مرجع خادمي مثل OPENROUTER_API_KEY، وليس قيمة السر."),
    dimensions ? field("أبعاد التمثيل", dimensions) : null,
    active.node,
    feedback,
  );
  const save = action("حفظ تهيئة التشغيل", async () => {
    if (!form.reportValidity()) return;
    save.disabled = true;
    feedback.replaceChildren();
    try {
      await jsonRequest(`/api/system/providers/runtime/${capability}`, "PUT", {
        provider: provider.value,
        model_id: model.value.trim(),
        endpoint: endpoint.value.trim(),
        credential_reference: credential.value.trim(),
        dimensions: dimensions ? Number(dimensions.value) : null,
        active: active.checkbox.checked,
      });
      notify("تم حفظ تهيئة التشغيل وأصبحت نافذة للعمليات اللاحقة.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error, "تعذر حفظ تهيئة التشغيل."));
    }
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); save.click(); });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(capability === "embedding" ? "تهيئة نموذج التمثيلات المتجهية" : "تهيئة نموذج التوليد", form);
}

export function providersPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaces = await systemWorkspaces();
      selectedWorkspace = selectedWorkspace || workspaces[0]?.id || null;
      const resource = `providers:${selectedWorkspace || "runtime"}`;
      load(resource, async () => {
        const [runtime, providers, assistants] = await Promise.all([
          getJSON("/api/system/providers/runtime"),
          selectedWorkspace ? getJSON(`/api/system/workspaces/${selectedWorkspace}/providers`) : Promise.resolve([]),
          selectedWorkspace && can("system_assistants.read") ? getJSON(`/api/system/workspaces/${selectedWorkspace}/assistants`) : Promise.resolve([]),
        ]);
        return { runtime, providers, assistants };
      }, host, (data) => {
        const reload = () => { invalidate(resource); render(); };
        const providerRows = data.providers.map((provider) => [
          primary(provider.display_name, provider.code),
          primary(providerTypeLabel(provider.provider_type), provider.provider_type),
          primary(providerStatusLabel(provider.administrative_status), provider.administrative_status),
          el("span", { className: `capability-state ${provider.enabled ? "enabled" : "disabled"}` }, provider.enabled ? "مسموح إداريًا" : "موقوف إداريًا"),
          action("عرض", () => providerDetails(selectedWorkspace, provider, render), "button secondary small"),
        ]);
        const assistantReferences = data.assistants.map((assistant) => [
          primary(assistant.name, assistant.language ? `اللغة: ${assistant.language}` : null),
          primary(providerDisplayName(assistant.provider), assistant.provider),
          technical(assistant.model_reference),
          "محفوظ على المساعد؛ غير مستخدم لاختيار نموذج runtime الحالي",
        ]);
        const sections = [
          pageHeader("المزودون والنماذج", "تهيئة نظام موحّدة للتوليد والتمثيلات المتجهية، مع فصل البيانات الإدارية ومراجع المساعدين."),
          panel(
            "تهيئة التشغيل الفعالة",
            el("p", { className: "detail-lead" }, "هذه هي التهيئة التي يستهلكها التنفيذ اللاحق فعليًا. التهيئة المحفوظة المفعلة لها الأولوية، وإلا تُستخدم بيئة التشغيل الاحتياطية كوحدة كاملة."),
            el("div", { className: "provider-runtime-grid" },
              runtimeConfigurationCard("التوليد", data.runtime.effective.generation),
              runtimeConfigurationCard("التمثيلات المتجهية", data.runtime.effective.embedding, true),
            ),
          ),
          panel(
            "تهيئة التشغيل المحفوظة",
            el("p", { className: "detail-lead" }, "تهيئة عالمية يملكها النظام. لا تصبح فعالة إلا عند اكتمالها وتفعيلها، وتُحفظ كل مراجعة مع مصدرها الزمني."),
            el("div", { className: "provider-runtime-grid" },
              persistedConfigurationCard("التوليد المحفوظ", "generation", data.runtime.persisted.generation, data.runtime.environment_fallback.generation, data.runtime.providers, reload),
              persistedConfigurationCard("التمثيلات المحفوظة", "embedding", data.runtime.persisted.embedding, data.runtime.environment_fallback.embedding, data.runtime.providers, reload),
            ),
          ),
          panel(
            "بيئة التشغيل الاحتياطية",
            el("p", { className: "detail-lead" }, "تُستخدم فقط عند عدم وجود تهيئة محفوظة مفعلة. لا تُخلط حقول المصدرين، ولا تعالج البيئة تهيئة محفوظة مفعلة لكنها غير صالحة."),
            el("div", { className: "provider-runtime-grid" },
              runtimeConfigurationCard("توليد احتياطي", data.runtime.environment_fallback.generation),
              runtimeConfigurationCard("تمثيلات احتياطية", data.runtime.environment_fallback.embedding, true),
            ),
          ),
          workspaces.length
            ? panel("نطاق البيانات الإدارية", el("p", { className: "detail-lead" }, "اختيار مساحة العمل يغيّر بيانات السماح الإداري ومراجع المساعدين فقط، ولا يغيّر تهيئة التشغيل العالمية أعلاه."), workspaceSelect(workspaces, selectedWorkspace, (value) => { selectedWorkspace = value; render(); }))
            : panel("نطاق البيانات الإدارية", emptyState("لا توجد مساحات عمل")),
        ];
        if (selectedWorkspace) {
          sections.push(
            panel("سجل المزود وإعداد المساحة", el("p", { className: "detail-lead" }, "الحالة والسماح هنا بيانات إدارية محفوظة، وليست إثباتًا لاتصال المزود أو مصدر اختيار النموذج التنفيذي."), providerRows.length ? table(["المزود المسجل", "القدرة المسجلة", "الحالة الإدارية", "سماح المساحة", ""], providerRows) : emptyState("لا توجد إعدادات مزود")),
            panel("مراجع النماذج المحفوظة على المساعدين", el("p", { className: "detail-lead" }, "هذه المراجع بيانات وصفية داخل إعداد كل مساعد، ولا تُستخدم لاختيار نموذج التنفيذ في هذا العقد."), assistantReferences.length ? table(["المساعد", "مرجع المزود المحفوظ", "مرجع النموذج المحفوظ", "الاستهلاك التنفيذي"], assistantReferences) : emptyState("لا توجد مراجع نماذج محفوظة على مساعدين في هذه المساحة")),
          );
        }
        host.replaceChildren(...sections);
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function credentialForm(workspaceId, providers, onSaved) {
  const name = el("input", { required: "required", maxlength: "80", dir: "ltr", placeholder: "OPENROUTER_API_KEY" });
  const provider = el("select", {}, el("option", { value: "" }, "دون مزود محدد"), ...providers.map((item) => el("option", { value: item.code }, item.display_name)));
  const type = el("select", {}, el("option", { value: "env" }, "متغير بيئة"), el("option", { value: "vault" }, "مرجع Vault"));
  const reference = el("input", { required: "required", dir: "ltr", placeholder: "OPENROUTER_API_KEY" });
  const status = el("select", {}, el("option", { value: "configured" }, "مهيأ"), el("option", { value: "disabled" }, "معطّل"), el("option", { value: "invalid" }, "غير صالح"));
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    el("p", { className: "provider-warning" }, "تُحفظ هوية المرجع فقط. لا تُدخل قيمة مفتاح أو سرًا في هذه الواجهة."),
    field("اسم المرجع", name),
    field("المزود", provider),
    el("div", { className: "form-grid" }, field("نوع المرجع", type), field("اسم المتغير أو مسار المرجع", reference)),
    field("الحالة", status),
    feedback,
  );
  const save = action("حفظ مرجع بيانات الاعتماد", async () => {
    const normalizedName = name.value.trim();
    const normalizedReference = reference.value.trim();
    if (!normalizedName || !normalizedReference) return;
    save.disabled = true;
    feedback.replaceChildren();
    try {
      await jsonRequest(`/api/system/workspaces/${workspaceId}/credentials`, "POST", {
        name: normalizedName,
        provider_code: provider.value || null,
        secret_reference: `${type.value}:${normalizedReference}`,
        status: status.value,
      });
      invalidate(`credentials:${workspaceId}`);
      notify("تم حفظ بيانات مرجع الاعتماد دون كشف قيمة سرية.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error));
    }
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); save.click(); });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer("مرجع بيانات اعتماد", form);
  name.focus();
}

function confirmCredentialDelete(workspaceId, item, onSaved) {
  const content = el("div", { className: "stack" }, el("p", {}, `سيُحذف مرجع ${item.name} الوصفي. لا تتم قراءة أو عرض أي قيمة سرية.`));
  const remove = action("تأكيد حذف المرجع", async () => {
    remove.disabled = true;
    try {
      await request(`/api/system/workspaces/${workspaceId}/credentials/${item.id}`, { method: "DELETE" });
      invalidate(`credentials:${workspaceId}`);
      notify("تم حذف مرجع بيانات الاعتماد.");
      modal.close();
      onSaved();
    } catch (error) {
      remove.disabled = false;
      content.append(apiError(error));
    }
  });
  content.append(el("div", { className: "form-actions" }, remove));
  const modal = drawer("حذف مرجع بيانات الاعتماد", content);
}

export function credentialsPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaces = await systemWorkspaces();
      selectedWorkspace = selectedWorkspace || workspaces[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("بيانات الاعتماد", "إدارة بيانات مراجع الاعتماد دون إظهار الأسرار."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const resource = `credentials:${selectedWorkspace}`;
      load(resource, async () => {
        const [credentials, providers] = await Promise.all([
          getJSON(`/api/system/workspaces/${selectedWorkspace}/credentials`),
          can("providers.read") ? getJSON(`/api/system/workspaces/${selectedWorkspace}/providers`) : Promise.resolve([]),
        ]);
        return { credentials, providers };
      }, host, (data) => {
        const add = can("credentials.manage") ? action("مرجع جديد", () => credentialForm(selectedWorkspace, data.providers, render)) : null;
        const rows = data.credentials.map((item) => {
          const actions = el("div", { className: "inline-actions" });
          if (can("credentials.manage")) actions.append(action("حذف المرجع", () => confirmCredentialDelete(selectedWorkspace, item, render), "button secondary small"));
          return [primary(item.name, item.id), item.provider_code || "—", item.reference_type === "env" ? "متغير بيئة" : item.reference_type === "vault" ? "Vault" : "غير معروف", knownStatus(item.status), formatDate(item.updated_at), actions];
        });
        host.replaceChildren(
          pageHeader("بيانات الاعتماد", "مراجع وصفية مرتبطة بالخادم؛ لا تُعاد قيم الأسرار إلى المتصفح.", add),
          panel("نطاق الإدارة", workspaceSelect(workspaces, selectedWorkspace, (value) => { selectedWorkspace = value; render(); })),
          panel("مراجع بيانات الاعتماد", rows.length ? table(["المرجع", "المزود", "النوع", "الحالة", "آخر تحديث", ""], rows) : emptyState("لا توجد مراجع بيانات اعتماد")),
        );
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function conversationOutcomeLabel(outcome) {
  return {
    GroundedAnswer: "إجابة مدعّمة بالأدلة",
    InsufficientEvidence: "لا توجد أدلة كافية",
    PolicyDenied: "منعته سياسة الحماية",
    TechnicalFailure: "تعذر إكمال المعالجة",
  }[outcome] || null;
}

async function systemAssistantCatalogue(workspaces, conversationItems = []) {
  const workspaceIds = new Set([
    ...conversationItems.map((item) => item.workspace_id).filter(Boolean),
  ]);
  const entries = await Promise.all([...workspaceIds].map(async (workspaceId) => [
    workspaceId,
    await getJSON(`/api/system/workspaces/${workspaceId}/assistants`),
  ]));
  return { workspaces, assistants: new Map(entries) };
}

function systemConversationForm(item, catalogue, onSaved) {
  const title = el("input", { required: "required", maxlength: "200", value: item?.title || "" });
  const workspace = el("select", { required: "required", disabled: item ? "disabled" : null },
    el("option", { value: "" }, "اختر مساحة العمل"),
    ...catalogue.workspaces.map((value) => el("option", { value: value.id }, value.name)),
  );
  const assistant = el("select", { required: "required", disabled: "disabled" }, el("option", { value: "" }, "اختر مساعدًا"));
  const feedback = el("div", { className: "form-feedback" });
  const loadAssistants = async (workspaceId, selectedId = null) => {
    assistant.disabled = true;
    assistant.replaceChildren(el("option", { value: "" }, "جاري تحميل المساعدين…"));
    try {
      const assistants = catalogue.assistants.get(workspaceId)
        || await getJSON(`/api/system/workspaces/${workspaceId}/assistants`);
      catalogue.assistants.set(workspaceId, assistants);
      assistant.replaceChildren(
        el("option", { value: "" }, "اختر مساعدًا"),
        ...assistants.map((value) => el("option", { value: value.id }, value.name)),
      );
      assistant.value = selectedId || "";
      assistant.disabled = false;
    } catch (error) {
      assistant.replaceChildren(el("option", { value: "" }, "تعذر تحميل المساعدين"));
      feedback.replaceChildren(apiError(error, "تعذر تحميل المساعدين."));
    }
  };
  if (item) {
    workspace.value = item.workspace_id || "";
    if (item.workspace_id) loadAssistants(item.workspace_id, item.assistant_id);
  } else {
    workspace.addEventListener("change", () => {
      feedback.replaceChildren();
      if (workspace.value) loadAssistants(workspace.value);
      else {
        assistant.disabled = true;
        assistant.replaceChildren(el("option", { value: "" }, "اختر مساعدًا"));
      }
    });
  }
  const form = el("form", { className: "source-create-form" },
    item ? null : field("مساحة العمل", workspace),
    item ? null : field("المساعد", assistant),
    field("عنوان المحادثة", title),
    feedback,
  );
  const save = action(item ? "حفظ العنوان" : "إنشاء المحادثة", async () => {
    if (!title.value.trim() || (!item && (!workspace.value || !assistant.value))) return;
    save.disabled = true;
    try {
      const value = item
        ? await jsonRequest(`/api/system/conversations/${item.id}/title`, "PATCH", { title: title.value.trim() })
        : await jsonRequest("/api/system/conversations", "POST", {
          workspace_id: workspace.value,
          assistant_id: assistant.value,
          title: title.value.trim(),
        });
      invalidate("system-conversations:ACTIVE", "system-conversations:ARCHIVED", "system-conversations:ALL", `system-conversation:${value.id}`);
      notify(item ? "تمت إعادة تسمية المحادثة." : "تم إنشاء محادثة النظام.");
      modal.close();
      onSaved(value);
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error, "تعذر حفظ المحادثة."));
    }
  });
  form.addEventListener("submit", (event) => { event.preventDefault(); save.click(); });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(item ? "إعادة تسمية المحادثة" : "محادثة نظام جديدة", form);
  title.focus();
}

function systemMessage(message) {
  const role = String(message.role || "").toLowerCase();
  const roleLabel = role === "user" ? "المستخدم" : role === "assistant" ? "المساعد" : "النظام";
  const outcome = conversationOutcomeLabel(message.outcome);
  return el(
    "article",
    { className: `message ${role}` },
    el("div", { className: "message-head" },
      el("span", { className: "message-role" }, roleLabel),
      outcome ? el("span", { className: "secondary-meta" }, outcome) : null,
      el("time", { className: "secondary-meta" }, formatDate(message.created_at)),
    ),
    el("p", { className: "message-content", dir: "auto" }, message.content),
    Array.isArray(message.evidence) && message.evidence.length ? el("div", { className: "message-evidence" },
      ...message.evidence.map((item, index) => el("article", { className: "evidence" },
        el("strong", {}, `دليل ${index + 1}`),
        el("p", { dir: "auto" }, item.content),
        el("span", { className: "secondary-meta technical-code", dir: "ltr" }, item.provenance_locator),
      )),
    ) : null,
  );
}

function systemConversationComposer(value, open) {
  const question = el("textarea", { rows: "3", required: "required", placeholder: "اكتب سؤالًا للمساعد…", "aria-label": "السؤال" });
  const feedback = el("div", { className: "form-feedback" });
  const send = action("إرسال", async () => {
    if (!question.value.trim()) return;
    send.disabled = true;
    try {
      await jsonRequest(`/api/system/conversations/${value.id}/ask`, "POST", { question: question.value.trim() });
      invalidate(`system-conversation:${value.id}`, "system-conversations:ACTIVE", "system-conversations:ALL");
      open(value);
    } catch (error) {
      feedback.replaceChildren(apiError(error, "تعذر إرسال السؤال."));
      send.disabled = false;
    }
  });
  const form = el("form", { className: "conversation-composer" }, field("رسالتك", question), feedback, el("div", { className: "form-actions" }, send));
  form.addEventListener("submit", (event) => { event.preventDefault(); send.click(); });
  return form;
}

export function systemConversationsPage() {
  const host = el("div", { className: "route-panel" });
  let selectedId = null;
  let status = "ACTIVE";
  const render = () => {
    const resource = `system-conversations:${status}`;
    load(resource, async () => {
      const items = await getJSON(`/api/system/conversations?status=${status}`);
      return { items, ...await systemAssistantCatalogue(await systemWorkspaces(), items) };
    }, host, (data) => {
      const { items, workspaces, assistants } = data;
      const catalogue = { workspaces, assistants };
      const workspaceName = (workspaceId) => workspaces.find((item) => item.id === workspaceId)?.name || "غير متاح";
      const assistantName = (workspaceId, assistantId) => (assistants.get(workspaceId) || []).find((item) => item.id === assistantId)?.name || "غير متاح";
      if (selectedId && !items.some((item) => item.id === selectedId)) selectedId = null;
      selectedId = selectedId || items[0]?.id || null;
      const list = el("div", { className: "conversation-list" });
      const detail = el("section", { className: "conversation-detail" });
      const open = (item) => {
        selectedId = item.id;
        [...list.querySelectorAll(".conversation-row")].forEach((node) => node.classList.toggle("active", node.dataset.id === item.id));
        detail.replaceChildren(loadingState("جاري تحميل المحادثة…"));
        load(`system-conversation:${item.id}`, () => getJSON(`/api/system/conversations/${item.id}`), detail, (value) => {
          const actions = el("div", { className: "inline-actions" });
          if (can("system_conversations.rename")) actions.append(action("إعادة تسمية", () => systemConversationForm(value, catalogue, () => render()), "button secondary small"));
          if (can("system_conversations.archive")) {
            const archived = value.status === "ARCHIVED";
            actions.append(action(archived ? "استعادة" : "أرشفة", async () => {
              try {
                await jsonRequest(`/api/system/conversations/${value.id}/archive`, "PATCH", { archived: !archived });
                invalidate(resource, `system-conversation:${value.id}`, "system-conversations:ACTIVE", "system-conversations:ARCHIVED", "system-conversations:ALL");
                notify(archived ? "تمت استعادة المحادثة." : "تمت أرشفة المحادثة دون حذفها.");
                selectedId = null;
                render();
              } catch (error) {
                detail.append(apiError(error, "تعذر تغيير حالة المحادثة."));
              }
            }, "button secondary small"));
          }
          const legacy = !value.workspace_id || !value.assistant_id;
          const detailContent = [
            el("header", { className: "conversation-head" }, el("div", {}, el("h2", {}, value.title), el("div", { className: "inline-actions" }, knownStatus(value.status), el("span", { className: "secondary-meta" }, `آخر تحديث: ${formatDate(value.updated_at)}`))), actions),
            el("dl", { className: "info-grid" },
              info("مساحة العمل", legacy ? "غير مرتبطة" : workspaceName(value.workspace_id)),
              info("المساعد", legacy ? "غير مرتبط" : assistantName(value.workspace_id, value.assistant_id)),
              info("تاريخ الإنشاء", formatDate(value.created_at)),
            ),
          ];
          if (legacy) {
            detailContent.push(errorState("محادثة قديمة غير مرتبطة بمساحة عمل ومساعد", "تبقى المحادثة قابلة للقراءة، لكنها غير متاحة لتنفيذ الذكاء الاصطناعي."));
          }
          const messages = value.messages?.length ? el("div", { className: "messages" }, ...value.messages.map(systemMessage)) : emptyState("لا توجد رسائل", "هذه المحادثة الإدارية لا تحتوي رسائل محفوظة.");
          detailContent.push(messages);
          if (!legacy && value.status === "ACTIVE" && can("system_conversations.create")) {
            detailContent.push(systemConversationComposer(value, open));
          }
          detail.replaceChildren();
          appendContent(detail, detailContent);
        });
      };
      items.forEach((item) => {
        const legacy = !item.workspace_id || !item.assistant_id;
        const row = el("button", { type: "button", className: `conversation-row ${item.id === selectedId ? "active" : ""}`, dataset: { id: item.id }, onclick: () => open(item) },
          el("div", { className: "conversation-row-head" }, el("strong", {}, item.title), knownStatus(item.status)),
          el("span", { className: "conversation-row-meta" }, legacy ? "محادثة قديمة غير مرتبطة" : `${workspaceName(item.workspace_id)} · ${assistantName(item.workspace_id, item.assistant_id)}`),
          el("span", { className: "conversation-row-meta" }, formatDate(item.updated_at)),
        );
        list.append(row);
      });
      if (!items.length) list.append(emptyState("لا توجد محادثات نظام", status === "ARCHIVED" ? "لا توجد محادثات مؤرشفة." : "أنشئ محادثة إدارية عند الحاجة."));
      const filter = el("select", { onchange: () => { status = filter.value; selectedId = null; render(); }, "aria-label": "حالة المحادثات" }, el("option", { value: "ACTIVE" }, "النشطة"), el("option", { value: "ARCHIVED" }, "المؤرشفة"), el("option", { value: "ALL" }, "الكل"));
      filter.value = status;
      const create = can("system_conversations.create") ? action("محادثة نظام جديدة", () => systemConversationForm(null, catalogue, (value) => { status = "ACTIVE"; selectedId = value.id; render(); })) : null;
      host.replaceChildren(
        pageHeader("المحادثات", "محادثات إدارية مدعّمة بالأدلة ضمن نطاق النظام، ومنفصلة عن محادثات مساحات العمل.", create),
        panel("التصفية", field("الحالة", filter)),
        el("div", { className: "conversation-layout system-conversation-layout" }, list, detail),
      );
      const selected = items.find((item) => item.id === selectedId);
      if (selected) open(selected);
      else detail.replaceChildren(emptyState("اختر محادثة", "اختر محادثة نظام لعرض تفاصيلها."));
    });
  };
  render();
  return host;
}

function auditDetails(event, workspaceName) {
  const metadata = el("pre", { className: "audit-metadata", dir: "ltr" }, JSON.stringify(event.metadata || {}, null, 2));
  drawer("تفاصيل حدث السجل", el("div", { className: "stack" },
    el("dl", { className: "info-grid" },
      info("مساحة العمل", workspaceName),
      info("الإجراء", event.action, true),
      info("نوع المورد", event.resource_type, true),
      info("معرّف المورد", event.resource_id || "—", true),
      info("النتيجة", event.outcome, true),
      info("الفاعل", event.actor_user_id || "غير متاح", true),
      info("معرّف الطلب", event.request_id || "—", true),
      info("التوقيت", formatDate(event.occurred_at)),
    ),
    panel("البيانات المنظمة", metadata),
  ));
}

export function auditPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  let actionFilter = "";
  let offset = 0;
  const limit = 25;
  const render = async () => {
    try {
      const workspaces = await systemWorkspaces();
      selectedWorkspace = selectedWorkspace || workspaces[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("سجل النظام", "تصفح أحداث التدقيق المصرح بها."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
      if (actionFilter) query.set("action", actionFilter);
      const resource = `audit:${selectedWorkspace}:${query}`;
      load(resource, () => getJSON(`/api/system/workspaces/${selectedWorkspace}/audit?${query}`), host, (items) => {
        const actionInput = el("input", { value: actionFilter, dir: "ltr", placeholder: "workspace.updated" });
        const search = action("تطبيق التصفية", () => { actionFilter = actionInput.value.trim(); offset = 0; render(); }, "button secondary");
        const workspaceName = workspaces.find((item) => item.id === selectedWorkspace)?.name || "—";
        const rows = items.map((item) => [primary(item.action, item.id), primary(item.resource_type, item.resource_id), item.outcome, item.actor_user_id ? technical(item.actor_user_id) : "—", formatDate(item.occurred_at), action("التفاصيل", () => auditDetails(item, workspaceName), "button secondary small")]);
        const pagination = el("div", { className: "form-actions" },
          action("الأحدث", () => { offset = Math.max(0, offset - limit); render(); }, "button secondary small"),
          el("span", { className: "secondary-meta" }, `العناصر ${offset + 1}–${offset + items.length}`),
          action("الأقدم", () => { offset += limit; render(); }, "button secondary small"),
        );
        pagination.firstElementChild.disabled = offset === 0;
        pagination.lastElementChild.disabled = items.length < limit;
        host.replaceChildren(
          pageHeader("سجل النظام", "أحداث التدقيق الحقيقية ضمن مساحة العمل المحددة وبصلاحية النظام."),
          panel("النطاق والتصفية", el("div", { className: "form-grid" }, workspaceSelect(workspaces, selectedWorkspace, (value) => { selectedWorkspace = value; offset = 0; render(); }), field("رمز الإجراء", actionInput)), search),
          panel("الأحداث", rows.length ? table(["الإجراء", "المورد", "النتيجة", "الفاعل", "التوقيت", ""], rows) : emptyState("لا توجد أحداث مطابقة"), pagination),
        );
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function systemAccessForm(data, onSaved) {
  const users = data.users.filter((user) => !data.assignments.some((assignment) => assignment.status === "active" && assignment.user_id === user.user_id && assignment.role_name === "SYSTEM_ADMIN"));
  const roles = [...new Map(data.assignments
    .filter((assignment) => assignment.role_name === "SYSTEM_ADMIN" && assignment.role_kind === "built_in")
    .map((assignment) => [assignment.role_id, { id: assignment.role_id, name: assignment.role_name }])).values()];
  const user = el("select", {}, ...users.map((item) => el("option", { value: item.user_id }, item.display_name || item.email)));
  const role = el("select", {}, ...roles.map((item) => el("option", { value: item.id }, ROLE_LABELS[item.name] || item.name)));
  const feedback = el("div", { className: "form-feedback" });
  const form = el("form", { className: "source-create-form" },
    el("p", { className: "detail-lead" }, "هذا تعيين مستقل لنطاق النظام ولا يُستنتج من عضوية أي مساحة عمل."),
    users.length ? field("المستخدم", user) : emptyState("لا يوجد مستخدم متاح للتعيين"),
    roles.length ? field("دور النظام", role) : emptyState("دور مدير النظام غير متاح"),
    feedback,
  );
  const save = action("تعيين مدير النظام", async () => {
    if (!user.value || !role.value) return;
    save.disabled = true;
    try {
      await jsonRequest("/api/system/access", "POST", { user_id: user.value, role_id: role.value });
      invalidate("system-access");
      notify("تم إنشاء تعيين نظام مستقل.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error));
    }
  });
  save.disabled = !users.length || !roles.length;
  form.addEventListener("submit", (event) => { event.preventDefault(); save.click(); });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer("تعيين الوصول للنظام", form);
}

function revokeSystemAccess(assignment, onSaved) {
  const content = el("div", { className: "stack" },
    el("p", {}, `إلغاء تعيين مدير النظام للمستخدم ${assignment.display_name || assignment.email}.`),
    el("p", { className: "provider-warning" }, "سيمنع الخادم إلغاء آخر تعيين نشط لمدير النظام."),
  );
  const revoke = action("تأكيد إلغاء التعيين", async () => {
    revoke.disabled = true;
    try {
      await request(`/api/system/access/${assignment.user_id}/${assignment.role_id}`, { method: "DELETE" });
      invalidate("system-access");
      notify("تم إلغاء تعيين الوصول للنظام.");
      modal.close();
      onSaved();
    } catch (error) {
      revoke.disabled = false;
      content.append(apiError(error));
    }
  });
  content.append(el("div", { className: "form-actions" }, revoke));
  const modal = drawer("إلغاء الوصول للنظام", content);
}

export function systemAccessPage() {
  const host = el("div", { className: "route-panel" });
  const render = () => load("system-access", async () => {
    const [assignments, users] = await Promise.all([
      getJSON("/api/system/access"),
      getJSON("/api/system/users"),
    ]);
    return { assignments, users };
  }, host, (data) => {
    const add = can("system_access.manage") ? action("تعيين مدير نظام", () => systemAccessForm(data, render)) : null;
    const rows = data.assignments.map((item) => {
      const actions = el("div", { className: "inline-actions" });
      if (item.status === "active" && can("system_access.manage")) actions.append(action("إلغاء التعيين", () => revokeSystemAccess(item, render), "button secondary small"));
      return [primary(item.display_name || item.email, item.email), primary(ROLE_LABELS[item.role_name] || item.role_name, item.role_name), knownStatus(item.status), item.assigned_by ? technical(item.assigned_by) : "—", formatDate(item.created_at), actions];
    });
    host.replaceChildren(
      pageHeader("إدارة الوصول للنظام", "تعيينات SYSTEM_ADMIN المستقلة عن أدوار وعضويات مساحات العمل.", add),
      panel("تعيينات نطاق النظام", rows.length ? table(["المستخدم", "دور النظام", "الحالة", "عيّنه", "التاريخ", ""], rows) : emptyState("لا توجد تعيينات نظام")),
      panel("حدود السلطة", el("p", { className: "detail-lead" }, "مدير مساحة العمل والعضو لا يملكان سلطة النظام تلقائيًا. عضوية مساحة العمل مستقلة عن التعيين المعروض هنا.")),
    );
  });
  render();
  return host;
}

export const SYSTEM_CONTROL_PAGES = {
  policies: policiesPage,
  usage: usagePage,
  providers: providersPage,
  credentials: credentialsPage,
  conversations: systemConversationsPage,
  audit: auditPage,
  access: systemAccessPage,
};
