import type { AnalysisProgress, ClaimSummary } from "../types/api";
import { append, element } from "../utils/dom";
import { stages } from "./progress";

type StageTimes = Record<string, { started_at?: string; completed_at?: string; failed_at?: string }>;

function stageList(
  completed: string[], active: string, status: string, times: StageTimes,
): HTMLElement {
  const list = element("ol", "debug-stage-list");
  const done = new Set(completed);
  for (const [key, label] of stages) {
    const stamp = times[key];
    const state = done.has(key) ? "Succeeded"
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

export function createDebugProgress(
  analysis: AnalysisProgress, claims: ClaimSummary[], pollError: string | null,
): HTMLElement {
  const panel = element("section", "debug-panel");
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
      analysis.status, analysis.stage_timestamps ?? {}),
  );
  if (pollError) append(panel, failureCode(pollError));

  const models = element("div", "debug-models");
  models.append(element("h3", "", "Model calls (this analysis)"));
  for (const model of analysis.debug_models ?? []) {
    const line = element("p", "");
    const result = model.status === "not_called" ? "Not called"
      : model.status === "calling" ? "Calling"
      : model.status === "responded" ? "Responded" : "Unavailable";
    line.textContent = `${model.role}: ${model.provider} / ${model.model} — ${result}${model.failure_type ? ` (${model.failure_type})` : ""}`;
    models.append(line);
  }
  panel.append(models);

  for (const claim of claims) {
    const block = element("div", "debug-claim");
    append(block,
      element("h3", "", `Claim ${claim.ordinal}: ${claim.status} at ${claim.stage}`),
      failureCode(claim.failure_code),
      stageList(claim.completed_stages, claim.stage, claim.status, claim.stage_timestamps),
    );
    if (claim.evidence_pack_id) block.append(element("p", "", "Evidence Pack created"));
    if (claim.verdict_run_id) block.append(element("p", "", "Verdict aggregation recorded"));
    if (claim.report_run_id) block.append(element("p", "", "Report created"));
    for (const judge of claim.debug_judge_runs ?? []) {
      const item = element("div", "debug-judge");
      append(item,
        element("p", "", `Judge ${judge.slot}: ${judge.model} (${judge.model_family}) — ${judge.outcome_status}`),
        element("p", "", `Attempts: ${judge.attempt_count}; elapsed: ${judge.latency_ms} ms; citation validation: ${judge.validation_status ?? "not recorded"}`),
        failureCode(judge.error_category),
        failureCode(judge.validation_error_category),
      );
      block.append(item);
    }
    panel.append(block);
  }
  if (analysis.debug_events?.length) {
    const responses = element("div", "debug-responses");
    responses.append(element("h3", "", "Model responses"));
    for (const event of analysis.debug_events) {
      const detail = element("details", "debug-response");
      detail.append(element("summary", "",
        `${event.role} · ${event.model} · attempt ${event.attempt} · ${event.status}${event.failure_type ? ` / ${event.failure_type}` : ""}`));
      detail.append(element("p", "",
        `HTTP ${event.http_status ?? "none"} · ${event.elapsed_ms} ms`));
      if (event.response_excerpt !== null) {
        detail.append(element("pre", "debug-response-text", event.response_excerpt));
      } else {
        detail.append(element("p", "", "No model content returned."));
      }
      responses.append(detail);
    }
    panel.append(responses);
  }
  return panel;
}
