// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAnalysisPage } from "../pages/analysis";
import { analysisId, claimId2, claimSummary, jsonResponse, progress, report, summaries } from "./fixtures";

let dispose: (() => void) | null = null;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  document.body.replaceChildren();
});
afterEach(() => { dispose?.(); dispose = null; vi.unstubAllGlobals(); });

function mount(): HTMLElement {
  const page = createAnalysisPage(analysisId);
  dispose = page.dispose;
  document.body.append(page.node);
  return page.node;
}

function mockResponses(analysis: ReturnType<typeof progress>, claims = summaries(), reportResponse = report()): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((url: string) => {
    if (url.endsWith("/report")) return Promise.resolve(jsonResponse(reportResponse));
    if (url.endsWith("/claims")) return Promise.resolve(jsonResponse(claims));
    return Promise.resolve(jsonResponse(analysis));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("analysis page", () => {
  it("loads progress, per-claim status, and a persisted report", async () => {
    const fetchMock = mockResponses(progress());
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Development / evaluation result"));
    expect(node.textContent).toContain("Vitamin C prevents the common cold.");
    expect(node.textContent).not.toContain("1 of 1 claims completed");
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/claims"))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith("/report"))).toBe(true);
  });

  it("keeps a completed report while another claim fails", async () => {
    mockResponses(progress({ status: "partially_completed", claim_count: 2, completed_claims: 1,
      claims: [...progress().claims, { ...progress().claims[0], claim_id: claimId2, ordinal: 2,
        raw_text: "A second claim." }] }), summaries([
      claimSummary(), claimSummary({ claim_id: claimId2, ordinal: 2, status: "failed", failure_code: "retrieving_failed", report_run_id: null }),
    ]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("1 of 2 completed"));
    await vi.waitFor(() => expect(node.textContent).toContain("Development / evaluation result"));
    expect(node.textContent).toContain("Unable to complete");
    expect(node.textContent).not.toContain("Some claims completed;");
  });

  it("shows no-checkable-claims without inventing a verdict", async () => {
    mockResponses(progress({ claim_count: 0, completed_claims: 0, claims: [] }), summaries([]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("No checkable medical claims were identified"));
    expect(node.textContent).not.toContain("Not Enough Evidence");
  });

  it("explains incomplete source-grounded claims without a medical verdict", async () => {
    mockResponses(progress({ status: "failed", completed_claims: 0 }), summaries([
      claimSummary({ status: "failed", failure_code: "normalization_incomplete",
                     report_run_id: null }),
    ]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("complete exposure and outcome"));
    expect(node.textContent).not.toContain("Not Enough Evidence");
  });

  it("distinguishes OCR failure from a medical result", async () => {
    mockResponses(progress({ status: "failed", stage: "extracting", input_type: "screenshot", claim_count: 0, claims: [],
      failure_code: "screenshot_text_not_found" }), summaries([]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("We couldn't read enough text"));
    expect(node.textContent).not.toContain("Not Enough Evidence");
  });

  it("identifies extraction-provider outages instead of a medical failure", async () => {
    mockResponses(progress({ status: "failed", stage: "extracting", claim_count: 0,
      claims: [], failure_code: "claim_extractor_unavailable" }), summaries([]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Claim extraction service unavailable"));
    expect(node.textContent).toContain("No medical result was generated");
  });

  it("identifies extraction rate limits and advises waiting", async () => {
    mockResponses(progress({ status: "failed", stage: "extracting", claim_count: 0,
      claims: [], failure_code: "claim_extractor_rate_limited" }), summaries([]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Claim extraction is rate-limited"));
    expect(node.textContent).toContain("Wait before starting a new analysis");
  });

  it("shows safe stage errors when development debug is enabled", async () => {
    mockResponses(progress({
      debug_enabled: true, status: "failed", stage: "extracting", completed_stages: [],
      failure_code: "claim_extractor_invalid_response", claim_count: 0, claims: [],
    }), summaries([]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Development diagnostics"));
    expect(node.textContent).toContain("Identifying medical claims");
    expect(node.textContent).toContain("claim_extractor_invalid_response");
    expect(node.textContent).toContain("Failed");
    expect(node.textContent).not.toContain("Bearer");
  });

  it("shows per-judge failures only when debug is enabled", async () => {
    const failed = claimSummary({ debug_judge_runs: [{
      slot: 1, provider: "openai_compatible", model: "inclusionai/ling-3.0-flash",
      model_family: "inclusionai", outcome_status: "failed", error_category: "timeout",
      attempt_count: 2, latency_ms: 80000, validation_status: null,
      validation_error_category: null,
    }] });
    mockResponses(progress({ debug_enabled: true }), summaries([failed]));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Judge 1: inclusionai/ling-3.0-flash"));
    expect(node.textContent).toContain("Error code: timeout");
    expect(node.textContent).toContain("citation validation: not recorded");
  });

  it("shows configured model reachability and visible responses in development debug", async () => {
    mockResponses(progress({ debug_enabled: true, debug_models: [
      { role: "extraction", provider: "openai_compatible", model: "fixture-extractor",
        status: "responded", failure_type: null },
      { role: "judge_1", provider: "openai_compatible", model: "fixture-judge",
        status: "unavailable", failure_type: "timeout" },
    ], debug_events: [{
      role: "extraction", provider: "openai_compatible", model: "fixture-extractor",
      attempt: 1, status: "responded", failure_type: null, http_status: 200,
      elapsed_ms: 1234, response_excerpt: '{"claims":[{"raw_span":"Vitamin C prevents the common cold."}]}',
    }] }), summaries());
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Model responses"));
    expect(node.textContent).toContain("fixture-extractor — Responded");
    expect(node.textContent).toContain("fixture-judge — Unavailable (timeout)");
    expect(node.querySelector(".debug-response-text")?.textContent).toContain("raw_span");
  });

  it("removes repeated result copy without hiding the qualification notice", async () => {
    mockResponses(progress(), summaries(), report("unable_to_verify_reliably", {
      headline: "Unable to Verify Reliably", short_summary: "Unable to Verify Reliably",
    }));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Development / evaluation result"));
    expect(node.querySelectorAll(".report-claim")).toHaveLength(0);
    expect(node.querySelectorAll(".verdict-headline")).toHaveLength(0);
    expect(node.querySelectorAll(".verdict-summary")).toHaveLength(0);
    expect(node.querySelector(".qualification-notice")?.textContent).toContain("Development evaluation only");
  });

  it("hides development diagnostics when the toggle is off", async () => {
    mockResponses(progress({ debug_enabled: false, failure_code: "claim_extractor_invalid_response" }));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Vitamin C prevents the common cold."));
    expect(node.textContent).not.toContain("Development diagnostics");
    expect(node.textContent).not.toContain("Error code:");
  });

  it("shows expired analysis without silently recreating it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ error: { code: "analysis_not_found" } }, 404)));
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("This analysis is no longer available"));
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method !== "POST")).toBe(true);
  });

  it("shows report qualification 403 separately from inability to verify", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.endsWith("/report")
      ? jsonResponse({ error: { code: "report_not_qualified" } }, 403)
      : url.endsWith("/claims") ? jsonResponse(summaries()) : jsonResponse(progress())));
    vi.stubGlobal("fetch", fetchMock);
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("release qualification requirements"));
    expect(node.textContent).not.toContain("Unable to Verify Reliably");
  });

  it("keeps polling through temporary network failure", async () => {
    let count = 0;
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("/claims")) return Promise.resolve(jsonResponse(summaries([])));
      count += 1;
      if (count === 1) return Promise.reject(new TypeError("offline"));
      return Promise.resolve(jsonResponse(progress({ status: "running", stage: "retrieving", claim_count: 0, claims: [] })));
    });
    vi.stubGlobal("fetch", fetchMock);
    const node = mount();
    await vi.waitFor(() => expect(node.textContent).toContain("Reconnecting"));
    expect(node.textContent).not.toContain("Verification could not be completed");
  });
});
