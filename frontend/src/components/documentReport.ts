import type { DocumentAssertion, DocumentCitation, DocumentCounts, DocumentGroup, DocumentReport, DocumentSummaryLine } from "../types/document";
import { append, element, safeExternalUrl } from "../utils/dom";
import { verdictLabels } from "../utils/format";
import { showDevelopmentUi } from "../utils/uiMode";

export type DocumentDisclosureState = Map<string, boolean>;
const sourceLabels = {
  identified: "Source identified", uncertain: "Source match is uncertain", not_found: "Searched; source not found",
  pending: "Source search pending", failed: "Source search failed", not_applicable: "Study search not applicable",
};
const reportingLabels = {
  supported: "Matches the paper", contradicted: "Does not match the paper",
  not_enough_evidence: "Could not verify this detail", unable_to_verify_reliably: "Check unavailable",
};

export function documentCounts(items: DocumentAssertion[]): DocumentCounts {
  const assessed = items.filter((a) => a.status === "completed").length;
  const unavailable = items.filter((a) => a.status === "unavailable").length;
  const background = items.filter((a) => a.status === "not_checkable" || a.status === "duplicate").length;
  const pending = items.filter((a) => a.status === "pending").length;
  return { total: items.length, assessed, unavailable, background, pending, processed: items.length - pending };
}

function isReporting(a: DocumentAssertion): boolean {
  return a.assessment_target === "reporting_fidelity" || ["reported_study_fact", "reported_study_result",
    "methodology", "methodological_detail", "sample_size"].includes(a.kind);
}
function isSourceNote(a: DocumentAssertion): boolean {
  return /^\s*source\s*:/i.test(a.text);
}
export function assertionLabel(a: DocumentAssertion): string {
  if (a.status === "pending") return "Checking";
  if (a.status === "unavailable") return "Check unavailable";
  if (a.status === "duplicate") return "Repeated wording; shared check";
  if (a.status === "not_checkable") return "Background wording; not assessed";
  return a.result_label ? (isReporting(a) ? reportingLabels[a.result_label] : verdictLabels[a.result_label]) : "Result unavailable";
}
function disclosure(key: string, className: string, states: DocumentDisclosureState): HTMLDetailsElement {
  const details = element("details", className);
  details.dataset.documentDisclosure = key; details.open = states.get(key) ?? false;
  details.addEventListener("toggle", () => states.set(key, details.open)); return details;
}
function localLink(id: string, label: string, states: DocumentDisclosureState): HTMLAnchorElement {
  const link = element("a", "source-link", label); link.href = `#${encodeURIComponent(id)}`;
  link.addEventListener("click", () => {
    const target = document.getElementById(id);
    let parent: HTMLElement | null = target;
    while (parent) {
      if (parent instanceof HTMLDetailsElement) {
        parent.open = true;
        if (parent.dataset.documentDisclosure) states.set(parent.dataset.documentDisclosure, true);
      }
      parent = parent.parentElement;
    }
    const focus = target instanceof HTMLDetailsElement ? target.querySelector("summary") : target;
    if (focus instanceof HTMLElement) focus.focus({ preventScroll: true });
  }); return link;
}
function traceLinks(line: DocumentSummaryLine, report: DocumentReport, states: DocumentDisclosureState): HTMLElement {
  const links = element("span", "document-trace-links");
  for (const aid of line.assertion_ids) {
    const group = report.groups.find((g) => g.assertions.some((a) => a.assertion_id === aid));
    if (group) links.append(localLink(`document-assertion-${group.group_id}-${aid}`, `Detail ${aid}`, states));
  } return links;
}

