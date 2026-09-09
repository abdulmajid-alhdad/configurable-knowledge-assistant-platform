export function appendContent(parent, value) {
  if (value === null || value === undefined || value === false) return;
  if (Array.isArray(value)) {
    value.forEach((item) => appendContent(parent, item));
    return;
  }
  if (typeof Node !== "undefined" && value instanceof Node) {
    parent.append(value);
    return;
  }
  if (["string", "number", "boolean"].includes(typeof value)) {
    parent.append(document.createTextNode(String(value)));
    return;
  }
  throw new TypeError("Unsupported DOM content");
}

export function el(tagName, properties = {}, ...children) {
  const node = document.createElement(tagName);
  Object.entries(properties).forEach(([key, value]) => {
    if (key === "className") node.className = value;
    else if (key === "textContent") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  });
  appendContent(node, children);
  return node;
}

export function text(value) {
  return document.createTextNode(String(value ?? ""));
}

export function isSafeInternalUrl(value) {
  if (typeof value !== "string" || value.startsWith("javascript:")) return false;
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin && !url.protocol.startsWith("javascript");
  } catch {
    return false;
  }
}

export function safeHref(value) {
  return isSafeInternalUrl(value) ? value : "#";
}

export function containsDom(value) {
  if (Array.isArray(value)) return value.some(containsDom);
  return typeof Node !== "undefined" && value instanceof Node;
}
