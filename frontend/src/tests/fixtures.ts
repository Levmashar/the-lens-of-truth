import type { AnalysisClaimsResponse, AnalysisProgress, ClaimSummary, VerdictLabel } from "../types/api";
import type { LensReport } from "../types/report";

export const analysisId = "11111111-1111-4111-8111-111111111111";
export const claimId = "22222222-2222-4222-8222-222222222222";
export const claimId2 = "33333333-3333-4333-8333-333333333333";

export function claimSummary(overrides: Partial<ClaimSummary> = {}): ClaimSummary {
  return {
    claim_id: claimId, ordinal: 1, status: "completed", stage: "building_report",
    completed_stages: ["extracting", "normalizing", "retrieving", "judging", "validating", "aggregating", "building_report"],
    stage_timestamps: {}, failure_code: null, evidence_pack_id: "44444444-4444-4444-8444-444444444444",
    evidence_pack_hash: "a".repeat(64), judge_run_ids: [], judge_validation_run_ids: [],
    verdict_run_id: "55555555-5555-4555-8555-555555555555", report_run_id: "66666666-6666-4666-8666-666666666666",
    production_qualified: false, result_label: "not_enough_evidence", ...overrides,
  };
}

export function progress(overrides: Partial<AnalysisProgress> = {}): AnalysisProgress {
  return {
    analysis_id: analysisId, status: "completed", stage: "completed",
    completed_stages: ["extracting", "normalizing", "retrieving", "judging", "validating", "aggregating", "building_report"],
    stage_timestamps: {}, claim_count: 1, completed_claims: 1, failure_code: null,
    language: "auto", input_type: "text",
    claims: [{ claim_id: claimId, ordinal: 1, span_start: 0, span_end: 35,
      raw_text: "Vitamin C prevents the common cold.", normalized_text: null, claim_type: "prevention",
      population: null, intervention_or_exposure: "Vitamin C", comparator: null, outcome: "the common cold",
      timeframe: null, risk_class: "standard", verifiability: null, coreference_uncertain: false,
      resolved_from_span_start: null, resolved_from_span_end: null, entities: [], pico: null,
      normalization_status: "normalized", normalization_quality: null }],
    screenshot_ocr: null, updated_at: "2026-09-28T10:00:00Z", ...overrides,
  };
}

export function summaries(claims: ClaimSummary[] = [claimSummary()]): AnalysisClaimsResponse {
  return { analysis_id: analysisId, claims };
}

export function report(verdict: VerdictLabel = "not_enough_evidence", overrides: Partial<LensReport> = {}): LensReport {
  return {
    report_version: "1.0", verdict_run_id: "55555555-5555-4555-8555-555555555555",
    claim: { text: "Vitamin C prevents the common cold.", claim_type: "prevention" },
    verdict, verdict_display: "Backend supplied display label", headline: "Evidence remains inconclusive.",
    short_summary: "The validated evidence does not justify a decisive result.",
    why_this_result: [{ code: "fixture_reason", text: "Backend-provided explanation." }],
    key_evidence: [{ evidence_id: "E1", pmid: "12345", doi: null, title: "Clinical study title",
      journal: null, publication_date: null, study_design: "unknown", integrity_status: "unknown",
      evidence_roles: ["relevant_but_insufficient"], exact_excerpt: "Exact frozen excerpt <script>alert(1)</script>",
      excerpt_truncated: false, passage_sha256: "c".repeat(64), passage_section: "ABSTRACT",
      source_url: "https://pubmed.ncbi.nlm.nih.gov/12345/", citation_validated: true,
      cited_by_judge_run_ids: [], cited_by_validation_run_ids: [], limitations: [] }],
    evidence_limitations: ["Association does not establish causation."],
    judge_summary: { qualified: 2, excluded: 1, validated_label_counts: { not_enough_evidence: 2 },
      description: "Two assessments were fully validated.", excluded_assessments: [] },
    verification_status: { evidence_state: "relevant_but_insufficient", validated_citations_shown: 1,
      production_qualified: false, development_notice: "Development evaluation only; not qualified for public release." },
    sources: [{ evidence_id: "E1", pmid: "12345", doi: null, url: "https://pubmed.ncbi.nlm.nih.gov/12345/" }],
    safety_notice: "This is public health information, not individual treatment advice.",
    production_qualified: false,
    provenance: { report_version: "1.0", verdict_run_id: "55555555-5555-4555-8555-555555555555",
      verdict_policy_version: "verdict-policy-1.0", verdict_semantic_hash: "d".repeat(64),
      evidence_pack_version: "1.3", evidence_pack_id: "44444444-4444-4444-8444-444444444444",
      evidence_pack_hash: "a".repeat(64),
      judge_run_ids: [], judge_validation_run_ids: [], report_builder_version: "report-builder-1.0",
      generated_at: "2026-09-28T10:00:00Z", production_qualified: false },
    semantic_hash: "b".repeat(64), ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}
