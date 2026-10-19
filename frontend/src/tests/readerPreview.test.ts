// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readerFixtures } from "../preview/fixtures";
import { assertion, citation, questionStatus, readerSentences, validateFixture } from "../preview/model";
import { createReaderScreen } from "../preview/screen";

const incomplete = readerFixtures.find((f) => f.id === "incomplete")!;
beforeEach(() => {
  document.body.replaceChildren();
  vi.stubEnv("DEV", true);
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function mount() {
  const node = createReaderScreen(incomplete); document.body.append(node); return node;
}
function openAdvanced(node: HTMLElement) {
  const details = node.querySelector<HTMLDetailsElement>(".reader-advanced")!;
  details.open = true; details.dispatchEvent(new Event("toggle")); return details;
}

describe("fixture-backed reader preview", () => {
  it("preserves the exact incomplete outcomes and keeps high-risk checks unavailable", () => {
    const before = JSON.stringify(incomplete.report);
    mount();
    expect(incomplete.report.analysis_id).toBe("a897813c-5ce9-4f56-b1b6-29c50ed2480e");
    const records = incomplete.report.groups.flatMap((g) => g.assertions);
    expect(records.filter((a) => a.status === "completed")).toHaveLength(4);
    expect(records.filter((a) => a.status === "unavailable")).toHaveLength(3);
    expect(records.filter((a) => a.status === "not_checkable")).toHaveLength(4);
    for (const id of ["A3", "A4", "A5"]) expect(assertion(incomplete.report, id).result_label).toBe("unable_to_verify_reliably");
    expect(JSON.stringify(incomplete.report)).toBe(before);
  });

  it.each(readerFixtures)("traces every $id sentence and preserves exact owned quotations", (fixture) => {
    expect(() => validateFixture(fixture)).not.toThrow();
    for (const sentence of readerSentences(fixture)) expect(sentence.references.length).toBeGreaterThan(0);
    for (const question of fixture.questions) for (const quote of question.quotes) {
      expect(citation(fixture.report, quote).exact_text).toContain(quote.text);
    }
    const words = [fixture.headline, ...fixture.established, ...fixture.limitation].map((s) => s.text).join(" ").split(/\s+/).length;
    expect(words).toBeGreaterThanOrEqual(80); expect(words).toBeLessThanOrEqual(150);
  });

  it("does not promote unavailable records to approved facts or finished scientific assessments", () => {
    const fixture = structuredClone(incomplete);
    fixture.headline.basis = "approved_finding";
    expect(() => validateFixture(fixture)).toThrow("cannot become an approved summary fact");
    fixture.headline.basis = "saved_assessment";
    expect(() => validateFixture(fixture)).toThrow("cannot become a completed scientific assessment");
  });

  it("rejects invented or foreign source excerpts", () => {
    const fixture = structuredClone(incomplete);
    fixture.questions[0].quotes[0].text = "A fabricated statement from a raw model reply.";
    expect(() => validateFixture(fixture)).toThrow("exact owned citation");
  });

  it("keeps scientific uncertainty distinct from incomplete checks", () => {
    const mixed = readerFixtures.find((f) => f.id === "inconclusive")!;
    const question = mixed.questions.find((q) => q.id === "number")!;
    expect(questionStatus(mixed, question)).toBe("Evidence is inconclusive");
    expect(questionStatus(incomplete, incomplete.questions.find((q) => q.id === "number")!)).toBe("We couldn’t complete this check");
    expect(mixed.origin).toBe("synthetic_scenario");
  });

  it("leads with the answer and hides identifiers, counts and raw responses from the ordinary view", () => {
    const node = mount(); const hero = node.querySelector(".reader-answer")!;
    expect(hero.textContent).toContain("couldn’t finish checking its main claims");
    expect(hero.textContent).not.toMatch(/A\d+|E\d+|Qwen|GLM|quorum|assertions processed|4 details match/);
    expect(hero.textContent).toContain("other risk factors also needs review");
    expect(hero.textContent).toContain("Not approved for public release");
    expect(node.querySelector(".debug-panel")).toBeNull();
    expect(node.querySelector(".reader-evidence")?.hasAttribute("hidden")).toBe(true);
  });

  it("opens evidence through a keyboard-compatible button and transfers focus", () => {
    const node = mount(); const button = node.querySelector<HTMLButtonElement>(".reader-actions button")!;
    button.click();
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(node.querySelector(".reader-evidence")?.hasAttribute("hidden")).toBe(false);
    expect(document.activeElement?.id).toBe("reader-evidence-title");
    button.click(); expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("pools full passages and opens the matching visible disclosure", () => {
    const node = mount(); node.querySelector<HTMLButtonElement>(".reader-actions button")!.click();
    const number = node.querySelector<HTMLDetailsElement>('[data-question="number"]')!; number.open = true;
    number.querySelector<HTMLButtonElement>(".reader-passage-button")!.click();
    const passages = node.querySelector<HTMLElement>(".reader-passages")!;
    expect(passages.hidden).toBe(false);
    expect(passages.querySelector("details[open]")).not.toBeNull();
    expect(document.activeElement?.tagName).toBe("SUMMARY");
    const quotedUnits = new Set(incomplete.questions.flatMap((q) => q.quotes.map((quote) => quote.sourceUnitId)));
    expect(passages.querySelectorAll(".reader-full-passage")).toHaveLength(quotedUnits.size);
  });

  it("flags adjustment without changing its saved supported label", () => {
    const node = mount();
    expect(node.querySelector('[data-question="adjustment"] .reader-check-status')?.textContent).toBe("Saved result: Matches the paper · Review flagged");
    expect(node.querySelector('[data-question="adjustment"] .reader-correctness-flag')?.textContent).toContain("Saved result unchanged");
    expect(assertion(incomplete.report, "A6").result_label).toBe("supported");
  });

  it("retains all original records and raw replies in the lazy advanced view", () => {
    const before = JSON.stringify(incomplete.report);
    const node = mount(); const advanced = openAdvanced(node);
    expect(advanced.querySelectorAll("[data-assertion-id]")).toHaveLength(11);
    expect(advanced.textContent).toContain("reporting_attribution_statement_ids_mismatch");
    expect(advanced.textContent).toContain("Reader wording and supporting references");
    expect(advanced.querySelector(".debug-panel")).not.toBeNull();
    expect(JSON.stringify(incomplete.report)).toBe(before);
  });

  it("copies complete saved diagnostics with raw model responses through the existing control", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const node = mount(); const advanced = openAdvanced(node);
    const copy = [...advanced.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Copy all diagnostics")!;
    copy.click(); await vi.waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    const payload = JSON.parse(writeText.mock.calls[0][0]);
    expect(payload.document.debug_group_runs).toEqual(incomplete.report.debug_group_runs);
    expect(payload.analysis.analysis_id).toBe(incomplete.report.analysis_id);
    expect(advanced.textContent).toContain("Copied all diagnostics, including raw model responses.");
  });

  it("handles denied clipboard access visibly", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    const advanced = openAdvanced(mount());
    [...advanced.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Copy all diagnostics")!.click();
    await vi.waitFor(() => expect(advanced.textContent).toContain("Could not copy diagnostics"));
  });

  it("uses real source links with safe target and rel values", () => {
    const node = mount(); const link = [...node.querySelectorAll<HTMLAnchorElement>("a")].find((a) => a.textContent === "Read the study")!;
    expect(link.href).toBe("https://pubmed.ncbi.nlm.nih.gov/37642678/");
    expect(link.rel).toBe("noopener noreferrer"); expect(link.target).toBe("_blank");
  });
});
