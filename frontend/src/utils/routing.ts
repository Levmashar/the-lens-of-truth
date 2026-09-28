export type Route = { page: "home" } | { page: "analysis"; id: string } | { page: "not_found" };

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function currentRoute(path = window.location.pathname): Route {
  if (path === "/") return { page: "home" };
  const match = /^\/analysis\/([^/]+)\/?$/.exec(path);
  if (match && uuidPattern.test(match[1])) return { page: "analysis", id: match[1] };
  return { page: "not_found" };
}

export function navigate(path: string): void {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo?.(0, 0);
}
