import { createDocumentReport, type DocumentDisclosureState } from "./documentReport";
import { createDebugProgress } from "./debugProgress";
import type { DocumentReport } from "../types/document";
import type { AnalysisProgress } from "../types/api";
import { append, element, safeExternalUrl } from "../utils/dom";
import { assertion, citation, fullPassage, questionStatus, readerSentences, validateFixture,
  type ReaderContent } from "../types/reader";

interface ReaderOptions {
  namespace?: string; advanced?: boolean; debugEnabled?: boolean;
  disclosures?: DocumentDisclosureState; heading?: "h1" | "h2";
}

function externalLink(url: string, label: string): HTMLAnchorElement | null {
  const safe = safeExternalUrl(url);
  if (!safe) return null;
  const link = element("a", "reader-source-link", label);
  link.href = safe; link.target = "_blank"; link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `${label} (opens a new tab)`);
  return link;
}

/** Traced reader rendering. No provider calls, medical classification or report mutation. */
export function createReaderScreen(fixture: ReaderContent, options: ReaderOptions = {}): HTMLElement {
  validateFixture(fixture);
  const prefix = options.namespace ?? "reader";
  const states = options.disclosures ?? new Map<string, boolean>();
  const debug = options.debugEnabled ?? true;
  function remember(details: HTMLDetailsElement, key: string): void {
    details.dataset.documentDisclosure = key; details.open = states.get(key) ?? false;
    details.addEventListener("toggle", () => states.set(key, details.open));
  }
  const page = element("article", "reader-screen"); page.dataset.fixture = fixture.id;
  const hero = element("section", "reader-answer"); hero.setAttribute("aria-labelledby", `${prefix}-title`);
  const scope = element("p", "reader-scope", fixture.scope === "study_reporting" ? "Checking what the paper reported"
    : fixture.scope === "mixed" ? "Study reporting and medical evidence are separate checks" : "Checking the medical evidence");
  const headline = element(options.heading ?? "h1", "reader-title", fixture.headline.text); headline.id = `${prefix}-title`;
  append(hero, scope, headline);
  const established = element("p", "reader-established", fixture.established.map((s) => s.text).join(" "));
  const limit = element("div", "reader-limitation"); limit.dataset.state = fixture.state ?? fixture.id;
  limit.append(element("p", "", fixture.limitation.map((s) => s.text).join(" ")));
  append(hero, established, limit);

  const actions = element("div", "reader-actions");
  const evidenceButton = element("button", "button button-primary", "See the evidence");
  evidenceButton.type = "button"; evidenceButton.setAttribute("aria-expanded", "false");
  evidenceButton.setAttribute("aria-controls", `${prefix}-evidence`);
  evidenceButton.dataset.documentDisclosure = `${prefix}:evidence-button`;
  const matched = fixture.report.groups.find((g) => g.assertions.some((a) => fixture.selectedAssertionIds.includes(a.assertion_id)) && g.source_match.status === "identified" && g.source_match.url);
  const sourceUrl = matched?.source_match.url ?? fixture.selectedAssertionIds.flatMap((id) => assertion(fixture.report, id).citations)[0]?.url;
  append(actions, evidenceButton, sourceUrl ? externalLink(sourceUrl, fixture.scope === "study_reporting" ? "Read the study" : "Read the source") : null);
  append(hero, actions);
  if (!fixture.report.production_qualified) hero.append(element("p", "reader-development-notice",
    fixture.origin ? "Development preview · Not approved for public release." : debug ? "Development result · Not approved for public release." : "This report is not approved for public release."));
  page.append(hero);

  const evidence = element("section", "reader-evidence"); evidence.id = `${prefix}-evidence`; evidence.hidden = !(states.get(`${prefix}:evidence`) ?? false);
  const evidenceTitle = element("h2", "reader-section-title", "What we checked"); evidenceTitle.tabIndex = -1;
  evidence.setAttribute("aria-labelledby", `${prefix}-evidence-title`); evidenceTitle.id = `${prefix}-evidence-title`;
  evidence.append(evidenceTitle);
  const passages = element("section", "reader-passages"); passages.hidden = !(states.get(`${prefix}:passages`) ?? false);
  const passageTitle = element("h2", "reader-section-title", "Original source passages");
  passageTitle.id = `${prefix}-passages-title`; passages.setAttribute("aria-labelledby", passageTitle.id); passages.append(passageTitle);
  const passageMap = new Map<string, HTMLDetailsElement>();

  for (const question of fixture.questions) {
    const details = element("details", "reader-question"); details.dataset.question = question.id;
    remember(details, `${prefix}:question:${question.id}`);
    const summary = element("summary");
    const title = element("span", "reader-question-title", question.question);
    const badge = element("span", "reader-check-status", question.correctnessFlag
      ? `Saved result: ${questionStatus(fixture, question)} · Review flagged` : questionStatus(fixture, question));
    badge.dataset.status = question.correctnessFlag || questionStatus(fixture, question).startsWith("We couldn’t") ? "incomplete"
      : questionStatus(fixture, question) === "Evidence is inconclusive" ? "inconclusive"
      : ["Does not match the paper", "Opposed by medical evidence"].includes(questionStatus(fixture, question)) ? "contradicted" : "completed";
    const affordance = element("span", "reader-expand-icon"); affordance.setAttribute("aria-hidden", "true");
    append(summary, title, badge, affordance); details.append(summary);
    const content = element("div", "reader-question-content");
    content.append(element("p", "reader-short-answer", question.answer.text));
    if (question.correctnessFlag) content.append(element("p", "reader-correctness-flag", question.correctnessFlag));
    for (const sentence of question.explanation) content.append(element("p", "", sentence.text));
    if (question.endpoints) {
      const list = element("ul", "reader-endpoints");
      for (const endpoint of question.endpoints) {
        const status = questionStatus(fixture, { ...question, assertionIds: endpoint.assertionIds });
        list.append(element("li", "", `${endpoint.label}: ${status}.`));
      } content.append(list);
    }
    for (const quote of question.quotes) {
      const source = citation(fixture.report, quote);
      const figure = element("figure", "reader-quote");
      if (quote.use !== "verified_passage") figure.append(element("p", "reader-quote-context",
        quote.use === "source_context" ? "Relevant source context · This check remains incomplete"
          : "Methods wording for the correctness review"));
      const block = element("blockquote"); block.append(element("mark", "", quote.text));
      const caption = element("figcaption", "reader-quote-caption");
      append(caption, externalLink(source.url, "Open original study"));
      let passage = passageMap.get(quote.sourceUnitId);
      if (!passage) {
        passage = element("details", "reader-full-passage");
        remember(passage, `${prefix}:passage:${quote.sourceUnitId}`);
        const label = source.section.toLowerCase().includes("method") ? "Methods passage"
          : source.section.toLowerCase().includes("result") ? "Results passage" : "Study passage";
        passage.append(element("summary", "", label));
        const original = fullPassage(fixture.report, quote.sourceUnitId) ?? source;
        passage.append(element("blockquote", "", original.exact_text));
        append(passage, externalLink(original.url, "Read the source online"));
        passages.append(passage); passageMap.set(quote.sourceUnitId, passage);
      }
      const fullButton = element("button", "reader-passage-button", "Full source passage"); fullButton.type = "button";
      const target = passage;
      fullButton.addEventListener("click", () => {
        passages.hidden = false; target.open = true;
        states.set(`${prefix}:passages`, true);
        target.querySelector("summary")?.focus(); target.scrollIntoView({ block: "start" });
      });
      caption.append(fullButton); append(figure, block, caption); content.append(figure);
    }
    details.append(content); evidence.append(details);
  }
  evidence.append(passages); page.append(evidence);
  evidenceButton.setAttribute("aria-expanded", String(!evidence.hidden));
  evidenceButton.textContent = evidence.hidden ? "See the evidence" : "Hide the evidence";
  evidenceButton.addEventListener("click", () => {
    evidence.hidden = !evidence.hidden;
    states.set(`${prefix}:evidence`, !evidence.hidden);
    evidenceButton.setAttribute("aria-expanded", String(!evidence.hidden));
    evidenceButton.textContent = evidence.hidden ? "See the evidence" : "Hide the evidence";
    if (!evidence.hidden) { evidenceTitle.focus({ preventScroll: true }); evidenceTitle.scrollIntoView({ block: "start" }); }
  });

  if (options.advanced === false) return page;
  const advanced = element("details", "reader-advanced"); remember(advanced, "reader:advanced");
  advanced.append(element("summary", "", "Advanced view · Original report and diagnostics"));
  let loaded = false;
  advanced.addEventListener("toggle", () => {
    if (!advanced.open || loaded) return;
    loaded = true;
    advanced.append(element("p", "reader-advanced-notice",
      fixture.origin ? "Development only. Original records and outcomes are unchanged. Synthetic scenarios describe a selected scope; the full saved report below may contain other unfinished checks. Raw responses appear only in this advanced view."
        : "Original records and outcomes are unchanged. This view keeps every assertion and full frozen passage. Development diagnostics, when enabled, appear only here."));
    const tracing = element("details", "reader-traces"); tracing.append(element("summary", "", "Reader wording and supporting references"));
    remember(tracing, "reader:traces");
    tracing.append(element("pre", "reader-json", JSON.stringify({
      fixture: fixture.id, origin: fixture.origin, selected_assertion_ids: fixture.selectedAssertionIds,
      analysis_id: fixture.report.analysis_id, sentences: readerSentences(fixture),
      reader_view: fixture.report.reader_view,
      questions: fixture.questions.map((q) => ({ question: q.question, assertion_ids: q.assertionIds,
        saved_records: q.assertionIds.map((id) => ({ id, status: assertion(fixture.report, id).status,
          result_label: assertion(fixture.report, id).result_label })), exact_quotes: q.quotes })),
    }, null, 2))); advanced.append(tracing);
    const original = element("details", "reader-original"); original.append(element("summary", "", "Complete saved report · All assertions and frozen passages"));
    remember(original, "reader:original");
    original.append(createDocumentReport(fixture.report, states, debug)); advanced.append(original);
    if (fixture.analysis && debug) advanced.append(createDebugProgress(fixture.analysis, [], null, fixture.report));
    else if (debug) {
      const button = element("button", "button button-secondary", "Copy all diagnostics"); button.type = "button";
      const status = element("p"); status.setAttribute("role", "status");
      button.addEventListener("click", async () => {
        try { await navigator.clipboard.writeText(JSON.stringify({ document: fixture.report }, null, 2));
          status.textContent = "Copied all saved diagnostics, including raw model responses.";
        } catch { status.textContent = "Could not copy diagnostics. Check clipboard permissions and try again."; }
      });
      const raw = element("details"); raw.append(element("summary", "", "Raw saved replies · Development only"),
        element("pre", "reader-json", JSON.stringify(fixture.report.debug_group_runs ?? null, null, 2)));
      advanced.append(button, status, raw);
    }
  }); page.append(advanced);
  return page;
}

export function createDocumentReader(report: DocumentReport, analysis: AnalysisProgress,
  states: DocumentDisclosureState, debug: boolean): HTMLElement {
  const view = report.reader_view;
  if (!view || view.version !== "reader-view-1.0" || !view.topics.length) throw new Error("Reader view unavailable");
  const host = element("section", "document-reader");
  let advanced: Element | null = null;
  view.topics.forEach((topic, i) => {
    const node = createReaderScreen({ ...topic, report, analysis }, { namespace: `reader-${topic.id}`,
      advanced: i === 0, debugEnabled: debug, disclosures: states, heading: i === 0 ? "h1" : "h2" });
    if (i === 0) { advanced = node.querySelector(".reader-advanced"); advanced?.remove(); }
    host.append(node);
  });
  if (advanced) host.append(advanced);
  return host;
}

