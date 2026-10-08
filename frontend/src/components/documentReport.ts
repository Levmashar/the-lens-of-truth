import type { DocumentAssertion, DocumentAssessment, DocumentCitation, DocumentGroup, DocumentReport } from "../types/document";
import { append, element, safeExternalUrl } from "../utils/dom";
import { verdictLabels } from "../utils/format";
import { showDevelopmentUi } from "../utils/uiMode";

export type DocumentDisclosureState = Map<string, boolean>;

const sourceLabels = {
  identified: "Source identified", uncertain: "Source match is uncertain", not_found: "Source not found",
};
const kindLabels: Record<string, string> = {
  reported_study_fact: "Reported study finding",
  reported_study_result: "Reported study finding",
  general_medical_assertion: "General medical assertion",
  general_medical: "General medical assertion",
  interpretation: "Interpretation or inference",
  methodology: "Study methods or sample details",
  methodological_detail: "Study methods or sample details",
  sample_size: "Study sample size",
  repetition: "Repeated statement",
  commentary: "Commentary",
  unclassified: "Unresolved document detail",
};

/** Render one document without inventing a summary verdict or combined truth score. */
export function createDocumentReport(
  report: DocumentReport, disclosures: DocumentDisclosureState = new Map(), debugEnabled = false,
  initialRender = true,
): HTMLElement {
  const article = element("article", "document-report");
  article.dataset.version = report.version;
  article.dataset.initial = String(initialRender);
  if (!report.production_qualified) {
    const notice = element("aside", "qualification-notice");
    append(notice, element("h4", "notice-title", showDevelopmentUi(debugEnabled)
      ? "Development / evaluation result" : "Verification status"),
    element("p", "", showDevelopmentUi(debugEnabled)
      ? "Development evaluation only; not qualified for public release."
      : "This report has not yet met the checks required for public release."));
    article.append(notice);
  }
  const overview = element("section", "document-overview");
  append(overview, element("p", "eyebrow", "Document check"),
    element("h2", "section-title", "Your document, checked in context"),
    element("p", "document-overview-copy", "Study reporting and medical conclusions are checked separately. Open a topic to see each detail, its source and what remains uncertain."));
  const { progress } = report;
  const counts = element("div", "document-progress");
  counts.setAttribute("role", "status");
  const assertions = element("span");
  append(assertions, element("strong", "", `${progress.assertions_completed} of ${progress.assertions_total}`),
    document.createTextNode(" details checked"));
  const topics = element("span");
  append(topics, element("strong", "", `${progress.groups_completed} of ${progress.groups_total}`),
    document.createTextNode(" topics completed"));
  append(counts, assertions, topics);
  overview.append(counts);
  const track = element("div", "document-progress-track");
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-label", "Document details checked");
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", String(progress.assertions_total));
  track.setAttribute("aria-valuenow", String(progress.assertions_completed));
  const fill = element("div", "document-progress-fill");
  fill.style.width = `${progress.assertions_total > 0
    ? Math.min(100, Math.max(0, progress.assertions_completed / progress.assertions_total * 100)) : 0}%`;
  track.append(fill);
  overview.append(track);
  article.append(overview);
  const groups = element("div", "document-groups");
  for (const [index, group] of report.groups.entries()) {
    groups.append(createGroup(group, disclosures, index === 0));
  }
  article.append(groups);
  return article;
}

function disclosure(key: string, className: string, states: DocumentDisclosureState,
  initiallyOpen = false): HTMLDetailsElement {
  const details = element("details", className);
  details.dataset.documentDisclosure = key;
  details.open = states.get(key) ?? initiallyOpen;
  details.addEventListener("toggle", () => states.set(key, details.open));
  return details;
}

function createGroup(group: DocumentGroup, states: DocumentDisclosureState,
  initiallyOpen: boolean): HTMLElement {
  const details = disclosure(`group:${group.group_id}`, "document-topic", states, initiallyOpen);
  const heading = element("summary");
  const title = element("div");
  append(title, element("span", "document-topic-title", group.title));
  const completed = group.assertions.filter((item) => item.status !== "pending").length;
  title.append(element("div", "document-topic-meta",
    `${completed} of ${group.assertions.length} details checked · ${sourceLabels[group.source_match.status]}`));
  heading.append(title);
  details.append(heading);
  const content = element("div", "document-topic-content");
  const source = element("section", "document-source");
  const sourceStatus = element("p", "document-source-status", sourceLabels[group.source_match.status]);
  sourceStatus.dataset.status = group.source_match.status;
  source.append(sourceStatus);
  if (group.source_match.title) {
    source.append(element("h3", "document-source-title", group.source_match.title));
  }
  if (group.source_match.reason) source.append(element("p", "document-source-reason", group.source_match.reason));
  if (group.source_match.url) append(source, sourceLink(group.source_match.url, "Read the source"));
  if (group.source_match.discrepancies.length) {
    const gaps = element("ul", "document-limits");
    for (const reason of group.source_match.discrepancies) gaps.append(element("li", "", reason));
    source.append(gaps);
  }
  if (group.source_match.candidates.length) {
    const candidates = disclosure(`candidates:${group.group_id}`, "document-candidates", states);
    candidates.append(element("summary", "details-summary", "Sources considered"));
    const list = element("ul", "source-list");
    for (const candidate of group.source_match.candidates) {
      const item = element("li");
      append(item, candidate.url ? sourceLink(candidate.url, candidate.title) : null,
        !candidate.url || !safeExternalUrl(candidate.url) ? element("span", "", candidate.title) : null);
      if (candidate.reason) item.append(element("p", "muted-copy", candidate.reason));
      list.append(item);
    }
    candidates.append(list);
    source.append(candidates);
  }
  content.append(source);
  const assertions = element("div", "document-assertions");
  for (const assertion of group.assertions) assertions.append(createAssertion(group.group_id, assertion, states));
  content.append(assertions);
  details.append(content);
  return details;
}

