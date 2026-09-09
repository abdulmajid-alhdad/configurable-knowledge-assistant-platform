import { isSafeInternalUrl } from "/assets/shared/dom.js";

const inflightGets = new Map();

export class ApiError extends Error {
  constructor(status, code = "REQUEST_FAILED", message = "تعذر إكمال الطلب.") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function apiUrl(path) {
  if (!isSafeInternalUrl(path)) throw new ApiError(0, "INVALID_API_URL", "مسار API غير صالح.");
  const url = new URL(path, window.location.origin);
  if (!url.pathname.startsWith("/api/")) {
    throw new ApiError(0, "INVALID_API_URL", "مسار API غير صالح.");
  }
  return url;
}

async function decode(response) {
  if (response.status === 204) return null;
  const body = await response.text();
  if (!body) return null;
  try {
    return JSON.parse(body);
  } catch {
    return { detail: "استجابة غير صالحة من الخادم." };
  }
}

export async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const url = apiUrl(path);
  const key = `${method}:${url.href}`;
  if (method === "GET" && inflightGets.has(key)) return inflightGets.get(key);
  const task = fetch(url.href, {
    ...options,
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(options.headers || {}) },
  }).then(async (response) => {
    const payload = await decode(response);
    if (!response.ok) {
      const detail = typeof payload?.detail === "string" ? payload.detail : "تعذر إكمال الطلب.";
      throw new ApiError(response.status, detail, detail);
    }
    return payload;
  });
  if (method === "GET") {
    inflightGets.set(key, task);
    task.then(() => inflightGets.delete(key), () => inflightGets.delete(key));
  }
  return task;
}

export const getJSON = (path) => request(path);
export const clearInflight = () => inflightGets.clear();
