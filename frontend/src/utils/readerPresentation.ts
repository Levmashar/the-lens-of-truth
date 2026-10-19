import type { VerdictLabel } from "../types/api";
import type { LensReport, ReportReadingGuide } from "../types/report";
import { verdictLabels } from "./format";

/** Display text only. Never round-trip these labels into a scientific verdict. */
export const readerVerdictLabels: Record<VerdictLabel, string> = {
  supported: "Supported by research",
  contradicted: "Research contradicts this",
  not_enough_evidence: "Not established by research",
  unable_to_verify_reliably: "We couldn't complete the check",
};

const lowerInitial = (text: string): string => /^(?:[A-Z][a-z]|A\s)/.test(text)
  ? text[0].toLowerCase() + text.slice(1) : text;

/** Conservative grammar changes; the original proposition remains in About this check. */
export function claimQuestion(claim: string): string {
  const text = claim.trim().replace(/[.!?]+$/, "").replace(/,\s+(?=increases?\b)/gi, " ")
    .replace(/\blaying(?= (?:down|on)\b)/gi, "lying").replace(/\blying down\b/gi, "lying")
    .replace(/\bincreases deterioration of\b/gi, "worsens");
  if (claim.trim().endsWith("?")) return claim.trim();
  // Do not rearrange multiple propositions or punctuation within a long passage.
  if (!/[.!;]\s/.test(text)) {
    const auxiliary = text.match(/^(.+?)\s+(does|do|is|are|can|may|will)\s+(.+)$/i);
    if (auxiliary) return /^not\b/i.test(auxiliary[3]) ? `Is it true that ${lowerInitial(text)}?`
      : `${auxiliary[2][0].toUpperCase()}${auxiliary[2].slice(1)} ${lowerInitial(auxiliary[1])} ${auxiliary[3]}?`;
    const verbs: Record<string, string> = { causes: "cause", cause: "cause", increases: "increase",
      increase: "increase", reduces: "reduce", reduce: "reduce", prevents: "prevent", prevent: "prevent",
      worsens: "worsen", improves: "improve", treats: "treat", cures: "cure", lowers: "lower",
      shortens: "shorten", protects: "protect" };
    const match = text.match(/^(.+?)\s+(causes?|increases?|reduces?|prevents?|worsens|improves|treats|cures|lowers|shortens|protects)\s+(.+)$/i);
    if (match) {
      const plural = /\b(antibiotics|vaccines|networks|showers|carrots|multivitamins|people)$/i.test(match[1]);
      return `${plural ? "Do" : "Does"} ${lowerInitial(match[1])} ${verbs[match[2].toLowerCase()]} ${match[3]}?`;
    }
  }
  return `Is it true that ${lowerInitial(text)}?`;
}

export interface ReaderAnswer {
  text: string;
  /** Trace every editorially simplified sentence to approved presentation fields. */
  references: string[];
}

function plainScopeFinding(text: string): string {
  // Grammar template + terminology glossary, independent of any claim or publication.
  return text.replace(/^The specific exposure of (.+) was not investigated as a separate risk factor for (.+)\.$/,
    "The studies did not separately test whether $1 affects $2.")
    .replace(/\blateral recumbent (.+?) use\b/gi, "using a $1 while lying on your side")
    .replace(/\bmyopia progression\b/gi, "how quickly short-sightedness gets worse");
}

export function readerAnswer(report: LensReport, guide?: ReportReadingGuide): ReaderAnswer {
  const explanation = report.verdict_explanation;
  const fallback = { text: explanation?.summary || report.short_summary,
    references: [explanation?.summary ? "verdict_explanation.summary" : "short_summary"] };
  if (!fallback.text.trim() || Object.values(verdictLabels).some(label => label.toLowerCase() === fallback.text.trim().toLowerCase())) {
    const historicalFallback: Record<VerdictLabel, string> = {
      supported: "The checked research supports this claim. See the evidence for its scope and limits.",
      contradicted: "The checked research points against this claim. See the evidence for its scope and limits.",
      not_enough_evidence: "The available evidence did not establish a clear answer at the scope of this claim.",
      unable_to_verify_reliably: "We couldn't verify enough information to give a reliable answer.",
    };
    fallback.text = historicalFallback[report.verdict];
    fallback.references = ["verdict"];
  }
  if (report.verdict === "unable_to_verify_reliably") return {
    text: `${fallback.text} This is an unfinished check, not evidence that the claim is true or false.`,
    references: [...fallback.references, "verdict"],
  };
  if (report.verdict === "supported" || report.verdict === "contradicted") {
    const generic = ["Multiple validated assessments found evidence supporting the claim at its stated scope.",
      "Validated evidence conflicts with the claim at its stated scope."];
    // Preserve summaries that carry quantitative, comparison or provisional limits.
    if (!generic.includes(fallback.text) || /\d/.test(report.claim.text)) return fallback;
    // Reuse a complete approved finding, never raw model prose or a new inference.
    // Lexical ranking only chooses which already-approved sentence to display first.
    const terms = (text: string) => text.toLowerCase().match(/[a-z]{4,}/g)?.map(word => word.replace(/s$/, "")) ?? [];
    const claimTerms = new Set(terms(report.claim.text));
    const candidates = guide?.findings.map((finding, index) => {
      const words = new Set(terms(finding.text));
      const common = [...words].filter(word => claimTerms.has(word)).length;
      return { finding, index, common, score: common / Math.sqrt(words.size || 1) };
    }).filter(({ finding, common }) => common >= 2 && finding.source_unit_ids.length > 0
      && finding.text.length <= 360 && finding.evidence_ids.length > 0
      && finding.evidence_ids.every(id => explanation?.evidence_ids.includes(id)))
      .sort((a, b) => b.score - a.score);
    if (candidates?.length) return { text: candidates[0].finding.text,
      references: [`findings.${candidates[0].index}`, ...candidates[0].finding.source_unit_ids] };
    return fallback;
  }
  // A conflict is not an absence of research. Never let search copy override it.
  if (/conflict|mixed|disagree/.test(explanation?.reason_category ?? "")) return fallback;
  if (guide?.retrieval?.state === "related_only" && explanation?.reason_category === "scope_too_narrow") {
    const index = guide.findings.findIndex(f => /^The specific exposure of .+ was not investigated as a separate risk factor for .+\.$/.test(f.text)
      && f.evidence_ids.length > 0 && f.source_unit_ids.length > 0
      && f.evidence_ids.every(id => explanation.evidence_ids.includes(id)));
    if (index >= 0) return {
      text: `Related ${guide.retrieval.sources.some(source => source.classification === "related_indirect") ? "research" : "information"} exists, but it does not establish this specific claim. ${plainScopeFinding(guide.findings[index].text)}`,
      references: ["retrieval.state", `findings.${index}`, ...guide.findings[index].source_unit_ids],
    };
  }
  return fallback;
}
