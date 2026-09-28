// Retained only for the active submission attempt; medical text and images never enter storage.
export class SubmissionAttempt {
  private key: string | null = null;
  private uploadId: string | null = null;

  currentKey(): string {
    this.key ??= crypto.randomUUID();
    return this.key;
  }

  get uploadedId(): string | null { return this.uploadId; }
  set uploadedId(value: string | null) { this.uploadId = value; }

  reset(): void {
    this.key = null;
    this.uploadId = null;
  }
}
