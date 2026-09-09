import { getJSON, request, ApiError } from "/assets/shared/api.js";
import { workspaceCache, workspaceKey } from "/assets/shared/cache.js";
import { el } from "/assets/shared/dom.js";
import { drawer, emptyState, errorState, loadingState, statusBadge, toast } from "/assets/shared/ui.js";
import { setCurrentWorkspaceName } from "/assets/shared/session.js?v=stage4-auth-footer-2";

const state = { workspaceId: null, workspace: null, permissions: new Set(), catalog: null };

const ROLE_LABELS = {
  WORKSPACE_MANAGER: "مدير مساحة العمل",
  MEMBER: "عضو",
};

const SOURCE_KIND_LABELS = {
  document: "مستند",
  structured: "بيانات منظّمة",
};

const EVALUATION_TYPE_LABELS = {
  deterministic: "حتمي",
  reference_based: "مرجعي",
  model_assisted: "بمساعدة نموذج",
};

const OUTCOME_LABELS = {
  GroundedAnswer: "إجابة موثّقة",
  InsufficientEvidence: "أدلة غير كافية",
  PolicyDenied: "مرفوض وفق السياسة",
  TechnicalFailure: "تعذر التنفيذ تقنيًا",
};

function pageHeader(title, description, ...actions) {
  return el("header", { className: "page-toolbar" },
    el("div", { className: "page-heading" },
      el("h2", {}, title),
      description ? el("p", { className: "page-intro" }, description) : null,
    ),
    actions.length ? el("div", { className: "toolbar-actions" }, actions) : null,
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

function technicalCode(value) {
  return value ? el("span", { className: "technical-code", dir: "ltr" }, String(value)) : null;
}

function infoField(label, value, { technical = false } = {}) {
  return el("div", { className: "info-field" },
    el("dt", {}, label),
    el("dd", { className: technical ? "technical-value" : "" }, value ?? "—"),
  );
}

function labeledControl(label, control, hint = null) {
  return el("label", { className: "field" },
    el("span", { className: "field-label" }, label),
    control,
    hint ? el("span", { className: "field-hint" }, hint) : null,
  );
}

function invalidateResources(...resources) {
  resources.forEach((resource) => workspaceCache.invalidate(workspaceKey(state.workspaceId, resource)));
}

function showToast(message) {
  const region = document.querySelector(".toast-region");
  if (region) toast(region, message);
}

function conversationTitle(value) {
  const title = String(value || "").trim();
  return !title || title.toLowerCase() === "untitled conversation" ? "محادثة بلا عنوان" : title;
}

function sourceKindLabel(kind) {
  return SOURCE_KIND_LABELS[String(kind || "").toLowerCase()] || "نوع غير معروف";
}

function evaluationTypeLabel(type) {
  return EVALUATION_TYPE_LABELS[String(type || "").toLowerCase()] || String(type || "");
}

function languageLabel(value) {
  const labels = { ar: "العربية", en: "الإنجليزية" };
  return labels[String(value || "").toLowerCase()] || value || "—";
}

function panel(title, ...children) {
  return el("section", { className: "panel" }, el("h2", { className: "panel-title" }, title), ...children);
}

function action(label, handler, className = "button") {
  return el("button", { className, type: "button", onclick: handler }, label);
}

function apiError(error) {
  if (error instanceof ApiError && error.status === 401) return errorState("انتهت الجلسة", "سجّل الدخول مرة أخرى للمتابعة.");
  if (error instanceof ApiError && error.status === 403) return errorState("الوصول غير متاح", "لا تملك صلاحية هذا الإجراء في مساحة العمل الحالية.");
  if (error instanceof ApiError && error.status === 404) return errorState("العنصر غير موجود", "قد يكون المورد قد تغيّر أو لم يعد متاحًا.");
  return errorState("تعذر تحميل البيانات", "حاول مرة أخرى لاحقًا.");
}

function workspaceKnowledgeError(error, actionType) {
  const titles = {
    create: "تعذر تسجيل المصدر.",
    upload: "تعذر رفع الملف.",
    process: "تعذر معالجة المصدر.",
  };
  const title = titles[actionType] || "تعذر تنفيذ الإجراء.";
  if (error instanceof ApiError) {
    const details = {
      "knowledge source addition is disabled":
        "إضافة محتوى المعرفة متوقفة وفق السياسة التشغيلية لمساحة العمل.",
      "source processing is disabled":
        "معالجة مصادر المعرفة متوقفة وفق السياسة التشغيلية لمساحة العمل.",
      "original artifact is not stored":
        "لا يوجد ملف أصلي محفوظ لهذا المصدر.",
      "source already has an original artifact":
        "الملف الأصلي محفوظ مسبقًا ولا يمكن استبداله.",
      "original artifact storage is incomplete":
        "بيانات الملف الأصلي غير مكتملة.",
      "artifact exceeds maximum size":
        "حجم الملف يتجاوز الحد المسموح.",
      "source lifecycle does not accept an original artifact":
        "حالة المصدر الحالية لا تسمح بإرفاق ملف أصلي.",
    };
    if (Object.hasOwn(details, error.code)) {
      return errorState(title, details[error.code]);
    }
    if (error.status === 401 || error.status === 403 || error.status === 404) {
      return apiError(error);
    }
  }
  return errorState(title, "لم يكتمل الإجراء. حاول مرة أخرى لاحقًا.");
}

async function ensureWorkspace() {
  if (state.workspaceId) return state.workspaceId;
  state.catalog = await getJSON("/api/me/workspaces");
  const selected = localStorage.getItem("selected_workspace_id");
  const current = state.catalog.find((item) => item.id === selected) || state.catalog[0];
  if (!current) throw new Error("workspace unavailable");
  state.workspaceId = current.id;
  state.workspace = current;
  state.permissions = new Set(current.permissions || []);
  setCurrentWorkspaceName(current.name);
  return state.workspaceId;
}

function loadResource(resource, loader, host, paint) {
  const key = workspaceKey(state.workspaceId, resource);
  const cached = workspaceCache.get(key);
  if (cached !== undefined) paint(cached, true);
  else host.replaceChildren(loadingState("جارٍ تحميل البيانات…"));
  const refresh = workspaceCache.staleWhileRevalidate(key, loader, {
    isCurrent: () => host.isConnected,
    onFresh: (value) => paint(value, false),
    onError: (error) => { if (cached === undefined && host.isConnected) host.replaceChildren(apiError(error)); },
  });
  refresh.refresh.catch(() => {});
}

function start(host, loader, paint) {
  ensureWorkspace().then(() => loadResource(loader.resource, loader.load, host, paint)).catch((error) => host.replaceChildren(apiError(error)));
}

function table(headers, rows) {
  const wrap = el("div", { className: "table-wrap" });
  const node = el("table", { className: "data-table" });
  const head = el("thead", {}, el("tr", {}, ...headers.map((h) => el("th", {}, h))));
  const body = el("tbody");
  rows.forEach((row) => body.append(el("tr", {}, ...row.map((cell) => el("td", {}, cell)))));
  node.append(head, body); wrap.append(node); return wrap;
}

function openAssistant(item) {
  const body = el("div", { className: "stack" },
    el("p", { className: "detail-lead" }, item.description || "لا يتوفر وصف لهذا المساعد."),
    el("dl", { className: "info-grid" },
      infoField("اللغة", languageLabel(item.language)),
      infoField("المعرّف التقني", item.id, { technical: true }),
    ),
    action("بدء محادثة", async () => {
      try {
        const conversation = await request(`/api/workspaces/${state.workspaceId}/assistants/${item.id}/conversations`, { method: "POST" });
        invalidateResources("home", "conversations");
        window.history.pushState({}, "", `/app/conversations/${conversation.id}`); window.dispatchEvent(new PopStateEvent("popstate"));
      } catch (error) { body.append(apiError(error)); }
    }),
  );
  drawer(item.name, body);
}

export function homePage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "home", load: async () => {
    const workspace = await getJSON(`/api/workspaces/${state.workspaceId}`);
    const [assistants, sources, conversations] = await Promise.all([
      getJSON(`/api/workspaces/${state.workspaceId}/assistants`),
      getJSON(`/api/workspaces/${state.workspaceId}/sources`),
      getJSON(`/api/workspaces/${state.workspaceId}/conversations`),
    ]);
    return { workspace, assistants, sources, conversations };
  }, }, (data) => {
    host.replaceChildren(
      pageHeader(data.workspace.name, "ملخص مساحة العمل الحالية"),
      el("section", { className: "metrics-grid", "aria-label": "مؤشرات مساحة العمل" },
        el("article", { className: "metric-card" }, el("span", { className: "metric-label" }, "المساعدون"), el("strong", { className: "metric-value" }, String(data.assistants.length)), el("span", { className: "metric-note" }, "متاح في مساحة العمل")),
        el("article", { className: "metric-card" }, el("span", { className: "metric-label" }, "مصادر المعرفة"), el("strong", { className: "metric-value" }, String(data.sources.length)), el("span", { className: "metric-note" }, "مصدر مسجّل")),
        el("article", { className: "metric-card" }, el("span", { className: "metric-label" }, "المحادثات النشطة"), el("strong", { className: "metric-value" }, String(data.conversations.length)), el("span", { className: "metric-note" }, "محادثة قابلة للمتابعة")),
      ),
    );
  });
  return host;
}

