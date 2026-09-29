// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SubmissionAttempt } from "../utils/idempotency";

beforeEach(() => {
  sessionStorage.clear();
  let counter = 0;
  vi.stubGlobal("crypto", {
    randomUUID: vi.fn(() => `key-${++counter}-abcdefgh`),
    subtle: { digest: vi.fn(async (_algorithm: string, input: BufferSource) => {
      const bytes = new Uint8Array(input as ArrayBuffer);
      const output = new Uint8Array(32);
      output.set(bytes.slice(0, 32));
      return output.buffer;
    }) },
  });
});
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });

describe("same-tab submission recovery", () => {
  it("recovers the same key for the same draft after a refresh", async () => {
    const first = new SubmissionAttempt();
    const key = await first.prepare("A health claim");
    expect(sessionStorage.length).toBe(1);
    const restored = new SubmissionAttempt();
    expect(await restored.prepare("A health claim")).toBe(key);
    expect(await restored.prepare("A health claim")).toBe(key);
    expect(vi.mocked(crypto.randomUUID)).toHaveBeenCalledTimes(1);
  });

  it("uses a new key for different input and clears storage after success", async () => {
    const first = new SubmissionAttempt();
    const key = await first.prepare("First health claim");
    const second = new SubmissionAttempt();
    const nextKey = await second.prepare("Different health claim");
    expect(nextKey).not.toBe(key);
    second.reset();
    expect(sessionStorage.length).toBe(0);
  });
});
