import type { AnalysisProgress, ClaimSummary } from "../types/api";
import { append, element } from "../utils/dom";
import { stages } from "./progress";

type StageTimes = Record<string, {
  started_at?: string; completed_at?: string; failed_at?: string; skipped_at?: string;
}>;

function stageList(
  completed: string[], active: string, status: string, times: StageTimes,
  skipped: string[] = [],
): HTMLElement {
  const list = element("ol", "debug-stage-list");
  const done = new Set(completed);
  const bypassed = new Set(skipped);
  for (const [key, label] of stages) {
    const stamp = times[key];
    const state = bypassed.has(key) || stamp?.skipped_at ? "Skipped"
      : done.has(key) ? "Completed"
      : stamp?.failed_at || (status === "failed" && active === key) ? "Failed"
      : active === key && status === "running" ? "Running"
      : stamp?.started_at ? "Stopped" : "Waiting";
    const item = element("li", "debug-stage");
    item.dataset.state = state.toLowerCase();
    append(item, element("span", "", label), element("span", "debug-stage-state", state));
    list.append(item);
  }
  return list;
}

function failureCode(code: string | null): HTMLElement | null {
  if (!code) return null;
  const note = element("p", "debug-error");
  append(note, element("span", "", "Error code: "), element("code", "", code));
  return note;
}

function codeCounts(codes: string[]): string {
  const counts = new Map<string, number>();
  for (const code of codes) counts.set(code, (counts.get(code) ?? 0) + 1);
  return [...counts].map(([code, count]) => `${code}${count > 1 ? ` x${count}` : ""}`)
    .join(", ") || "none";
}

function judgeFailureSummary(
  error: string | null, validationError: string | null, qualified: boolean | undefined,
): string | null {
  if (error === "timeout") return "No usable answer arrived before the judge deadline.";
  if (error === "invalid_source_unit" || error === "invalid_evidence_citation") {
    return "The judge cited a source outside its permitted frozen view.";
  }
  if (validationError === "material_preflight_failure") {
    return "A required numerical statement or source reference could not be verified; this assessment was excluded.";
  }
  if (qualified === false) return "The assessment did not meet the qualification rules.";
  return null;
}

