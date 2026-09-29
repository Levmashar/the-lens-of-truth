export type AnalysisStatus = "queued" | "running" | "completed" | "partially_completed" | "failed";
export type ClaimStatus = "queued" | "running" | "completed" | "failed";
export type VerdictLabel = "supported" | "contradicted" | "not_enough_evidence" | "unable_to_verify_reliably";

export interface ApiErrorPayload {
  error?: { code?: string; message?: string; request_id?: string };
}

export interface HealthResponse {
  status: "ok";
  service: string;
  environment: string;
  debug_enabled: boolean;
  request_id: string;
}

export interface ScreenshotUpload {
  upload_id: string;
  status: "uploaded";
  media_type: "image/png";
  byte_count: number;
  width: number;
  height: number;
  purge_after: string;
}

export type AnalysisInput = { type: "text"; text: string } | { type: "screenshot"; upload_id: string };

export interface AnalysisStarted {
  analysis_id: string;
  status: AnalysisStatus;
  stage: string;
  claim_count: number;
  completed_claims: number;
}

export interface AnalysisClaim {
  claim_id: string;
  ordinal: number;
  span_start: number | null;
  span_end: number | null;
  raw_text: string;
  normalized_text: string | null;
  claim_type: string | null;
  population: string | null;
  intervention_or_exposure: string | null;
  comparator: string | null;
  outcome: string | null;
  timeframe: string | null;
  risk_class: string;
  verifiability: number | null;
  coreference_uncertain: boolean;
  resolved_from_span_start: number | null;
  resolved_from_span_end: number | null;
  entities: MedicalEntity[];
  pico: {
    original_claim: string;
    population: string | null;
    intervention_or_exposure: string | null;
    comparator: string | null;
    outcome: string | null;
    timeframe: string | null;
    claim_type: string | null;
  } | null;
  normalization_status: string;
  normalization_quality: {
    normalization_coverage: number | null;
    missing_explicit_concepts: string[];
    required_slots_missing: string[];
    ambiguous_concepts: string[];
    normalization_warnings: string[];
    terminology_version: string | null;
    terminology_sha256: string | null;
  } | null;
}

export interface MedicalEntity {
  surface_text: string;
  entity_type: "population" | "intervention_or_exposure" | "comparator" | "outcome" | "disease" | "drug" | "measurement" | "other";
  umls_cui: string | null;
  umls_version: string | null;
  mesh_id: string | null;
  preferred_name: string | null;
  confidence: number | null;
  match_type: "exact" | "synonym" | "fuzzy" | "unresolved";
  ambiguous: boolean;
  terminology_source: "mesh" | "umls" | null;
  terminology_version: string | null;
  terminology_sha256: string | null;
  tree_numbers: string[];
  candidates: {
    mesh_id: string; preferred_name: string; match_type: "exact" | "synonym" | "fuzzy" | "unresolved";
    confidence: number; terminology_source: "mesh"; terminology_version: string;
    terminology_sha256: string | null; tree_numbers: string[];
  }[];
}

export interface AnalysisProgress {
  analysis_id: string;
  status: AnalysisStatus | "claims_extracted";
  stage?: string;
  completed_stages?: string[];
  stage_timestamps?: Record<string, { started_at?: string; completed_at?: string }>;
  claim_count?: number;
  completed_claims?: number;
  failure_code?: string | null;
  language: string | null;
  input_type: "text" | "screenshot" | null;
  claims: AnalysisClaim[];
  screenshot_ocr: { provider: string; confidence: number | null; pii_redaction_count: number } | null;
  updated_at: string;
  debug_enabled?: boolean;
  debug_models?: DebugModelStatus[] | null;
  debug_events?: DebugModelEvent[] | null;
}

export interface DebugModelStatus {
  role: string;
  provider: string;
  model: string;
  status: string;
  failure_type: string | null;
}

export interface DebugModelEvent {
  role: string;
  provider: string;
  model: string;
  attempt: number;
  status: string;
  failure_type: string | null;
  http_status: number | null;
  elapsed_ms: number;
  response_excerpt: string | null;
}

export interface DebugJudgeRun {
  slot: number;
  provider: string;
  model: string;
  model_family: string;
  outcome_status: string;
  error_category: string | null;
  attempt_count: number;
  latency_ms: number;
  validation_status: string | null;
  validation_error_category: string | null;
}

export interface ClaimSummary {
  claim_id: string;
  ordinal: number;
  status: ClaimStatus;
  stage: string;
  completed_stages: string[];
  stage_timestamps: Record<string, { started_at?: string; completed_at?: string }>;
  failure_code: string | null;
  evidence_pack_id: string | null;
  evidence_pack_hash: string | null;
  judge_run_ids: string[];
  judge_validation_run_ids: string[];
  verdict_run_id: string | null;
  report_run_id: string | null;
  production_qualified: boolean | null;
  result_label: VerdictLabel | null;
  debug_judge_runs?: DebugJudgeRun[] | null;
}

export interface AnalysisClaimsResponse {
  analysis_id: string;
  claims: ClaimSummary[];
}
