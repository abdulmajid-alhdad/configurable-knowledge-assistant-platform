import { containsDom } from "/assets/shared/dom.js";

function dataOnly(value) {
  if (containsDom(value)) throw new TypeError("DOM nodes cannot enter the data cache");
  return value;
}

export function workspaceKey(workspaceId, resource, query = "") {
  return `${workspaceId || "anonymous"}:${resource}:${query}`;
}

export class WorkspaceCache {
  constructor() {
    this.entries = new Map();
    this.inflight = new Map();
  }

  get(key) { return this.entries.get(key)?.value; }
  has(key) { return this.entries.has(key); }

  set(key, value) {
    this.entries.set(key, { value: dataOnly(value), updatedAt: Date.now() });
    return value;
  }

  invalidate(key) { this.entries.delete(key); }

  invalidateWorkspace(workspaceId) {
    const prefix = `${workspaceId}:`;
    [...this.entries.keys()].filter((key) => key.startsWith(prefix)).forEach((key) => this.entries.delete(key));
  }

  clear() {
    this.entries.clear();
    this.inflight.clear();
  }

  fetch(key, loader) {
    if (this.inflight.has(key)) return this.inflight.get(key);
    const task = Promise.resolve().then(loader).then((value) => this.set(key, value));
    this.inflight.set(key, task);
    task.then(() => this.inflight.delete(key), () => this.inflight.delete(key));
    return task;
  }

  staleWhileRevalidate(key, loader, { isCurrent, onFresh, onError } = {}) {
    const cached = this.get(key);
    const refresh = this.fetch(key, loader).then((value) => {
      if (!isCurrent || isCurrent()) onFresh?.(value);
      return value;
    }).catch((error) => {
      onError?.(error);
      throw error;
    });
    return { cached, refresh };
  }
}

export const workspaceCache = new WorkspaceCache();
export const invalidateWorkspace = (workspaceId) => workspaceCache.invalidateWorkspace(workspaceId);

export function prefetchAuthorized({ workspaceId, permissions, resources }) {
  resources.filter((resource) => permissions?.has(resource.permission)).forEach((resource) => {
    const key = workspaceKey(workspaceId, resource.key, resource.query || "");
    if (!workspaceCache.has(key)) workspaceCache.fetch(key, resource.loader).catch(() => {});
  });
}
