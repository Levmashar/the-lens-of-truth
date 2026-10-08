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
  document_not_ready: "The document report is not available yet. Refresh this page to try again.",
  report_not_qualified: "This analysis completed, but the report does not meet the current release qualification requirements.",
  screenshot_too_large: "The screenshot is too large. Choose a smaller image.",
  sanitized_screenshot_too_large: "The screenshot is too large after processing. Choose a smaller image.",
  upload_too_large: "The screenshot is too large. Choose a smaller image.",
  unsupported_screenshot_format: "Choose a PNG, JPEG, or WebP screenshot.",
  invalid_screenshot: "We couldn't read this image. Choose a different screenshot.",
  empty_screenshot: "This image file is empty. Choose another screenshot.",
  animated_screenshot_not_allowed: "Animated images are not supported. Choose a still screenshot.",
  screenshot_dimensions_not_allowed: "This image's dimensions are too large. Choose a smaller screenshot.",
  screenshot_upload_not_found: "The uploaded screenshot is no longer available. Upload it again.",
  screenshot_upload_already_used: "This screenshot was already submitted. Choose it again to start a new verification.",
  screenshot_text_not_found: "We couldn't read enough text from this screenshot.",
  screenshot_text_too_long: "There's too much text in this screenshot. Crop it to the claim you want to check.",
  screenshot_text_not_ready: "Read the screenshot again before checking its text.",
  upload_not_available: "The uploaded screenshot is no longer available. Upload it again.",
  upload_storage_unavailable: "We couldn't save the screenshot. Try again, or paste the text instead.",
  ocr_unavailable: "Screenshot reading is temporarily unavailable. Paste the text instead, or try again later.",
  ocr_failed: "We couldn't read enough text from this screenshot.",
  ocr_timeout: "Reading this screenshot took too long. Try another image or paste the text.",
  unsupported_image: "Choose a PNG, JPEG, or WebP screenshot.",
  ocr_no_text: "We couldn't read enough text from this screenshot.",
  ocr_empty: "We couldn't read enough text from this screenshot.",
  no_claims_extracted: "No checkable medical claims were identified in this content.",
  worker_interrupted: "The analysis was interrupted. Start a new verification.",
  claim_extractor_rate_limited: "The claim extraction service is rate-limited. Wait before trying again.",
  claim_extractor_unavailable: "The claim extraction service is temporarily unavailable. Try again later.",
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
  const code = payload.error?.code ?? "unknown_error";
  return new ApiError(status, code, errorMessage(new ApiError(status, code, "")));
}
