import type { LensReport } from "../types/report";
import { createEvidenceCard } from "./evidenceCard";
import { append, element, labeledValue, safeExternalUrl } from "../utils/dom";
import { readableToken, verdictLabels } from "../utils/format";

export function createClaimResult(report: LensReport, analysisId: string, claimId: string): HTMLElement {
  const article = element("article", "report-card");
  article.dataset.verdict = report.verdict;

  if (!report.production_qualified) {
    const notice = element("aside", "qualification-notice");
    append(notice, element("h4", "notice-title", "Development / evaluation result"),
      element("p", "", report.verification_status.development_notice ?? "This result is not production qualified."));
    article.append(notice);
  }

  const verdict = element("section", "verdict-card");
  verdict.dataset.verdict = report.verdict;
  const label = verdictLabels[report.verdict];
  verdict.append(element("p", "verdict-label", label));
  if (report.headline.trim().toLowerCase() !== label.toLowerCase()) {
    verdict.append(element("p", "verdict-headline", report.headline));
  }
  if (report.short_summary.trim().toLowerCase() !== label.toLowerCase()
      && report.short_summary.trim().toLowerCase() !== report.headline.trim().toLowerCase()) {
    verdict.append(element("p", "verdict-summary", report.short_summary));
  }
  article.append(verdict);

  const why = element("section", "report-section");
  append(why, element("h4", "card-title", "Why this result"));
  const reasons = element("ul", "reason-list");
  for (const reason of report.why_this_result) reasons.append(element("li", "", reason.text));
  why.append(reasons);
  article.append(why);

  const evidence = element("section", "report-section");
  append(evidence, element("h4", "card-title", "Key evidence"));
  if (report.key_evidence.length) {
    const cards = element("div", "evidence-grid");
    for (const source of report.key_evidence) cards.append(createEvidenceCard(source));
    evidence.append(cards);
  } else evidence.append(element("p", "muted-copy", "No source excerpts qualified for display in this report."));
  article.append(evidence);

  if (report.evidence_limitations.length) {
    const limits = element("section", "limitations-card");
    append(limits, element("h4", "card-title", "Limitations"));
    const list = element("ul", "reason-list");
    for (const item of report.evidence_limitations) list.append(element("li", "", item));
    limits.append(list);
    article.append(limits);
  }

  const assessment = element("details", "assessment-details");
  assessment.append(element("summary", "details-summary", "How was this checked?"));
  const assessmentBody = element("div", "details-body");
  assessmentBody.append(element("p", "", report.judge_summary.description));
  const facts = element("dl", "meta-grid");
  append(facts, labeledValue("Qualified assessments", String(report.judge_summary.qualified)),
    labeledValue("Excluded assessments", String(report.judge_summary.excluded)),
    labeledValue("Validated citations shown", String(report.verification_status.validated_citations_shown)),
    labeledValue("Evidence state", readableToken(report.verification_status.evidence_state)));
  assessmentBody.append(facts);
  const counts = Object.entries(report.judge_summary.validated_label_counts).filter(([, count]) => count);
  if (counts.length) assessmentBody.append(element("p", "muted-copy",
    `Validated assessments: ${counts.map(([label, count]) => `${readableToken(label)} ${count}`).join(" · ")}`));
  assessment.append(assessmentBody);
  article.append(assessment);

  if (report.sources.length > report.key_evidence.length) {
    const sources = element("section", "report-section");
    sources.append(element("h4", "card-title", "Sources"));
    const list = element("ul", "source-list");
    for (const source of report.sources) {
      const item = element("li");
      const link = element("a", "source-link", `PMID ${source.pmid}${source.doi ? ` · DOI ${source.doi}` : ""} ↗`);
      const safeUrl = safeExternalUrl(source.url);
      if (safeUrl) {
        link.href = safeUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        item.append(link);
        list.append(item);
      }
    }
    sources.append(list);
    article.append(sources);
  }

  const safety = element("aside", "safety-notice");
  append(safety, element("h4", "card-title", "Health information safety"),
    element("p", "", report.safety_notice));
  article.append(safety);

  const technical = element("details", "technical-details");
  technical.append(element("summary", "details-summary", "Technical details"));
  const technicalFacts = element("dl", "meta-grid");
  append(technicalFacts,
    labeledValue("Report version", report.report_version),
    labeledValue("Evidence Pack version", report.provenance.evidence_pack_version),
    labeledValue("Verdict policy", report.provenance.verdict_policy_version),
    labeledValue("Selected evidence shown", String(report.key_evidence.length)),
    labeledValue("Production qualified", report.production_qualified ? "Yes" : "No"),
    labeledValue("Analysis ID", analysisId), labeledValue("Claim ID", claimId));
  technical.append(technicalFacts);
  article.append(technical);
  return article;
}
