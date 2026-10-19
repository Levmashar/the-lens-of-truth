import { createBrandLogo, createThemeToggle } from "../components/themeToggle";
import { append, element } from "../utils/dom";
import { readerFixtures } from "./fixtures";
import { createReaderScreen } from "./screen";
import "../styles/reset.css";
import "../styles/tokens.css";
import "../styles/global.css";
import "../styles/layout.css";
import "../styles/document.css";
import "../styles/components.css";
import "./reader.css";

if (!import.meta.env.DEV) throw new Error("Reader preview is development-only and is not a live report route");
const root = document.getElementById("reader-preview");
if (!root) throw new Error("Reader preview root missing");
const skip = element("a", "reader-skip", "Skip to the result"); skip.href = "#reader-content";
const header = element("header", "reader-header");
const brand = element("a", "brand"); brand.href = "/"; brand.setAttribute("aria-label", "The Lens of Truth, home");
brand.append(createBrandLogo());
const theme = createThemeToggle(); header.append(brand, theme.node);
const toolbar = element("section", "reader-fixture-controls"); toolbar.setAttribute("aria-label", "Development preview controls");
const label = element("label", "", "Preview state"); label.htmlFor = "reader-fixture";
const select = element("select"); select.id = "reader-fixture";
for (const fixture of readerFixtures) { const option = element("option", "", fixture.label); option.value = fixture.id; select.append(option); }
const requested = new URLSearchParams(location.search).get("fixture");
select.value = readerFixtures.some((f) => f.id === requested) ? requested! : "incomplete";
const fixtureNotice = element("p", "reader-fixture-notice"); fixtureNotice.setAttribute("role", "status");
append(toolbar, label, select, fixtureNotice);
const main = element("main", "reader-content"); main.id = "reader-content"; main.tabIndex = -1;
append(root, skip, header, toolbar, main);

function render(): void {
  const fixture = readerFixtures.find((f) => f.id === select.value)!;
  fixtureNotice.textContent = fixture.origin === "synthetic_scenario" ? `Synthetic fixture. ${fixture.originNotice}` : fixture.originNotice;
  main.replaceChildren(createReaderScreen(fixture));
  const url = new URL(location.href); url.searchParams.set("fixture", fixture.id); history.replaceState(null, "", url);
  document.title = `${fixture.id === "completed" ? "Completed" : fixture.id === "inconclusive" ? "Scientifically unresolved" : "Incomplete"} · Lens reader preview`;
}
select.addEventListener("change", render); render();
