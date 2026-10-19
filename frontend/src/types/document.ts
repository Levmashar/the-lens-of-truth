import type { VerdictLabel } from "./api";
import type { DocumentReaderView } from "./reader";

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
  excerpt?: string;
  excerpt_start?: number;
  excerpt_end?: number;
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
  heading?: string;
  assessment_target?: "reporting_fidelity" | "medical_evidence";
  association_caveat?: string | null;
  display_parent_group_id?: string | null;
  reason_codes?: string[];
  field_diagnostics?: { field: string; statuses: string[]; source_unit_ids: string[]; source_quantity_ids: string[] }[];
}

export interface DocumentGroup {
  group_id: string;
  title: string;
  status: string;
  source_match: {
    status: "identified" | "uncertain" | "not_found" | "pending" | "failed" | "not_applicable";
    search_state?: "pending" | "searched" | "failed" | "not_applicable";
    title: string | null;
    url: string | null;
    reason: string;
    candidates: { title: string; url: string | null; reason: string }[];
    discrepancies: string[];
  };
  assertions: DocumentAssertion[];
  counts?: DocumentCounts;
  sources?: DocumentCitation[];
  display_parent_group_id?: string | null;
  processing_status?: string;
}

export interface DocumentCounts {
  total: number; assessed: number; unavailable: number; background: number; pending: number; processed: number;
}

export interface DocumentSummaryLine {
  text: string; assertion_ids: string[]; group_ids: string[];
  evidence: { assertion_id: string; group_id: string; source_unit_ids: string[] }[];
  explanation?: string;
  status?: string;
  result_label?: VerdictLabel;
  assessment_target?: string;
}

export interface DocumentProgress {
  groups_total: number;
  groups_completed: number;
  assertions_total: number;
  assertions_completed: number;
}

/** A server-owned projection of frozen, validated document results. */
export interface DocumentReport {
  reader_view?: DocumentReaderView;
  version: "document-report-1.0" | "document-report-1.1" | "document-report-1.2" | "document-report-1.3";
  analysis_id: string;
  status: string;
  production_qualified: boolean;
  groups: DocumentGroup[];
  progress: DocumentProgress;
  debug_group_runs?: unknown;
  completion_text?: string;
  reading_summary?: { main_takeaway: DocumentSummaryLine[]; attention: DocumentSummaryLine[];
    matches: DocumentSummaryLine[]; limits: DocumentSummaryLine[] };
}
