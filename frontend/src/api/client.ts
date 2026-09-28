import { parseApiError } from "./errors";
import type { ApiErrorPayload } from "../types/api";

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { cache: "no-store", ...options });
  } catch (error) {
    // Keep AbortError recognizable to polling/navigation cleanup.
    throw error;
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as ApiErrorPayload;
    throw parseApiError(response.status, payload);
  }
  return await response.json() as T;
}
