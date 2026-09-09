-- Stage 7A live security correction: least privilege and extension placement.
revoke insert on table platform.workspaces from knowledge_platform_runtime;

alter extension citext set schema extensions;
