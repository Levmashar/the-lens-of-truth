// Only a digest, upload reference, and opaque key may be saved for a retry in this tab.
const storageKey = "lens.pending-submission.v1";

interface StoredAttempt { digest: string; key: string; uploadId: string | null }

export class SubmissionAttempt {
  private key: string | null = null;
  private uploadId: string | null = null;
  private digest: string | null = null;

  async prepare(content: string | File): Promise<string> {
    if (this.key) return this.key;
    try {
      if (crypto.subtle) {
        const bytes = typeof content === "string" ? new TextEncoder().encode(content) :
          typeof content.arrayBuffer === "function" ? await content.arrayBuffer() : null;
        if (bytes) {
          const hash = await crypto.subtle.digest("SHA-256", bytes);
          this.digest = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
          try {
            const stored = JSON.parse(sessionStorage.getItem(storageKey) ?? "null") as StoredAttempt | null;
            if (stored?.digest === this.digest && /^[A-Za-z0-9._~-]{8,128}$/.test(stored.key)) {
              this.key = stored.key;
              this.uploadId = stored.uploadId && /^[0-9a-f-]{36}$/i.test(stored.uploadId) ? stored.uploadId : null;
            }
          } catch { /* Storage is optional. */ }
        }
      }
    } catch { /* Digest failure leaves the in-memory retry path available. */ }
    this.key ??= typeof crypto.randomUUID === "function" ? crypto.randomUUID() :
      Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
    this.save();
    return this.key;
  }

  get uploadedId(): string | null { return this.uploadId; }
  set uploadedId(value: string | null) { this.uploadId = value; this.save(); }

  private save(): void {
    if (!this.digest || !this.key) return;
    try { sessionStorage.setItem(storageKey, JSON.stringify({ digest: this.digest, key: this.key, uploadId: this.uploadId })); }
    catch { /* Private browsing may disable storage; in-memory retry still works. */ }
  }

  reset(): void {
    const hadAttempt = this.key !== null;
    this.key = null;
    this.uploadId = null;
    this.digest = null;
    if (hadAttempt) {
      try { sessionStorage.removeItem(storageKey); } catch { /* Optional storage. */ }
    }
  }
}
