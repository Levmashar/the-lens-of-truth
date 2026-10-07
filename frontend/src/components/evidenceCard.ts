import type { ReportReadingGuide, SourceCard } from "../types/report";
import { append, element, safeExternalUrl } from "../utils/dom";
import { readableToken } from "../utils/format";

const roleLabels = {
  supporting: "Supports",
  opposing: "Opposes",
  relevant_but_insufficient: "Relevant but insufficient",
};

export function createEvidenceCard(source: SourceCard,
  highlights: ReportReadingGuide["highlights"] = [], anchorPrefix = ""): HTMLElement {
  const article = element("article", "evidence-card");
  const sourceAnchor = (id: string) => ["source", anchorPrefix, id].filter(Boolean).join("-");
  article.id = sourceAnchor(source.evidence_id);
  const design = source.analysis_design === "secondary_observational_analysis"
    ? "Secondary observational analysis within a randomized trial cohort"
    : source.analysis_design === "unknown" ? "Study design unavailable"
    : readableToken(source.analysis_design || source.study_design);
  append(article, element("p", "evidence-kicker", source.organization
    ? `${source.organization} · ${readableToken(source.document_purpose || "other")}` : design),
    element("h4", "evidence-title", source.title));
  const publication = [source.journal, source.publication_date].filter(Boolean).join(" · ");
  if (publication) article.append(element("p", "evidence-meta", source.organization
    ? `Updated/reviewed: ${publication}` : publication));
  const roles = element("p", "evidence-role", source.evidence_roles.map((role) => roleLabels[role]).join(" · "));
  article.append(roles);
  const excerpts = source.excerpts?.length ? source.excerpts : [{
    evidence_id: source.evidence_id, section: source.passage_section,
    source_unit_id: `${source.evidence_id}.U1`, exact_text: source.exact_excerpt, truncated: source.excerpt_truncated,
  }];
  for (const excerpt of excerpts) {
    const group = element("section", "source-passage");
    if (excerpt.evidence_id !== source.evidence_id) group.id = sourceAnchor(excerpt.evidence_id);
    group.append(element("p", "excerpt-label", `Quoted from ${readableToken(excerpt.section)} · ${excerpt.evidence_id}`));
    const exactHighlights = source.citation_validated ? [...new Set(highlights
      .filter((highlight) => highlight.source_unit_id === excerpt.source_unit_id
        && highlight.exact_text.length >= 25 && excerpt.exact_text.includes(highlight.exact_text))
      .map((highlight) => highlight.exact_text))] : [];
    for (const text of exactHighlights.slice(0, 3)) {
      const sourceSummary = highlights.some((highlight) => highlight.source_unit_id === excerpt.source_unit_id
        && highlight.exact_text === text && highlight.kind === "source_summary");
      if (sourceSummary) group.append(element("p", "quote-origin", "From the source’s conclusion"));
      const quote = element("blockquote", "evidence-quote evidence-key-quote");
      quote.append(element("mark", "evidence-highlight", text));
      group.append(quote);
    }
    const fullQuote = highlightedQuote(excerpt.exact_text, exactHighlights);
    if (exactHighlights.length || excerpt.exact_text.length > 600) {
      const details = element("details", "source-context");
      details.append(element("summary", "details-summary", "Read the full cited passage"), fullQuote);
      group.append(details);
    } else group.append(fullQuote);
    article.append(group);
    if (excerpt.truncated) article.append(element("p", "field-hint", "Excerpt shortened in the frozen report."));
  }
  if (source.attribution) article.append(element("p", "field-hint", source.attribution));
  const foot = element("div", "evidence-footer");
  if (source.pmid) foot.append(element("span", "source-id", `PMID ${source.pmid}`));
  if (source.doi) foot.append(element("span", "source-id", `DOI ${source.doi}`));
  const safeUrl = safeExternalUrl(source.source_url);
  if (safeUrl) {
    const link = element("a", "source-link", "View original source ↗");
    link.href = safeUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    foot.append(link);
  }
  article.append(foot);
  const integrity = element("p", "integrity-note", source.integrity_status === "valid"
    ? "Publication integrity: no signal found in completed checks"
    : `Publication integrity: ${readableToken(source.integrity_status)}`);
  integrity.dataset.status = source.integrity_status;
  if (source.organization) integrity.textContent = `Source currency: ${source.currency || "unknown"}`;
  article.append(integrity);
  for (const limitation of source.limitations) article.append(element("p", "source-limitation", limitation));
  return article;
}

function highlightedQuote(text: string, phrases: string[]): HTMLElement {
  const quote = element("blockquote", "evidence-quote evidence-full-quote");
  const ranges: { start: number; end: number }[] = [];
  for (const phrase of phrases) {
    let start = text.indexOf(phrase);
    while (start >= 0 && ranges.length < 48) {
      ranges.push({ start, end: start + phrase.length });
      start = text.indexOf(phrase, start + phrase.length);
    }
  }
  ranges.sort((a, b) => a.start - b.start || b.end - a.end);
  const merged: { start: number; end: number }[] = [];
  for (const range of ranges) {
    const previous = merged.at(-1);
    if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
    else merged.push({ ...range });
  }
  let cursor = 0;
  for (const range of merged) {
    quote.append(document.createTextNode(text.slice(cursor, range.start)),
      element("mark", "evidence-highlight", text.slice(range.start, range.end)));
    cursor = range.end;
  }
  quote.append(document.createTextNode(text.slice(cursor)));
  return quote;
}
