// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createClaimResult } from "../components/claimResult";
import { createEvidenceCard } from "../components/evidenceCard";
import { createProgress, updateProgress } from "../components/progress";
import { errorMessage, parseApiError } from "../api/errors";
import { currentRoute } from "../utils/routing";
import { Poller } from "../utils/polling";
import { analysisId, claimId, progress, report } from "./fixtures";
import type { ReportReadingGuide } from "../types/report";

afterEach(() => vi.unstubAllEnvs());

describe("report presentation", () => {
  it("uses the saved explanation below the label and shows development details on demand", () => {
    const saved = report("not_enough_evidence", { verdict_explanation: {
      version: "1.0", reason_category: "numeric_magnitude_unverified",
      summary: "Direction is supported; the claimed 85% magnitude is not established.",
      established: "Direction is supported.", unresolved: "85% is not established.",
      evidence_ids: ["E1"],
    } });
    const normal = createClaimResult(saved, analysisId, claimId);
    expect(normal.querySelector(".verdict-summary")?.textContent).toBe(saved.verdict_explanation?.summary);
    expect(normal.querySelector(".verdict-meaning")).toBeNull();
    expect(normal.textContent).not.toContain("Studies may be limited, give mixed results");
    expect(normal.querySelector(".evidence-clarity")?.textContent).toContain("85% is not established.");
    expect(normal.textContent).toContain("Why this result");
    expect(normal.querySelector(".verdict-explanation-details")).toBeNull();
    const debug = createClaimResult(saved, analysisId, claimId, true);
    const details = debug.querySelector(".verdict-explanation-details");
    expect(details?.textContent).toContain("Verdict explanation");
    expect(details?.textContent).toContain("numeric_magnitude_unverified");
    expect(details?.textContent).toContain("E1");
    expect(details?.textContent).toContain("85% is not established.");
  });

  it("retains historical summary fallback and treats explanation strings as text", () => {
    const historical = report();
    expect(createClaimResult(historical, analysisId, claimId)
      .querySelector(".verdict-summary")?.textContent).toBe(historical.short_summary);
    const saved = report("not_enough_evidence", { verdict_explanation: {
      version: "1.0", reason_category: "other_bounded_reason", evidence_ids: [],
      summary: "<script>alert(1)</script>", established: null, unresolved: null,
    } });
    const node = createClaimResult(saved, analysisId, claimId, true);
    expect(node.querySelector("script")).toBeNull();
    expect(node.querySelector(".verdict-summary")?.textContent).toBe(saved.verdict_explanation?.summary);
  });

  it("renders one authoritative card with multiple exact units and no fake PMID", () => {
    const card = { ...report().key_evidence[0], pmid: null,
      source_kind: "authoritative_public_health" as const, organization: "NCI",
      document_purpose: "systematic_evidence_summary", currency: "current" as const,
      excerpts: ["E1", "E2"].map((id) => ({ evidence_id: id, source_unit_id: `${id}.U1`,
        section: "Assessment", exact_text: `Frozen ${id} <script>x()</script>`,
        truncated: false, passage_sha256: "a".repeat(64) })),
    };
    const node = createEvidenceCard(card);
    expect(node.querySelectorAll(".evidence-quote")).toHaveLength(2);
    expect(node.querySelectorAll(".evidence-title")).toHaveLength(1);
    expect(node.textContent).toContain("NCI");
    expect(node.textContent).not.toContain("PMID");
    expect(node.querySelector("script")).toBeNull();
  });

  it("displays the exposure analysis instead of a parent trial label", () => {
    const node = createEvidenceCard({ ...report().key_evidence[0],
      study_design: "randomized_controlled_trial", analysis_design: "secondary_observational_analysis",
    });
    expect(node.textContent).toContain("Secondary observational analysis within a randomized trial cohort");
    expect(node.textContent).not.toContain("Randomized Controlled Trial");
  });
  it.each([
    ["supported", "Supported"], ["contradicted", "Contradicted"],
    ["not_enough_evidence", "Not Enough Evidence"],
    ["unable_to_verify_reliably", "Unable to Verify Reliably"],
  ] as const)("renders %s without truth scores or model ranking", (label, display) => {
    const node = createClaimResult(report(label), analysisId, claimId);
    expect(node.querySelector(".verdict-label")?.textContent).toBe(display);
    expect(node.textContent).not.toMatch(/truth score|87% confidence|ChatGPT:|Gemini:|Qwen:/i);
  });

  it("keeps the development notice visible and uses exact source text safely", () => {
    const node = createClaimResult(report(), analysisId, claimId);
    expect(node.querySelector(".qualification-notice")?.textContent).toContain("Development evaluation only");
    expect(node.querySelector(".qualification-notice")?.closest("details")).toBeNull();
    expect(node.querySelector(".evidence-quote")?.textContent).toBe("Exact frozen excerpt <script>alert(1)</script>");
    expect(node.querySelector("script")).toBeNull();
    expect(node.textContent).toContain("Association does not establish causation.");
    expect(node.textContent).toContain("How was this checked?");
    expect(node.textContent).toContain("This is public health information");
    expect(node.textContent).toContain("Publication integrity: Unknown");
    expect(node.textContent).not.toContain("DOI null");
    expect(node.textContent).not.toContain("undefined");
    const source = node.querySelector(".source-link") as HTMLAnchorElement;
    expect(source.rel).toBe("noopener noreferrer");
    expect(source.target).toBe("_blank");
  });

  it("omits the development warning only for a qualified report", () => {
    const qualified = report("supported", {
      production_qualified: true,
      verification_status: { evidence_state: "validated_support", validated_citations_shown: 1,
        production_qualified: true, development_notice: null },
    });
    expect(createClaimResult(qualified, analysisId, claimId).querySelector(".qualification-notice")).toBeNull();
  });

  it("does not turn a malicious source URL into a link", () => {
    const source = { ...report().key_evidence[0], source_url: "javascript:alert(1)" };
    const node = createEvidenceCard(source);
    expect(node.querySelector("a")).toBeNull();
  });

  it("shows neutral frozen sources for development Unable without claiming support", () => {
    const unable = report("unable_to_verify_reliably", {
      key_evidence: [], sources: [], neutral_retrieved_sources: [{
        evidence_id: "E8", pmid: "123", doi: null, title: "Frozen review",
        publication_date: null, passage_section: "RESULTS",
        exact_excerpt: "Exact result <script>unsafe()</script>",
        excerpt_truncated: false, passage_sha256: "a".repeat(64),
        source_url: "https://pubmed.ncbi.nlm.nih.gov/123/",
      }],
    });
    const node = createClaimResult(unable, analysisId, claimId);
    expect(node.textContent).toContain("Retrieved sources — not validated support");
    expect(node.textContent).toContain("Exact result <script>unsafe()</script>");
    expect(node.querySelector("script")).toBeNull();
    expect(node.textContent).not.toContain("Supporting evidence");
  });

  it("explains why an empty evidence search did not call a judge", () => {
    const empty = report("not_enough_evidence", {
      key_evidence: [], sources: [], judge_summary: {
        qualified: 0, excluded: 0, validated_label_counts: {},
        description: "", excluded_assessments: [],
      },
    });
    const node = createClaimResult(empty, analysisId, claimId);
    expect(node.querySelector(".details-body")?.textContent)
      .toContain("No judge assessment ran because the search selected no usable evidence.");
  });

  it("uses actual backend stages without a fabricated percentage", () => {
    const node = createProgress(progress({ status: "running", stage: "retrieving", completed_stages: ["extracting", "normalizing"] }));
    expect(node.textContent).toContain("Searching scientific evidence");
    expect(node.querySelector('[data-state="active"]')?.textContent).toContain("Searching scientific evidence");
    expect(node.textContent).not.toMatch(/\d+%/);
  });

  it("fills every preceding milestone when the completion list lags the current stage", () => {
    const node = createProgress(progress({ status: "running", stage: "validating", completed_stages: ["extracting"] }));
    expect([...node.querySelectorAll<HTMLElement>(".step")].map((step) => step.dataset.state))
      .toEqual(["complete", "complete", "complete", "complete", "active", "future", "future"]);
    expect(node.querySelector('[aria-current="step"]')?.getAttribute("data-stage")).toBe("validating");
  });

  it("keeps the current milestone active and does not invent completed stages while queued", () => {
    const node = createProgress(progress({ status: "running", stage: "extracting", completed_stages: ["extracting"] }));
    expect(node.querySelector<HTMLElement>('.step[data-stage="extracting"]')?.dataset.state).toBe("active");
    updateProgress(node, progress({ status: "queued", stage: "queued", completed_stages: [] }));
    expect([...node.querySelectorAll<HTMLElement>(".step")].every((step) => step.dataset.state === "future")).toBe(true);
    expect(node.querySelector('[aria-current="step"]')).toBeNull();
  });

  it("updates real progress without replacing the animated lens or stage nodes", () => {
    const node = createProgress(progress({ status: "running", stage: "retrieving", completed_stages: ["extracting", "normalizing"] }));
    const lens = node.querySelector(".loading-lens");
    const markers = [...node.querySelectorAll(".step-marker")];
    updateProgress(node, progress({ status: "running", stage: "judging", completed_stages: ["extracting", "normalizing", "retrieving"] }));
    expect(node.querySelector(".loading-lens")).toBe(lens);
    expect([...node.querySelectorAll(".step-marker")]).toEqual(markers);
    expect(node.querySelector('[aria-current="step"]')?.textContent).toContain("Comparing claims with the evidence");
    expect(node.querySelector<HTMLElement>('[data-stage="retrieving"]')?.dataset.state).toBe("complete");
    expect(node.dataset.stage).toBe("judging");
    expect(node.querySelector(".progress-phase")?.textContent).toBe("Step 04 of 07");
    expect(node.querySelectorAll(".step-marker")).toHaveLength(7);
    expect(node.querySelector(".step-marker")?.textContent).toBe("");
  });

  it("shows saved source-validated case findings with working source anchors", () => {
    const saved = report();
    const guide: ReportReadingGuide = {
      version: "report-reading-guide-1.0", verdict_run_id: saved.verdict_run_id,
      report_semantic_hash: saved.semantic_hash,
      findings: [{ text: "The review found benefit limited to physically stressed participants.",
        evidence_ids: ["E1"], source_unit_ids: ["E1.U1"] }], highlights: [],
    };
    const node = createClaimResult(saved, analysisId, claimId, false, guide);
    expect(node.querySelector(".case-finding")?.textContent).toContain(guide.findings[0].text);
    expect(node.querySelector(".finding-citation")?.getAttribute("href")).toBe(`#source-${claimId}-E1`);
    expect(node.querySelector(`#source-${claimId}-E1`)).not.toBeNull();
  });

  it("never uses an explanation belonging to another saved report", () => {
    const node = createClaimResult(report(), analysisId, claimId, false, {
      version: "report-reading-guide-1.0", verdict_run_id: "foreign",
      report_semantic_hash: "wrong", highlights: [],
      findings: [{ text: "Unrelated finding", evidence_ids: ["E1"], source_unit_ids: ["E1.U1"] }],
    });
    expect(node.querySelector(".case-explanation")).toBeNull();
  });

  it("highlights exact owned quotes while preserving every character of the full passage", () => {
    const text = "Some background. The randomized study found fewer invasive melanomas with daily sunscreen use. Limits apply.";
    const phrase = "The randomized study found fewer invasive melanomas with daily sunscreen use.";
    const source = { ...report().key_evidence[0], exact_excerpt: text };
    const node = createEvidenceCard(source, [{ source_unit_id: "E1.U1", exact_text: phrase }]);
    expect(node.querySelector(".evidence-key-quote mark")?.textContent).toBe(phrase);
    expect(node.querySelector(".evidence-full-quote")?.textContent).toBe(text);
    expect(node.querySelector(".source-context")?.hasAttribute("open")).toBe(false);
    expect(node.querySelector(".evidence-full-quote mark")?.textContent).toBe(phrase);
  });

  it("does not highlight guessed wording or quotes belonging to a different unit", () => {
    const text = "The study did not reduce the measured disease incidence in the general population.";
    const source = { ...report().key_evidence[0], exact_excerpt: text };
    const node = createEvidenceCard(source, [
      { source_unit_id: "E2.U1", exact_text: text },
      { source_unit_id: "E1.U1", exact_text: "The study reduced disease incidence in the general population." },
    ]);
    expect(node.querySelector("mark")).toBeNull();
    expect(node.querySelector(".evidence-full-quote")?.textContent).toBe(text);
  });

  it("merges overlapping highlights safely without altering source text or executing HTML", () => {
    const text = "The source contains literal <script>unsafe()</script> wording and no HTML execution.";
    const node = createEvidenceCard({ ...report().key_evidence[0], exact_excerpt: text }, [
      { source_unit_id: "E1.U1", exact_text: text },
      { source_unit_id: "E1.U1", exact_text: "literal <script>unsafe()</script> wording" },
    ]);
    expect(node.querySelector(".evidence-full-quote")?.textContent).toBe(text);
    expect(node.querySelectorAll(".evidence-full-quote mark")).toHaveLength(1);
    expect(node.querySelector("script")).toBeNull();
  });

  it("uses public production presentation without changing release qualification", () => {
    vi.stubEnv("DEV", false);
    const node = createClaimResult(report(), analysisId, claimId, false);
    expect(node.textContent).not.toContain("Development / evaluation");
    expect(node.querySelector(".technical-details")).toBeNull();
    expect(node.querySelector(".qualification-notice")?.textContent)
      .toContain("has not yet met the checks required for public release");
  });

  it("shows report diagnostics in a production build only when authorized by the backend", () => {
    vi.stubEnv("DEV", false);
    const saved = report("not_enough_evidence", { verdict_explanation: {
      version: "1.0", reason_category: "numeric_magnitude_unverified", evidence_ids: ["E1"],
      summary: "The exact magnitude is unresolved.", established: null, unresolved: "85% is not established.",
    } });
    const node = createClaimResult(saved, analysisId, claimId, true);
    expect(node.querySelector(".technical-details")).not.toBeNull();
    expect(node.querySelector(".verdict-explanation-details")?.textContent).toContain("numeric_magnitude_unverified");
    expect(node.querySelector(".qualification-notice")?.textContent).toContain("Development evaluation only");
    expect(saved.production_qualified).toBe(false);
  });

  it("honors an explicit frontend diagnostic opt-out even when backend debug is enabled", () => {
    vi.stubEnv("DEV", false);
    vi.stubEnv("VITE_SHOW_DEVELOPMENT_UI", "false");
    const node = createClaimResult(report(), analysisId, claimId, true);
    expect(node.querySelector(".technical-details")).toBeNull();
    expect(node.textContent).not.toContain("Development / evaluation");
  });
});

