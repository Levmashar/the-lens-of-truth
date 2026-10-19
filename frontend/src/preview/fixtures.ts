import incompleteRaw from "./fixtures/incomplete.json?raw";
import historicalRaw from "./fixtures/historical.json?raw";
import analysisRaw from "./fixtures/incomplete-analysis.json?raw";
import type { DocumentReport } from "../types/document";
import type { AnalysisProgress } from "../types/api";
import { assertion, validateFixture, type ReaderFixture, type ReaderSentence, type ReaderQuote } from "./model";

const incomplete = JSON.parse(incompleteRaw) as DocumentReport;
const historical = JSON.parse(historicalRaw) as DocumentReport;
const analysis = JSON.parse(analysisRaw) as AnalysisProgress;

function line(id: string, text: string, ids: string[], basis: ReaderSentence["basis"] = "saved_status",
  units: string[] = [], fields = ["status", "result_label", "explanation"]): ReaderSentence {
  return { id, text, basis, references: [{ assertionIds: ids, sourceUnitIds: units, fields }] };
}
function quote(report: DocumentReport, aid: string, uid: string, literal?: string,
  use: ReaderQuote["use"] = "verified_passage"): ReaderQuote {
  const source = assertion(report, aid).citations.find((c) => c.source_unit_id === uid);
  if (!source) throw new Error("Missing fixture citation");
  return { assertionId: aid, sourceUnitId: uid, text: literal ?? source.excerpt ?? source.exact_text, use };
}
const studyQuestion = {
  id: "study", question: "Did we find the study described?", assertionIds: ["A1", "A2"],
  answer: line("study-answer", "Yes. Its size and subject match the description.", ["A1", "A2"], "approved_finding", ["E202.U1"], ["status", "citations", "source_match"]),
  explanation: [line("study-explanation", "The paper used UK Biobank data and included 472,672 people in its skin-cancer analysis.",
    ["A1"], "approved_finding", ["E202.U1"], ["citations.exact_text"])],
  quotes: [quote(incomplete, "A1", "E202.U1")],
};
const incompleteFixture: ReaderFixture = {
  id: "incomplete", label: "Incomplete · Saved report", origin: "retained_report", scope: "study_reporting",
  originNotice: "Saved report from 13 October 2026. No new analysis was run. All original outcomes are preserved.",
  report: incomplete, analysis, selectedAssertionIds: ["A1", "A2", "A3", "A4", "A5", "A6", "A10"],
  headline: line("incomplete-title", "We found the study, but couldn’t finish checking its main claims.", ["A1", "A2", "A3", "A4", "A5"]),
  established: [
    line("incomplete-study", "The paragraph refers to a UK Biobank paper involving more than 470,000 people.", ["A1", "A2"], "approved_finding", ["E202.U1"], ["citations", "source_match"]),
    line("incomplete-unfinished", "We confirmed its size and subject, but this run did not finish verifying the claims about higher skin-cancer rates, including the “292% increase.”", ["A1", "A2", "A3", "A4", "A5"]),
  ],
  limitation: [
    line("incomplete-adjustment", "The claim about other risk factors also needs review.", ["A6"], "correctness_finding", ["E203.U1"], ["citations.exact_text", "field_diagnostics", "correctness finding: joint adjustment not established"]),
    line("incomplete-status", "This is an incomplete check, not a conclusion that those claims are true or false.", ["A3", "A4", "A5"]),
    line("incomplete-scope", "It should not be read as confirmation that sunscreen causes cancer.", ["A3", "A4", "A5"], "scope_limit", [], ["status", "assessment_target", "association_caveat"]),
    line("incomplete-next", "You can read the study and see the evidence already available, alongside the checks that remain unfinished.", ["A1", "A3", "A4", "A5"], "scope_limit", [], ["citations", "source_match.url", "status"]),
  ],
  questions: [studyQuestion, {
    id: "rates", question: "Did it report higher cancer rates among sunscreen users?", assertionIds: ["A3", "A5"],
    answer: line("rates-answer", "This run did not finish verifying the higher-rate claims.", ["A3", "A5"]),
    explanation: [line("rates-explanation", "Relevant passages were found, but the specific claims about higher rates did not complete validation. The separate broad association summary does not complete these checks.", ["A3", "A5", "A10"] )],
    endpoints: [{ label: "Higher skin-cancer risk", assertionIds: ["A3"] }, { label: "Basal-cell and squamous-cell carcinoma rates", assertionIds: ["A5"] }],
    quotes: [quote(incomplete, "A3", "E205.U1", "BCC was positively correlated with male sex (RR=1.23) and frequent use of sunscreen (RR=2.40); and inversely correlated with light olive, dark olive or brown skin (RR=0.47~0.50), ease of tanning (RR=0.66), dark brown hair (RR=0.5), and older than expected appearance (RR = 0.79).", "source_context")],
  }, {
    id: "number", question: "What does the 292% figure mean?", assertionIds: ["A4"],
    answer: line("number-answer", "The claimed increase was not verified in this run.", ["A4"]),
    explanation: [line("number-explanation", "A partial validated check flagged a problem with interpreting the statistic as an increase in disease probability. The full check remains incomplete; a number appearing in the paper is not enough to confirm the paragraph’s interpretation.", ["A4"], "saved_status", ["E205.U1", "E203.U1"], ["status", "partial_detail", "citations"] )],
    quotes: [quote(incomplete, "A4", "E205.U1", undefined, "source_context")],
  }, {
    id: "adjustment", question: "Were other risk factors accounted for?", assertionIds: ["A6"],
    answer: line("adjustment-answer", "Saved as matching the paper, but the evidence needs review.", ["A6"], "correctness_finding", ["E203.U1"], ["status", "result_label", "citations", "correctness finding"]),
    explanation: [line("adjustment-explanation", "The cited methods say analysis was performed “for each predictor variable.” That does not establish that the sunscreen estimate accounts for all the named factors together. It also does not prove that no adjustment occurred. The saved result has not been changed.", ["A6"], "correctness_finding", ["E203.U1"], ["citations.exact_text", "field_diagnostics", "correctness finding: joint adjustment not established"])],
    correctnessFlag: "Correctness issue flagged · Saved result unchanged",
    quotes: [quote(incomplete, "A6", "E203.U1", "The relevel function was used to select the healthy control group as the baseline outcome group, and analysis was performed using the multinom function for each predictor variable.", "correctness_review")],
  }],
};