export function assistantsPage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "assistants", load: () => getJSON(`/api/workspaces/${state.workspaceId}/assistants`) }, (items) => {
    const grid = el("div", { className: "assistant-list" });
    if (!items.length) grid.append(emptyState("لا توجد مساعدات", "لا تتوفر مساعدات في مساحة العمل الحالية."));
    items.forEach((item) => grid.append(el("article", { className: "assistant-card" },
      el("div", { className: "assistant-card-copy" },
        el("h3", {}, item.name),
        el("p", {}, item.description || "لا يتوفر وصف لهذا المساعد."),
      ),
      el("div", { className: "assistant-card-actions" }, action("استخدام المساعد", () => openAssistant(item))),
    )));
    host.replaceChildren(pageHeader("المساعدون", "المساعدون المتاحون للاستخدام في مساحة العمل الحالية."), grid);
  });
  return host;
}

function sourceDetails(source, host) {
  if (!Object.hasOwn(source, "artifact")) {
    const loading = el("div", { className: "stack" }, loadingState("جاري التحقق من الملف الأصلي…"));
    const pending = drawer(source.name, loading);
    getJSON(`/api/workspaces/${state.workspaceId}/sources/${source.id}/artifact`)
      .then((artifact) => {
        source.artifact = artifact;
        pending.close();
        sourceDetails(source, host);
      })
      .catch((error) => loading.replaceChildren(apiError(error)));
    return;
  }
  const lifecycleBadge = statusBadge(source.lifecycle);
  const content = el("div", { className: "stack" },
    el("dl", { className: "info-grid" },
      infoField("النوع", sourceKindLabel(source.kind)),
      infoField("الحالة", lifecycleBadge),
      infoField("توفر الملف الأصلي", statusBadge(source.artifact.artifact_state)),
      infoField("المعرّف التقني", source.id, { technical: true }),
    ),
  );
  if (source.artifact.artifact_present) {
    content.append(
      el("section", { className: "detail-actions" },
        el("h3", {}, "الملف الأصلي"),
        el("div", { className: "artifact-present" },
          el("div", { className: "artifact-identity" },
            el("span", { className: "artifact-identity-label" }, "اسم الملف الأصلي"),
            source.artifact.original_filename
              ? el("strong", { className: "artifact-filename", dir: "auto" }, source.artifact.original_filename)
              : el("span", { className: "secondary-meta" }, "اسم الملف غير متاح"),
          ),
          el("dl", { className: "artifact-metadata" },
            infoField("نوع المحتوى", source.artifact.media_type
              ? technicalCode(source.artifact.media_type)
              : "غير متاح"),
            infoField("الحجم", formatBytes(source.artifact.byte_size)),
            source.artifact.stored_at
              ? infoField("تاريخ الحفظ", formatDate(source.artifact.stored_at))
              : null,
            source.artifact.suffix
              ? infoField("الامتداد التقني", technicalCode(source.artifact.suffix))
              : null,
          ),
        ),
      ),
    );
  } else {
    const description = source.artifact.artifact_state === "LEGACY_UNAVAILABLE"
      ? "المعرفة المفهرسة الحالية متاحة، لكن إعادة المعالجة تتطلب إرفاق الملف الأصلي أولًا."
      : "ارفع الملف الأصلي مرة واحدة قبل بدء معالجة المصدر.";
    content.append(
      emptyState(
        source.artifact.artifact_state === "LEGACY_UNAVAILABLE"
          ? "الملف الأصلي غير متوفر — مصدر تاريخي"
          : "بانتظار رفع الملف الأصلي",
        description,
      ),
    );
  }
  const actions = el("section", { className: "detail-actions" }, el("h3", {}, "إجراءات المصدر"));
  const uploadFeedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  const processFeedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  let selectedFile = null;
  if (
    state.permissions.has("knowledge.create")
    && !source.artifact.artifact_present
    && source.artifact.upload_allowed
  ) {
    const selectedName = el("span", { className: "field-hint" }, "لم يتم اختيار ملف");
    const file = el("input", {
      type: "file",
      accept: ".txt,.md,.markdown,.json,.docx,.pdf",
      className: "file-input",
      onchange: () => {
        selectedFile = file.files?.[0] || null;
        selectedName.textContent = selectedFile?.name || "لم يتم اختيار ملف";
        upload.disabled = !selectedFile;
      },
    });
    const upload = action("رفع الملف الأصلي", async () => {
      if (!selectedFile) return;
      upload.disabled = true;
      uploadFeedback.replaceChildren();
      try {
        const stored = await request(`/api/workspaces/${state.workspaceId}/sources/${source.id}/upload`, {
          method: "POST",
          headers: {
            "x-file-name": encodeURIComponent(selectedFile.name),
            "x-file-name-encoding": "percent",
            "content-type": selectedFile.type || "application/octet-stream",
          },
          body: selectedFile,
        });
        source.artifact = stored;
        detail.close();
        sourceDetails(source, host);
        showToast("تم رفع ملف المصدر بنجاح.");
      } catch (error) {
        uploadFeedback.replaceChildren(workspaceKnowledgeError(error, "upload"));
        upload.disabled = false;
      }
    });
    upload.disabled = true;
    actions.append(
      labeledControl("ملف المصدر", el("div", { className: "file-picker" }, file, selectedName), "الملفات المدعومة: TXT وMarkdown وJSON وDOCX وPDF"),
      upload,
      uploadFeedback,
    );
  }
  if (state.permissions.has("knowledge.process") && source.artifact.artifact_present) {
    const process = action("معالجة المصدر", async () => {
      process.disabled = true;
      processFeedback.replaceChildren();
      try {
        const updated = await request(`/api/workspaces/${state.workspaceId}/sources/${source.id}/process`, { method: "POST" });
        Object.assign(source, updated);
        const sourcesKey = workspaceKey(state.workspaceId, "sources");
        const cached = workspaceCache.get(sourcesKey);
        if (Array.isArray(cached)) {
          workspaceCache.set(
            sourcesKey,
            cached.map((item) => item.id === source.id ? { ...item, ...updated } : item),
          );
        }
        detail.close();
        sourceDetails(source, host);
        showToast(String(updated.lifecycle || "").toUpperCase() === "READY"
          ? "اكتملت معالجة المصدر."
          : "تم تحديث حالة معالجة المصدر.");
        host.dispatchEvent(new Event("refresh"));
      } catch (error) {
        processFeedback.replaceChildren(workspaceKnowledgeError(error, "process"));
        process.disabled = false;
      }
    });
    process.textContent = String(source.lifecycle || "").toUpperCase() === "READY"
      ? "إعادة معالجة المصدر"
      : "معالجة المصدر";
    actions.append(process, processFeedback);
  }
  if (actions.children.length > 1) content.append(actions);
  const detail = drawer(source.name, content);
}

