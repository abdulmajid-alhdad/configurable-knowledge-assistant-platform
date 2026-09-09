import { ApiError, getJSON, request } from "/assets/shared/api.js";
import { workspaceCache, workspaceKey } from "/assets/shared/cache.js";
import { el, isSafeInternalUrl } from "/assets/shared/dom.js";
import {
  drawer,
  emptyState,
  errorState,
  loadingState,
  statusBadge,
  toast,
} from "/assets/shared/ui.js";

const SYSTEM_CACHE_SCOPE = "SYSTEM";
const state = {
  permissions: new Set(),
  workspaces: null,
};

const ROLE_LABELS = {
  SYSTEM_ADMIN: "مدير النظام",
  WORKSPACE_MANAGER: "مدير مساحة العمل",
  MEMBER: "عضو",
};

const SOURCE_KIND_LABELS = {
  document: "مستند",
  structured: "بيانات منظّمة",
};

const SCOPE_LABELS = {
  SYSTEM: "النظام",
  WORKSPACE: "مساحة العمل",
};

const RESOURCE_LABELS = {
  api_keys: "مفاتيح API",
  assistant: "المساعدون",
  audit: "سجل النظام",
  conversations: "محادثات مساحة العمل",
  credentials: "بيانات الاعتماد",
  evaluation: "التقييم",
  governance: "الضوابط والسياسات",
  invitations: "الدعوات",
  knowledge: "مصادر المعرفة",
  members: "الأعضاء",
  notifications: "الإشعارات",
  operations: "العمليات الإدارية",
  plans: "الخطط",
  providers: "المزودون",
  roles: "الأدوار",
  security: "الأمان",
  settings: "الإعدادات",
  subscriptions: "الاشتراكات",
  system_access: "الوصول للنظام",
  system_assistants: "إدارة المساعدين",
  system_conversations: "محادثات النظام",
  system_knowledge: "إدارة المعرفة",
  system_memberships: "إدارة العضويات",
  system_workspaces: "إدارة مساحات العمل",
  teams: "الفرق",
  usage: "الاستخدام",
  workspace: "مساحات العمل",
  workspace_settings: "إعدادات مساحات العمل",
};

const ACTION_LABELS = {
  archive: "أرشفة واستعادة",
  assign: "تعيين وربط",
  create: "إنشاء",
  manage: "إدارة",
  process: "معالجة",
  read: "عرض",
  rename: "إعادة تسمية",
  update: "تعديل",
};

function currentPermissions() {
  state.permissions = new Set(window.__controlPlanePermissions || []);
  return state.permissions;
}

function can(permission) {
  return currentPermissions().has(permission);
}

function pageHeader(title, description, ...actions) {
  return el(
    "header",
    { className: "page-toolbar" },
    el(
      "div",
      { className: "page-heading" },
      el("h2", {}, title),
      description ? el("p", { className: "page-intro" }, description) : null,
    ),
    actions.length ? el("div", { className: "toolbar-actions" }, actions) : null,
  );
}

function panel(title, ...children) {
  return el(
    "section",
    { className: "panel" },
    title ? el("h2", { className: "panel-title" }, title) : null,
    ...children,
  );
}

function action(label, handler, className = "button") {
  return el("button", { className, type: "button", onclick: handler }, label);
}

function labeledControl(label, control, hint = null) {
  return el(
    "label",
    { className: "field" },
    el("span", { className: "field-label" }, label),
    control,
    hint ? el("span", { className: "field-hint" }, hint) : null,
  );
}

function infoField(label, value, { technical = false } = {}) {
  return el(
    "div",
    { className: "info-field" },
    el("dt", {}, label),
    el("dd", { className: technical ? "technical-value" : "" }, value ?? "—"),
  );
}

function technicalCode(value) {
  return value
    ? el("span", { className: "technical-code", dir: "ltr" }, String(value))
    : null;
}

function primaryCell(primary, secondary = null) {
  return el(
    "div",
    { className: "primary-cell" },
    el("strong", {}, primary || "—"),
    secondary ? el("span", { className: "secondary-meta" }, secondary) : null,
  );
}

