import type { LensReport, ReportReadingGuide } from "../types/report";
import { createEvidenceCard } from "./evidenceCard";
import { append, element, labeledValue, safeExternalUrl } from "../utils/dom";
import { readableToken } from "../utils/format";
import { claimQuestion, readerAnswer, readerVerdictLabels } from "../utils/readerPresentation";
import { showDevelopmentUi } from "../utils/uiMode";

export function createClaimResult(report: LensReport, analysisId: string, claimId: string,
  debugEnabled = false, readingGuide?: ReportReadingGuide): HTMLElement {
  const article = element("article", "report-card consumer-report");
  article.dataset.verdict = report.verdict;
  const guide = readingGuide?.verdict_run_id === report.verdict_run_id
    && readingGuide.report_semantic_hash === report.semantic_hash ? readingGuide : undefined;
  const developmentUi = showDevelopmentUi(debugEnabled);
  const verdict = element("section", "consumer-answer");
  verdict.setAttribute("aria-label", "Research assessment");
  verdict.append(element("h2", "verdict-label", readerVerdictLabels[report.verdict]));
  verdict.append(element("p", "claim-question", claimQuestion(report.claim.text)));
  const answer = readerAnswer(report, guide);
  const summary = element("p", "verdict-summary", answer.text);
  summary.dataset.reportReferences = answer.references.join(" ");
  verdict.append(summary);
  if (report.verdict === "not_enough_evidence") {
    verdict.append(element("p", "consumer-uncertainty", "Not established doesn't mean disproven."));
  }
  article.append(verdict);
  if (guide?.retrieval?.state === "search_incomplete") {
    verdict.append(element("p", "consumer-search-warning", "The source search could not be completed. This limits what this check can tell you."));
  }

  if (!report.production_qualified) {
    const notice = element("aside", "qualification-notice");
    notice.append(element("p", "", developmentUi
      ? "Development preview. Not qualified for medical use."
      : "This report has not yet met the checks required for public release."));
    if (report.judge_summary.excluded > 0) notice.append(element("p", "",
      "Some assessments could not be verified; the result uses only those that passed."));
    article.append(notice);
  }

  const evidence = element("details", "consumer-evidence");
  evidence.dataset.documentDisclosure = `claim-evidence-${claimId}`;
  evidence.append(element("summary", "consumer-disclosure", "See the evidence"));
  const evidenceBody = element("div", "consumer-evidence-body");
  if (guide?.findings.length) {
    const findings = element("section", "case-explanation");
    findings.append(element("h3", "meaning-title", "What the checked sources found"));
    for (const finding of guide.findings) {
      const paragraph = element("p", "case-finding", finding.text);
      const citations = element("span", "finding-citations");
      for (const evidenceId of finding.evidence_ids) {
        const owner = report.key_evidence.findIndex(source => source.evidence_id === evidenceId
          || source.excerpts?.some(excerpt => excerpt.evidence_id === evidenceId));
        if (owner < 0) continue;
        const link = element("a", "finding-citation", `Source ${owner + 1}`);
        link.href = `#source-${claimId}-${evidenceId}`;
        link.setAttribute("aria-label", `Read source ${owner + 1}: ${report.key_evidence[owner].title}`);
        link.addEventListener("click", () => {
          const target = article.querySelector<HTMLElement>(`[id="source-${claimId}-${evidenceId}"]`);
          for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
            if (parent instanceof HTMLDetailsElement) parent.open = true;
          }
          if (target) { target.tabIndex = -1; target.focus({ preventScroll: true }); }
        });
        citations.append(link);
      }
      append(paragraph, document.createTextNode(" "), citations);
      findings.append(paragraph);
    }
    evidenceBody.append(findings);
  }

  if (guide?.retrieval?.version === "retrieval-coverage-2.0") {
    const coverage = element("section", "limitations-card");
    const titles = { search_incomplete: "The search was incomplete",
      no_eligible_sources: "No usable sources found in this search",
      related_only: "Related evidence has limits", direct_candidates: "What the search found" };
    append(coverage, element("h4", "card-title", titles[guide.retrieval.state]),
      element("p", "", guide.retrieval.explanation));
    if (guide.retrieval.sources.length) {
      const disclosure = element("details", "assessment-details");
      disclosure.append(element("summary", "details-summary", "Explore the sources found"));
      const body = element("div", "details-body");
      for (const source of guide.retrieval.sources) {
        const url = safeExternalUrl(source.url);
        if (!url) continue;
        const row = element("p", "");
        const label = source.classification === "direct" ? "Matching research candidate"
          : source.classification === "background_guidance" ? "Background clinical guidance"
          : "Related, indirect research";
        row.append(element("span", "muted-copy", `${label}: `));
        const link = element("a", "source-link", source.title);
        link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
        row.append(link);
        body.append(row);
      }
      disclosure.append(body); coverage.append(disclosure);
    }
    evidenceBody.append(coverage);
  }

  if (report.key_evidence.length) {
    const cards = element("div", "evidence-grid");
    for (const [index, source] of report.key_evidence.entries()) {
      const disclosure = element("details", "consumer-source");
      disclosure.dataset.documentDisclosure = `claim-source-${claimId}-${index}`;
      disclosure.append(element("summary", "consumer-source-title", source.title),
        createEvidenceCard(source, guide?.highlights, claimId));
      cards.append(disclosure);
    }
    evidenceBody.append(cards);
  } else evidenceBody.append(element("p", "muted-copy", "No source excerpts qualified for display in this report."));

  if (report.verdict === "unable_to_verify_reliably" &&
      !report.production_qualified && report.neutral_retrieved_sources?.length) {
    const neutral = element("section", "report-section");
    append(neutral,
      element("h4", "card-title", "Retrieved sources — not validated support for a final conclusion"),
      element("p", "muted-copy", "These are exact frozen excerpts. Their relevance or direction was not validated as a final medical conclusion."),
    );
    for (const source of report.neutral_retrieved_sources) {
      const card = element("article", "evidence-card");
      append(card,
        element("p", "", `${source.evidence_id}${source.pmid ? ` · PMID ${source.pmid}` : ""} · ${source.passage_section}`),
        element("h5", "", source.title),
        element("blockquote", "", source.exact_excerpt),
      );
      const safeUrl = safeExternalUrl(source.source_url);
      if (safeUrl) {
        const link = element("a", "source-link", "View original source ↗");
        link.href = safeUrl;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        card.append(link);
      }
      neutral.append(card);
    }
    evidenceBody.append(neutral);
  }

  evidence.append(evidenceBody);
  article.append(evidence);

  const about = element("details", "consumer-about");
  about.dataset.documentDisclosure = `claim-about-${claimId}`;
  about.append(element("summary", "consumer-disclosure", "About this check"));
  const aboutBody = element("div", "consumer-about-body");
  append(aboutBody, element("h3", "card-title", "Claim checked"), element("p", "original-claim", report.claim.text));
  if (report.verdict_explanation?.established || report.verdict_explanation?.unresolved) {
    const clarity = element("dl", "evidence-clarity");
    if (report.verdict_explanation.established) clarity.append(labeledValue("What was established", report.verdict_explanation.established));
    if (report.verdict_explanation.unresolved) clarity.append(labeledValue("What remains unclear", report.verdict_explanation.unresolved));
    aboutBody.append(clarity);
  }
  if (report.why_this_result.length) {
    const why = element("section", "report-section");
    why.append(element("h3", "card-title", "Why this result"));
    const reasons = element("ul", "reason-list");
    for (const reason of report.why_this_result) reasons.append(element("li", "", reason.text));
    why.append(reasons); aboutBody.append(why);
  }
  if (!report.production_qualified && report.verification_status.development_notice) {
    aboutBody.append(element("p", "full-qualification-notice", report.verification_status.development_notice));
  }

  if (report.evidence_limitations.length) {
    const limits = element("section", "limitations-card");
    append(limits, element("h4", "card-title", "Limitations"));
    const list = element("ul", "reason-list");
    for (const item of report.evidence_limitations) list.append(element("li", "", item));
    limits.append(list);
    aboutBody.append(limits);
  }

  const assessment = element("details", "assessment-details");
  assessment.append(element("summary", "details-summary", "How was this checked?"));
  const assessmentBody = element("div", "details-body");
  const assessmentDescription = report.judge_summary.description.trim() || (
    report.verdict === "not_enough_evidence"
      && report.judge_summary.qualified === 0
      && report.judge_summary.excluded === 0
      ? "No judge assessment ran because the search selected no usable evidence."
      : "No assessment description was recorded."
  );
  assessmentBody.append(element("p", "", assessmentDescription));
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
  aboutBody.append(assessment);

  if (report.sources.length > report.key_evidence.length) {
    const sources = element("section", "report-section");
    sources.append(element("h4", "card-title", "Sources"));
    const list = element("ul", "source-list");
    for (const source of report.sources) {
      const item = element("li");
      const label = source.pmid ? `PMID ${source.pmid}` : "Original source";
      const link = element("a", "source-link", `${label}${source.doi ? ` · DOI ${source.doi}` : ""} ↗`);
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
    evidenceBody.append(sources);
  }



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
  if (debugEnabled && report.verdict_explanation) {
    const explanation = report.verdict_explanation;
    const diagnostics = element("section", "verdict-explanation-details");
    diagnostics.append(element("h4", "card-title", "Verdict explanation"));
    const facts = element("dl", "meta-grid");
    append(facts,
      labeledValue("Version", explanation.version),
      labeledValue("Reason category", explanation.reason_category),
      labeledValue("Established", explanation.established ?? "None"),
      labeledValue("Unresolved", explanation.unresolved ?? "None"),
      labeledValue("Evidence IDs", explanation.evidence_ids.join(", ") || "None"));
    diagnostics.append(facts);
    technical.append(diagnostics);
  }
  if (developmentUi) aboutBody.append(technical);
  about.append(aboutBody);
  article.append(about, element("p", "consumer-safety", report.safety_notice));
  return article;
}