export function knowledgePage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "sources", load: () => getJSON(`/api/workspaces/${state.workspaceId}/sources`) }, (items) => {
    const content = [];
    if (state.permissions.has("knowledge.create")) {
      const name = el("input", { type: "text", placeholder: "مثال: دليل السياسات", required: "true", maxlength: "200", autocomplete: "off" });
      const kind = el("select", {},
        el("option", { value: "document" }, "مستند"),
        el("option", { value: "structured" }, "بيانات منظّمة"),
      );
      const create = el("button", { className: "button", type: "submit" }, "تسجيل المصدر");
      const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
      const form = el("form", { className: "panel source-create-form", onsubmit: async (event) => {
        event.preventDefault();
        feedback.replaceChildren();
        if (!name.value.trim()) {
          feedback.append(errorState("اسم المصدر مطلوب", "أدخل اسمًا واضحًا للمصدر قبل المتابعة."));
          name.focus();
          return;
        }
        create.disabled = true;
        try {
          await request(`/api/workspaces/${state.workspaceId}/sources`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: name.value.trim(), kind: kind.value }) });
          invalidateResources("home", "sources");
          showToast("تم تسجيل مصدر المعرفة.");
          host.dispatchEvent(new Event("refresh"));
        } catch (error) {
          feedback.append(workspaceKnowledgeError(error, "create"));
        } finally {
          create.disabled = false;
        }
      } },
      el("div", { className: "form-heading" },
        el("h3", {}, "إضافة مصدر معرفة"),
        el("p", { className: "muted" }, "سجّل المصدر أولًا، ثم ارفع ملفه وابدأ المعالجة من تفاصيله."),
      ),
      el("div", { className: "form-grid" },
        labeledControl("اسم المصدر", name),
        labeledControl("نوع المصدر", kind),
      ),
      el("div", { className: "form-actions" }, create),
      feedback,
      );
      content.push(form);
    }
    const rows = items.map((source) => {
      const sourceName = el("div", { className: "primary-cell" },
        el("strong", {}, source.name),
        technicalCode(source.kind),
      );
      const sourceStatus = el("div", { className: "status-cell" }, statusBadge(source.lifecycle), technicalCode(source.lifecycle));
      return [sourceName, sourceKindLabel(source.kind), sourceStatus, action("فتح التفاصيل", () => sourceDetails(source, host), "button secondary small")];
    });
    content.push(rows.length
      ? panel("المصادر المسجّلة", table(["المصدر", "النوع", "الحالة", "الإجراء"], rows))
      : emptyState("لا توجد مصادر معرفة", "لا توجد مصادر مسجّلة في مساحة العمل الحالية."));
    host.replaceChildren(pageHeader("مصادر المعرفة", "إدارة المصادر ضمن صلاحيات الإضافة والمعالجة المتاحة."), ...content);
  });
  host.addEventListener("refresh", () => host.replaceWith(knowledgePage()));
  return host;
}

