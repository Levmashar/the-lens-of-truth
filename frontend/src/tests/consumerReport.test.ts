// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { createClaimResult } from "../components/claimResult";
import { claimQuestion } from "../utils/readerPresentation";
import { analysisId, claimId, report } from "./fixtures";
import type { ReportReadingGuide } from "../types/report";

function scopeCase() {
  const saved = report("not_enough_evidence", { claim: {
    text: "Using your phone while laying down on your side, increases deterioration of myopia.", claim_type: "causal" },
    verdict_explanation: { version: "1.0", summary: "The evidence covers a narrower scope.",
      reason_category: "scope_too_narrow", established: null, unresolved: "Scope not established.", evidence_ids: ["E1"] } });
  const guide: ReportReadingGuide = { version: "report-reading-guide-1.0", verdict_run_id: saved.verdict_run_id,
    report_semantic_hash: saved.semantic_hash, findings: [{
      text: "The specific exposure of lateral recumbent phone use was not investigated as a separate risk factor for myopia progression.",
      evidence_ids: ["E1"], source_unit_ids: ["E1.U1"] }], highlights: [],
    retrieval: { version: "retrieval-coverage-2.0", state: "related_only", explanation: "Related sources have narrower scope.", sources: [
      { title: "Related study", url: "https://pubmed.ncbi.nlm.nih.gov/12345/", classification: "related_indirect", missing_qualifiers: ["exposure:side"] },
    ] } };
  return { saved, guide };
}

describe("consumer report fidelity", () => {
  it("uses only an approved, referenced finding for a generic decisive summary", () => {
    const { guide } = scopeCase();
    const saved = report("supported", { claim: { text: "Smoking causes lung cancer.", claim_type: "causal" },
      verdict_explanation: { version: "1.0", summary: "Multiple validated assessments found evidence supporting the claim at its stated scope.",
        reason_category: "supported_by_validated_evidence", established: null, unresolved: null, evidence_ids: ["E1"] } });
    guide.findings = [
      { text: "Smoking causes lung cancer.", evidence_ids: ["UNAPPROVED"], source_unit_ids: ["UNAPPROVED.U1"] },
      { text: "Cigarette smoking is a cause of lung cancer according to the checked assessment.", evidence_ids: ["E1"], source_unit_ids: ["E1.U1"] },
    ];
    const node = createClaimResult(saved, analysisId, claimId, false, guide);
    expect(node.querySelector(".verdict-summary")?.textContent).toBe(guide.findings[1].text);
    expect(node.querySelector(".verdict-summary")?.getAttribute("data-report-references")).toContain("findings.1");
    saved.verdict_explanation!.summary += " The conclusion applies to the tested comparison.";
    expect(createClaimResult(saved, analysisId, claimId, false, guide).querySelector(".verdict-summary")?.textContent)
      .toBe(saved.verdict_explanation!.summary);
  });
  it("explains a specific missing exposure from an approved, hash-matched finding", () => {
    const { saved, guide } = scopeCase();
    const before = JSON.stringify(saved);
    const node = createClaimResult(saved, analysisId, claimId, true, guide);
    const answer = node.querySelector(".consumer-answer")!;
    expect(answer.textContent).toContain("Related research exists");
    expect(answer.textContent).toContain("using a phone while lying on your side");
    expect(answer.textContent).toContain("how quickly short-sightedness gets worse");
    expect(answer.textContent).not.toMatch(/E1|qualified|judge|narrower scope/);
    expect(node.querySelector(".verdict-summary")?.getAttribute("data-report-references")).toContain("E1.U1");
    expect(node.querySelector(".consumer-evidence")?.hasAttribute("open")).toBe(false);
    expect(node.querySelector(".qualification-notice")?.closest("details")).toBeNull();
    expect(node.querySelector(".qualification-notice")?.textContent).toContain("could not be verified");
    expect(node.querySelector(".original-claim")?.textContent).toBe(saved.claim.text);
    expect(JSON.stringify(saved)).toBe(before);
  });

  it("never lets an unbound guide or a retrieval gap override scientific conflict", () => {
    const { saved, guide } = scopeCase();
    const mismatch = createClaimResult(saved, analysisId, claimId, false, { ...guide, report_semantic_hash: "wrong" });
    expect(mismatch.querySelector(".verdict-summary")?.textContent).toBe(saved.verdict_explanation?.summary);
    const conflict = { ...saved, verdict_explanation: { ...saved.verdict_explanation!,
      reason_category: "conflicting_evidence", summary: "Comparable findings point in different directions." } };
    const node = createClaimResult(conflict, analysisId, claimId, false, guide);
    expect(node.querySelector(".verdict-summary")?.textContent).toBe(conflict.verdict_explanation.summary);
    expect(node.dataset.verdict).toBe("not_enough_evidence");
    expect(node.querySelector(".verdict-label")?.textContent).not.toContain("contradicts");
  });

  it("retains operational warnings without relabelling an NEI assessment", () => {
    const { saved, guide } = scopeCase();
    guide.retrieval!.state = "search_incomplete";
    const node = createClaimResult(saved, analysisId, claimId, false, guide);
    expect(node.dataset.verdict).toBe("not_enough_evidence");
    expect(node.querySelector(".consumer-search-warning")?.closest("details")).toBeNull();
    expect(node.querySelector(".consumer-search-warning")?.textContent).toContain("could not be completed");
    const unable = createClaimResult(report("unable_to_verify_reliably"), analysisId, claimId);
    expect(unable.querySelector(".verdict-summary")?.textContent).toContain("unfinished check");
  });

  it("opens the owning source before a citation receives keyboard focus", () => {
    const { saved, guide } = scopeCase();
    const node = createClaimResult(saved, analysisId, claimId, true, guide);
    document.body.append(node);
    (node.querySelector(".finding-citation") as HTMLAnchorElement).click();
    expect(node.querySelector<HTMLDetailsElement>(".consumer-evidence")?.open).toBe(true);
    expect(node.querySelector<HTMLDetailsElement>(".consumer-source")?.open).toBe(true);
    expect(document.activeElement?.id).toBe(`source-${claimId}-E1`);
    node.remove();
  });

  it.each([
    ["Smoking causes lung cancer.", "Does smoking cause lung cancer?"],
    ["Smoking does not cause lung cancer.", "Is it true that smoking does not cause lung cancer?"],
    ["Antibiotics can treat bacterial pneumonia.", "Can antibiotics treat bacterial pneumonia?"],
    ["Vaccines cause autism.", "Do vaccines cause autism?"],
    ["Persistent high-risk HPV infection can cause cervical cancer.", "Can persistent high-risk HPV infection cause cervical cancer?"],
  ])("keeps the meaning when questioning %s", (claim, question) => expect(claimQuestion(claim)).toBe(question));

  it("preserves all details in a long, multi-sentence claim", () => {
    const text = "This study followed 470,000 participants for many years. It reported higher risks in one group after an observational analysis.";
    const node = createClaimResult(report("not_enough_evidence", { claim: { text, claim_type: "causal" } }), analysisId, claimId);
    expect(node.querySelector(".claim-question")?.textContent).toContain("470,000 participants");
    expect(node.querySelector(".claim-question")?.textContent).toContain("observational analysis");
    expect(node.querySelector(".original-claim")?.textContent).toBe(text);
  });
});
