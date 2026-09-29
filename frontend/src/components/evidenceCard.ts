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
  append(article, element("p", "evidence-kicker", readableToken(source.study_design)),
    element("h4", "evidence-title", source.title));
  const publication = [source.journal, source.publication_date].filter(Boolean).join(" · ");
  if (publication) article.append(element("p", "evidence-meta", publication));
  const roles = element("p", "evidence-role", source.evidence_roles.map((role) => roleLabels[role]).join(" · "));
  article.append(roles);
  article.append(element("p", "excerpt-label", "Exact evidence excerpt"));
  const quote = element("blockquote", "evidence-quote", source.exact_excerpt);
  article.append(quote);
  if (source.excerpt_truncated) article.append(element("p", "field-hint", "Excerpt shortened in the frozen report."));
  const foot = element("div", "evidence-footer");
  foot.append(element("span", "source-id", `PMID ${source.pmid}`));
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
  article.append(integrity);
  for (const limitation of source.limitations) article.append(element("p", "source-limitation", limitation));
  return article;
}
