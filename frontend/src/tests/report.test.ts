// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { createClaimResult } from "../components/claimResult";
import { createEvidenceCard } from "../components/evidenceCard";
import { createProgress } from "../components/progress";
import { errorMessage, parseApiError } from "../api/errors";
import { currentRoute } from "../utils/routing";
import { Poller } from "../utils/polling";
import { analysisId, claimId, progress, report } from "./fixtures";

describe("report presentation", () => {
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
