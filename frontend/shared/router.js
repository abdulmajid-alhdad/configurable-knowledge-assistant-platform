import { isSafeInternalUrl } from "/assets/shared/dom.js";

function routeSpace(pathname) {
  if (pathname === "/app" || pathname.startsWith("/app/")) return "app";
  if (pathname === "/system" || pathname.startsWith("/system/")) return "system";
  return null;
}

function isModifiedClick(event) {
  return event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey;
}

export function createRouter({ surface, routes, render }) {
  let generation = 0;
  let started = false;

  function match(pathname) {
    return routes.find((route) => route.path === pathname) || routes.find((route) => route.path !== `/${surface}` && pathname.startsWith(`${route.path}/`));
  }

  function current() {
    return { path: `${window.location.pathname}${window.location.search}${window.location.hash}`, generation };
  }

  function navigate(path, { replace = false } = {}) {
    if (!isSafeInternalUrl(path)) return false;
    const url = new URL(path, window.location.origin);
    if (routeSpace(url.pathname) !== surface) return false;
    const next = `${url.pathname}${url.search}${url.hash}`;
    if (replace) window.history.replaceState({}, "", next);
    else window.history.pushState({}, "", next);
    generation += 1;
    render({ ...current(), route: match(url.pathname) });
    return true;
  }

  function onPopState() {
    if (routeSpace(window.location.pathname) !== surface) return;
    generation += 1;
    render({ ...current(), route: match(window.location.pathname) });
  }

  function onClick(event) {
    if (isModifiedClick(event)) return;
    const anchor = event.target.closest?.("a[href]");
    if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
    const href = anchor.getAttribute("href");
    if (!href || !isSafeInternalUrl(href)) return;
    const url = new URL(href, window.location.origin);
    if (url.origin !== window.location.origin || routeSpace(url.pathname) !== surface) return;
    event.preventDefault();
    navigate(`${url.pathname}${url.search}${url.hash}`);
  }

  function start() {
    if (started) return router;
    started = true;
    window.addEventListener("popstate", onPopState);
    document.addEventListener("click", onClick);
    generation += 1;
    render({ ...current(), route: match(window.location.pathname) });
    return router;
  }

  const router = { current, navigate, start, get generation() { return generation; } };
  return router;
}