export function membersPage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "members", load: () => getJSON(`/api/workspaces/${state.workspaceId}/members`) }, (items) => {
    const rows = items.map((item) => [
      el("div", { className: "primary-cell" },
        el("strong", {}, item.display_name || item.email),
        item.display_name && item.email ? el("span", { className: "muted" }, item.email) : null,
      ),
      el("div", { className: "primary-cell" },
        el("span", {}, ROLE_LABELS[item.role_name] || item.role_name),
        technicalCode(item.role_name),
      ),
      statusBadge(item.status),
    ]);
    host.replaceChildren(
      pageHeader("الأعضاء", "دليل أعضاء مساحة العمل ومعلومات عضويتهم."),
      rows.length ? panel("أعضاء مساحة العمل", table(["العضو", "الدور", "الحالة"], rows)) : emptyState("لا يوجد أعضاء", "لا توجد عضويات متاحة."),
    );
  });
  return host;
}

function openRenameConversation(conversation) {
  const title = el("input", { type: "text", value: conversation.title || "", maxlength: "200", required: "true" });
  const feedback = el("div", { className: "form-feedback", "aria-live": "polite" });
  const form = el("form", { className: "form stack", onsubmit: async (event) => {
    event.preventDefault();
    feedback.replaceChildren();
    const nextTitle = title.value.trim();
    if (!nextTitle) {
      feedback.append(errorState("العنوان مطلوب", "أدخل عنوانًا واضحًا للمحادثة."));
      title.focus();
      return;
    }
    save.disabled = true;
    try {
      await request(`/api/workspaces/${state.workspaceId}/conversations/${conversation.id}/title`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: nextTitle }),
      });
      invalidateResources("home", "conversations");
      dialog.close();
      window.dispatchEvent(new PopStateEvent("popstate"));
    } catch (error) {
      feedback.append(apiError(error));
    } finally {
      save.disabled = false;
    }
  } },
  labeledControl("عنوان المحادثة", title),
  el("div", { className: "form-actions" }, action("إلغاء", () => dialog.close(), "button secondary"), el("button", { className: "button", type: "submit" }, "حفظ العنوان")),
  feedback,
  );
  const save = form.querySelector('button[type="submit"]');
  const dialog = drawer("إعادة تسمية المحادثة", form);
  title.focus();
}