function assertionLabel(assertion: DocumentAssertion): string {
  if (assertion.status === "pending") return "Checking";
  if (assertion.status === "unavailable") return "Unable to Verify Reliably";
  if (assertion.status === "duplicate") return "Checked with its original statement";
  if (assertion.status === "not_checkable") return "Not a checkable assertion";
  return assertion.result_label ? verdictLabels[assertion.result_label] : "Result unavailable";
}

function createAssertion(groupId: string, assertion: DocumentAssertion,
  states: DocumentDisclosureState): HTMLElement {
  const details = disclosure(`assertion:${groupId}:${assertion.assertion_id}`, "document-assertion", states);
  details.dataset.assertionId = assertion.assertion_id;
  details.id = `document-assertion-${groupId}-${assertion.assertion_id}`;
  const heading = element("summary");
  const title = element("span", "document-assertion-title", assertion.text);
  title.append(element("span", "document-assertion-kind", kindLabels[assertion.kind] ?? "Document detail"));
  const result = element("span", "document-assertion-result", assertionLabel(assertion));
  if (assertion.status === "completed" && assertion.result_label) result.dataset.verdict = assertion.result_label;
  append(heading, title, result);
  details.append(heading);
  const content = element("div", "document-assertion-content");
  if (assertion.status === "pending") {
    content.append(element("p", "document-pending", "This detail is still being checked. Completed checks remain available while the document analysis continues."));
  } else {
    const reporting = assertion.kind === "reported_study_fact" || assertion.kind === "reported_study_result";
    const methodology = assertion.kind === "methodology" || assertion.kind === "methodological_detail"
      || assertion.kind === "sample_size";
    const mainTitle = assertion.status === "duplicate" || assertion.status === "not_checkable"
      ? "Why this was not independently checked" : reporting ? "Accuracy of the reported study finding"
      : methodology ? "Accuracy of the study detail" : "Medical evidence assessment";
    if (assertion.reporting_fidelity) {
      content.append(assessment("Accuracy of the reported study finding", assertion.reporting_fidelity, true));
    } else content.append(assessment(mainTitle, {
      result_label: assertion.status === "completed" ? assertion.result_label : null,
      explanation: assertion.explanation,
    }, reporting || methodology));
    if (assertion.source_reports) {
      const reports = element("section", "document-assessment");
      append(reports, element("h4", "", "What the source reports"), element("p", "", assertion.source_reports));
      content.append(reports);
    }
    const medicalDuplicatesMain = !assertion.reporting_fidelity && !reporting && !methodology
      && assertion.medical_interpretation?.result_label === assertion.result_label
      && assertion.medical_interpretation?.explanation === assertion.explanation;
    if (assertion.medical_interpretation && !medicalDuplicatesMain) {
      content.append(assessment("Medical interpretation", assertion.medical_interpretation, false));
    }
    if (assertion.interpretation_limits.length) {
      const limits = element("section", "document-interpretation");
      limits.append(element("h4", "", "What this does and does not establish"));
      const list = element("ul", "document-limits");
      for (const limit of assertion.interpretation_limits) list.append(element("li", "", limit));
      limits.append(list);
      content.append(limits);
    }
    if (assertion.status === "duplicate") {
      const note = element("p", "document-note",
        "This repeats an earlier statement. Its context is retained without treating it as independent evidence.");
      if (assertion.duplicate_of) {
        const link = element("a", "source-link", "Read the original check");
        link.href = `#${encodeURIComponent(`document-assertion-${groupId}-${assertion.duplicate_of}`)}`;
        append(note, document.createTextNode(" "), link);
      }
      content.append(note);
    }
    if (assertion.status === "completed" && assertion.citations.length) {
      const citations = element("section", "document-citations");
      citations.append(element("h4", "", "Exact cited passages"));
      for (const citation of assertion.citations) citations.append(createCitation(citation));
      content.append(citations);
    }
  }
  if (assertion.source_spans.length) {
    const original = disclosure(`original:${groupId}:${assertion.assertion_id}`, "document-original-text", states);
    original.append(element("summary", "details-summary", assertion.source_spans.length > 1
      ? "Original wording and repeated passages" : "Original wording"));
    for (const span of assertion.source_spans) original.append(element("blockquote", "", span.text));
    content.append(original);
  }
  details.append(content);
  return details;
}

function assessment(title: string, result: DocumentAssessment, reporting: boolean): HTMLElement {
  const section = element("section", "document-assessment");
  let heading = title;
  if (result.result_label === "supported") heading = reporting
    ? "Supported as an accurate account of this study"
    : "Supported as a general medical conclusion";
  else if (result.result_label === "contradicted") heading = reporting
    ? "Contradicted as an account of this study" : "Contradicted by the medical evidence";
  append(section, element("h4", "", heading), element("p", "", result.explanation));
  return section;
}

function sourceLink(url: string, label: string): HTMLAnchorElement | null {
  const safeUrl = safeExternalUrl(url);
  if (!safeUrl) return null;
  const link = element("a", "source-link", label);
  link.href = safeUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function createCitation(citation: DocumentCitation): HTMLElement {
  const figure = element("figure", "document-citation");
  const quote = element("blockquote", "evidence-quote");
  quote.append(element("mark", "evidence-highlight", citation.exact_text));
  const caption = element("figcaption", "document-citation-meta");
  append(caption, document.createTextNode(`${citation.title} · ${citation.section} · ${citation.evidence_id} `),
    sourceLink(citation.url, "Read original source"));
  append(figure, quote, caption);
  return figure;
}
