import { createHomePage } from "./pages/home";
import { createAnalysisPage } from "./pages/analysis";
import { createBrandLogo, createThemeToggle } from "./components/themeToggle";
import { append, clear, element } from "./utils/dom";
import { currentRoute, navigate } from "./utils/routing";
import "./styles/reset.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/layout.css";
import "./styles/home.css";
import "./styles/analysis.css";
import "./styles/progress.css";
import "./styles/document.css";
import "./styles/components.css";
import "./styles/responsive.css";

const root = document.getElementById("app");
if (!root) throw new Error("Application root not found");

const header = element("header", "site-header");
const headerContent = element("div", "header-content content-width");
const brand = element("button", "brand");
brand.type = "button";
brand.setAttribute("aria-label", "The Lens of Truth, home");
brand.append(createBrandLogo());
brand.addEventListener("click", () => navigate("/"));
const headerRight = element("div", "header-right");
const methodLink = element("a", "header-link", "How it works");
methodLink.href = "/#method";
methodLink.addEventListener("click", (event) => {
  if (window.location.pathname !== "/") {
    event.preventDefault();
    navigate("/");
    document.getElementById("method")?.scrollIntoView();
  }
});
const theme = createThemeToggle();
headerRight.append(methodLink, theme.node);
append(headerContent, brand, headerRight);
header.append(headerContent);
const main = element("main", "site-main");
main.id = "main-content";
const footer = element("footer", "site-footer");
const footContent = element("div", "footer-content content-width");
append(footContent, element("span", "", "The Lens of Truth"),
  element("span", "", "Health claims, checked against research."));
footer.append(footContent);
root.append(header, main, footer);

let disposePage: (() => void) | null = null;
let renderedPath: string | null = null;

function renderRoute(): void {
  // Native citation anchors must scroll within the existing report, not reload it.
  if (renderedPath === window.location.pathname) return;
  renderedPath = window.location.pathname;
  disposePage?.();
  clear(main);
  const route = currentRoute();
  if (route.page === "home") {
    const page = createHomePage();
    page.node.querySelector(".how-section")?.setAttribute("id", "method");
    main.append(page.node);
    disposePage = page.dispose;
  } else if (route.page === "analysis") {
    const page = createAnalysisPage(route.id);
    main.append(page.node);
    disposePage = page.dispose;
  } else {
    const missing = element("section", "content-width error-state");
    append(missing, element("h1", "page-title", "Page not found"),
      element("p", "", "The page you requested is not available."));
    const button = element("button", "button button-primary", "Return home");
    button.addEventListener("click", () => navigate("/"));
    missing.append(button);
    main.append(missing);
    disposePage = null;
  }
}

window.addEventListener("popstate", renderRoute);
renderRoute();
