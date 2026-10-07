import { getAnalysis, getClaimReport, getClaims, getReportReadingGuide } from "../api/analyses";
import { ApiError, errorMessage } from "../api/errors";
import { createClaimResult } from "../components/claimResult";
import { createDebugProgress } from "../components/debugProgress";
import { createProgress, stageLabel, updateProgress } from "../components/progress";
import type { AnalysisClaim, AnalysisProgress, ClaimSummary } from "../types/api";
import type { LensReport, ReportReadingGuide } from "../types/report";
import { append, clear, element } from "../utils/dom";
import { Poller } from "../utils/polling";
import { navigate } from "../utils/routing";
import { showDevelopmentUi } from "../utils/uiMode";

const terminal = new Set(["completed", "partially_completed", "failed", "claims_extracted"]);

function analysisFailureCopy(analysis: AnalysisProgress): [string, string] {
  const code = analysis.failure_code;
  if (analysis.input_type === "screenshot" && (code === "screenshot_text_not_found" || code?.startsWith("ocr_"))) {
    return ["Screenshot text could not be read", "We couldn't read enough text from this screenshot. Try another image or paste the text instead."];
  }
  if (code === "no_claims_extracted") {
    return ["No checkable claims", "No checkable medical claims were identified in this content. Try a more specific claim."];
  }
  if (code?.endsWith("_timeout") || code === "claim_extractor_deadline_exceeded") {
    return ["Analysis took too long", "The verification timed out. No medical result was generated; you can start a new analysis."];
  }
  if (code === "claim_extractor_rate_limited") {
    return ["Claim extraction is rate-limited", "The connected extraction service is limiting requests. Wait before starting a new analysis. No medical result was generated."];
  }
  if (code === "claim_extractor_unavailable") {
    return ["Claim extraction service unavailable", "The connected extraction service is temporarily unavailable. Wait and start a new analysis later. No medical result was generated."];
  }
  if (code === "claim_extractor_invalid_response") {
    return ["Claims could not be read reliably", "The extraction service returned an unusable claim structure. No medical result was generated; try again later."];
  }
  return ["Verification could not be completed", "This analysis could not be completed reliably. No medical result was generated."];
}

