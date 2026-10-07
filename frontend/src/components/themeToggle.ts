import darkLettering from "../assets/logo_dark.png";
import lightLettering from "../assets/logo_light.png";
import { append, element } from "../utils/dom";

type Theme = "light" | "dark";
const storageKey = "lens-theme";

function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(storageKey);
    return value === "light" || value === "dark" ? value : null;
  } catch { return null; }
}

export function createThemeToggle(): { node: HTMLButtonElement; dispose: () => void } {
  const media = window.matchMedia?.("(prefers-color-scheme: dark)");
  let preference = savedTheme();
  let theme: Theme = preference ?? (media?.matches ? "dark" : "light");
  const button = element("button", "theme-toggle");
  button.type = "button";
  const icon = element("span", "theme-icon");
  icon.setAttribute("aria-hidden", "true");
  const label = element("span", "theme-label");
  append(button, icon, label);

  function apply(next: Theme): void {
    theme = next;
    document.documentElement.dataset.theme = theme;
    button.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
    button.setAttribute("aria-pressed", String(theme === "dark"));
    icon.dataset.theme = theme;
    label.textContent = theme === "dark" ? "Light mode" : "Dark mode";
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
      ?.setAttribute("content", theme === "dark" ? "#10141d" : "#f7f8fc");
  }
  button.addEventListener("click", () => {
    preference = theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(storageKey, preference); } catch { /* Switching still works without storage. */ }
    apply(preference);
  });
  const onSystemChange = (event: MediaQueryListEvent): void => {
    if (!preference) apply(event.matches ? "dark" : "light");
  };
  media?.addEventListener("change", onSystemChange);
  apply(theme);
  return { node: button, dispose: () => media?.removeEventListener("change", onSystemChange) };
}

export function createBrandLogo(): HTMLElement {
  const logo = element("span", "brand-logo");
  for (const [src, className] of [[darkLettering, "logo-on-light"], [lightLettering, "logo-on-dark"]]) {
    const image = element("img", className);
    image.src = src;
    image.alt = "";
    image.width = 270;
    image.height = 90;
    logo.append(image);
  }
  return logo;
}
