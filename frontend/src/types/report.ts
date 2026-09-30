import type { VerdictLabel } from "./api";

export interface ReportReason { code: string; text: string }

export interface SourceCard {
  evidence_id: string;
  pmid: string;
  doi: string | null;
  title: string;
  journal: string | null;
  publication_date: string | null;
  study_design: string;
  integrity_status: string;
  evidence_roles: ("supporting" | "opposing" | "relevant_but_insufficient")[];
  exact_excerpt: string;
  excerpt_truncated: boolean;
  passage_sha256: string;
  passage_section: string;
  source_url: string;
  citation_validated: boolean;
  cited_by_judge_run_ids: string[];
  cited_by_validation_run_ids: string[];
  limitations: string[];
}

export interface LensReport {
  report_version: string;
  verdict_run_id: string;
  claim: { text: string; claim_type: string | null };
  verdict: VerdictLabel;
  verdict_display: string;
  headline: string;
  short_summary: string;
  why_this_result: ReportReason[];
  key_evidence: SourceCard[];
  neutral_retrieved_sources?: {
    evidence_id: string; pmid: string; doi: string | null; title: string;
    publication_date: string | null; passage_section: string;
    exact_excerpt: string; excerpt_truncated: boolean;
    passage_sha256: string; source_url: string;
  }[];
  evidence_limitations: string[];
  judge_summary: {
    qualified: number;
    excluded: number;
    validated_label_counts: Partial<Record<"supported" | "contradicted" | "not_enough_evidence", number>>;
    description: string;
    excluded_assessments: { judge_run_id: string; slot: number; reasons: ReportReason[] }[];
  };
  verification_status: {
    evidence_state: string;
    validated_citations_shown: number;
    production_qualified: boolean;
    development_notice: string | null;
  };
  sources: { evidence_id: string; pmid: string; doi: string | null; url: string }[];
  safety_notice: string;
  production_qualified: boolean;
  provenance: {
    report_version: string;
    verdict_run_id: string;
    verdict_policy_version: string;
    verdict_semantic_hash: string;
    evidence_pack_version: string;
    evidence_pack_id: string;
    evidence_pack_hash: string;
    judge_run_ids: string[];
    judge_validation_run_ids: string[];
    report_builder_version: string;
    generated_at: string;
    production_qualified: boolean;
  };
  semantic_hash: string;
}
