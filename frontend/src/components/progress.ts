import type { AnalysisProgress } from "../types/api";
import { append, element } from "../utils/dom";

export const stages = [
  ["extracting", "Identifying medical claims"],
  ["normalizing", "Understanding medical concepts"],
  ["retrieving", "Searching scientific evidence"],
  ["judging", "Comparing claims with the evidence"],
  ["validating", "Checking citations and reasoning"],
  ["aggregating", "Combining verified assessments"],
  ["building_report", "Preparing the report"],
] as const;

export function stageLabel(stage: string): string {
  return stages.find(([key]) => key === stage)?.[1] ?? (stage === "queued" ? "Waiting to begin" : "Analysis in progress");
}

export function createProgress(progress: AnalysisProgress): HTMLElement {
  const section = element("section", "progress-card");
  section.setAttribute("aria-label", "Verification progress");
  const heading = element("h2", "card-title", "Verification progress");
  const list = element("ol", "stepper");
  const complete = new Set(progress.completed_stages ?? []);
  for (const [key, label] of stages) {
    const item = element("li", "step");
    const state = complete.has(key) ? "complete" : progress.stage === key ? "active" : "future";
    item.dataset.state = state;
    const marker = element("span", "step-marker", state === "complete" ? "✓" : String(stages.findIndex(([name]) => name === key) + 1));
    marker.setAttribute("aria-hidden", "true");
    append(item, marker, element("span", "step-label", label));
    list.append(item);
  }
  append(section, heading, list);
  return section;
}
