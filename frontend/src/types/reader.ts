import type { DocumentAssertion, DocumentCitation, DocumentReport } from "./document";
import type { AnalysisProgress } from "./api";

export type ReaderState = "completed" | "inconclusive" | "incomplete";
export interface ReaderReference {
  assertionIds: string[];
  sourceUnitIds: string[];
  fields: string[];
}
export interface ReaderSentence {
  id: string;
  text: string;
  basis: "approved_finding" | "saved_assessment" | "saved_status" | "scope_limit" | "correctness_finding";
  references: ReaderReference[];
}
export interface ReaderQuote {
  assertionId: string;
  sourceUnitId: string;
  text: string;
  use: "verified_passage" | "source_context" | "correctness_review";
}
export interface ReaderQuestion {
  id: string;
  question: string;
  answer: ReaderSentence;
  explanation: ReaderSentence[];
  assertionIds: string[];
  quotes: ReaderQuote[];
  correctnessFlag?: string;
  endpoints?: { label: string; assertionIds: string[] }[];
}
export interface ReaderContent {
  id: string;
  state?: ReaderState;
  label?: string;
  origin?: "retained_report" | "synthetic_scenario";
  originNotice?: string;
  scope: "study_reporting" | "medical_evidence" | "mixed";
  headline: ReaderSentence;
  established: ReaderSentence[];
  limitation: ReaderSentence[];
  questions: ReaderQuestion[];
  /** The complete immutable original, never a relabelled synthetic execution. */
  report: DocumentReport;
  analysis?: AnalysisProgress;
  selectedAssertionIds: string[];
}

export interface ReaderFixture extends ReaderContent {
  id: ReaderState;
  label: string;
  origin: "retained_report" | "synthetic_scenario";
  originNotice: string;
  scope: "study_reporting";
}
export interface DocumentReaderView {
  version: "reader-view-1.0";
  topics: Omit<ReaderContent, "report" | "analysis" | "origin" | "label" | "originNotice">[];
}

export function assertion(report: DocumentReport, id: string): DocumentAssertion {
  const found = report.groups.flatMap((g) => g.assertions).find((a) => a.assertion_id === id);
  if (!found) throw new Error(`Fixture reference not found: ${id}`);
  return found;
}

export function citation(report: DocumentReport, quote: ReaderQuote): DocumentCitation {
  const found = assertion(report, quote.assertionId).citations.find((c) => c.source_unit_id === quote.sourceUnitId);
  if (!found || !found.exact_text.includes(quote.text)) throw new Error("Fixture excerpt is not an exact owned citation");
  return found;
}

export function fullPassage(report: DocumentReport, unitId: string): DocumentCitation | undefined {
  return report.groups.flatMap((g) => g.sources ?? []).find((c) => c.source_unit_id === unitId);
}

/** Labels derive from actual saved records, independently of editorial wording. */
export function questionStatus(fixture: ReaderContent, question: ReaderQuestion): string {
  const records = question.assertionIds.map((id) => assertion(fixture.report, id));
  if (records.some((a) => a.status === "unavailable")) return "We couldn’t complete this check";
  if (records.some((a) => a.status === "pending")) return "Still being checked";
  if (records.some((a) => a.result_label === "not_enough_evidence")) return "Evidence is inconclusive";
  const medical = records.every((a) => a.assessment_target === "medical_evidence");
  if (records.every((a) => a.status === "completed" && a.result_label === "supported")) return medical ? "Supported by medical evidence" : "Matches the paper";
  if (records.some((a) => a.result_label === "contradicted")) return medical ? "Opposed by medical evidence" : "Does not match the paper";
  return "Background; not independently checked";
}

export function readerSentences(fixture: ReaderContent): ReaderSentence[] {
  return [fixture.headline, ...fixture.established, ...fixture.limitation,
    ...fixture.questions.flatMap((q) => [q.answer, ...q.explanation])];
}

/** Presentation trace guard. This does not qualify or relabel evidence. */
export function validateFixture(fixture: ReaderContent): void {
  for (const sentence of readerSentences(fixture)) {
    if (!sentence.text.trim() || !sentence.references.length) throw new Error("Untraced reader wording");
    for (const ref of sentence.references) {
      if (!ref.assertionIds.length || !ref.fields.length) throw new Error("Incomplete reader trace");
      const records = ref.assertionIds.map((id) => assertion(fixture.report, id));
      if (sentence.basis === "approved_finding" && records.some((a) => a.status !== "completed" || a.result_label !== "supported")) {
        throw new Error("An unavailable or inconclusive finding cannot become an approved summary fact");
      }
      if (sentence.basis === "saved_assessment" && records.some((a) => a.status !== "completed")) {
        throw new Error("An incomplete assessment cannot become a completed scientific assessment");
      }
      const allowed = new Set(records.flatMap((a) => a.citations.map((c) => c.source_unit_id)));
      if (ref.sourceUnitIds.some((id) => !allowed.has(id))) throw new Error("Reader trace crosses citation ownership");
    }
  }
  for (const question of fixture.questions) {
    question.assertionIds.forEach((id) => assertion(fixture.report, id));
    question.quotes.forEach((q) => citation(fixture.report, q));
  }
}
