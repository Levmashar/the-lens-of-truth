import type { VerdictLabel } from "./api";

export interface DocumentAssessment {
  result_label: VerdictLabel | null;
  explanation: string;
}

export interface DocumentCitation {
  evidence_id: string;
  source_unit_id: string;
  title: string;
  url: string;
  exact_text: string;
  section: string;
}

export interface DocumentAssertion {
  assertion_id: string;
  text: string;
  kind: string;
  status: "pending" | "completed" | "unavailable" | "not_checkable" | "duplicate";
  result_label: VerdictLabel | null;
  explanation: string;
  source_reports?: string | null;
  reporting_fidelity?: DocumentAssessment | null;
  medical_interpretation?: DocumentAssessment | null;
  interpretation_limits: string[];
  citations: DocumentCitation[];
  source_spans: { start: number; end: number; text: string }[];
  duplicate_of?: string | null;
}

export interface DocumentGroup {
  group_id: string;
  title: string;
  status: string;
  source_match: {
    status: "identified" | "uncertain" | "not_found";
    title: string | null;
    url: string | null;
    reason: string;
    candidates: { title: string; url: string | null; reason: string }[];
    discrepancies: string[];
  };
  assertions: DocumentAssertion[];
}

export interface DocumentProgress {
  groups_total: number;
  groups_completed: number;
  assertions_total: number;
  assertions_completed: number;
}

/** A server-owned projection of frozen, validated document results. */
export interface DocumentReport {
  version: "document-report-1.0";
  analysis_id: string;
  status: string;
  production_qualified: boolean;
  groups: DocumentGroup[];
  progress: DocumentProgress;
  debug_group_runs?: unknown;
}
