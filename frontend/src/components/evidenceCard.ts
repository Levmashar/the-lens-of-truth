import type { SourceCard } from "../types/report";
import { append, element, safeExternalUrl } from "../utils/dom";
import { readableToken } from "../utils/format";

const roleLabels = {
  supporting: "Supports",
  opposing: "Opposes",
  relevant_but_insufficient: "Relevant but insufficient",
};

export function createEvidenceCard(source: SourceCard): HTMLElement {
  const article = element("article", "evidence-card");
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
    exact_text: source.exact_excerpt, truncated: source.excerpt_truncated,
  }];
  for (const excerpt of excerpts) {
    article.append(element("p", "excerpt-label", `${excerpt.section} · ${excerpt.evidence_id}`));
    article.append(element("blockquote", "evidence-quote", excerpt.exact_text));
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
