export type PollResult = "active" | "terminal";

export class Poller {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private controller: AbortController | null = null;
  private stopped = true;
  private failures = 0;

  constructor(
    private readonly request: (signal: AbortSignal) => Promise<PollResult>,
    private readonly onError: (error: unknown, failures: number) => void,
    private readonly intervalMs = 1500,
  ) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    void this.tick();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.controller?.abort();
    this.controller = null;
  }

  private async tick(): Promise<void> {
    if (this.stopped) return;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const outcome = await this.request(controller.signal);
      if (controller.signal.aborted || this.stopped) return;
      this.failures = 0;
      if (outcome === "terminal") { this.stop(); return; }
    } catch (error) {
      if (controller.signal.aborted || this.stopped) return;
      this.failures += 1;
      this.onError(error, this.failures);
    } finally {
      if (this.controller === controller) this.controller = null;
      if (!this.stopped) {
        const delay = this.failures ? Math.min(this.intervalMs * 2 ** Math.min(this.failures, 3), 12000) : this.intervalMs;
        this.timer = setTimeout(() => void this.tick(), delay);
      }
    }
  }
}