function table(headers, rows) {
  const body = el("tbody");
  rows.forEach((row) => body.append(el("tr", {}, ...row.map((cell) => el("td", {}, cell)))));
  return el(
    "div",
    { className: "table-wrap" },
    el(
      "table",
      { className: "data-table" },
      el("thead", {}, el("tr", {}, ...headers.map((header) => el("th", {}, header)))),
      body,
    ),
  );
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatBytes(value) {
  if (value === null || value === undefined || value === "") return "—";
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} بايت`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} كيلوبايت`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} ميغابايت`;
}

function roleLabel(value) {
  return ROLE_LABELS[String(value || "").toUpperCase()] || value || "—";
}

function sourceKindLabel(value) {
  return SOURCE_KIND_LABELS[String(value || "").toLowerCase()] || value || "—";
}

function artifactAvailability(artifact) {
  if (!artifact || artifact.load_error) {
    return el("span", { className: "secondary-meta" }, "تعذر التحقق");
  }
  return statusBadge(artifact.artifact_state);
}

function showToast(message) {
  const region = document.querySelector(".toast-region");
  if (region) toast(region, message);
}

function apiError(error) {
  if (error instanceof ApiError && error.status === 401) {
    return errorState("انتهت الجلسة", "سجّل الدخول مرة أخرى للمتابعة.");
  }
  if (error instanceof ApiError && error.status === 403) {
    return errorState("الوصول غير متاح", "لا تتوفر الصلاحية النظامية المطلوبة لهذا الإجراء.");
  }
  if (error instanceof ApiError && error.status === 404) {
    return errorState("العنصر غير موجود", "قد يكون المورد تغيّر أو لم يعد متاحًا.");
  }
  if (error instanceof ApiError && error.status === 409) {
    const knownConflicts = {
      "knowledge source addition is disabled": "إضافة مصادر المعرفة متوقفة وفق السياسة التشغيلية لمساحة العمل.",
      "source processing is disabled": "معالجة مصادر المعرفة متوقفة وفق السياسة التشغيلية لمساحة العمل.",
      WORKSPACE_SUSPENDED: "مساحة العمل معلّقة، لذلك لا يمكن تنفيذ المعالجة.",
      WORKSPACE_AI_EXECUTION_DISABLED: "تنفيذ الذكاء الاصطناعي متوقف في مساحة العمل.",
      "original artifact is not stored": "لا يوجد ملف أصلي محفوظ لهذا المصدر.",
    };
    if (Object.hasOwn(knownConflicts, error.code)) {
      return errorState("تعذر تنفيذ الإجراء", knownConflicts[error.code]);
    }
    return errorState("تعذر تنفيذ الإجراء", "يتعارض الإجراء مع الحالة الحالية للمورد.");
  }
  return errorState("تعذر تحميل البيانات", "حاول مرة أخرى لاحقًا.");
}

function mutationError(error, title = "تعذر حفظ التغييرات") {
  if (error instanceof ApiError && [401, 403, 404, 409].includes(error.status)) {
    return apiError(error);
  }
  if (error instanceof ApiError && error.status === 422) {
    return errorState(title, "تحقق من الحقول المطلوبة والقيم المدخلة ثم حاول مرة أخرى.");
  }
  return errorState(title, "لم تُحفظ التغييرات. حاول مرة أخرى لاحقًا.");
}

function jsonRequest(path, method, payload) {
  return request(path, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function systemKey(resource, query = "") {
  return workspaceKey(SYSTEM_CACHE_SCOPE, resource, query);
}

function invalidate(...resources) {
  resources.forEach((resource) => workspaceCache.invalidate(systemKey(resource)));
}

function loadResource(resource, loader, host, paint) {
  const key = systemKey(resource);
  const cached = workspaceCache.get(key);
  if (cached !== undefined) paint(cached, true);
  else host.replaceChildren(loadingState("جاري تحميل البيانات…"));
  const refresh = workspaceCache.staleWhileRevalidate(key, loader, {
    isCurrent: () => host.isConnected,
    onFresh: (value) => paint(value, false),
    onError: (error) => {
      if (cached === undefined && host.isConnected) host.replaceChildren(apiError(error));
    },
  });
  refresh.refresh.catch(() => {});
}

async function workspaces() {
  if (state.workspaces) return state.workspaces;
  state.workspaces = await getJSON("/api/system/workspaces");
  return state.workspaces;
}

function refreshWorkspaces() {
  state.workspaces = null;
  invalidate("workspaces", "home", "assistants", "knowledge", "members", "teams", "roles");
}

function commitWorkspace(saved) {
  const current = state.workspaces || workspaceCache.get(systemKey("workspaces")) || [];
  const exists = current.some((item) => item.id === saved.id);
  const next = exists
    ? current.map((item) => (item.id === saved.id ? saved : item))
    : [...current, saved];
  state.workspaces = next;
  workspaceCache.set(systemKey("workspaces"), next);
  invalidate("home", "assistants", "knowledge", "members", "teams", "roles");
}

function commitAssistant(saved) {
  const key = systemKey("assistants");
  const current = workspaceCache.get(key);
  if (!current) return;
  const groups = current.groups.map((group) => {
    if (group.workspace.id !== saved.workspace_id) return group;
    const exists = group.items.some((item) => item.id === saved.id);
    return {
      ...group,
      items: exists
        ? group.items.map((item) => (item.id === saved.id ? saved : item))
        : [...group.items, saved],
    };
  });
  workspaceCache.set(key, { ...current, groups });
}

function commitSource(saved) {
  const key = systemKey("knowledge");
  const current = workspaceCache.get(key);
  if (!current) return;
  const groups = current.groups.map((group) => {
    if (group.workspace.id !== saved.workspace_id) return group;
    const exists = group.items.some((item) => item.id === saved.id);
    return {
      ...group,
      items: exists
        ? group.items.map((item) => (item.id === saved.id ? saved : item))
        : [...group.items, saved],
    };
  });
  workspaceCache.set(key, { ...current, groups });
}

function workspaceSelect(items, selectedId, onChange, label = "مساحة العمل") {
  const select = el(
    "select",
    {
      onchange: () => onChange(select.value),
      "aria-label": label,
    },
    ...items.map((item) =>
      el("option", { value: item.id, selected: item.id === selectedId ? "selected" : null }, item.name),
    ),
  );
  return labeledControl(label, select);
}

function renderPermissionDenied(title) {
  return errorState(title, "لا تتوفر الصلاحية النظامية اللازمة لهذا الإجراء.");
}

function metric(label, value, note) {
  return el(
    "article",
    { className: "metric-card" },
    el("span", { className: "metric-label" }, label),
    el("strong", { className: "metric-value" }, String(value)),
    note ? el("span", { className: "metric-note" }, note) : null,
  );
}

function confirmDrawer(title, message, confirmLabel, onConfirm) {
  const content = el(
    "div",
    { className: "stack" },
    el("p", { className: "detail-lead" }, message),
  );
  const confirm = action(confirmLabel, async () => {
    confirm.disabled = true;
    try {
      await onConfirm();
      modal.close();
    } catch (error) {
      confirm.disabled = false;
      content.append(apiError(error));
    }
  });
  content.append(el("div", { className: "form-actions" }, confirm));
  const modal = drawer(title, content);
  return modal;
}

async function aggregateWorkspaceResources(items, permission, pathSuffix) {
  if (!can(permission)) return null;
  const lists = await Promise.all(
    items.map((workspace) => getJSON(`/api/system/workspaces/${workspace.id}/${pathSuffix}`)),
  );
  return lists.reduce((total, list) => total + list.length, 0);
}

export function homePage() {
  const host = el("div", { className: "route-panel" });
  loadResource(
    "home",
    async () => {
      const workspaceItems = await workspaces();
      const [assistants, sources, members] = await Promise.all([
        aggregateWorkspaceResources(workspaceItems, "system_assistants.read", "assistants"),
        aggregateWorkspaceResources(workspaceItems, "system_knowledge.read", "sources"),
        aggregateWorkspaceResources(workspaceItems, "system_memberships.read", "members"),
      ]);
      return { workspaces: workspaceItems, assistants, sources, members };
    },
    host,
    (data) => {
      const metrics = [metric("مساحات العمل", data.workspaces.length, "مساحة مسجّلة في المنصة")];
      if (data.assistants !== null) metrics.push(metric("المساعدون", data.assistants, "مساعد عبر مساحات العمل"));
      if (data.sources !== null) metrics.push(metric("مصادر المعرفة", data.sources, "مصدر مسجّل"));
      if (data.members !== null) metrics.push(metric("العضويات", data.members, "عضوية مساحة عمل"));
      host.replaceChildren(
        pageHeader("الرئيسية", "ملخص تنظيمي مستمد من بيانات المنصة الفعلية."),
        el("section", { className: "metrics-grid system-metrics", "aria-label": "ملخص إدارة النظام" }, metrics),
      );
    },
  );
  return host;
}

function workspaceForm(item, onSaved) {
  const name = el("input", { value: item?.name || "", required: "required", maxlength: "200" });
  const status = el(
    "select",
    {},
    el("option", { value: "ACTIVE", selected: item?.operational_status !== "SUSPENDED" ? "selected" : null }, "نشطة"),
    el("option", { value: "SUSPENDED", selected: item?.operational_status === "SUSPENDED" ? "selected" : null }, "معلّقة"),
  );
  const ai = el("input", {
    type: "checkbox",
    checked: item ? (item.ai_execution_enabled ? "checked" : null) : "checked",
  });
  const syncState = () => {
    if (status.value === "SUSPENDED") {
      ai.checked = false;
      ai.disabled = true;
    } else {
      ai.disabled = false;
    }
  };
  status.addEventListener("change", syncState);
  syncState();
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    labeledControl("اسم مساحة العمل", name),
    item ? labeledControl("الحالة التشغيلية", status) : null,
    el(
      "label",
      { className: "toggle-field" },
      ai,
      el("span", {}, "السماح بتنفيذ الذكاء الاصطناعي"),
      el(
        "small",
        {},
        item
          ? "يمكن تعطيله مع بقاء مساحة العمل نشطة. تعليق مساحة العمل يعطّله دائمًا."
          : "مفعّل افتراضيًا وفق إعداد الخادم، ويمكن إنشاء مساحة عمل نشطة مع تعطيله.",
      ),
    ),
    feedback,
  );
  const save = action(item ? "حفظ التغييرات" : "إنشاء مساحة العمل", async () => {
    const normalized = name.value.trim();
    if (!normalized) return;
    save.disabled = true;
    feedback.replaceChildren();
    try {
      let saved;
      if (item) {
        saved = await jsonRequest(`/api/system/workspaces/${item.id}`, "PATCH", {
          name: normalized,
          operational_status: status.value,
          ai_execution_enabled: ai.checked,
        });
      } else {
        saved = await jsonRequest("/api/system/workspaces", "POST", {
          name: normalized,
          ai_execution_enabled: ai.checked,
        });
      }
      commitWorkspace(saved);
      showToast(item ? "تم تحديث مساحة العمل." : "تم إنشاء مساحة العمل.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(mutationError(error));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(item ? "إدارة مساحة العمل" : "مساحة عمل جديدة", form);
  name.focus();
}

function workspaceDetails(item, onSaved) {
  const content = el(
    "div",
    { className: "stack" },
    el(
      "dl",
      { className: "info-grid" },
      infoField("الحالة", statusBadge(item.operational_status)),
      infoField("تنفيذ الذكاء الاصطناعي", item.ai_execution_enabled ? "مسموح" : "متوقف"),
      infoField("المعرّف التقني", item.id, { technical: true }),
    ),
  );
  if (
    can("workspace.manage")
    && can("governance.manage")
    && can("workspace_settings.manage")
    && can("settings.read")
  ) {
    content.append(action("تعديل الإعدادات", () => {
      details.close();
      workspaceForm(item, onSaved);
    }));
  }
  const details = drawer(item.name, content);
}

export function workspacesPage() {
  const host = el("div", { className: "route-panel" });
  const render = () => loadResource("workspaces", workspaces, host, (items) => {
    const create = can("workspace.manage")
      ? action("مساحة عمل جديدة", () => workspaceForm(null, render))
      : null;
    const content = items.length
      ? table(
          ["مساحة العمل", "الحالة", "تنفيذ الذكاء الاصطناعي", ""],
          items.map((item) => [
            primaryCell(item.name, item.id),
            statusBadge(item.operational_status),
            el("span", { className: `capability-state ${item.ai_execution_enabled ? "enabled" : "disabled"}` }, item.ai_execution_enabled ? "مسموح" : "متوقف"),
            action("عرض وإدارة", () => workspaceDetails(item, render), "button secondary small"),
          ]),
        )
      : emptyState("لا توجد مساحات عمل", "أنشئ مساحة العمل الأولى لبدء تنظيم موارد المنصة.");
    host.replaceChildren(
      pageHeader("مساحات العمل", "إدارة دورة حياة مساحات العمل وحالة تنفيذ الذكاء الاصطناعي.", create),
      panel(null, content),
    );
  });
  render();
  return host;
}

async function allAssistants() {
  const workspaceItems = await workspaces();
  const groups = await Promise.all(
    workspaceItems.map(async (workspace) => ({
      workspace,
      items: await getJSON(`/api/system/workspaces/${workspace.id}/assistants`),
    })),
  );
  return { workspaces: workspaceItems, groups };
}

function assistantForm(workspaceItems, item, onSaved) {
  const workspaceId = el(
    "select",
    { disabled: item ? "disabled" : null },
    ...workspaceItems.map((workspace) =>
      el("option", { value: workspace.id, selected: workspace.id === item?.workspace_id ? "selected" : null }, workspace.name),
    ),
  );
  const name = el("input", { value: item?.name || "", required: "required" });
  const description = el("textarea", { rows: "3" }, item?.description || "");
  const instructions = el("textarea", { rows: "6", required: "required" }, item?.instructions || "");
  const language = el("input", { value: item?.language || "ar", required: "required", dir: "ltr" });
  const provider = el("input", { value: item?.provider || "", required: "required", dir: "ltr" });
  const model = el("input", { value: item?.model_reference || "", required: "required", dir: "ltr" });
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    labeledControl("مساحة العمل", workspaceId, item ? "يبقى المساعد ضمن مساحة العمل المعيّنة له." : null),
    labeledControl("اسم المساعد", name),
    labeledControl("الوصف", description),
    labeledControl("التعليمات الإدارية", instructions),
    el(
      "div",
      { className: "form-grid" },
      labeledControl("اللغة", language),
      labeledControl("المزود", provider),
    ),
    labeledControl("مرجع النموذج", model),
    feedback,
  );
  const save = action(item ? "حفظ إعدادات المساعد" : "إنشاء المساعد", async () => {
    if (!form.reportValidity()) return;
    const payload = {
      name: name.value.trim(),
      description: description.value.trim() || null,
      instructions: instructions.value.trim(),
      language: language.value.trim(),
      provider: provider.value.trim(),
      model_reference: model.value.trim(),
    };
    if (!payload.name || !payload.instructions || !payload.language || !payload.provider || !payload.model_reference) {
      feedback.replaceChildren(errorState("الحقول المطلوبة غير مكتملة", "أكمل بيانات المساعد المطلوبة قبل الحفظ."));
      return;
    }
    save.disabled = true;
    feedback.replaceChildren();
    try {
      const base = `/api/system/workspaces/${workspaceId.value}/assistants`;
      const saved = await jsonRequest(item ? `${base}/${item.id}` : base, item ? "PATCH" : "POST", payload);
      commitAssistant(saved);
      invalidate("home");
      showToast(item ? "تم تحديث إعدادات المساعد." : "تم إنشاء المساعد.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(mutationError(error, item ? "تعذر حفظ إعدادات المساعد" : "تعذر إنشاء المساعد"));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(item ? "إعدادات المساعد" : "مساعد جديد", form);
  name.focus();
}

async function assistantBindings(item) {
  const [sources, attached] = await Promise.all([
    getJSON(`/api/system/workspaces/${item.workspace_id}/sources`),
    getJSON(`/api/system/workspaces/${item.workspace_id}/assistants/${item.id}/sources`),
  ]);
  return { sources, attachedIds: new Set(attached.map((source) => source.id)) };
}

function bindingManager(item) {
  const content = el("div", { className: "stack" }, loadingState("جاري تحميل مصادر مساحة العمل…"));
  const modal = drawer(`ربط المعرفة — ${item.name}`, content);
  const paint = ({ sources, attachedIds }) => {
    const rows = el("div", { className: "selection-list" });
    if (!sources.length) rows.append(emptyState("لا توجد مصادر", "لا توجد مصادر معرفة في مساحة عمل هذا المساعد."));
    sources.forEach((source) => {
      const attached = attachedIds.has(source.id);
      const toggle = action(attached ? "إلغاء الربط" : "ربط المصدر", async () => {
        toggle.disabled = true;
        try {
          await request(
            `/api/system/workspaces/${item.workspace_id}/assistants/${item.id}/sources/${source.id}`,
            { method: attached ? "DELETE" : "POST" },
          );
          const updatedIds = new Set(attachedIds);
          if (attached) updatedIds.delete(source.id);
          else updatedIds.add(source.id);
          invalidate("assistants", "knowledge");
          showToast(attached ? "تم إلغاء ربط المصدر." : "تم ربط المصدر.");
          paint({ sources, attachedIds: updatedIds });
        } catch (error) {
          toggle.disabled = false;
          rows.append(mutationError(error, attached ? "تعذر إلغاء الربط" : "تعذر ربط المصدر"));
        }
      }, attached ? "button secondary small" : "button small");
      rows.append(el(
        "article",
        { className: "selection-row" },
        primaryCell(source.name, sourceKindLabel(source.kind)),
        el("div", { className: "inline-actions" }, statusBadge(source.lifecycle), toggle),
      ));
    });
    content.replaceChildren(
      el("p", { className: "detail-lead" }, "تظهر هنا مصادر مساحة العمل نفسها فقط؛ ويرفض الخادم أي ربط عابر لمساحات العمل."),
      rows,
    );
  };
  assistantBindings(item).then(paint).catch((error) => content.replaceChildren(apiError(error)));
  return modal;
}

function assistantDetails(item, workspaceName, workspacesList, onSaved) {
  const content = el(
    "div",
    { className: "stack" },
    el("p", { className: "detail-lead" }, item.description || "لا يتوفر وصف لهذا المساعد."),
    el(
      "dl",
      { className: "info-grid" },
      infoField("مساحة العمل", workspaceName),
      infoField("اللغة", item.language),
      infoField("المزود", item.provider, { technical: true }),
      infoField("مرجع النموذج", item.model_reference, { technical: true }),
      infoField("المعرّف التقني", item.id, { technical: true }),
    ),
    el("section", { className: "instruction-preview" }, el("h3", {}, "التعليمات"), el("p", {}, item.instructions)),
  );
  const actions = el("div", { className: "form-actions" });
  if (can("assistant.update")) {
    actions.append(action("تعديل الإعدادات", () => {
      detail.close();
      assistantForm(workspacesList, item, onSaved);
    }));
  }
  if (can("knowledge.attach") && can("system_knowledge.read")) {
    actions.append(action("إدارة مصادر المعرفة", () => bindingManager(item), "button secondary"));
  }
  if (actions.childElementCount) content.append(actions);
  const detail = drawer(item.name, content);
}

export function assistantsPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = "all";
  const render = () => loadResource("assistants", allAssistants, host, (data) => {
    const all = data.groups.flatMap(({ workspace, items }) =>
      items.map((item) => ({ ...item, workspace_name: workspace.name })),
    );
    const paintRows = (container) => {
      const visible = selectedWorkspace === "all"
        ? all
        : all.filter((item) => item.workspace_id === selectedWorkspace);
      container.replaceChildren(
        visible.length
          ? table(
              ["المساعد", "مساحة العمل", "اللغة", "النموذج", ""],
              visible.map((item) => [
                primaryCell(item.name, item.description || "لا يتوفر وصف"),
                item.workspace_name,
                item.language,
                technicalCode(item.model_reference),
                action("عرض", () => assistantDetails(item, item.workspace_name, data.workspaces, render), "button secondary small"),
              ]),
            )
          : emptyState("لا توجد مساعدات", "لا تتوفر مساعدات في النطاق المحدد."),
      );
    };
    const filter = el(
      "select",
      {
        onchange: () => {
          selectedWorkspace = filter.value;
          paintRows(rows);
        },
        "aria-label": "تصفية حسب مساحة العمل",
      },
      el("option", { value: "all" }, "كل مساحات العمل"),
      ...data.workspaces.map((workspace) => el("option", { value: workspace.id }, workspace.name)),
    );
    filter.value = selectedWorkspace;
    const rows = el("div");
    const create = can("assistant.create")
      ? action("مساعد جديد", () => assistantForm(data.workspaces, null, render))
      : null;
    host.replaceChildren(
      pageHeader("المساعدون والربط", "إدارة المساعدين وإعداداتهم وربطهم بمصادر المعرفة ضمن مساحة العمل نفسها.", create),
      panel("التصفية", labeledControl("مساحة العمل", filter)),
      panel("المساعدون", rows),
    );
    paintRows(rows);
  });
  render();
  return host;
}

async function allSources() {
  const workspaceItems = await workspaces();
  const groups = await Promise.all(
    workspaceItems.map(async (workspace) => {
      const sources = await getJSON(`/api/system/workspaces/${workspace.id}/sources`);
      const items = await Promise.all(sources.map(async (source) => {
        try {
          const artifact = await getJSON(
            `/api/system/workspaces/${workspace.id}/sources/${source.id}/artifact`,
          );
          return { ...source, artifact };
        } catch {
          return { ...source, artifact: { load_error: true } };
        }
      }));
      return { workspace, items };
    }),
  );
  return { workspaces: workspaceItems, groups };
}

function createSourceForm(workspaceItems, onSaved) {
  const workspaceId = el("select", {}, ...workspaceItems.map((workspace) => el("option", { value: workspace.id }, workspace.name)));
  const name = el("input", { required: "required", maxlength: "200" });
  const kind = el(
    "select",
    {},
    el("option", { value: "document" }, "مستند"),
    el("option", { value: "structured" }, "بيانات منظّمة"),
  );
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    labeledControl("مساحة العمل المستهدفة", workspaceId),
    labeledControl("اسم المصدر", name),
    labeledControl("نوع المصدر", kind),
    feedback,
  );
  const save = action("إنشاء المصدر", async () => {
    if (!name.value.trim()) return;
    save.disabled = true;
    feedback.replaceChildren();
    try {
      const saved = await jsonRequest(`/api/system/workspaces/${workspaceId.value}/sources`, "POST", {
        name: name.value.trim(),
        kind: kind.value,
      });
      commitSource(saved);
      invalidate("home");
      showToast("تم إنشاء مصدر المعرفة.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(mutationError(error, "تعذر إنشاء مصدر المعرفة"));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer("مصدر معرفة جديد", form);
  name.focus();
}

async function sourceAssistantBindings(source) {
  const assistants = await getJSON(`/api/system/workspaces/${source.workspace_id}/assistants`);
  const attachedPairs = await Promise.all(
    assistants.map(async (assistant) => ({
      assistant,
      sources: await getJSON(`/api/system/workspaces/${source.workspace_id}/assistants/${assistant.id}/sources`),
    })),
  );
  return attachedPairs.map(({ assistant, sources }) => ({
    assistant,
    attached: sources.some((item) => item.id === source.id),
  }));
}

function sourceBindings(source) {
  const content = el("div", { className: "stack" }, loadingState("جاري تحميل مساعدات مساحة العمل…"));
  const modal = drawer(`ربط المصدر — ${source.name}`, content);
  const paint = (bindings) => {
    const rows = el("div", { className: "selection-list" });
    if (!bindings.length) rows.append(emptyState("لا توجد مساعدات", "لا توجد مساعدات في مساحة عمل هذا المصدر."));
    bindings.forEach(({ assistant, attached }) => {
      const toggle = action(attached ? "إلغاء الربط" : "ربط", async () => {
        toggle.disabled = true;
        try {
          await request(
            `/api/system/workspaces/${source.workspace_id}/assistants/${assistant.id}/sources/${source.id}`,
            { method: attached ? "DELETE" : "POST" },
          );
          const updated = bindings.map((binding) => (
            binding.assistant.id === assistant.id
              ? { ...binding, attached: !attached }
              : binding
          ));
          invalidate("assistants", "knowledge");
          showToast(attached ? "تم إلغاء الربط." : "تم الربط.");
          paint(updated);
        } catch (error) {
          toggle.disabled = false;
          rows.append(mutationError(error, attached ? "تعذر إلغاء الربط" : "تعذر ربط المصدر"));
        }
      }, attached ? "button secondary small" : "button small");
      rows.append(el("article", { className: "selection-row" }, primaryCell(assistant.name, assistant.description), toggle));
    });
    content.replaceChildren(
      el("p", { className: "detail-lead" }, "لا يُتاح الربط إلا مع مساعدات مساحة عمل المصدر نفسها."),
      rows,
    );
  };
  sourceAssistantBindings(source).then(paint).catch((error) => content.replaceChildren(apiError(error)));
  return modal;
}

function sourceDetails(source, workspaceName, onSaved) {
  const artifactStatusHost = el(
    "span",
    {},
    artifactAvailability(source.artifact),
  );
  const content = el(
    "div",
    { className: "stack" },
    el(
      "dl",
      { className: "info-grid" },
      infoField("مساحة العمل", workspaceName),
      infoField("النوع", sourceKindLabel(source.kind)),
      infoField("حالة المعالجة", statusBadge(source.lifecycle)),
      infoField("توفر الملف الأصلي", artifactStatusHost),
      infoField("المعرّف التقني", source.id, { technical: true }),
    ),
    String(source.lifecycle || "").toUpperCase() === "FAILED"
      ? el(
          "p",
          { className: "field-hint" },
          "تعكس حالة «فشل» آخر محاولة معالجة؛ ولا تعني وحدها فشل رفع الملف الأصلي.",
        )
      : null,
  );
  const artifactHost = el(
    "section",
    { className: "detail-actions" },
    el("h3", {}, "الملف الأصلي"),
    loadingState("جاري التحقق من ملف المصدر…"),
  );
  const processingHost = el("div", { className: "form-actions" });
  content.append(artifactHost, processingHost);

  const paintProcessing = (artifact) => {
    processingHost.replaceChildren();
    if (!artifact.artifact_present || !can("system_knowledge.process")) return;
    const reprocess = String(source.lifecycle || "").toUpperCase() === "READY";
    processingHost.append(action(reprocess ? "إعادة معالجة المصدر" : "معالجة المصدر", () => confirmDrawer(
      reprocess ? "تأكيد إعادة المعالجة" : "تأكيد المعالجة",
      "يتحقق الخادم من حالة مساحة العمل وتنفيذ الذكاء الاصطناعي وضوابط الأمان قبل أي استخدام لموارد المزود.",
      reprocess ? "بدء إعادة المعالجة" : "بدء المعالجة",
      async () => {
        await request(`/api/system/workspaces/${source.workspace_id}/sources/${source.id}/process`, { method: "POST" });
        invalidate("knowledge");
        showToast(reprocess ? "اكتملت إعادة معالجة المصدر." : "اكتملت معالجة المصدر.");
        detail.close();
        onSaved();
      },
    )));
  };

  const paintArtifact = (artifact) => {
    artifactStatusHost.replaceChildren(artifactAvailability(artifact));
    const heading = el("h3", {}, "الملف الأصلي");
    if (artifact.artifact_present) {
      const filename = artifact.original_filename;
      artifactHost.replaceChildren(
        heading,
        el(
          "div",
          { className: "artifact-present" },
          el(
            "div",
            { className: "artifact-identity" },
            el("span", { className: "artifact-identity-label" }, "اسم الملف الأصلي"),
            filename
              ? el("strong", { className: "artifact-filename", dir: "auto" }, filename)
              : el("span", { className: "secondary-meta" }, "اسم الملف غير متاح"),
          ),
          el(
            "dl",
            { className: "artifact-metadata" },
            infoField(
              "نوع المحتوى",
              artifact.media_type ? technicalCode(artifact.media_type) : "غير متاح",
            ),
            infoField("الحجم", formatBytes(artifact.byte_size)),
            artifact.stored_at ? infoField("تاريخ الحفظ", formatDate(artifact.stored_at)) : null,
            artifact.suffix ? infoField("الامتداد التقني", technicalCode(artifact.suffix)) : null,
          ),
        ),
      );
      paintProcessing(artifact);
      return;
    }
    paintProcessing(artifact);
    const legacyUnavailable = artifact.artifact_state === "LEGACY_UNAVAILABLE";
    const unavailableTitle = legacyUnavailable
      ? "لا يتوفر الملف الأصلي المحفوظ لهذا المصدر."
      : artifact.artifact_state === "AWAITING_UPLOAD"
        ? "بانتظار رفع الملف الأصلي"
        : "لا يوجد ملف أصلي";
    const unavailableDescription = legacyUnavailable
      ? "المعرفة المفهرسة الحالية متاحة، لكن إعادة المعالجة تتطلب إرفاق الملف الأصلي أولًا."
      : "ارفع الملف الأصلي مرة واحدة قبل بدء معالجة المصدر.";
    if (!can("system_knowledge.create")) {
      artifactHost.replaceChildren(
        heading,
        emptyState(unavailableTitle, unavailableDescription),
      );
      return;
    }
    if (!artifact.upload_allowed) {
      artifactHost.replaceChildren(
        heading,
        emptyState(unavailableTitle, unavailableDescription),
      );
      return;
    }
    let selectedFile = null;
    const file = el("input", {
      type: "file",
      className: "file-input",
      accept: ".txt,.md,.markdown,.json,.docx,.pdf",
      onchange: () => {
        selectedFile = file.files?.[0] || null;
        upload.disabled = !selectedFile;
      },
    });
    const uploadFeedback = el("div", { className: "form-feedback" });
    const upload = action(legacyUnavailable ? "إرفاق الملف الأصلي" : "رفع الملف الأصلي", async () => {
      if (!selectedFile) return;
      upload.disabled = true;
      uploadFeedback.replaceChildren();
      try {
        const stored = await request(
          `/api/system/workspaces/${source.workspace_id}/sources/${source.id}/upload`,
          {
            method: "POST",
            headers: {
              "x-file-name": encodeURIComponent(selectedFile.name),
              "x-file-name-encoding": "percent",
              "content-type": selectedFile.type || "application/octet-stream",
            },
            body: selectedFile,
          },
        );
        invalidate("knowledge");
        source.artifact = stored;
        paintArtifact(stored);
        showToast(legacyUnavailable ? "تم إرفاق ملف المصدر الأصلي." : "تم رفع ملف المصدر الأصلي.");
      } catch (error) {
        upload.disabled = false;
        uploadFeedback.replaceChildren(
          mutationError(error, "تعذر رفع الملف الأصلي"),
        );
      }
    });
    upload.disabled = true;
    artifactHost.replaceChildren(
      heading,
      el("strong", { className: "artifact-state-title" }, unavailableTitle),
      el("p", { className: "field-hint" }, legacyUnavailable
        ? "يمكن إرفاق الملف الأصلي المفقود مرة واحدة. لا يغيّر الإرفاق التمثيلات الحالية؛ إعادة المعالجة إجراء مستقل."
        : "يمكن رفع الملف الأصلي مرة واحدة؛ لا تتيح هذه الواجهة استبداله بصمت."),
      el("div", { className: "file-picker" }, file, upload),
      uploadFeedback,
    );
  };

  if (source.artifact && !source.artifact.load_error) paintArtifact(source.artifact);
  getJSON(`/api/system/workspaces/${source.workspace_id}/sources/${source.id}/artifact`)
    .then((artifact) => {
      source.artifact = artifact;
      paintArtifact(artifact);
    })
    .catch((error) => {
      processingHost.replaceChildren();
      artifactHost.replaceChildren(el("h3", {}, "الملف الأصلي"), apiError(error));
    });

  const actions = el("div", { className: "form-actions" });
  if (can("knowledge.attach") && can("system_assistants.read")) {
    actions.append(action("إدارة ربط المساعدين", () => sourceBindings(source), "button secondary"));
  }
  if (actions.childElementCount) content.append(actions);
  const detail = drawer(source.name, content);
}

export function knowledgePage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = "all";
  const render = () => loadResource("knowledge", allSources, host, (data) => {
    const all = data.groups.flatMap(({ workspace, items }) =>
      items.map((item) => ({ ...item, workspace_name: workspace.name })),
    );
    const rows = el("div");
    const paintRows = () => {
      const visible = selectedWorkspace === "all" ? all : all.filter((item) => item.workspace_id === selectedWorkspace);
      rows.replaceChildren(
        visible.length
          ? table(
              ["المصدر", "مساحة العمل", "النوع", "حالة المعالجة", "الملف الأصلي", ""],
              visible.map((source) => [
                primaryCell(source.name, source.id),
                source.workspace_name,
                primaryCell(sourceKindLabel(source.kind), source.kind),
                statusBadge(source.lifecycle),
                artifactAvailability(source.artifact),
                action("عرض وإدارة", () => sourceDetails(source, source.workspace_name, render), "button secondary small"),
              ]),
            )
          : emptyState("لا توجد مصادر", "لا تتوفر مصادر معرفة في النطاق المحدد."),
      );
    };
    const filter = el(
      "select",
      { onchange: () => { selectedWorkspace = filter.value; paintRows(); } },
      el("option", { value: "all" }, "كل مساحات العمل"),
      ...data.workspaces.map((workspace) => el("option", { value: workspace.id }, workspace.name)),
    );
    filter.value = selectedWorkspace;
    const create = can("system_knowledge.create")
      ? action("مصدر معرفة جديد", () => createSourceForm(data.workspaces, render))
      : null;
    host.replaceChildren(
      pageHeader("مصادر المعرفة", "إدارة المصادر ومعالجتها وربطها داخل حدود مساحة العمل المستهدفة.", create),
      panel("التصفية", labeledControl("مساحة العمل", filter)),
      panel("المصادر", rows),
    );
    paintRows();
  });
  render();
  return host;
}

async function workspaceAccessData(workspaceId) {
  const [members, roles, invitations] = await Promise.all([
    getJSON(`/api/system/workspaces/${workspaceId}/members`),
    can("roles.read")
      ? getJSON(`/api/system/workspaces/${workspaceId}/roles`)
      : Promise.resolve([]),
    can("invitations.read") ? getJSON(`/api/system/workspaces/${workspaceId}/invitations`) : Promise.resolve([]),
  ]);
  return { members, roles, invitations };
}

function provisioningError(error) {
  if (!(error instanceof ApiError)) return mutationError(error, "تعذر إنشاء المستخدم");
  const messages = {
    IDENTITY_ALREADY_EXISTS: "يوجد حساب بهذا البريد الإلكتروني. إدارة عضوية مستخدم موجود إجراء مستقل.",
    INVITATION_ALREADY_PENDING: "توجد دعوة تفعيل سارية لهذا البريد الإلكتروني.",
    TEAM_WORKSPACE_MISMATCH: "يجب أن ينتمي الفريق إلى مساحة العمل المحددة.",
    WORKSPACE_ROLE_INVALID: "الدور المحدد ليس دور مساحة عمل صالحًا.",
    IDENTITY_INPUT_REJECTED: "رفضت خدمة الهوية بيانات الحساب. راجع البريد وكلمة المرور.",
    SECURITY_POLICY_DENIED: "إنشاء الدعوات متوقف وفق إعدادات الأمان لمساحة العمل.",
    INVITATION_EXPIRY_EXCEEDS_POLICY: "مدة الدعوة تتجاوز الحد المسموح لمساحة العمل.",
    IDENTITY_ADMIN_NOT_CONFIGURED: "خدمة إدارة الهوية غير مفعلة في بيئة التشغيل.",
    IDENTITY_PROVIDER_FAILURE: "تعذر الاتصال بخدمة الهوية. لم تكتمل عملية الإنشاء.",
    IDENTITY_COMPENSATION_FAILED: "تعذر إكمال الإنشاء أو التراجع الآمن. يلزم تدخل تشغيلي.",
  };
  return errorState(
    "تعذر إنشاء المستخدم",
    messages[error.code] || "لم يتم تجهيز الحساب أو العضوية. راجع البيانات وحاول مرة أخرى.",
  );
}

function provisioningForm(workspaceItems, initialWorkspaceId, onSaved) {
  const username = el("input", { required: "required", maxlength: "120", autocomplete: "off" });
  const email = el("input", { type: "email", required: "required", dir: "ltr", autocomplete: "off" });
  const password = el("input", {
    type: "password",
    required: "required",
    minlength: "8",
    maxlength: "256",
    autocomplete: "new-password",
  });
  const workspace = el(
    "select",
    { required: "required" },
    el("option", { value: "", disabled: "disabled" }, "اختر مساحة العمل"),
    ...workspaceItems.map((item) => el("option", { value: item.id }, item.name)),
  );
  workspace.value = initialWorkspaceId || "";
  const role = el("select", { required: "required", disabled: "disabled" });
  const team = el("select", { disabled: "disabled" });
  const expiry = el("input", { type: "number", min: "1", max: "90", value: "7", required: "required" });
  const optionsFeedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  let optionsWorkspace = null;

  const refreshOptions = async () => {
    const workspaceId = workspace.value;
    optionsWorkspace = null;
    role.disabled = true;
    team.disabled = true;
    role.replaceChildren(el("option", { value: "" }, "جاري تحميل الأدوار…"));
    team.replaceChildren(el("option", { value: "" }, "بدون فريق"));
    optionsFeedback.replaceChildren();
    if (!workspaceId) return;
    try {
      const [roles, teams] = await Promise.all([
        getJSON(`/api/system/workspaces/${workspaceId}/roles`),
        can("teams.read")
          ? getJSON(`/api/system/workspaces/${workspaceId}/teams`)
          : Promise.resolve([]),
      ]);
      if (workspace.value !== workspaceId) return;
      const workspaceRoles = roles.filter((item) =>
        item.status === "active"
        && ["built_in", "custom"].includes(item.role_kind)
        && item.canonical_scope === "WORKSPACE"
        && String(item.name).toUpperCase() !== "SYSTEM_ADMIN"
      );
      role.replaceChildren(
        el("option", { value: "", disabled: "disabled", selected: "selected" }, "اختر دور مساحة العمل"),
        ...workspaceRoles.map((item) => el("option", { value: item.id }, roleLabel(item.name))),
      );
      team.replaceChildren(
        el("option", { value: "" }, "بدون فريق"),
        ...teams.map((item) => el("option", { value: item.id }, item.name)),
      );
      role.disabled = !workspaceRoles.length;
      team.disabled = !can("teams.read");
      optionsWorkspace = workspaceId;
    } catch (error) {
      optionsFeedback.replaceChildren(apiError(error));
    }
  };

  workspace.addEventListener("change", refreshOptions);
  const form = el(
    "form",
    { className: "source-create-form" },
    labeledControl("اسم المستخدم", username),
    labeledControl("البريد الإلكتروني", email),
    labeledControl(
      "كلمة المرور الأولية",
      password,
      "لا تُحفظ في بيانات المنصة ولا تظهر بعد إنشاء الحساب.",
    ),
    labeledControl("مساحة العمل", workspace),
    labeledControl("دور مساحة العمل", role),
    labeledControl("الفريق (اختياري)", team, "تظهر فقط فرق مساحة العمل المحددة."),
    labeledControl("مدة صلاحية الدعوة بالأيام", expiry),
    optionsFeedback,
    feedback,
  );
  const save = action("إنشاء المستخدم", async () => {
    if (!form.reportValidity() || optionsWorkspace !== workspace.value) return;
    save.disabled = true;
    feedback.replaceChildren();
    try {
      const invitation = await jsonRequest("/api/system/identity/provision", "POST", {
        username: username.value.trim(),
        email: email.value.trim(),
        password: password.value,
        workspace_id: workspace.value,
        role_id: role.value,
        team_id: team.value || null,
        expires_in_days: Number(expiry.value),
      });
      password.value = "";
      if (!isSafeInternalUrl(invitation.activation_path)) {
        throw new ApiError(0, "INVALID_ACTIVATION_URL");
      }
      const activationUrl = new URL(invitation.activation_path, window.location.origin).href;
      const linkValue = el("input", {
        className: "one-time-link",
        value: activationUrl,
        readonly: "readonly",
        dir: "ltr",
        "aria-label": "رابط تفعيل الحساب",
      });
      const copy = action("نسخ رابط التفعيل", async () => {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(activationUrl);
          showToast("تم نسخ رابط التفعيل.");
        } else {
          linkValue.select();
        }
      }, "button secondary");
      form.replaceChildren(
        el("div", { className: "one-time-result", role: "status" },
          el("strong", {}, "تم تجهيز الحساب غير المفعّل"),
          el("p", {}, "سلّم كلمة المرور للمستخدم عبر قناة موثوقة منفصلة."),
          el("span", { className: "field-label" }, "رابط التفعيل (يظهر مرة واحدة)"),
          linkValue,
          el("div", { className: "form-actions" }, copy),
          el("p", { className: "field-hint" }, "الرابط للتفعيل فقط؛ لا يسجّل الدخول ولا ينشئ جلسة."),
        ),
      );
      invalidate(`members:${invitation.workspace_id}`);
      showToast("تم إنشاء المستخدم ودعوة التفعيل.");
      onSaved(invitation.workspace_id);
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(provisioningError(error));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer("إنشاء مستخدم", form);
  refreshOptions();
  username.focus();
  return modal;
}

function memberRoleForm(workspaceId, member, roles, onSaved) {
  const selectable = roles.filter((role) => role.status === "active" && role.role_kind !== "legacy");
  const role = el("select", {}, ...selectable.map((item) => el("option", {
    value: item.id,
    selected: item.id === member.role_id ? "selected" : null,
  }, roleLabel(item.name))));
  const feedback = el("div", { className: "form-feedback" });
  const content = el(
    "div",
    { className: "stack" },
    primaryCell(member.display_name || member.email, member.email),
    labeledControl("دور مساحة العمل", role),
    feedback,
  );
  const save = action("حفظ الدور", async () => {
    save.disabled = true;
    try {
      await jsonRequest(`/api/system/workspaces/${workspaceId}/members/${member.user_id}`, "PATCH", { role_id: role.value });
      invalidate("members");
      showToast("تم تحديث دور العضوية.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error));
    }
  });
  content.append(el("div", { className: "form-actions" }, save));
  const modal = drawer("تعديل دور العضوية", content);
}

export function membersPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaceItems = await workspaces();
      selectedWorkspace = selectedWorkspace || workspaceItems[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("الأعضاء والعضويات", "إدارة عضويات مساحات العمل."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const resource = `members:${selectedWorkspace}`;
      loadResource(resource, () => workspaceAccessData(selectedWorkspace), host, (data) => {
        const workspace = workspaceItems.find((item) => item.id === selectedWorkspace);
        const membersTable = data.members.length
          ? table(
              ["العضو", "الدور", "الفرق", "الحالة", "تاريخ الانضمام", ""],
              data.members.map((member) => {
                const actions = el("div", { className: "inline-actions" });
                if (can("members.manage") && can("roles.read")) {
                  actions.append(
                    action("تغيير الدور", () => memberRoleForm(selectedWorkspace, member, data.roles, render), "button secondary small"),
                    action("إزالة العضوية", () => confirmDrawer(
                      "إزالة العضوية",
                      `سيتم إلغاء عضوية ${member.display_name || member.email} من مساحة العمل.`,
                      "تأكيد الإزالة",
                      async () => {
                        await request(`/api/system/workspaces/${selectedWorkspace}/members/${member.user_id}`, { method: "DELETE" });
                        invalidate(resource);
                        showToast("تمت إزالة العضوية.");
                        render();
                      },
                    ), "button secondary small"),
                  );
                }
                return [
                  primaryCell(member.display_name || member.email, member.email),
                  primaryCell(roleLabel(member.role_name), member.role_name),
                  (member.team_names || []).join("، ") || "—",
                  el("div", { className: "status-cell" }, statusBadge(member.status), technicalCode(member.status)),
                  formatDate(member.joined_at || member.created_at),
                  actions,
                ];
              }),
            )
          : emptyState("لا توجد عضويات", "لا توجد عضويات مسجّلة في مساحة العمل المحددة.");
        const invitations = data.invitations.length
          ? table(
              ["المستخدم", "الدور", "الفريق", "حالة التفعيل", "تنتهي في", ""],
              data.invitations.map((invitation) => [
                primaryCell(invitation.provisioned_display_name || invitation.email, invitation.email),
                roleLabel(invitation.role_name),
                invitation.team_name || "—",
                el("div", { className: "status-cell" }, statusBadge(invitation.status), technicalCode(invitation.status)),
                formatDate(invitation.expires_at),
                can("invitations.manage") && invitation.status === "pending"
                  ? action("إلغاء الدعوة", () => confirmDrawer(
                      "إلغاء الدعوة",
                      `سيتم إلغاء الدعوة المرسلة إلى ${invitation.email}.`,
                      "تأكيد الإلغاء",
                      async () => {
                        await request(`/api/system/workspaces/${selectedWorkspace}/invitations/${invitation.id}`, { method: "DELETE" });
                        invalidate(resource);
                        showToast("تم إلغاء الدعوة.");
                        render();
                      },
                    ), "button secondary small")
                  : null,
              ]),
            )
          : emptyState("لا توجد دعوات", "لا توجد دعوات مسجّلة لمساحة العمل المحددة.");
        const selector = workspaceSelect(workspaceItems, selectedWorkspace, (value) => {
          selectedWorkspace = value;
          render();
        });
        const invite = can("invitations.manage") && can("roles.read")
          ? action("إنشاء مستخدم", () => provisioningForm(
              workspaceItems,
              selectedWorkspace,
              (workspaceId) => {
                selectedWorkspace = workspaceId;
                render();
              },
            ))
          : null;
        host.replaceChildren(
          pageHeader("الأعضاء والعضويات", `إدارة عضويات ${workspace?.name || "مساحة العمل"} ودعواتها.`, invite),
          panel("مساحة العمل", selector),
          panel("العضويات", membersTable),
          can("invitations.read") ? panel("الدعوات", invitations) : null,
        );
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function teamForm(workspaceItems, team, onSaved) {
  const workspace = team
    ? null
    : el(
        "select",
        { required: "required", "aria-label": "مساحة العمل" },
        el("option", { value: "", selected: "selected", disabled: "disabled" }, "اختر مساحة العمل"),
        ...workspaceItems.map((item) => el("option", { value: item.id }, item.name)),
      );
  const teamWorkspace = team
    ? workspaceItems.find((item) => item.id === team.workspace_id)
    : null;
  const name = el("input", {
    value: team?.name || "",
    required: "required",
    maxlength: "120",
  });
  const description = el(
    "textarea",
    { rows: "3", maxlength: "500" },
    team?.description || "",
  );
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    team
      ? el(
          "div",
          { className: "form-context" },
          el("span", { className: "field-label" }, "مساحة العمل"),
          el("strong", {}, teamWorkspace?.name || "مساحة العمل"),
          technicalCode(team.workspace_id),
          el("span", { className: "field-hint" }, "ملكية مساحة العمل ثابتة بعد إنشاء الفريق."),
        )
      : labeledControl(
          "مساحة العمل",
          workspace,
          "اختيار مساحة العمل مطلوب، ولا يمكن للفريق الانتماء إلى أكثر من مساحة عمل.",
        ),
    labeledControl("اسم الفريق", name),
    labeledControl("الوصف", description),
    feedback,
  );
  const save = action(team ? "حفظ الفريق" : "إنشاء الفريق", async () => {
    if (!form.reportValidity()) return;
    const workspaceId = team?.workspace_id || workspace?.value;
    if (!workspaceId || !name.value.trim()) return;
    save.disabled = true;
    try {
      const base = `/api/system/workspaces/${workspaceId}/teams`;
      await jsonRequest(team ? `${base}/${team.id}` : base, team ? "PATCH" : "POST", {
        name: name.value.trim(),
        description: description.value.trim() || null,
      });
      invalidate(`teams:${workspaceId}`);
      showToast(team ? "تم تحديث الفريق." : "تم إنشاء الفريق.");
      modal.close();
      onSaved(workspaceId);
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(mutationError(error, "تعذر حفظ الفريق"));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(team ? "تعديل الفريق" : "فريق جديد", form);
  (workspace || name).focus();
}

function teamMembers(workspaceId, team, members, onSaved) {
  const rows = el("div", { className: "selection-list" });
  const current = new Set(team.member_ids || []);
  if (!members.length) {
    rows.append(
      emptyState(
        "لا توجد عضويات مؤهلة",
        "لا يمكن إسناد أعضاء قبل وجود عضويات في مساحة عمل الفريق.",
      ),
    );
  }
  members.forEach((member) => {
    const checked = current.has(member.user_id);
    const active = String(member.status || "").toLowerCase() === "active";
    const input = el("input", {
      type: "checkbox",
      checked: checked ? "checked" : null,
      disabled: !checked && !active ? "disabled" : null,
      "aria-label": `${checked ? "إزالة" : "إضافة"} ${member.display_name || member.email}`,
    });
    input.addEventListener("change", async () => {
      input.disabled = true;
      try {
        await request(`/api/system/workspaces/${workspaceId}/teams/${team.id}/members/${member.user_id}`, {
          method: input.checked ? "PUT" : "DELETE",
        });
        if (input.checked) current.add(member.user_id);
        else current.delete(member.user_id);
        team.member_ids = [...current];
        showToast(input.checked ? "تمت إضافة العضو إلى الفريق." : "تمت إزالة العضو من الفريق.");
        onSaved();
      } catch (error) {
        input.checked = !input.checked;
        input.disabled = !input.checked && !active;
        rows.append(apiError(error));
      }
    });
    rows.append(el(
      "label",
      { className: "selection-row selectable" },
      el("span", { className: "selection-check" }, input),
      el(
        "div",
        { className: "team-member-option" },
        primaryCell(member.display_name || member.email, member.email),
        el(
          "div",
          { className: "team-member-option-meta" },
          el("span", {}, roleLabel(member.role_name)),
          statusBadge(member.status),
        ),
      ),
    ));
  });
  return el(
    "div",
    { className: "stack" },
    el("p", { className: "detail-lead" }, "عضوية الفريق تنظيمية ولا تغيّر نطاق الصلاحيات."),
    rows,
  );
}

function teamDetails(workspace, team, members, onChanged) {
  const content = el("div", { className: "stack" });
  let details;
  const paint = () => {
    const memberIds = new Set(team.member_ids || []);
    const assigned = members.filter((member) => memberIds.has(member.user_id));
    const memberTable = !can("system_memberships.read")
      ? emptyState(
          "تفاصيل الأعضاء غير متاحة",
          `يضم الفريق ${memberIds.size} عضوًا، ولا تتوفر صلاحية عرض بيانات العضويات.`,
        )
      : assigned.length
      ? table(
          ["العضو", "الدور", "حالة العضوية"],
          assigned.map((member) => [
            primaryCell(member.display_name || member.email, member.email),
            roleLabel(member.role_name),
            el(
              "div",
              { className: "status-cell" },
              statusBadge(member.status),
              technicalCode(member.status),
            ),
          ]),
        )
      : emptyState("لا يوجد أعضاء في الفريق", "يمكن إسناد أعضاء مساحة العمل من قسم إدارة العضوية.");
    const edit = can("teams.manage")
      ? action("تعديل بيانات الفريق", () => {
          details.close();
          teamForm([workspace], team, onChanged);
        }, "button secondary")
      : null;
    const remove = can("teams.manage")
      ? action("حذف الفريق", () => confirmDrawer(
          "حذف الفريق",
          `سيتم حذف فريق ${team.name} فقط. لن تُحذف عضويات مساحة العمل ولن تتغير صلاحيات المستخدمين.`,
          "تأكيد الحذف",
          async () => {
            await request(`/api/system/workspaces/${workspace.id}/teams/${team.id}`, {
              method: "DELETE",
            });
            details.close();
            invalidate(`teams:${workspace.id}`);
            showToast("تم حذف الفريق.");
            onChanged(workspace.id);
          },
        ), "button secondary")
      : null;
    content.replaceChildren(
      el(
        "dl",
        { className: "info-grid" },
        infoField("اسم الفريق", team.name),
        infoField("مساحة العمل", workspace.name),
        infoField("الوصف", team.description || "لا يتوفر وصف"),
        infoField("تاريخ الإنشاء", formatDate(team.created_at)),
        infoField("المعرّف التقني للفريق", team.id, { technical: true }),
        infoField("معرّف مساحة العمل", team.workspace_id, { technical: true }),
      ),
      panel("أعضاء الفريق", memberTable),
      can("teams.manage") && can("system_memberships.read")
        ? panel(
            "إدارة العضوية",
            teamMembers(workspace.id, team, members, () => {
              invalidate(`teams:${workspace.id}`);
              paint();
              onChanged(workspace.id);
            }),
          )
        : null,
      edit || remove ? el("div", { className: "form-actions" }, edit, remove) : null,
    );
  };
  paint();
  details = drawer(`عرض وإدارة — ${team.name}`, content);
  return details;
}

export function teamsPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaceItems = await workspaces();
      selectedWorkspace = selectedWorkspace || workspaceItems[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("الفرق", "تنظيم فرق مساحات العمل."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const resource = `teams:${selectedWorkspace}`;
      loadResource(
        resource,
        async () => {
          const [teams, members] = await Promise.all([
            getJSON(`/api/system/workspaces/${selectedWorkspace}/teams`),
            can("system_memberships.read")
              ? getJSON(`/api/system/workspaces/${selectedWorkspace}/members`)
              : Promise.resolve([]),
          ]);
          return { teams, members };
        },
        host,
        (data) => {
          const selector = workspaceSelect(workspaceItems, selectedWorkspace, (value) => {
            selectedWorkspace = value;
            render();
          });
          const selectedWorkspaceItem = workspaceItems.find(
            (workspace) => workspace.id === selectedWorkspace,
          );
          const selectedWorkspaceName = selectedWorkspaceItem?.name || "—";
          const rerenderWorkspace = (workspaceId = selectedWorkspace) => {
            selectedWorkspace = workspaceId;
            render();
          };
          const create = can("teams.manage")
            ? action(
                "فريق جديد",
                () => teamForm(workspaceItems, null, rerenderWorkspace),
              )
            : null;
          const content = data.teams.length
            ? table(
                ["الفريق", "مساحة العمل", "الأعضاء", "تاريخ الإنشاء", ""],
                data.teams.map((team) => {
                  const actions = el("div", { className: "inline-actions" });
                  actions.append(action(
                    "عرض وإدارة",
                    () => teamDetails(
                      selectedWorkspaceItem,
                      team,
                      data.members,
                      rerenderWorkspace,
                    ),
                    "button secondary small",
                  ));
                  return [
                    primaryCell(team.name, team.description || "لا يتوفر وصف"),
                    el(
                      "div",
                      { className: "primary-cell" },
                      el("strong", {}, selectedWorkspaceName),
                      technicalCode(team.workspace_id),
                    ),
                    primaryCell(
                      String((team.member_ids || []).length),
                      (team.member_ids || []).length === 1 ? "عضو واحد" : "أعضاء الفريق",
                    ),
                    formatDate(team.created_at),
                    actions,
                  ];
                }),
              )
            : emptyState("لا توجد فرق", "لا توجد فرق مسجّلة في مساحة العمل المحددة.");
          host.replaceChildren(
            pageHeader("الفرق", "تنظيم الفرق داخل مساحات العمل دون تحويلها إلى نطاق صلاحيات.", create),
            panel("مساحة العمل", selector),
            panel("الفرق", content),
          );
        },
      );
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

function permissionLabel(definition) {
  const resource = RESOURCE_LABELS[definition.resource] || definition.resource;
  const actionName = ACTION_LABELS[definition.action] || definition.action;
  return `${actionName} — ${resource}`;
}

function permissionSelection(catalogue, selectedCodes) {
  const selected = new Set(selectedCodes || []);
  const container = el("div", { className: "permission-selection" });
  const available = catalogue.filter((item) => item.scope === "WORKSPACE" && item.active && item.delegable);
  available.forEach((definition) => {
    const input = el("input", {
      type: "checkbox",
      value: definition.code,
      checked: selected.has(definition.code) ? "checked" : null,
    });
    container.append(el(
      "label",
      { className: "permission-option" },
      input,
      el("span", {}, el("strong", {}, permissionLabel(definition)), technicalCode(definition.code)),
    ));
  });
  return {
    node: container,
    values: () => [...container.querySelectorAll("input:checked")].map((input) => input.value),
  };
}

function customRoleForm(workspaceId, role, catalogue, onSaved) {
  const name = el("input", { value: role?.name || "", required: "required", maxlength: "80" });
  const permissions = permissionSelection(catalogue, role?.permissions || []);
  const feedback = el("div", { className: "form-feedback" });
  const form = el(
    "form",
    { className: "source-create-form" },
    labeledControl("اسم الدور المخصص", name),
    el("fieldset", { className: "permission-fieldset" }, el("legend", {}, "صلاحيات مساحة العمل"), permissions.node),
    feedback,
  );
  const save = action(role ? "حفظ الدور" : "إنشاء الدور", async () => {
    if (!name.value.trim()) return;
    save.disabled = true;
    try {
      const base = `/api/system/workspaces/${workspaceId}/roles`;
      await jsonRequest(role ? `${base}/${role.id}` : base, role ? "PATCH" : "POST", {
        name: name.value.trim(),
        permissions: permissions.values(),
      });
      invalidate(`roles:${workspaceId}`);
      showToast(role ? "تم تحديث الدور المخصص." : "تم إنشاء الدور المخصص.");
      modal.close();
      onSaved();
    } catch (error) {
      save.disabled = false;
      feedback.replaceChildren(apiError(error));
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    save.click();
  });
  form.append(el("div", { className: "form-actions" }, save));
  const modal = drawer(role ? "تعديل دور مخصص" : "دور مخصص جديد", form);
  name.focus();
}

function roleDetails(role, scope, catalogue, workspaceId, onSaved) {
  const builtIn = role.role_kind === "built_in";
  const deprecated = role.status === "deprecated" || role.role_kind === "legacy";
  const definitionByCode = new Map(catalogue.map((item) => [item.code, item]));
  const permissions = el("div", { className: "permission-chip-list" });
  (role.permissions || []).forEach((code) => {
    const definition = definitionByCode.get(code);
    permissions.append(el(
      "span",
      { className: "permission-chip" },
      definition ? permissionLabel(definition) : code,
      technicalCode(code),
    ));
  });
  const content = el(
    "div",
    { className: "stack" },
    el(
      "dl",
      { className: "info-grid" },
      infoField("النطاق", SCOPE_LABELS[scope]),
      infoField("النوع", builtIn ? "مدمج غير قابل للتعديل" : deprecated ? "تاريخي / متوقف" : "مخصص"),
      infoField("عدد الصلاحيات", String((role.permissions || []).length)),
      role.member_count === undefined ? null : infoField("عدد الأعضاء", String(role.member_count)),
      infoField("المعرّف التقني", role.id, { technical: true }),
    ),
    panel("الصلاحيات", permissions.childElementCount ? permissions : emptyState("لا توجد صلاحيات")),
  );
  if (scope === "WORKSPACE" && !builtIn && !deprecated && can("roles.manage")) {
    content.append(action("تعديل الدور المخصص", () => {
      details.close();
      customRoleForm(workspaceId, role, catalogue, onSaved);
    }));
  }
  const details = drawer(roleLabel(role.name), content);
}

async function rolesData(workspaceId) {
  const [systemRoles, workspaceRoles, catalogue] = await Promise.all([
    getJSON("/api/system/roles"),
    getJSON(`/api/system/workspaces/${workspaceId}/roles`),
    getJSON("/api/system/permissions"),
  ]);
  return { systemRoles, workspaceRoles, catalogue };
}

function catalogueTable(catalogue) {
  return table(
    ["الصلاحية", "النطاق", "الحالة", "قابلة للتفويض"],
    catalogue.map((definition) => [
      primaryCell(permissionLabel(definition), definition.code),
      primaryCell(SCOPE_LABELS[definition.scope] || definition.scope, definition.scope),
      definition.active ? "نشطة" : "تاريخية / غير نشطة",
      definition.delegable ? "نعم" : "لا",
    ]),
  );
}

export function rolesPage() {
  const host = el("div", { className: "route-panel" });
  let selectedWorkspace = null;
  const render = async () => {
    try {
      const workspaceItems = await workspaces();
      selectedWorkspace = selectedWorkspace || workspaceItems[0]?.id || null;
      if (!selectedWorkspace) {
        host.replaceChildren(pageHeader("الأدوار والصلاحيات", "إدارة نموذج الصلاحيات النهائي."), emptyState("لا توجد مساحات عمل"));
        return;
      }
      const resource = `roles:${selectedWorkspace}`;
      loadResource(resource, () => rolesData(selectedWorkspace), host, (data) => {
        const selector = workspaceSelect(workspaceItems, selectedWorkspace, (value) => {
          selectedWorkspace = value;
          render();
        });
        const create = can("roles.manage")
          ? action("دور مساحة عمل مخصص", () => customRoleForm(selectedWorkspace, null, data.catalogue, render))
          : null;
        const systemRows = data.systemRoles.map((role) => [
          primaryCell(roleLabel(role.name), role.name),
          "النظام",
          role.role_kind === "built_in" ? "مدمج غير قابل للتعديل" : "مخصص",
          String((role.permissions || []).length),
          action("عرض", () => roleDetails(role, "SYSTEM", data.catalogue, null, render), "button secondary small"),
        ]);
        const workspaceRows = data.workspaceRoles.map((role) => {
          const builtIn = role.role_kind === "built_in";
          const historical = role.role_kind === "legacy" || role.status === "deprecated";
          return [
            primaryCell(roleLabel(role.name), role.name),
            "مساحة العمل",
            builtIn ? "مدمج غير قابل للتعديل" : historical ? "تاريخي / متوقف" : "مخصص",
            String((role.permissions || []).length),
            action("عرض", () => roleDetails(role, "WORKSPACE", data.catalogue, selectedWorkspace, render), "button secondary small"),
          ];
        });
        host.replaceChildren(
          pageHeader("الأدوار والصلاحيات", "عرض النطاق القانوني لكل صلاحية وإدارة أدوار مساحات العمل المخصصة.", create),
          panel("مساحة العمل", selector),
          panel("الأدوار المدمجة للنظام", systemRows.length
            ? table(["الدور", "النطاق", "النوع", "الصلاحيات", ""], systemRows)
            : emptyState("لا توجد أدوار نظامية")),
          panel("أدوار مساحة العمل", workspaceRows.length
            ? table(["الدور", "النطاق", "النوع", "الصلاحيات", ""], workspaceRows)
            : emptyState("لا توجد أدوار لمساحة العمل")),
          panel("دليل الصلاحيات الكامل", catalogueTable(data.catalogue)),
        );
      });
    } catch (error) {
      host.replaceChildren(apiError(error));
    }
  };
  render();
  return host;
}

export const SYSTEM_PAGES = {
  home: homePage,
  workspaces: workspacesPage,
  assistants: assistantsPage,
  knowledge: knowledgePage,
  members: membersPage,
  teams: teamsPage,
  roles: rolesPage,
};
