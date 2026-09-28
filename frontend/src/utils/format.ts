import type { VerdictLabel } from "../types/api";

export const verdictLabels: Record<VerdictLabel, string> = {
  supported: "Supported",
  contradicted: "Contradicted",
  not_enough_evidence: "Not Enough Evidence",
  unable_to_verify_reliably: "Unable to Verify Reliably",
};

export function readableToken(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function fileSize(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}