export function createDebugProgress(
  analysis: AnalysisProgress, claims: ClaimSummary[], pollError: string | null,
): HTMLElement {
  const panel = element("section", "debug-panel");
  const globallySkipped = stages
    .map(([key]) => key)
    .filter((key) => claims.length > 0 && claims.every((claim) =>
      claim.skipped_stages?.includes(key)));
  panel.setAttribute("aria-label", "Development diagnostics");
  append(panel,
    element("p", "eyebrow", "Development diagnostics"),
    element("h2", "card-title", "Live process status"),
    element("p", "debug-notice",
      "Development only. Model response excerpts may repeat submitted text. Requests and provider reasoning are not displayed; do not submit secrets."),
    element("p", "debug-summary",
      `Analysis ${analysis.status} · stage ${analysis.stage ?? "queued"} · ID ${analysis.analysis_id}`),
    failureCode(analysis.failure_code ?? null),
    stageList(analysis.completed_stages ?? [], analysis.stage ?? "queued",
      analysis.status, analysis.stage_timestamps ?? {}, globallySkipped),
  );
  if (pollError) append(panel, failureCode(pollError));

  const models = element("div", "debug-models");
  models.append(element("h3", "", "Models used / configured"));
  for (const model of analysis.debug_models ?? []) {
    const line = element("p", "");
    const result = model.status === "not_called" ? "Not called"
      : model.status === "calling" ? "Calling"
      : model.status === "responded" ? "Responded" : "Unavailable";
    const origin = model.origin === "analysis" ? "this analysis"
      : model.origin === "current_configuration" ? "current configuration" : "";
    line.textContent = `${model.role}: ${model.provider} / ${model.model} — ${result}${model.failure_type ? ` (${model.failure_type})` : ""}${origin ? ` · ${origin}` : ""}`;
    models.append(line);
  }
  panel.append(models);

  for (const claim of claims) {
    const block = element("div", "debug-claim");
    append(block,
      element("h3", "", `Claim ${claim.ordinal}: ${claim.status} at ${claim.stage}`),
      failureCode(claim.failure_code),
      stageList(["extracting", ...claim.completed_stages], claim.stage, claim.status,
        claim.stage_timestamps, claim.skipped_stages ?? []),
    );
    if (!claim.stage_timestamps.extracting) {
      block.append(element("p", "muted-copy", "Extraction: completed at submission level"));
    }
    if (claim.evidence_pack_id) block.append(element("p", "", "Evidence Pack created"));
    if (claim.skipped_stages?.includes("judging")) {
      block.append(element("p", "", "Judging: skipped because no evidence was selected"));
    } else if (claim.completed_stages.includes("judging")) {
      const responses = (claim.debug_judge_runs ?? []).filter((item) => item.outcome_status === "succeeded").length;
      block.append(element("p", "", `Judging: completed, ${responses} structured response(s)`));
    }
    if (claim.skipped_stages?.includes("validating")) {
      block.append(element("p", "", "Validation: skipped because no judge was called"));
    } else if (claim.completed_stages.includes("validating")) {
      const audits = (claim.debug_judge_runs ?? []).filter((item) => item.validation_status !== null);
      const accepted = audits.filter((item) => item.validation_status === "validated").length;
      const rejected = audits.filter((item) => item.validation_status === "invalid" || item.validation_status === "partially_validated").length;
      const unavailable = audits.filter((item) => item.validation_status === "unable_to_validate").length;
      block.append(element("p", "", audits.length
        ? `Validation: completed, ${accepted} accepted / ${rejected} rejected / ${unavailable} unavailable`
        : "Validation: stage completed; no judge assessment was available to validate"));
    }
    if (claim.verdict_run_id) block.append(element("p", "", "Verdict aggregation recorded"));
    if (claim.report_run_id) block.append(element("p", "", "Report created"));
    const diagnostic = claim.debug_diagnostics;
    if (diagnostic) {
      const extraction = diagnostic.extraction;
      if (extraction) {
        const details = element("details", "debug-evidence-axes");
        details.append(element("summary", "", "Extraction and PICO"));
        details.append(element("p", "", `Raw: ${extraction.raw_claim}`));
        details.append(element("p", "", `Normalized: ${extraction.normalized_claim ?? "none"}`));
        details.append(element("p", "", `Type: ${extraction.claim_type ?? "unknown"} · risk: ${extraction.risk_class}`));
        details.append(element("pre", "debug-response-text", JSON.stringify(extraction.pico, null, 2)));
        details.append(element("p", "", `Submitted quantity: ${JSON.stringify(extraction.numeric_effect ?? null)}`));
        block.append(details);
      }
      const retrieval = diagnostic.retrieval;
      block.append(element("p", "", `Retrieval: ${retrieval.candidates ?? "unknown"} candidates · ${retrieval.selected_documents ?? "unknown"} selected (${retrieval.selected_authoritative} authoritative, ${retrieval.selected_pubmed} PubMed) · direct ${retrieval.roles.direct ?? 0}, contextual ${retrieval.roles.contextual ?? 0}, incompatible ${retrieval.roles.incompatible ?? 0}`));
      const waterfall = element("details", "debug-evidence-axes");
      waterfall.open = true;
      waterfall.append(element("summary", "", "Failure waterfall (pipeline status only)"));
      for (const [key, value] of Object.entries(diagnostic.waterfall)) {
        waterfall.append(element("p", "", `${key.replaceAll("_", " ")}: ${value}`));
      }
      block.append(waterfall);
      block.append(element("p", "", `Final: ${diagnostic.final.qualified_judges}/3 qualified · ${diagnostic.final.qualified_positions.join(", ") || "none"} · ${diagnostic.final.aggregation_reasons.join(", ") || "no aggregation reason"} · production ${diagnostic.final.production_qualified ? "yes" : "no"} · calls ${diagnostic.final.total_model_calls ?? "unavailable"} · ${diagnostic.final.elapsed_ms ?? "unknown"} ms`));
    }
    for (const judge of claim.debug_judge_runs ?? []) {
      const item = element("div", "debug-judge");
      append(item,
        element("p", "", `Judge ${judge.slot}: ${judge.model} (${judge.model_family}) — ${judge.outcome_status}`),
        element("p", "", `Attempts: ${judge.attempt_count}; elapsed: ${judge.latency_ms} ms; citation validation: ${judge.validation_status ?? "not recorded"}`),
        element("p", "", `Judge run ${judge.judge_run_id ?? "unknown"} · validation run ${judge.validation_run_id ?? "none"} · semantic revision ${judge.semantic_revision_number ?? 0}`),
        failureCode(judge.error_category),
        failureCode(judge.validation_error_category),
      );
      item.append(element("p", "", `Proposal: ${judge.proposed_label ?? "none"} · structured ${judge.outcome_status === "succeeded" ? "yes" : "no"} · findings ${judge.finding_count ?? 0} · qualified ${judge.qualification_success ? "yes" : "no"}`));
      const failureSummary = judgeFailureSummary(judge.error_category,
        judge.validation_error_category, judge.qualification_success);
      if (failureSummary) item.append(element("p", "", failureSummary));
      item.append(element("p", "", `Reasons: ${codeCounts(judge.qualification_reason_codes ?? [])} · optional numeric: ${codeCounts((judge.targeted_issue_codes ?? []).filter((code) => code.startsWith("OPTIONAL_")))} · material numeric: ${codeCounts((judge.targeted_issue_codes ?? []).filter((code) => code === "NUMERIC_UNCERTAIN" || code.includes("NUMERIC_MISMATCH")))}`));
      if (judge.exclusion_reasons?.length) item.append(element("p", "", `Aggregation exclusions: ${judge.exclusion_reasons.join(", ")}`));
      item.append(element("p", "", `Tokens: ${judge.input_tokens ?? "unknown"} in / ${judge.output_tokens ?? "unknown"} out · identity verified ${judge.model_identity_verified ? "yes" : "no"} · family verified ${judge.model_family_verified ? "yes" : "no"}`));
      if (judge.failure_categories?.length) item.append(element("p", "", `Failure categories: ${judge.failure_categories.join(", ")}`));
      if (judge.attempt_failure_types?.length) item.append(element("p", "", `Attempt failures: ${judge.attempt_failure_types.join(", ")}`));
      if (judge.revision_of_judge_run_id) item.append(element("p", "", `Revises ${judge.revision_of_judge_run_id}`));
      if (judge.conclusion_status) item.append(element("p", "", `Conclusion: ${judge.conclusion_status}`));
      for (const [statementId, status] of Object.entries(judge.statement_statuses ?? {})) {
        item.append(element("p", "", `${statementId}: ${status}`));
      }
      const axesEntries = Object.entries(judge.evidence_axes ?? {});
      if (axesEntries.length) {
        const axesDetails = element("details", "debug-evidence-axes");
        axesDetails.append(element("summary", "", "Evidence axes"));
        for (const [statementId, axes] of axesEntries) {
          axesDetails.append(element("p", "", `${statementId} · Direction: ${axes.direction} · Scope: ${axes.scope} · Strength: ${axes.strength} · Role: ${axes.role}`));
        }
        item.append(axesDetails);
      }
      for (const [statementId, axes] of axesEntries) {
        const note = judge.null_diagnostics?.[statementId];
        item.append(element("p", "", `${statementId}: ${(judge.source_ids?.[statementId] ?? []).join(", ")} · ${axes.finding_basis ?? "unknown"} / ${axes.scope_basis ?? "unknown"}${note?.null_precision_reason ? ` · null ${note.null_precision_reason}` : ""}${note?.gradient_kind ? ` · contrast ${note.gradient_kind}` : ""}`));
      }
      if (judge.id_normalizations?.length) item.append(element("p", "", `ID normalization: ${judge.id_normalizations.map((n) => `${n.returned_id} → ${n.resolved_id}`).join(", ")}`));
      if (judge.judge_unit_id_normalizations?.length) item.append(element("p", "", `Development source-unit ID normalization: ${judge.judge_unit_id_normalizations.map((n) => `${n.from} → ${n.to}`).join(", ")}`));
      if (judge.targeted_issue_codes?.length) {
        item.append(element("p", "", `Validation issues: ${codeCounts(judge.targeted_issue_codes)}`));
      }
      for (const numeric of judge.numeric_findings ?? []) {
        if (!numeric.material) continue;
        const text = (value: string) => value.replaceAll("_", " ");
        item.append(element("p", "debug-numeric-finding",
          `${numeric.target_id} (${numeric.asserted_values.join("–")}) · Numeric source fidelity: ${text(numeric.source_fidelity)} · Source measure: ${text(numeric.source_measure)} · Claim measure: ${text(numeric.claim_measure)} · Comparability: ${text(numeric.comparability)} · Numeric effect: ${text(numeric.numeric_effect)}${numeric.semantic_scope_checked ? "" : " · preliminary; semantic scope not yet checked"}${numeric.structure_status === "structured" ? "" : ` · output discipline: ${text(numeric.structure_status)}`}`));
      }
      block.append(item);
    }
    panel.append(block);
  }
  if (analysis.debug_events?.length) {
    const responses = element("details", "debug-responses");
    responses.append(element("summary", "", "Model responses — raw (development only)"));
    for (const event of analysis.debug_events) {
      const detail = element("details", "debug-response");
      detail.append(element("summary", "",
        `${event.role} · ${event.operation_kind ?? "model_call"} · ${event.model} · attempt ${event.attempt} · ${event.status}${event.failure_type ? ` / ${event.failure_type}` : ""}`));
      detail.append(element("p", "",
        `HTTP ${event.http_status ?? "none"} · ${event.elapsed_ms} ms · analysis ${event.analysis_id ?? analysis.analysis_id} · claim ${event.claim_id ?? "submission"} · judge ${event.judge_run_id ?? "none"} · statements ${(event.statement_ids ?? []).join(", ") || "none"} · evidence ${(event.evidence_ids ?? []).join(", ") || "none"} · validation ${event.validation_run_id ?? "none"} · call ${event.call_id ?? "none"} · revision ${event.semantic_revision_number ?? 0}`));
      if (event.response_excerpt !== null) {
        detail.append(element("pre", "debug-response-text", event.response_excerpt));
      } else {
        detail.append(element("p", "", event.status === "calling"
          ? "Awaiting model response." : "No model content returned."));
      }
      responses.append(detail);
    }
    panel.append(responses);
  }
  return panel;
}
