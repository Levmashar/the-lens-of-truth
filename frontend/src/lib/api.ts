export type HealthResponse = {
  status: "ok";
  service: string;
  environment: string;
  request_id: string;
};

export type ScreenshotUploadResponse = {
  upload_id: string;
  status: "uploaded";
  media_type: "image/png";
  byte_count: number;
  width: number;
  height: number;
  purge_after: string;
};

export type CreateAnalysisResponse = {
  analysis_id: string;
  status: "claims_extracted";
  claim_count: number;
};

export type AnalysisClaim = {
  claim_id: string;
  ordinal: number;
  span_start: number | null;
  span_end: number | null;
  raw_text: string;
  normalized_text: string | null;
  claim_type: string | null;
  risk_class: string;
  verifiability: number | null;
  coreference_uncertain: boolean;
  resolved_from_span_start: number | null;
  resolved_from_span_end: number | null;
};

export type AnalysisDetail = {
  analysis_id: string;
  status: "claims_extracted";
  language: string;
  input_type: "text" | "screenshot";
  claims: AnalysisClaim[];
  screenshot_ocr: {
    provider: string;
    confidence: number | null;
    pii_redaction_count: number;
  } | null;
  updated_at: string;
};

type ErrorPayload = {
  error?: {
    code?: string;
    message?: string;
  };
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message);
  }
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
    throw new ApiError(
      payload.error?.message ?? `Request failed with status ${response.status}.`,
      payload.error?.code,
    );
  }
  return (await response.json()) as T;
}

function analysisRequest(input: { type: "text"; text: string } | { type: "screenshot"; uploadId: string }) {
  return {
    schema_version: "1.0",
    client: "web",
    lang: "auto",
    input:
      input.type === "text"
        ? { type: "text", text: input.text }
        : { type: "screenshot", upload_id: input.uploadId },
    consent: { privacy_notice_version: "2026-09-01", accepted: true },
  };
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/healthz`);
  return parseJson<HealthResponse>(response);
}

export async function uploadScreenshot(file: File): Promise<ScreenshotUploadResponse> {
  const form = new FormData();
  form.append("screenshot", file);
  const response = await fetch(`${apiBaseUrl}/v1/analyses/uploads/screenshots`, {
    method: "POST",
    body: form,
  });
  return parseJson<ScreenshotUploadResponse>(response);
}

export async function createAnalysis(
  input: { type: "text"; text: string } | { type: "screenshot"; uploadId: string },
): Promise<CreateAnalysisResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/analyses`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(analysisRequest(input)),
  });
  return parseJson<CreateAnalysisResponse>(response);
}

export async function getAnalysis(analysisId: string): Promise<AnalysisDetail> {
  const response = await fetch(`${apiBaseUrl}/v1/analyses/${analysisId}`);
  return parseJson<AnalysisDetail>(response);
}
