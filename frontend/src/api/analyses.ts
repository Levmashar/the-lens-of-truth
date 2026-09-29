import { apiRequest } from "./client";
import type { AnalysisClaimsResponse, AnalysisInput, AnalysisProgress, AnalysisStarted, HealthResponse, ScreenshotUpload } from "../types/api";
import type { LensReport } from "../types/report";

export const PRIVACY_NOTICE_VERSION = "2026-09-01";

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/healthz", { signal });
}

export function uploadScreenshot(file: File, signal?: AbortSignal): Promise<ScreenshotUpload> {
  const body = new FormData();
  body.append("screenshot", file);
  return apiRequest<ScreenshotUpload>("/v1/analyses/uploads/screenshots", { method: "POST", body, signal }, 201);
}

export function startAnalysis(input: AnalysisInput, key: string, signal?: AbortSignal): Promise<AnalysisStarted> {
  return apiRequest<AnalysisStarted>("/v1/analyses", {
    method: "POST", signal,
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify({
      schema_version: "1.0", client: "web", lang: "auto", input,
      consent: { privacy_notice_version: PRIVACY_NOTICE_VERSION, accepted: true },
    }),
  }, 202);
}

export function getAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisProgress> {
  return apiRequest<AnalysisProgress>(`/v1/analyses/${encodeURIComponent(id)}`, { signal });
}

export function getClaims(id: string, signal?: AbortSignal): Promise<AnalysisClaimsResponse> {
  return apiRequest<AnalysisClaimsResponse>(`/v1/analyses/${encodeURIComponent(id)}/claims`, { signal });
}

export function getClaimReport(id: string, claimId: string, signal?: AbortSignal): Promise<LensReport> {
  return apiRequest<LensReport>(
    `/v1/analyses/${encodeURIComponent(id)}/claims/${encodeURIComponent(claimId)}/report`,
    { signal },
  );
}