describe("API and routing safety", () => {
  it("maps typed errors without exposing backend internals", () => {
    const error = parseApiError(503, { error: { code: "backend_internal", message: "Traceback secret prompt" } });
    expect(errorMessage(error)).toContain("temporarily unavailable");
    expect(errorMessage(error)).not.toContain("Traceback");
    expect(errorMessage(parseApiError(403, { error: { code: "report_not_qualified" } }))).toContain("release qualification");
    expect(errorMessage(parseApiError(410, { error: { code: "idempotency_key_expired" } }))).toContain("expired");
    expect(errorMessage(parseApiError(413, {}))).toContain("too large");
  });

  it("recognizes clean analysis routes for refresh/resume", () => {
    expect(currentRoute(`/analysis/${analysisId}`)).toEqual({ page: "analysis", id: analysisId });
    expect(currentRoute("/analysis/not-a-uuid")).toEqual({ page: "not_found" });
  });
});

describe("polling", () => {
  it("stops on terminal outcome and never overlaps", async () => {
    let calls = 0;
    const poller = new Poller(async () => { calls += 1; return "terminal"; }, () => {});
    poller.start();
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(calls).toBe(1);
    poller.stop();
  });

  it("aborts in-flight work during page cleanup", () => {
    let aborted = false;
    const poller = new Poller(async (received) => {
      received.addEventListener("abort", () => { aborted = true; });
      return await new Promise<"active">(() => {});
    }, () => {});
    poller.start();
    poller.stop();
    expect(aborted).toBe(true);
  });

  it("does not overlap polls and backs off after a temporary failure", async () => {
    vi.useFakeTimers();
    try {
      let finish: ((result: "active") => void) | null = null;
      const request = vi.fn().mockRejectedValueOnce(new TypeError("offline"))
        .mockImplementationOnce(() => new Promise<"active">((resolve) => { finish = resolve; }))
        .mockResolvedValue("terminal");
      const onError = vi.fn();
      const poller = new Poller(request, onError, 100);
      poller.start();
      await Promise.resolve();
      expect(onError).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(199);
      expect(request).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1);
      expect(request).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(1000);
      expect(request).toHaveBeenCalledTimes(2);
      if (finish) (finish as (result: "active") => void)("active");
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(100);
      expect(request).toHaveBeenCalledTimes(3);
      await vi.advanceTimersByTimeAsync(1000);
      expect(request).toHaveBeenCalledTimes(3);
      poller.stop();
    } finally { vi.useRealTimers(); }
  });
});
