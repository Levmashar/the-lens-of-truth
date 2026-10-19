// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDocumentReader } from "../components/documentReader";
import { readerFixtures } from "../preview/fixtures";
import { createAnalysisPage } from "../pages/analysis";
import { jsonResponse, progress } from "./fixtures";
import type { DocumentReport } from "../types/document";

const fixture = readerFixtures.find((f) => f.id === "incomplete")!;
function liveReport(): DocumentReport {
  const { report, analysis: _analysis, label: _label, origin: _origin, originNotice: _notice, ...topic } = fixture;
  return { ...structuredClone(report), reader_view: { version: "reader-view-1.0", topics: [{ ...topic, id: "G1", state: "incomplete" }] } };
}
beforeEach(() => { document.body.replaceChildren(); Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() }); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe("live document reader", () => {
  it("uses the reader answer while keeping raw diagnostics out of the ordinary view", () => {
    const report = liveReport();
    const before = JSON.stringify(report);
    const node = createDocumentReader(report, fixture.analysis!, new Map(), true);
    expect(node.textContent).toContain("couldn’t finish checking its main claims");
    expect(node.querySelector(".debug-panel")).toBeNull();
    expect(node.querySelector(".reader-development-notice")?.textContent).toBe("Development result · Not approved for public release.");
    expect(node.textContent).not.toContain("Synthetic");
    expect(JSON.stringify(report)).toBe(before);
  });

  it("preserves disclosure and evidence state across report polling", () => {
    const report = liveReport(); const states = new Map<string, boolean>();
    const first = createDocumentReader(report, fixture.analysis!, states, true); document.body.append(first);
    first.querySelector<HTMLButtonElement>(".reader-actions button")!.click();
    const question = first.querySelector<HTMLDetailsElement>(".reader-question")!;
    question.open = true; question.dispatchEvent(new Event("toggle"));
    const updated = createDocumentReader(report, fixture.analysis!, states, true);
    expect(updated.querySelector<HTMLElement>(".reader-evidence")?.hidden).toBe(false);
    expect(updated.querySelector<HTMLDetailsElement>(".reader-question")?.open).toBe(true);
  });

  it("keeps topic IDs unique and the original audit view singular", () => {
    const report = liveReport();
    report.reader_view!.topics.push({ ...report.reader_view!.topics[0], id: "G2" });
    const node = createDocumentReader(report, fixture.analysis!, new Map(), true);
    const ids = [...node.querySelectorAll<HTMLElement>("[id]")].map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(node.querySelectorAll(".reader-advanced")).toHaveLength(1);
    expect(node.querySelectorAll("h1")).toHaveLength(1);
  });

  it("does not render development-only raw replies when diagnostics are disabled", () => {
    const node = createDocumentReader(liveReport(), fixture.analysis!, new Map(), false);
    const advanced = node.querySelector<HTMLDetailsElement>(".reader-advanced")!;
    advanced.open = true; advanced.dispatchEvent(new Event("toggle"));
    expect(node.querySelector(".debug-panel")).toBeNull();
    expect(node.textContent).not.toContain("Raw saved replies");
  });

  it("connects the normal analysis page to the server-owned reader view", async () => {
    const report = liveReport();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return jsonResponse(url.endsWith("/document") ? report : url.endsWith("/claims") ? { claims: [] }
        : progress({ analysis_id: report.analysis_id, document_mode: true, status: "partially_completed", claims: [], debug_enabled: true }));
    }));
    const page = createAnalysisPage(report.analysis_id); document.body.append(page.node);
    try {
      await vi.waitFor(() => expect(page.node.querySelector(".document-reader")).not.toBeNull());
      expect(page.node.querySelector<HTMLElement>(".analysis-heading")?.hidden).toBe(true);
      expect(page.node.querySelector(".debug-panel")).toBeNull();
    } finally { page.dispose(); }
  });

  it("never announces success for a failed document with no assessed claims", async () => {
    const report = liveReport(); report.status = "failed"; report.progress.assertions_completed = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      return jsonResponse(url.endsWith("/document") ? report : url.endsWith("/claims") ? { claims: [] }
        : progress({ analysis_id: report.analysis_id, document_mode: true, status: "failed",
          stage: "building_report", claims: [], debug_enabled: true, failure_code: "document_assessments_unavailable" }));
    }));
    const page = createAnalysisPage(report.analysis_id); document.body.append(page.node);
    try {
      await vi.waitFor(() => expect(page.node.dataset.state).toBe("failed"));
      expect(page.node.querySelector(".connection-note")?.textContent).toContain("No claims were successfully assessed");
      expect(page.node.querySelector(".sr-only")?.textContent).toBe("Check could not be completed reliably");
      expect(page.node.querySelector(".sr-only")?.textContent).not.toBe("Analysis finished");
    } finally { page.dispose(); }
  });
});
