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
  const intro = element("div", "progress-intro");
  const lens = element("div", "loading-lens");
  lens.setAttribute("aria-hidden", "true");
  const sheet = element("span", "lens-sheet");
  for (let index = 0; index < 4; index += 1) sheet.append(element("span", "lens-line"));
  const core = element("span", "lens-core");
  core.append(sheet, element("span", "lens-scan"));
  append(lens, element("span", "lens-halo"), element("span", "lens-orbit"),
    element("span", "lens-orbit lens-orbit-inner"), core);
  for (let index = 0; index < 3; index += 1) {
    const spark = element("span", "lens-spark");
    spark.style.setProperty("--spark-index", String(index));
    lens.append(spark);
  }
  const copy = element("div", "progress-copy");
  append(copy, element("p", "progress-phase"),
    element("h2", "progress-title"), element("p", "progress-description"));
  append(intro, lens, copy);
  const list = element("ol", "stepper");
  const shortLabels = ["Read", "Understand", "Find", "Compare", "Verify", "Combine", "Report"];
  for (const [index, [key, label]] of stages.entries()) {
    const item = element("li", "step");
    item.dataset.stage = key;
    const marker = element("span", "step-marker");
    marker.setAttribute("aria-hidden", "true");
    item.setAttribute("aria-label", label);
    append(item, marker, element("span", "step-label", shortLabels[index]), element("span", "sr-only", label));
    list.append(item);
  }
  append(section, intro, list, element("p", "progress-reassurance", "You can leave this tab open. Your results will appear here."));
  updateProgress(section, progress);
  return section;
}

const stageDescriptions: Record<string, string> = {
  queued: "Your check is queued and will begin shortly.",
  extracting: "Finding the health statements that can be checked.",
  normalizing: "Making sure we understand the claim and its medical terms.",
  retrieving: "Looking for studies and relevant public health sources.",
  judging: "Comparing what the sources say with your exact claim.",
  validating: "Checking that each finding matches its source and applies to the claim.",
  aggregating: "Bringing the checked findings together, including any uncertainty.",
  building_report: "Putting the explanation and original sources into your report.",
};

export function updateProgress(section: HTMLElement, progress: AnalysisProgress): void {
  const stage = progress.stage ?? "queued";
  section.dataset.stage = stage;
  const stageIndex = stages.findIndex(([key]) => key === stage);
  const phase = section.querySelector(".progress-phase");
  if (phase) phase.textContent = stageIndex >= 0 ? `Step ${String(stageIndex + 1).padStart(2, "0")} of 07` : "Getting started";
  const title = section.querySelector(".progress-title");
  const description = section.querySelector(".progress-description");
  if (title) title.textContent = stageLabel(stage);
  if (description) description.textContent = stageDescriptions[stage] ?? "Your check is still in progress.";
  const complete = new Set(progress.completed_stages ?? []);
  section.querySelectorAll<HTMLElement>(".step").forEach((item, index) => {
    // The analysis-level completion list can lag the current claim's pipeline.
    // Reaching a stage also fills its preceding milestones on the visual rail.
    const state = stage === item.dataset.stage ? "active"
      : index < stageIndex || complete.has(item.dataset.stage ?? "") ? "complete" : "future";
    item.dataset.state = state;
    if (state === "active") item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
}