/** Server-owned, traceable reading view; never generate a document verdict. */
export function createDocumentReport(report: DocumentReport, states: DocumentDisclosureState = new Map(),
  debugEnabled = false, initialRender = true): HTMLElement {
  const article = element("article", "document-report");
  article.dataset.version = report.version; article.dataset.initial = String(initialRender);
  if (!report.production_qualified) {
    const notice = element("aside", "qualification-notice");
    append(notice, element("h2", "notice-title", showDevelopmentUi(debugEnabled) ? "Development / evaluation result" : "Verification status"),
      element("p", "", showDevelopmentUi(debugEnabled) ? "Development evaluation only; not qualified for public release."
        : "This report has not yet met the checks required for public release.")); article.append(notice);
  }
  const counts = documentCounts(report.groups.flatMap((g) => g.assertions));
  const overview = element("section", "document-overview");
  append(overview, element("p", "eyebrow", "Document check"), element("h2", "section-title", "Main takeaway"));
  if (report.reading_summary) {
    for (const line of report.reading_summary.main_takeaway) {
      const paragraph = element("p", "document-takeaway", line.text);
      paragraph.append(traceLinks(line, report, states)); overview.append(paragraph);
    }
  } else overview.append(element("p", "document-takeaway", `${counts.assessed} details were assessed; ${counts.unavailable} checks were unavailable. Study reporting and medical conclusions are shown separately below.`));
  const status = element("p", "document-completion", report.completion_text
    ?? (report.status === "running" ? "Checks in progress" : counts.unavailable ? "Finished with limitations" : "Processing finished"));
  status.setAttribute("role", "status"); overview.append(status);
  const progress = element("div", "document-progress");
  for (const [amount, label] of [[counts.assessed, "assessed"], [counts.unavailable, "unavailable"],
    [counts.background, "background / not assessed"], [counts.pending, "pending"]] as const) {
    const item = element("span"); append(item, element("strong", "", String(amount)), document.createTextNode(` ${label}`)); progress.append(item);
  } overview.append(progress);
  if (counts.pending) {
    const track = element("div", "document-progress-track"); track.setAttribute("role", "progressbar");
    track.setAttribute("aria-label", "Document processing progress; includes background and failed checks");
    track.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", String(counts.total));
    track.setAttribute("aria-valuenow", String(counts.processed));
    track.setAttribute("aria-valuetext", `${counts.assessed} assessed, ${counts.unavailable} unavailable, ${counts.background} background, ${counts.pending} pending`);
    const fill = element("div", "document-progress-fill"); fill.style.width = `${counts.total ? counts.processed / counts.total * 100 : 0}%`;
    track.append(fill); overview.append(track);
  } article.append(overview);
  if (report.reading_summary) {
    article.append(readingSection("What needs attention", report.reading_summary.attention, report, states, true));
    article.append(readingSection("What matches the source", report.reading_summary.matches, report, states, false));
    if (report.reading_summary.limits.length) article.append(readingSection("Important interpretation limits", report.reading_summary.limits, report, states, false));
  }
  const detailed = element("section", "document-detailed-checks"); detailed.append(element("h2", "section-title", "Detailed checks and sources"));
  const groups = element("div", "document-groups");
  for (const g of report.groups) {
    if (g.display_parent_group_id && report.groups.some((parent) => parent.group_id === g.display_parent_group_id)) continue;
    const attached = report.groups.filter((other) => other.group_id !== g.group_id).map((other) => ({
      ...other, assertions: other.assertions.filter((a) => a.display_parent_group_id === g.group_id
        || other.display_parent_group_id === g.group_id),
    })).filter((other) => other.assertions.length > 0);
    const own = g.assertions.filter((a) => !a.display_parent_group_id
      || a.display_parent_group_id === g.group_id || !report.groups.some((parent) => parent.group_id === a.display_parent_group_id));
    groups.append(createGroup({ ...g, assertions: own }, attached, states));
  } detailed.append(groups); article.append(detailed); return article;
}
function readingSection(title: string, lines: DocumentSummaryLine[], report: DocumentReport,
  states: DocumentDisclosureState, attention: boolean): HTMLElement {
  const section = element("section", attention ? "document-reading-section document-attention" : "document-reading-section");
  section.append(element("h2", "section-title", title));
  if (!lines.length) section.append(element("p", "muted-copy", attention ? "No unresolved or mismatching assessed details are listed." : "No qualified matches are available yet."));
  const list = element("ul", "document-reading-list");
  for (const line of lines) {
    const row = element("li");
    const related = report.groups.flatMap((g) => g.assertions).find((a) => a.assertion_id === line.assertion_ids[0]);
    const label = line.assertion_ids.length === 1 && related && isSourceNote(related) ? "Source note" : line.text;
    append(row, element(attention ? "strong" : "span", "", label), traceLinks(line, report, states));
    if (line.result_label) {
      const a = report.groups.flatMap((g) => g.assertions).find((a) => a.assertion_id === line.assertion_ids[0]);
      if (a) row.append(element("span", "document-reading-result", assertionLabel(a)));
    }
    if (line.explanation) row.append(element("p", "", line.explanation)); list.append(row);
    if (related?.association_caveat) row.append(element("p", "document-association-caveat", related.association_caveat));
  } section.append(list); return section;
}
function createGroup(group: DocumentGroup, attached: DocumentGroup[], states: DocumentDisclosureState): HTMLElement {
  const details = disclosure(`group:${group.group_id}`, "document-topic", states);
  const summary = element("summary"); const title = element("div");
  const counts = documentCounts([...group.assertions, ...attached.flatMap((g) => g.assertions)]);
  append(title, element("h3", "document-topic-title", group.title), element("p", "document-topic-meta",
    `${counts.assessed} assessed \u00b7 ${counts.unavailable} unavailable \u00b7 ${counts.background} background \u00b7 ${sourceLabels[group.source_match.status]}`));
  summary.append(title); details.append(summary);
  const content = element("div", "document-topic-content"); const source = element("section", "document-source");
  const status = element("p", "document-source-status", sourceLabels[group.source_match.status]); status.dataset.status = group.source_match.status; source.append(status);
  if (group.source_match.title) source.append(element("h4", "document-source-title", group.source_match.title));
  if (group.source_match.reason) source.append(element("p", "document-source-reason", group.source_match.reason));
  append(source, group.source_match.url ? sourceLink(group.source_match.url, "Read the identified paper") : null);
  if (group.source_match.discrepancies.length) {
    const gaps = element("ul", "document-limits"); for (const reason of group.source_match.discrepancies) gaps.append(element("li", "", reason)); source.append(gaps);
  }
  if (group.source_match.candidates.length) {
    const candidates = disclosure(`candidates:${group.group_id}`, "document-candidates", states);
    candidates.append(element("summary", "details-summary", "Sources considered")); const list = element("ul", "source-list");
    for (const candidate of group.source_match.candidates) {
      const item = element("li"); item.append(sourceLink(candidate.url ?? "", candidate.title) ?? element("span", "", candidate.title));
      if (candidate.reason) item.append(element("p", "muted-copy", candidate.reason)); list.append(item);
    } candidates.append(list); source.append(candidates);
  } content.append(source);
  const assertions = element("div", "document-assertions");
  for (const a of group.assertions.filter((a) => !a.duplicate_of && a.status !== "not_checkable" && !isSourceNote(a))) assertions.append(createAssertion(group.group_id, a, states, !!group.sources));
  const background = [...group.assertions.filter((a) => a.duplicate_of || a.status === "not_checkable" || isSourceNote(a)), ...attached.flatMap((g) => g.assertions)];
  if (background.length) {
    const context = disclosure(`background:${group.group_id}`, "document-background", states);
    context.append(element("summary", "details-summary", `Related context and source notes (${background.length})`));
    for (const a of background) {
      const owner = attached.find((g) => g.assertions.includes(a)) ?? group;
      context.append(createAssertion(owner.group_id, a, states, !!owner.sources));
    } assertions.append(context);
  } content.append(assertions);
  const sourceOwners = [group, ...attached];
  if (sourceOwners.some((owner) => owner.sources?.length)) {
    const library = element("section", "document-frozen-sources"); library.append(element("h4", "", "Full frozen passages"));
    for (const owner of sourceOwners) for (const citation of owner.sources ?? []) {
      const passage = disclosure(`source:${owner.group_id}:${citation.source_unit_id}`, "document-full-passage", states);
      passage.id = `document-source-${owner.group_id}-${citation.source_unit_id}`;
      passage.append(element("summary", "details-summary", `${citation.section} \u00b7 ${citation.source_unit_id}`), element("blockquote", "", citation.exact_text));
      append(passage, sourceLink(citation.url, `Read original source: ${citation.title}`)); library.append(passage);
    } content.append(library);
  } details.append(content); return details;
}
function createAssertion(groupId: string, a: DocumentAssertion, states: DocumentDisclosureState, pooledSources: boolean): HTMLElement {
  const details = disclosure(`assertion:${groupId}:${a.assertion_id}`, "document-assertion", states);
  details.dataset.assertionId = a.assertion_id; details.id = `document-assertion-${groupId}-${a.assertion_id}`;
  const heading = element("summary"); const title = element("h4", "document-assertion-title", isSourceNote(a) ? "Source note" : a.heading ?? a.text);
  title.append(element("span", "document-assertion-kind", `${a.assertion_id} \u00b7 ${isReporting(a) ? "Study reporting" : a.status === "not_checkable" ? "Background" : "Medical evidence"}`));
  const result = element("span", "document-assertion-result", assertionLabel(a));
  if (a.status === "completed" && a.result_label) result.dataset.verdict = a.result_label;
  append(heading, title, result); details.append(heading); const content = element("div", "document-assertion-content");
  append(content, element("p", "document-wording-label", "Submitted wording"), element("blockquote", "document-submitted-wording", a.text));
  const explanation = a.status === "pending" ? "This detail is still being checked." : a.explanation;
  const assessment = element("section", "document-assessment"); append(assessment, element("h5", "", assertionLabel(a)), element("p", "", explanation)); content.append(assessment);
  if (a.association_caveat) content.append(element("p", "document-association-caveat", a.association_caveat));
  const limits = a.interpretation_limits.filter((l) => l !== a.association_caveat);
  if (limits.length) { const list = element("ul", "document-limits"); for (const l of limits) list.append(element("li", "", l)); content.append(list); }
  if (a.status === "completed" && a.medical_interpretation && a.reporting_fidelity) append(content, element("h5", "", "Medical interpretation"), element("p", "", a.medical_interpretation.explanation));
  if (a.status === "duplicate" && a.duplicate_of) content.append(localLink(`document-assertion-${groupId}-${a.duplicate_of}`, "Read the original check", states));
  if (a.status === "completed" && a.citations.length) {
    const citations = element("section", "document-citations"); citations.append(element("h5", "", "Source excerpts")); const used = new Set<string>();
    for (const c of a.citations) { const key = `${c.source_unit_id}:${c.excerpt ?? c.exact_text}`; if (used.has(key)) continue;
      used.add(key); citations.append(createCitation(groupId, c, states, pooledSources)); } content.append(citations);
  }
  if (a.source_spans.length > 1 || a.source_spans[0]?.text !== a.text) {
    const original = disclosure(`original:${groupId}:${a.assertion_id}`, "document-original-text", states);
    original.append(element("summary", "details-summary", "All original occurrences")); for (const span of a.source_spans) original.append(element("blockquote", "", span.text)); content.append(original);
  } details.append(content); return details;
}
function sourceLink(url: string, label: string): HTMLAnchorElement | null {
  const safe = safeExternalUrl(url); if (!safe) return null;
  const link = element("a", "source-link", label); link.href = safe; link.target = "_blank"; link.rel = "noopener noreferrer"; return link;
}
function createCitation(groupId: string, c: DocumentCitation, states: DocumentDisclosureState, pooledSources: boolean): HTMLElement {
  const figure = element("figure", "document-citation"); const quote = element("blockquote", "evidence-quote");
  quote.append(element("mark", "evidence-highlight", c.excerpt && c.exact_text.includes(c.excerpt) ? c.excerpt : c.exact_text));
  const caption = element("figcaption", "document-citation-meta"); caption.append(element("span", "", `${c.title} \u00b7 ${c.section}`));
  if (pooledSources) caption.append(localLink(`document-source-${groupId}-${c.source_unit_id}`, `Read full frozen passage ${c.source_unit_id}`, states));
  else append(caption, sourceLink(c.url, `Read original source: ${c.title}`)); append(figure, quote, caption); return figure;
}
