export type HealthResponse = {
  status: "ok";
  service: string;
  environment: string;
  request_id: string;
};

export type CreateAnalysisResponse = {
  analysis_id: string;
  status: "processing";
  is_mock: true;
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}.`);
  }
  return (await response.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/healthz`);
  return parseJson<HealthResponse>(response);
}

export async function createMockAnalysis(text: string): Promise<CreateAnalysisResponse> {
  const response = await fetch(`${apiBaseUrl}/v1/analyses`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      schema_version: "1.0",
      client: "web",
      lang: "auto",
      input: { type: "text", text },
      consent: { privacy_notice_version: "2026-09-01", accepted: true },
    }),
  });
  return parseJson<CreateAnalysisResponse>(response);
}
