import { ApiError, parseApiError } from "./errors";
import type { ApiErrorPayload } from "../types/api";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function apiRequest<T>(path: string, options: RequestInit = {}, expectedStatus?: number): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { cache: "no-store", ...options });
  if (!response.ok) {
    const raw: unknown = await response.json().catch(() => ({}));
    const payload = raw && typeof raw === "object" ? raw as ApiErrorPayload : {};
    throw parseApiError(response.status, payload);
  }
  if (expectedStatus !== undefined && response.status !== expectedStatus) {
    throw new ApiError(502, "unexpected_response", "The service returned an unexpected response.");
  }
  return await response.json() as T;
}
