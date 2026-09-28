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
  raw_text: string;
  normalized_text: string | null;
  claim_type: string | null;
  risk_class: string;
  normalization_status: string;
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
}

export interface AnalysisClaimsResponse {
  analysis_id: string;
  claims: ClaimSummary[];
}