export function createAnalysisPage(id: string): { node: HTMLElement; dispose: () => void } {
  const page = element("div", "analysis-page content-width");
  const top = element("section", "analysis-heading");
  append(top, element("h1", "page-title", "Your claim check"));
  const status = element("p", "connection-note");
  status.setAttribute("role", "status");
  const stageAnnouncement = element("p", "sr-only");
  stageAnnouncement.setAttribute("role", "status");
  stageAnnouncement.setAttribute("aria-live", "polite");
  const body = element("div", "analysis-body");
  const progressHost = element("div", "progress-host");
  progressHost.hidden = true;
  let progressNode: HTMLElement | null = null;
  const back = element("button", "button button-secondary", "Check another claim");
  back.type = "button";
  back.addEventListener("click", () => navigate("/"));
  append(page, top, status, stageAnnouncement, progressHost, body, back);

  let analysis: AnalysisProgress | null = null;
  let claims: ClaimSummary[] = [];
  const reports = new Map<string, LensReport>();
  const readingGuides = new Map<string, ReportReadingGuide>();
  const reportErrors = new Map<string, string>();
  const reportLoading = new Set<string>();
  const reportControllers = new Map<string, AbortController>();
  let previousStage: string | null = null;
  let disposed = false;
  let permanentError: string | null = null;
  let pollError: string | null = null;
  let poller: Poller;

  function render(): void {
    if (disposed) return;
    clear(body);
    if (permanentError) {
      progressHost.hidden = true;
      const error = element("section", "error-state");
      append(error, element("h2", "card-title", "Analysis unavailable"),
        element("p", "", permanentError));
      body.append(error);
      return;
    }
    if (!analysis) {
      const skeleton = element("div", "skeleton-stack");
      skeleton.setAttribute("aria-label", "Loading analysis");
      skeleton.append(element("div", "skeleton skeleton-title"), element("div", "skeleton skeleton-card"));
      body.append(skeleton);
      return;
    }

    const isTerminal = terminal.has(analysis.status);
    page.dataset.state = isTerminal ? "finished" : "running";
    progressHost.hidden = isTerminal;
    if (!isTerminal) {
      if (!progressNode) {
        progressNode = createProgress(analysis);
        progressHost.append(progressNode);
      } else updateProgress(progressNode, analysis);
    }
    if (analysis.status === "failed" && analysis.claims.length === 0) {
      const failure = element("section", "error-state");
      const [title, message] = analysisFailureCopy(analysis);
      append(failure,
        element("h2", "card-title", title), element("p", "", message));
      body.append(failure);
    }
    if (analysis.status === "completed" && analysis.claim_count === 0) {
      const empty = element("section", "empty-state");
      append(empty, element("h2", "card-title", "No checkable claims"),
        element("p", "", "No checkable medical claims were identified in this content. Try a more specific health claim or a clearer screenshot."));
      body.append(empty);
    }
    if (analysis.claims.length) {
      const heading = element("div", "claims-heading");
      const count = analysis.claim_count ?? analysis.claims.length;
      append(heading, element("h2", "section-title", `${count} claim${count === 1 ? "" : "s"} identified`));
      if (isTerminal && count > 1) {
        heading.append(element("p", "muted-copy", `${analysis.completed_claims ?? 0} of ${count} completed`));
      }
      body.append(heading);
      const list = element("div", "claim-list");
      for (const claim of analysis.claims) list.append(createClaimCard(claim));
      body.append(list);
    }
    if (analysis.debug_enabled && showDevelopmentUi()) body.append(createDebugProgress(analysis, claims, pollError));
  }

  function createClaimCard(claim: AnalysisClaim): HTMLElement {
    const summary = claims.find((item) => item.claim_id === claim.claim_id);
    const card = element("section", "claim-card");
    const cardTop = element("div", "claim-card-top");
    append(cardTop, element("p", "eyebrow", `Claim ${claim.ordinal}`));
    const claimStatus = summary?.status === "completed" ? "Completed" : summary?.status === "failed" ? "Unable to complete" : summary?.status === "running" ? "Analyzing" : "Waiting";
    cardTop.append(element("span", "claim-status", claimStatus));
    // Coordinated source spans can omit a shared subject. Show the verified
    // standalone proposition that retrieval and judging actually assess.
    append(card, cardTop, element("h3", "claim-text", claim.normalized_text ?? claim.raw_text));
    if (summary?.status === "failed") {
      if (summary.failure_code === "normalization_incomplete") {
        card.append(element("h4", "claim-result-label", "Unable to Verify Reliably"));
      }
      card.append(element("p", "claim-failure", summary.failure_code?.endsWith("_timeout")
        ? "This claim took too long to verify. No report is available."
        : summary.failure_code === "normalization_incomplete"
          ? "This claim could not be grounded in a complete exposure and outcome. Try submitting each claim as a complete sentence. No medical result was generated."
        : "This claim could not be completed reliably. No report is available."));
    } else if (summary?.status === "completed") {
      const report = reports.get(claim.claim_id);
      if (report) card.append(createClaimResult(report, id, claim.claim_id,
        analysis?.debug_enabled, readingGuides.get(claim.claim_id)));
      else if (reportErrors.has(claim.claim_id)) card.append(element("p", "report-error", reportErrors.get(claim.claim_id)));
      else card.append(element("div", "skeleton skeleton-report"));
    } else {
      card.append(element("p", "claim-stage", summary?.status === "running" ? stageLabel(summary.stage) : "Waiting for analysis"));
    }
    return card;
  }

  function loadReadyReports(): void {
    for (const claim of claims) {
      if (claim.status !== "completed" || !claim.report_run_id || reports.has(claim.claim_id)
          || reportErrors.has(claim.claim_id) || reportLoading.has(claim.claim_id)) continue;
      reportLoading.add(claim.claim_id);
      const controller = new AbortController();
      reportControllers.set(claim.claim_id, controller);
      void getClaimReport(id, claim.claim_id, controller.signal).then(async (report) => {
        if (disposed) return;
        reports.set(claim.claim_id, report);
        render();
        try {
          const guide = await getReportReadingGuide(id, claim.claim_id, controller.signal);
          if (!disposed && guide.verdict_run_id === report.verdict_run_id
              && guide.report_semantic_hash === report.semantic_hash) {
            readingGuides.set(claim.claim_id, guide);
          }
        } catch {
          // Older servers and an unavailable reading guide do not hide a saved report.
        }
      }).catch((error: unknown) => {
        if (!disposed && !controller.signal.aborted) reportErrors.set(claim.claim_id, errorMessage(error));
      }).finally(() => {
        reportControllers.delete(claim.claim_id);
        reportLoading.delete(claim.claim_id);
        render();
      });
    }
  }

  poller = new Poller(async (signal) => {
    const [nextAnalysis, nextClaims] = await Promise.all([getAnalysis(id, signal), getClaims(id, signal)]);
    if (disposed) return "terminal";
    const stageChanged = nextAnalysis.stage !== previousStage;
    analysis = nextAnalysis;
    claims = nextClaims.claims;
    pollError = null;
    status.textContent = "";
    render();
    if (stageChanged) {
      previousStage = nextAnalysis.stage ?? null;
      stageAnnouncement.textContent = terminal.has(nextAnalysis.status)
        ? "Analysis finished" : stageLabel(nextAnalysis.stage ?? "queued");
    }
    loadReadyReports();
    return terminal.has(nextAnalysis.status) ? "terminal" : "active";
  }, (error, failures) => {
    if (error instanceof ApiError && (error.status === 404 || error.status === 410)) {
      permanentError = "This analysis is no longer available. Start a new analysis.";
      status.textContent = "";
      poller.stop();
      render();
      return;
    }
    pollError = error instanceof ApiError
      ? `poll_http_${error.status}_${error.code}` : "poll_network_error";
    if (analysis?.debug_enabled) render();
    status.textContent = failures >= 3
      ? "Connection interrupted. Refresh this page to resume the analysis."
      : "Reconnecting to the analysis…";
  });
  render();
  poller.start();
  return { node: page, dispose: () => {
    disposed = true;
    poller.stop();
    for (const controller of reportControllers.values()) controller.abort();
    reportControllers.clear();
  } };
}
