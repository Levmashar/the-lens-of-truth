import type { ApiErrorPayload } from "../types/api";

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const messages: Record<string, string> = {
  request_validation_failed: "Please check the information you entered.",
  invalid_idempotency_key: "The submission could not be started. Please try again.",
  idempotency_conflict: "This request key was used for different content. Start a new verification.",
  idempotency_key_expired: "This submission has expired. Start a new verification.",
  analysis_not_found: "This analysis is no longer available.",
  report_not_found: "The report is not available yet.",
  report_not_qualified: "This analysis completed, but the report does not meet the current release qualification requirements.",
  screenshot_too_large: "The screenshot is too large. Choose a smaller image.",
  upload_too_large: "The screenshot is too large. Choose a smaller image.",
  unsupported_image: "Choose a PNG, JPEG, or WebP screenshot.",
  ocr_no_text: "We couldn't read enough text from this screenshot.",
  ocr_empty: "We couldn't read enough text from this screenshot.",
  no_claims_extracted: "No checkable medical claims were identified in this content.",
  worker_interrupted: "The analysis was interrupted. Start a new verification.",
};

export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Could not reach the service. Check your connection and try again.";
  if (messages[error.code]) return messages[error.code];
  if (error.status === 403) return messages.report_not_qualified;
  if (error.status === 404 || error.status === 410) return messages.analysis_not_found;
  if (error.status === 413) return messages.upload_too_large;
  if (error.status === 415) return messages.unsupported_image;
  if (error.status === 429) return "The service is busy. Please wait and try again.";
  if (error.status >= 500) return "The service is temporarily unavailable. Please try again later.";
  if (error.status === 400 || error.status === 422) return messages.request_validation_failed;
  return "The request could not be completed. Please try again.";
}

export function parseApiError(status: number, payload: ApiErrorPayload): ApiError {
  // Backend messages are intentionally not shown verbatim; codes are mapped to safe copy.
  return new ApiError(status, payload.error?.code ?? "unknown_error", errorMessage(
    new ApiError(status, payload.error?.code ?? "unknown_error", ""),
  ));
}