function renderMessage(message) {
  const evidence = message.evidence || [];
  return el("article", { className: `message ${message.role === "user" ? "user" : "assistant"}` },
    el("header", { className: "message-head" },
      el("span", { className: "message-role" }, message.role === "user" ? "أنت" : "المساعد"),
      message.outcome ? el("span", { className: "outcome-label", title: message.outcome }, OUTCOME_LABELS[message.outcome] || message.outcome) : null,
    ),
    el("p", { className: "message-content" }, message.content),
    evidence.length ? el("section", { className: "evidence-list", "aria-label": "الأدلة" },
      el("h4", {}, "الأدلة"),
      ...evidence.map((item) => el("article", { className: "evidence-item" },
        el("p", {}, item.content),
        el("span", { className: "evidence-source" }, item.provenance_locator || `المصدر ${item.source_id}`),
      )),
    ) : null,
  );
}

function conversationDetail(id, host) {
  host.replaceChildren(loadingState("جارٍ فتح المحادثة…"));
  return request(`/api/workspaces/${state.workspaceId}/conversations/${id}`).then((conversation) => {
    const messages = el("div", { className: "messages" });
    if (conversation.messages.length) conversation.messages.forEach((message) => messages.append(renderMessage(message)));
    else messages.append(emptyState("لا توجد رسائل بعد", "ابدأ بالسؤال الأول في هذه المحادثة."));

    const input = el("textarea", { placeholder: "اكتب سؤالك…", rows: "3", maxlength: "4000" });
    const send = action("إرسال", async () => {
      const question = input.value.trim();
      if (!question) {
        input.focus();
        return;
      }
      send.disabled = true;
      try {
        await request(`/api/workspaces/${state.workspaceId}/conversations/${id}/ask`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question }),
        });
        input.value = "";
        invalidateResources("conversations");
        await conversationDetail(id, host);
      } catch (error) {
        host.append(apiError(error));
      } finally {
        send.disabled = conversation.status === "ARCHIVED";
      }
    });
    const archive = action(conversation.status === "ACTIVE" ? "أرشفة" : "استعادة", async () => {
      archive.disabled = true;
      try {
        await request(`/api/workspaces/${state.workspaceId}/conversations/${id}/archive`, {
          method: "PATCH",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ archived: conversation.status !== "ARCHIVED" }),
        });
        invalidateResources("home", "conversations");
        window.dispatchEvent(new PopStateEvent("popstate"));
      } catch (error) {
        host.append(apiError(error));
        archive.disabled = false;
      }
    }, "button secondary");
    const composer = conversation.status === "ARCHIVED"
      ? el("div", { className: "archived-notice" }, "هذه المحادثة مؤرشفة. استعدها لإرسال رسالة جديدة.")
      : el("form", { className: "composer", onsubmit: (event) => { event.preventDefault(); send.click(); } }, input, send);
    host.replaceChildren(
      el("header", { className: "conversation-head" },
        el("div", {}, el("h2", {}, conversationTitle(conversation.title)), statusBadge(conversation.status)),
        el("div", { className: "toolbar-actions" }, action("إعادة تسمية", () => openRenameConversation(conversation), "button secondary"), archive),
      ),
      messages,
      composer,
    );
    return conversation;
  }).catch((error) => host.replaceChildren(apiError(error)));
}

