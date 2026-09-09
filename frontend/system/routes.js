import { SYSTEM_CONTROL_PAGES } from "/assets/system/controls-pages.js?v=stage4-provider-resolution-1";
import { SYSTEM_PAGES } from "/assets/system/pages.js?v=stage4-provider-resolution-1";

const system = (path, label, permission, description, render = null) => ({
  path, label, requiredPermission: permission, scope: "SYSTEM",
  render,
});

export const SYSTEM_ROUTES = [
  system("/system", "الرئيسية", "system_workspaces.read", null, SYSTEM_PAGES.home),
  system("/system/workspaces", "مساحات العمل", "system_workspaces.read", null, SYSTEM_PAGES.workspaces),
  system("/system/assistants", "المساعدون والربط", "system_assistants.read", null, SYSTEM_PAGES.assistants),
  system("/system/knowledge", "مصادر المعرفة", "system_knowledge.read", null, SYSTEM_PAGES.knowledge),
  system("/system/teams", "الفرق", "teams.read", null, SYSTEM_PAGES.teams),
  system("/system/members", "الأعضاء والعضويات", "system_memberships.read", null, SYSTEM_PAGES.members),
  system("/system/roles", "الأدوار والصلاحيات", "roles.read", null, SYSTEM_PAGES.roles),
  system("/system/policies", "الضوابط والسياسات", "governance.read", null, SYSTEM_CONTROL_PAGES.policies),
  system("/system/usage", "الاستخدام", "usage.read", null, SYSTEM_CONTROL_PAGES.usage),
  system("/system/providers", "المزودون والنماذج", "providers.read", null, SYSTEM_CONTROL_PAGES.providers),
  system("/system/credentials", "بيانات الاعتماد", "credentials.read", null, SYSTEM_CONTROL_PAGES.credentials),
  system("/system/conversations", "المحادثات", "system_conversations.read", null, SYSTEM_CONTROL_PAGES.conversations),
  system("/system/audit", "سجل النظام", "audit.read", null, SYSTEM_CONTROL_PAGES.audit),
  system("/system/access", "إدارة الوصول للنظام", "system_access.read", null, SYSTEM_CONTROL_PAGES.access),
];
