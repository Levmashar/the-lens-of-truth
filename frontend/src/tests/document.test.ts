// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createDocumentReport } from "../components/documentReport";
import { createDebugProgress } from "../components/debugProgress";
import { createAnalysisPage } from "../pages/analysis";
import type { DocumentAssertion, DocumentGroup, DocumentReport } from "../types/document";
import { analysisId, jsonResponse, progress, summaries } from "./fixtures";

let dispose: (() => void) | null = null;
beforeEach(() => document.body.replaceChildren());
afterEach(() => { dispose?.(); dispose = null; vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

function assertion(overrides: Partial<DocumentAssertion> = {}): DocumentAssertion {
  return {
    assertion_id: "A1", text: "The study reported a higher melanoma risk.", kind: "reported_study_fact",
    status: "completed", result_label: "supported", explanation: "The matched source reports this association.",
    source_reports: "The observational analysis reported a higher estimated risk.",
    reporting_fidelity: { result_label: "supported", explanation: "The statistic matches the frozen study passage." },
    medical_interpretation: { result_label: "not_enough_evidence", explanation: "This association does not establish causation." },
    interpretation_limits: ["The exposure was not randomized."],
    citations: [{ evidence_id: "E1", source_unit_id: "E1.U1", title: "Cohort report",
      url: "https://pubmed.ncbi.nlm.nih.gov/123/", section: "RESULTS",
      exact_text: "Exact source wording <script>unsafe()</script>." }],
    source_spans: [{ start: 0, end: 42, text: "The study reported a higher melanoma risk." }], ...overrides,
  };
}

function group(overrides: Partial<DocumentGroup> = {}): DocumentGroup {
  return {
    group_id: "G1", title: "Sunscreen and skin cancer", status: "completed",
    source_match: { status: "identified", title: "Cohort report", url: "https://pubmed.ncbi.nlm.nih.gov/123/",
      reason: "Population, exposure and study clues match.", candidates: [], discrepancies: [] },
    assertions: [assertion()], ...overrides,
  };
}

function documentReport(overrides: Partial<DocumentReport> = {}): DocumentReport {
  return {
    version: "document-report-1.0", analysis_id: analysisId, status: "completed", production_qualified: false,
    groups: [group()], progress: { groups_total: 1, groups_completed: 1, assertions_total: 1, assertions_completed: 1 },
    ...overrides,
  };
}

function mount(): HTMLElement {
  const page = createAnalysisPage(analysisId);
  dispose = page.dispose;
  document.body.append(page.node);
  return page.node;
}

describe("document presentation", () => {
  it("keeps reporting fidelity separate from medical interpretation without an overall truth label", () => {
    const node = createDocumentReport(documentReport());
    expect(node.textContent).toContain("Supported as an accurate account of this study");
    expect(node.textContent).toContain("Medical interpretation");
    expect(node.textContent).toContain("This association does not establish causation.");
    expect(node.querySelector(".document-source-status")?.textContent).toBe("Source identified");
    expect(node.querySelectorAll(".verdict-label")).toHaveLength(0);
    expect(node.textContent).not.toMatch(/truth score|overall supported|\d+% confidence/i);
  });

  it("uses the general-medical meaning only for an actual medical assessment", () => {
    const node = createDocumentReport(documentReport({ groups: [group({ assertions: [assertion({
      kind: "general_medical_assertion", reporting_fidelity: null, medical_interpretation: null,
      text: "Smoking causes lung cancer.", explanation: "Validated evidence supports causation.",
    })] })] }));
    expect(node.textContent).toContain("Supported as a general medical conclusion");
    expect(node.textContent).not.toContain("Supported as an accurate account of this study");
  });

  it("shows an ordinary medical assessment once when the projection repeats its interpretation", () => {
    const explanation = "Validated evidence supports causation.";
    const node = createDocumentReport(documentReport({ groups: [group({ assertions: [assertion({
      kind: "general_medical_assertion", reporting_fidelity: null, source_reports: null,
      text: "Smoking causes lung cancer.", explanation,
      medical_interpretation: { result_label: "supported", explanation },
    })] })] }));
    expect(node.querySelectorAll(".document-assessment")).toHaveLength(1);
    expect(node.textContent?.split(explanation)).toHaveLength(2);
    expect(node.textContent).toContain("Supported as a general medical conclusion");
  });

  it("renders exact cited text and untrusted strings without executing markup", () => {
    const node = createDocumentReport(documentReport({ groups: [group({ title: "<img src=x onerror=bad()>",
      source_match: { ...group().source_match, title: "<script>bad()</script>", url: "javascript:bad()",
        candidates: [{ title: "Unsafe candidate", url: "javascript:bad()", reason: "Unmatched" }] },
    })] }));
    expect(node.querySelector(".document-citation mark")?.textContent)
      .toBe("Exact source wording <script>unsafe()</script>.");
    expect(node.querySelector("script, img")).toBeNull();
    expect([...node.querySelectorAll<HTMLAnchorElement>("a")].every((link) => !link.href.startsWith("javascript:"))).toBe(true);
    expect(node.textContent).toContain("Unsafe candidate");
    const link = node.querySelector(".document-citation a") as HTMLAnchorElement;
    expect(link.rel).toBe("noopener noreferrer");
    expect(link.target).toBe("_blank");
  });

  it("shows uncertain identification and discrepancies without presenting a candidate as established", () => {
    const node = createDocumentReport(documentReport({ groups: [group({ source_match: {
      status: "uncertain", title: "Candidate study", url: null, reason: "The endpoint matches but the stated statistic differs.",
      discrepancies: ["The comparison group remains unresolved."],
      candidates: [{ title: "Possible source", url: "https://example.org/source", reason: "Same population" }],
    } })] }));
    expect(node.querySelector(".document-source-status")?.textContent).toBe("Source match is uncertain");
    expect(node.textContent).toContain("The comparison group remains unresolved.");
    expect(node.textContent).toContain("Sources considered");
  });

  it("shows real partial completion and never gives pending assertions a saved label", () => {
    const node = createDocumentReport(documentReport({ status: "running",
      progress: { groups_total: 1, groups_completed: 0, assertions_total: 2, assertions_completed: 1 },
      groups: [group({ status: "running", assertions: [assertion(), assertion({ assertion_id: "A2", status: "pending",
        result_label: "contradicted", explanation: "Unchecked proposal", citations: [] })] })],
    }));
    expect(node.querySelector(".document-progress")?.textContent).toContain("1 of 2 details checked");
    expect(node.querySelector('[data-assertion-id="A2"] .document-assertion-result')?.textContent).toBe("Checking");
    expect(node.textContent).not.toContain("Unchecked proposal");
    expect(node.querySelector('[role="progressbar"]')?.getAttribute("aria-valuenow")).toBe("1");
  });

  it("does not show unavailable model citations as validated proof", () => {
    const node = createDocumentReport(documentReport({ groups: [group({ assertions: [assertion({
      status: "unavailable", result_label: null, reporting_fidelity: null, medical_interpretation: null,
      explanation: "This assessment could not be validated.",
    })] })] }));
    expect(node.querySelector(".document-assertion-result")?.textContent).toBe("Unable to Verify Reliably");
    expect(node.querySelector(".document-citations")).toBeNull();
  });

  it("retains duplicates and original wording without treating them as independent evidence", () => {
    const node = createDocumentReport(documentReport({ groups: [group({ assertions: [assertion(), assertion({
      assertion_id: "A2", status: "duplicate", result_label: null, duplicate_of: "A1",
      reporting_fidelity: null, medical_interpretation: null, citations: [],
      source_spans: [{ start: 45, end: 87, text: "Repeated source sentence." }],
    })] })] }));
    expect(node.textContent).toContain("Checked with its original statement");
    expect(node.textContent).toContain("Repeated source sentence.");
    expect(node.querySelector('[data-assertion-id="A2"] a')?.getAttribute("href"))
      .toBe("#document-assertion-G1-A1");
  });

  it("keeps separate studies and unrelated topics as separate expandable groups", () => {
    const node = createDocumentReport(documentReport({ groups: [group(), group({ group_id: "G2", title: "Another trial" }),
      group({ group_id: "G3", title: "An unrelated claim" })] }));
    expect(node.querySelectorAll(".document-topic")).toHaveLength(3);
    expect(node.querySelectorAll(".document-source")).toHaveLength(3);
    expect(node.querySelectorAll(".document-topic[open]")).toHaveLength(1);
  });

  it("keeps release qualification visible in public presentation", () => {
    vi.stubEnv("DEV", false);
    const node = createDocumentReport(documentReport());
    expect(node.querySelector(".qualification-notice")?.textContent).toContain("required for public release");
    expect(createDocumentReport(documentReport({ production_qualified: true })).querySelector(".qualification-notice")).toBeNull();
  });

  it("copies grouped diagnostics including raw replies without changing the existing export", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const saved = documentReport({ debug_group_runs: [{ group_id: "G1", raw_response: "Full grouped model reply" }] });
    const analysis = progress({ debug_enabled: true, document_mode: true });
    const panel = createDebugProgress(analysis, [], null, saved);
    (panel.querySelector("button") as HTMLButtonElement).click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({ analysis, claims: [], poll_error: null, document: saved });
    expect(panel.querySelector(".debug-grouped-responses")?.textContent).toContain("Full grouped model reply");
    expect(panel.querySelector(".debug-grouped-responses")?.hasAttribute("open")).toBe(false);
  });
});

describe("document API flow", () => {
  it("loads one document overview without requesting individual claim reports", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(jsonResponse(url.endsWith("/document")
      ? documentReport() : url.endsWith("/claims") ? summaries([]) : progress({ document_mode: true, claims: [] }))));
    vi.stubGlobal("fetch", fetchMock);
    const node = mount();
    await vi.waitFor(() => expect(node.querySelector(".document-report")).not.toBeNull());
    expect(node.querySelector("h1")?.textContent).toBe("Your document check");
    expect(node.querySelector(".claim-list")).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => url.includes("/report"))).toBe(false);
  });

  it("does not fetch the document endpoint for ordinary single-claim analyses", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(jsonResponse(url.endsWith("/claims")
      ? summaries([]) : progress({ claims: [], claim_count: 0 }))));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/document"))).toBe(false);
  });

  it("waits for planning instead of treating document_not_ready as a terminal error", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/document")
      ? jsonResponse({ error: { code: "document_not_ready" } }, 404)
      : jsonResponse(url.endsWith("/claims") ? summaries([])
        : progress({ document_mode: true, status: "running", stage: "extracting", claims: [] })))));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Reading the document in context"));
    expect(node.querySelector(".report-error")).toBeNull();
    expect(node.querySelector(".progress-host")?.hasAttribute("hidden")).toBe(false);
  });

  it("shows one terminal planner failure without suggesting an unfinished report will arrive", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(jsonResponse(url.endsWith("/claims")
      ? summaries([]) : progress({ document_mode: true, status: "failed", stage: "extracting",
        claims: [], failure_code: "document_planner_invalid_document_plan" }))));
    vi.stubGlobal("fetch", fetchMock);
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Document could not be read reliably"));
    expect(node.textContent).not.toContain("Reading the document in context");
    expect(node.querySelector(".report-error")).toBeNull();
    expect(node.querySelector(".progress-host")?.hasAttribute("hidden")).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/document"))).toBe(false);
  });

  it("shows a production-gate refusal distinctly from a medical conclusion", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/document")
      ? jsonResponse({ error: { code: "report_not_qualified" } }, 403)
      : jsonResponse(url.endsWith("/claims") ? summaries([]) : progress({ document_mode: true, claims: [] })))));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("release qualification requirements"));
    expect(node.querySelector(".document-report")).toBeNull();
    expect(node.querySelector(".verdict-label")).toBeNull();
  });

  it("refuses a report belonging to another analysis", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(jsonResponse(url.endsWith("/document")
      ? documentReport({ analysis_id: "foreign-analysis" }) : url.endsWith("/claims")
        ? summaries([]) : progress({ document_mode: true, claims: [] })))));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("could not be matched to this analysis"));
    expect(node.querySelector(".document-report")).toBeNull();
  });

  it("keeps open details and keyboard focus across a partial-completion poll", async () => {
    vi.useFakeTimers();
    try {
      let snapshots = 0;
      const fetchMock = vi.fn((url: string) => Promise.resolve(jsonResponse(url.endsWith("/document")
        ? documentReport({ status: "running", progress: { groups_total: 1, groups_completed: 0,
          assertions_total: 2, assertions_completed: ++snapshots > 1 ? 2 : 1 } })
        : url.endsWith("/claims") ? summaries([])
          : progress({ document_mode: true, status: "running", stage: "validating", claims: [] }))));
      vi.stubGlobal("fetch", fetchMock);
      const node = mount();
      await vi.advanceTimersByTimeAsync(0);
      const details = node.querySelector<HTMLDetailsElement>(".document-assertion")!;
      details.open = true;
      details.dispatchEvent(new Event("toggle"));
      details.querySelector("summary")!.focus();
      await vi.advanceTimersByTimeAsync(1500);
      const updated = node.querySelector<HTMLDetailsElement>(".document-assertion")!;
      expect(updated.open).toBe(true);
      expect(document.activeElement).toBe(updated.querySelector("summary"));
      expect(node.querySelector(".document-progress")?.textContent).toContain("2 of 2 details checked");
      expect(node.querySelector(".document-report")?.getAttribute("data-initial")).toBe("false");
      expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/claims"))).toHaveLength(1);
    } finally { vi.useRealTimers(); }
  });
});