function conversationIdFromPath() {
  const match = window.location.pathname.match(/^\/app\/conversations\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

async function openNewConversation(host) {
  const content = el("div", {}, loadingState("جارٍ تحميل المساعدين…"));
  const dialog = drawer("محادثة جديدة", content);
  try {
    const assistants = await getJSON(`/api/workspaces/${state.workspaceId}/assistants`);
    if (!assistants.length) {
      content.replaceChildren(emptyState("لا يوجد مساعد متاح", "لا تتوفر مساعدات يمكن بدء محادثة معها في مساحة العمل الحالية."));
      return;
    }
    const assistant = el("select", {}, ...assistants.map((item) => el("option", { value: item.id }, item.name)));
    const create = action("بدء المحادثة", async () => {
      create.disabled = true;
      try {
        const created = await request(`/api/workspaces/${state.workspaceId}/assistants/${assistant.value}/conversations`, { method: "POST" });
        invalidateResources("home", "conversations");
        dialog.close();
        window.history.pushState({}, "", `/app/conversations/${created.id}`);
        window.dispatchEvent(new PopStateEvent("popstate"));
      } catch (error) {
        content.append(apiError(error));
        create.disabled = false;
      }
    });
    content.replaceChildren(
      el("div", { className: "stack" },
        labeledControl("اختر المساعد", assistant),
        el("div", { className: "form-actions" }, action("إلغاء", () => dialog.close(), "button secondary"), create),
      ),
    );
  } catch (error) {
    content.replaceChildren(apiError(error));
  }
}

export function conversationsPage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "conversations", load: async () => {
    const [active, archived] = await Promise.all([
      getJSON(`/api/workspaces/${state.workspaceId}/conversations?conversation_status=ACTIVE`),
      getJSON(`/api/workspaces/${state.workspaceId}/conversations?conversation_status=ARCHIVED`),
    ]);
    return { active, archived };
  } }, (data) => {
    const selectedId = conversationIdFromPath();
    const selected = [...data.active, ...data.archived].find((item) => String(item.id) === selectedId);
    let mode = selected?.status === "ARCHIVED" ? "ARCHIVED" : "ACTIVE";
    const list = el("div", { className: "conversation-list" });
    const detail = el("section", { className: "conversation-detail" });
    const filters = el("div", { className: "segmented-control", role: "group", "aria-label": "تصفية المحادثات" });

    const renderList = () => {
      const items = mode === "ARCHIVED" ? data.archived : data.active;
      list.replaceChildren();
      filters.querySelectorAll("button").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.status === mode)));
      if (!items.length) {
        list.append(emptyState(mode === "ARCHIVED" ? "لا توجد محادثات مؤرشفة" : "لا توجد محادثات نشطة", "لا توجد عناصر ضمن هذا العرض."));
        return;
      }
      items.forEach((item) => list.append(el("button", {
        className: `conversation-row${String(item.id) === selectedId ? " active" : ""}`,
        type: "button",
        dataset: { conversationId: item.id },
        onclick: () => {
          window.history.pushState({}, "", `/app/conversations/${item.id}`);
          list.querySelectorAll(".conversation-row").forEach((row) => row.classList.toggle("active", row.dataset.conversationId === String(item.id)));
          conversationDetail(item.id, detail);
        },
      },
      el("span", { className: "conversation-row-head" }, el("strong", {}, conversationTitle(item.title)), statusBadge(item.status)),
      el("span", { className: "conversation-row-meta" }, `${item.message_count} رسالة`, item.created_at ? ` · ${formatDate(item.created_at)}` : ""),
      item.last_message_preview ? el("span", { className: "conversation-preview" }, item.last_message_preview) : null,
      )));
    };
    [
      ["ACTIVE", "النشطة", data.active.length],
      ["ARCHIVED", "المؤرشفة", data.archived.length],
    ].forEach(([value, label, count]) => filters.append(el("button", {
      type: "button",
      className: "segment-button",
      dataset: { status: value },
      "aria-pressed": String(mode === value),
      onclick: () => { mode = value; renderList(); },
    }, `${label} (${count})`)));

    renderList();
    host.replaceChildren(
      pageHeader("المحادثات", "محادثات مساحة العمل النشطة والمؤرشفة.", action("محادثة جديدة", () => openNewConversation(host))),
      filters,
      el("div", { className: "conversation-layout" }, list, detail),
    );
    if (selectedId) conversationDetail(selectedId, detail);
    else detail.replaceChildren(emptyState("اختر محادثة", "اختر محادثة من القائمة لعرض الرسائل والأدلة."));
  });
  host.addEventListener("refresh", () => host.replaceWith(conversationsPage()));
  return host;
}

