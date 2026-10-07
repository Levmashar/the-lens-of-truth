// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createHomePage } from "../pages/home";
import { analysisId, jsonResponse } from "./fixtures";

let dispose: (() => void) | null = null;

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa") });
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:test"), revokeObjectURL: vi.fn() }));
  vi.stubGlobal("scrollTo", vi.fn());
  document.body.replaceChildren();
  window.history.replaceState({}, "", "/");
});
afterEach(() => { dispose?.(); dispose = null; vi.unstubAllGlobals(); });

function mount(): HTMLElement {
  const page = createHomePage();
  dispose = page.dispose;
  document.body.append(page.node);
  return page.node;
}

const flush = async (): Promise<void> => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };

describe("submission page", () => {
  it("renders product copy, text mode, and required consent", () => {
    const node = mount();
    expect(node.textContent).toContain("Heard a health claim?");
    expect(node.textContent).not.toMatch(/Start a verification|Service connected|Evidence-based medical information verification/);
    expect(node.querySelector("textarea")).not.toBeNull();
    expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(true);
    expect((node.querySelector("[name=consent]") as HTMLInputElement).checked).toBe(false);
  });

  it("switches modes by keyboard and validates screenshot type and size", () => {
    const node = mount();
    const tab = node.querySelector("#text-tab") as HTMLButtonElement;
    tab.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(node.querySelector("#screenshot-tab")?.getAttribute("aria-selected")).toBe("true");
    expect(node.querySelector("[type=file]")).not.toBeNull();
    const input = node.querySelector("[type=file]") as HTMLInputElement;
    Object.defineProperty(input, "files", { configurable: true, value: [new File(["bad"], "bad.gif", { type: "image/gif" })] });
    input.dispatchEvent(new Event("change"));
    expect(node.textContent).toContain("Choose a PNG, JPEG, or WebP screenshot.");
  });

  it("submits text with consent and an idempotency key, then navigates", async () => {
    const fetchMock = vi.mocked(fetch).mockResolvedValue(jsonResponse({ analysis_id: analysisId, status: "queued", stage: "queued", claim_count: 0, completed_claims: 0 }, 202));
    const node = mount();
    const input = node.querySelector("textarea") as HTMLTextAreaElement;
    input.value = "Vitamin C prevents the common cold.";
    input.dispatchEvent(new Event("input"));
    const consent = node.querySelector("[name=consent]") as HTMLInputElement;
    consent.checked = true;
    consent.dispatchEvent(new Event("change"));
    (node.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect((options.headers as Record<string, string>)["Idempotency-Key"]).toBe("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(JSON.parse(options.body as string).consent.privacy_notice_version).toBe("2026-09-01");
    expect(window.location.pathname).toBe(`/analysis/${analysisId}`);
  });

  it("reuses the key after network failure but changes it when draft changes", async () => {
    const random = vi.fn().mockReturnValueOnce("key-11111111").mockReturnValueOnce("key-22222222");
    vi.stubGlobal("crypto", { randomUUID: random });
    const fetchMock = vi.mocked(fetch).mockRejectedValue(new TypeError("network"));
    const node = mount();
    const input = node.querySelector("textarea") as HTMLTextAreaElement;
    input.value = "First claim";
    input.dispatchEvent(new Event("input"));
    const consent = node.querySelector("[name=consent]") as HTMLInputElement;
    consent.checked = true;
    consent.dispatchEvent(new Event("change"));
    const form = node.querySelector("form") as HTMLFormElement;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    input.value = "A different claim";
    input.dispatchEvent(new Event("input"));
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    const keys = fetchMock.mock.calls.map(([, options]) => (options?.headers as Record<string, string>)["Idempotency-Key"]);
    expect(keys).toEqual(["key-11111111", "key-11111111", "key-22222222"]);
  });

  it("uploads a screenshot before posting its upload ID", async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ analysis_id: analysisId, status: "queued" }, 202));
    const node = mount();
    (node.querySelector("#screenshot-tab") as HTMLButtonElement).click();
    const input = node.querySelector("[type=file]") as HTMLInputElement;
    Object.defineProperty(input, "files", { configurable: true, value: [new File(["png"], "screen.png", { type: "image/png" })] });
    input.dispatchEvent(new Event("change"));
    expect(node.textContent).toContain("screen.png");
    const consent = node.querySelector("[name=consent]") as HTMLInputElement;
    consent.checked = true;
    consent.dispatchEvent(new Event("change"));
    (node.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { cancelable: true }));
    await flush();
    expect(fetchMock.mock.calls[0][0]).toContain("/uploads/screenshots");
    expect(JSON.parse((fetchMock.mock.calls[1][1] as RequestInit).body as string).input.upload_id).toBe("upload-1");
  });
});
