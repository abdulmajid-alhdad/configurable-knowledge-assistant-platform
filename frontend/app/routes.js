import { APP_PAGES } from "/assets/app/pages.js?v=stage4-auth-footer-2";

export const APP_ROUTES = [
  { path: "/app", label: "الرئيسية", requiredPermission: "workspace.read", scope: "WORKSPACE", render: APP_PAGES.home },
  { path: "/app/assistants", label: "المساعدون", requiredPermission: "assistant.read", scope: "WORKSPACE", render: APP_PAGES.assistants },
  { path: "/app/knowledge", label: "مصادر المعرفة", requiredPermission: "knowledge.read", scope: "WORKSPACE", render: APP_PAGES.knowledge },
  { path: "/app/evaluation", label: "التقييم", requiredPermission: "evaluation.read", scope: "WORKSPACE", render: APP_PAGES.evaluation },
  { path: "/app/members", label: "الأعضاء", requiredPermission: "members.read", scope: "WORKSPACE", render: APP_PAGES.members },
  { path: "/app/conversations", label: "المحادثات", requiredPermission: "conversations.read", scope: "WORKSPACE", render: APP_PAGES.conversations },
];