export function evaluationPage() {
  const host = el("div", { className: "route-panel" });
  start(host, { resource: "evaluation", load: async () => Promise.all([getJSON(`/api/workspaces/${state.workspaceId}/evaluation/suites`), getJSON(`/api/workspaces/${state.workspaceId}/evaluation/runs`)]).then(([suites, runs]) => ({ suites, runs: runs.items || [] })) }, (data) => {
    const suiteList = el("div", { className: "suite-grid" });

    const suiteDetails = async (suite) => {
      try {
        const detail = await getJSON(`/api/workspaces/${state.workspaceId}/evaluation/suites/${encodeURIComponent(suite.key)}`);
        drawer(detail.name || detail.key, el("div", { className: "stack" },
          el("dl", { className: "info-grid" },
            infoField("الإصدار", detail.version),
            infoField("عدد الحالات", detail.case_count),
            infoField("هوية التعريف", detail.sha256, { technical: true }),
          ),
          el("section", { className: "case-list" },
            el("h3", {}, "حالات التقييم"),
            ...detail.cases.map((item) => el("article", { className: "case-card" },
              el("div", { className: "case-head" }, el("strong", {}, item.key), technicalCode(item.evaluation_type)),
              el("p", {}, item.question),
              item.expected_outcome ? el("p", { className: "case-expected" }, `النتيجة المتوقعة: ${item.expected_outcome}`) : null,
            )),
          ),
        ));
      } catch (error) {
        host.append(apiError(error));
      }
    };

    const runSuite = async (suite) => {
      const content = el("div", {}, loadingState("جارٍ تحميل المساعدين…"));
      const dialog = drawer("تشغيل التقييم", content);
      try {
        const assistants = await getJSON(`/api/workspaces/${state.workspaceId}/assistants`);
        if (!assistants.length) {
          content.replaceChildren(emptyState("لا يوجد مساعد متاح", "لا يمكن تشغيل التقييم دون مساعد في مساحة العمل."));
          return;
        }
        const assistant = el("select", {}, ...assistants.map((item) => el("option", { value: item.id }, item.name)));
        const run = action("تشغيل التقييم", async () => {
          run.disabled = true;
          try {
            await request(`/api/workspaces/${state.workspaceId}/evaluation/runs`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ suite_key: suite.key, assistant_id: assistant.value }),
            });
            invalidateResources("evaluation");
            dialog.close();
            showToast("اكتمل تشغيل التقييم وحُفظت النتيجة.");
            host.dispatchEvent(new Event("refresh"));
          } catch (error) {
            content.append(apiError(error));
            run.disabled = false;
          }
        });
        content.replaceChildren(el("div", { className: "stack" },
          el("dl", { className: "info-grid" },
            infoField("المجموعة", suite.name || suite.key),
            infoField("الإصدار", suite.version),
            infoField("عدد الحالات", suite.case_count),
          ),
          labeledControl("المساعد", assistant),
          el("div", { className: "provider-warning", role: "note" },
            el("strong", {}, "تنبيه استخدام المزود"),
            el("p", {}, "قد يستدعي تشغيل هذه المجموعة مسار المساعد المعتاد ويستهلك موارد النموذج أو التضمين بحسب الحالات والإعدادات الحالية."),
          ),
          el("div", { className: "form-actions" }, action("إلغاء", () => dialog.close(), "button secondary"), run),
        ));
      } catch (error) {
        content.replaceChildren(apiError(error));
      }
    };

    data.suites.forEach((suite) => suiteList.append(el("article", { className: "suite-card" },
      el("div", { className: "suite-card-head" },
        el("div", {}, el("h3", {}, suite.name || suite.key), technicalCode(suite.key)),
        suite.supported ? el("span", { className: "support-label supported" }, "متاح للتشغيل") : el("span", { className: "support-label unsupported" }, "غير متاح للتشغيل"),
      ),
      el("dl", { className: "suite-meta" },
        infoField("الإصدار", suite.version),
        infoField("الحالات", suite.case_count),
        infoField("النوع", (suite.evaluation_types || []).map(evaluationTypeLabel).join("، ")),
      ),
      !suite.supported ? el("p", { className: "unsupported-note" }, "التقييم بمساعدة نموذج غير مفعّل لعدم توفر حَكَم إنتاجي معتمد.") : null,
      el("div", { className: "card-actions" },
        action("عرض الحالات", () => suiteDetails(suite), "button secondary"),
        suite.supported && state.permissions.has("evaluation.run") ? action("تشغيل التقييم", () => runSuite(suite)) : null,
      ),
    )));

    const runDetails = async (run) => {
      try {
        const detail = await getJSON(`/api/workspaces/${state.workspaceId}/evaluation/runs/${run.id}`);
        const body = el("div", { className: "stack" },
          el("dl", { className: "info-grid" },
            infoField("المجموعة", detail.suite_key),
            infoField("الإصدار", detail.suite_version),
            infoField("المساعد", detail.assistant_name || "—"),
            infoField("الحالة", statusBadge(detail.status)),
            infoField("النتيجة", `${detail.passed_count} ناجحة من ${detail.case_count}`),
            infoField("بدأ", formatDate(detail.started_at)),
            infoField("اكتمل", formatDate(detail.completed_at)),
          ),
          detail.failure_category ? el("div", { className: "failure-note" }, `فئة التعثر: ${detail.failure_category}`) : null,
          state.permissions.has("evaluation.run") ? action("إعادة التشغيل", async () => {
            const content = el("div", { className: "stack" },
              el("div", { className: "provider-warning", role: "note" },
                el("strong", {}, "تنبيه استخدام المزود"),
                el("p", {}, "قد تستهلك إعادة التشغيل موارد النموذج أو التضمين وفق الإعدادات الحالية."),
              ),
            );
            const rerunDialog = drawer("تأكيد إعادة التشغيل", content);
            const confirm = action("إعادة التشغيل", async () => {
              confirm.disabled = true;
              try {
                await request(`/api/workspaces/${state.workspaceId}/evaluation/runs/${run.id}/rerun`, { method: "POST" });
                invalidateResources("evaluation");
                rerunDialog.close();
                showToast("تم إنشاء تشغيل تقييم جديد.");
                host.dispatchEvent(new Event("refresh"));
              } catch (error) {
                content.append(apiError(error));
                confirm.disabled = false;
              }
            });
            content.append(el("div", { className: "form-actions" }, action("إلغاء", () => rerunDialog.close(), "button secondary"), confirm));
          }, "button secondary") : null,
          el("section", { className: "case-list" },
            el("h3", {}, "نتائج الحالات"),
            ...detail.results.map((item) => el("article", { className: "case-card" },
              el("div", { className: "case-head" }, el("strong", {}, item.case_key), el("span", { className: `result-badge ${item.passed ? "passed" : "failed"}` }, item.passed ? "ناجحة" : "لم تنجح")),
              item.input ? el("p", {}, item.input) : null,
              item.expected_outcome ? el("p", { className: "case-expected" }, `المتوقع: ${item.expected_outcome}`) : null,
              item.actual ? el("p", { className: "case-actual" }, `النتيجة الفعلية: ${item.actual}`) : null,
              item.failure_category ? el("p", { className: "failure-note" }, item.failure_category) : null,
            )),
          ),
        );
        drawer(`نتيجة ${detail.suite_key}`, body);
      } catch (error) {
        host.append(apiError(error));
      }
    };

    const history = data.runs.map((run) => [
      el("div", { className: "primary-cell" }, el("strong", {}, run.suite_key), el("span", { className: "secondary-meta" }, `الإصدار ${run.suite_version}`)),
      run.assistant_name || "—",
      statusBadge(run.status),
      `${run.passed_count}/${run.case_count}`,
      formatDate(run.started_at),
      action("التفاصيل", () => runDetails(run), "button secondary small"),
    ]);
    host.replaceChildren(
      pageHeader("التقييم", "مجموعات تقييم معتمدة للقراءة وسجل تشغيل محفوظ."),
      panel("مجموعات التقييم", suiteList.children.length ? suiteList : emptyState("لا توجد مجموعات تقييم", "لا تتوفر تعريفات تقييم في الكتالوج الحالي.")),
      panel("سجل التشغيل", history.length ? table(["المجموعة", "المساعد", "الحالة", "النتيجة", "وقت البدء", ""], history) : emptyState("لا يوجد سجل تشغيل", "لم يتم تشغيل تقييم في مساحة العمل.")),
    );
  });
  host.addEventListener("refresh", () => host.replaceWith(evaluationPage()));
  return host;
}

export const APP_PAGES = {
  home: homePage,
  assistants: assistantsPage,
  knowledge: knowledgePage,
  evaluation: evaluationPage,
  members: membersPage,
  conversations: conversationsPage,
};