const completed: ReaderFixture = {
  id: "completed", label: "Completed · Synthetic fixture", origin: "synthetic_scenario", scope: "study_reporting",
  originNotice: "Uses the saved, completed study-description checks only. This is not a completed execution of the full paragraph.",
  report: incomplete, analysis, selectedAssertionIds: ["A1", "A2"],
  headline: line("complete-title", "The paper matches the study description.", ["A1", "A2"], "approved_finding"),
  established: [
    line("complete-size", "The study we found used UK Biobank data and included 472,672 people.", ["A1"], "approved_finding", ["E202.U1"], ["citations.exact_text"]),
    line("complete-subject", "That confirms the paragraph’s description of a study involving more than 470,000 participants and examining sunscreen use and skin cancer.", ["A1", "A2"], "approved_finding", ["E202.U1", "E205.U1"], ["status", "citations", "text"]),
  ],
  limitation: [
    line("complete-scope", "This preview focuses on the study’s identity, size and subject; it does not cover the paragraph’s claims about higher cancer rates or the “292% increase.”", ["A1", "A2", "A3", "A4"], "scope_limit", [], ["selectedAssertionIds", "text", "status"]),
    line("complete-medical", "Matching a paper’s description is different from showing that sunscreen causes cancer.", ["A1", "A2"], "scope_limit", [], ["assessment_target", "medical_interpretation"]),
    line("complete-next", "Read the original study below, or open the evidence to see the exact passages behind these checks.", ["A1", "A2"], "scope_limit", [], ["citations", "source_match.url"]),
  ],
  questions: [studyQuestion, {
    id: "subject", question: "Did the paper examine sunscreen use and skin cancer?", assertionIds: ["A2"],
    answer: line("subject-answer", "Yes. That matches the paper’s subject.", ["A2"], "approved_finding"),
    explanation: [line("subject-explanation", "The completed reporting check confirms that the study examined demographic and environmental factors, including sunscreen use, in relation to skin-cancer groups.", ["A2"], "approved_finding", ["E205.U1"], ["status", "citations.exact_text"])],
    quotes: [quote(incomplete, "A2", "E205.U1", "Using multinomial logistic regression(23), we computed ratios corresponding to skin cancer risk for each of our chosen demographic and environmental variables, using our four disease groups as outcome variables.")],
  }],
};

const inconclusive: ReaderFixture = {
  id: "inconclusive", label: "Unresolved · Synthetic fixture", origin: "synthetic_scenario", scope: "study_reporting",
  originNotice: "Assembled from completed checks in the saved 8 October report. The full original report remains unchanged in the advanced view; this is not a new execution.",
  report: historical, selectedAssertionIds: ["A1", "A2", "A4", "A6"],
  headline: line("mixed-title", "The paper was found. Its headline risk claim remains unresolved.", ["A1", "A2", "A4"], "saved_assessment"),
  established: [
    line("mixed-finding", "The study’s size and subject match the paragraph, but the completed check did not establish the claimed “292% increase” as an increase in someone’s chance of developing invasive melanoma.", ["A1", "A2", "A4"], "saved_assessment"),
  ],
  limitation: [
    line("mixed-uncertainty", "The numeric result’s meaning remains unresolved, and the saved checks also disagree about the claim that other risk factors were accounted for.", ["A4", "A6"], "saved_assessment", [], ["explanation", "reason_codes", "result_label"]),
    line("mixed-finished", "Those are unresolved findings, rather than an interrupted check, for the details shown in this scenario.", ["A4", "A6"], "saved_assessment"),
    line("mixed-scope", "This checks how accurately the paragraph describes the paper. It does not establish that sunscreen causes cancer, and the large participant count cannot resolve the disputed interpretation.", ["A1", "A4", "A6"], "scope_limit", [], ["assessment_target", "association_caveat", "result_label"]),
    line("mixed-next", "Open the evidence to see where the explanation becomes uncertain.", ["A4", "A6"], "scope_limit", [], ["explanation", "citations"]),
  ],
  questions: [{ ...studyQuestion,
    answer: line("mixed-study-answer", "Yes. Its size and subject match the description.", ["A1", "A2"], "approved_finding"),
    explanation: [line("mixed-study-explanation", "The saved checks confirmed the UK Biobank study’s size and subject.", ["A1", "A2"], "approved_finding")],
    quotes: [quote(historical, "A1", "E166.U1")],
  }, {
    id: "number", question: "What does the 292% figure mean?", assertionIds: ["A4"],
    answer: line("mixed-number-answer", "The percentage interpretation remains unresolved.", ["A4"], "saved_assessment"),
    explanation: [line("mixed-number-explanation", "The completed check found that the cited statistical measure was not established as comparable to the paragraph’s risk-increase claim. The number alone cannot confirm the claimed change in disease probability.", ["A4"], "saved_assessment", [], ["reason_codes", "explanation", "numeric_detail"])],
    quotes: [quote(historical, "A4", "E169.U1")],
  }, {
    id: "adjustment", question: "Were other risk factors accounted for?", assertionIds: ["A6"],
    answer: line("mixed-adjustment-answer", "The completed checks disagree.", ["A6"], "saved_assessment"),
    explanation: [line("mixed-adjustment-explanation", "The saved assessment did not settle whether the paragraph’s adjustment claim matches the paper. Listing variables is not the same as showing that the sunscreen estimate accounts for all of them together; uncertainty is not proof that no adjustment occurred.", ["A6"], "saved_assessment", [], ["reason_codes", "explanation", "field_diagnostics"])],
    quotes: [quote(historical, "A6", "E167.U1")],
  }],
};

export const readerFixtures = [completed, inconclusive, incompleteFixture];
readerFixtures.forEach(validateFixture);
