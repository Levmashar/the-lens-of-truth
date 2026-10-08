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

  it("reads a screenshot for review before submitting the edited text and upload ID", async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", redacted_text: "Smoking causes cancer.", confidence: 0.95 }))
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
    await vi.waitFor(() => expect(node.querySelector("#screenshot-text")?.closest(".screenshot-review")?.hasAttribute("hidden")).toBe(false));
    expect(fetchMock.mock.calls[0][0]).toContain("/uploads/screenshots");
    expect(fetchMock.mock.calls[1][0]).toContain("/uploads/screenshots/upload-1/read");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const readOptions = fetchMock.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(readOptions.body as string).consent.accepted).toBe(true);
    const review = node.querySelector("#screenshot-text") as HTMLTextAreaElement;
    expect(review.value).toBe("Smoking causes cancer.");
    review.value = "Smoking causes lung cancer.";
    review.dispatchEvent(new Event("input"));
    (node.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse((fetchMock.mock.calls[2][1] as RequestInit).body as string).input).toEqual({
      type: "screenshot", upload_id: "upload-1", reviewed_text: "Smoking causes lung cancer.",
    });
    await vi.waitFor(() => expect(window.location.pathname).toBe(`/analysis/${analysisId}`));
  });

  function screenshotForm(): HTMLElement {
    const node = mount();
    (node.querySelector("#screenshot-tab") as HTMLButtonElement).click();
    const input = node.querySelector("[type=file]") as HTMLInputElement;
    Object.defineProperty(input, "files", { configurable: true, value: [new File(["png"], "screen.png", { type: "image/png" })] });
    input.dispatchEvent(new Event("change"));
    const consent = node.querySelector("[name=consent]") as HTMLInputElement;
    consent.checked = true;
    consent.dispatchEvent(new Event("change"));
    return node;
  }

  it("retries failed OCR without uploading the same file again", async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ error: { code: "ocr_timeout" } }, 504))
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", redacted_text: "A claim." }));
    const node = screenshotForm();
    const form = node.querySelector("form") as HTMLFormElement;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(node.textContent).toContain("Reading this screenshot took too long"));
    expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(false);
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect((node.querySelector("#screenshot-text") as HTMLTextAreaElement).value).toBe("A claim."));
    expect((node.querySelector(".form-error") as HTMLElement).hidden).toBe(true);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      expect.stringContaining("/uploads/screenshots"),
      expect.stringContaining("/upload-1/read"),
      expect.stringContaining("/upload-1/read"),
    ]);
  });

  it("clears an expired upload reference so retry uploads a fresh screenshot", async () => {
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "old-upload", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ error: { code: "screenshot_upload_not_found" } }, 404))
      .mockResolvedValueOnce(jsonResponse({ upload_id: "fresh-upload", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ upload_id: "fresh-upload", redacted_text: "A claim." }));
    const node = screenshotForm();
    const form = node.querySelector("form") as HTMLFormElement;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(node.textContent).toContain("Upload it again"));
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(fetchMock.mock.calls[2][0]).toContain("/uploads/screenshots");
    expect(fetchMock.mock.calls[3][0]).toContain("/fresh-upload/read");
  });

  it("locks image and mode controls while OCR is pending, then restores them on failure", async () => {
    let rejectRead: (reason: Error) => void = () => {};
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", status: "uploaded" }, 201))
      .mockImplementationOnce(() => new Promise<Response>((_resolve, reject) => { rejectRead = reject; }));
    const node = screenshotForm();
    (node.querySelector("form") as HTMLFormElement).dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(node.textContent).toContain("Reading screenshot"));
    expect((node.querySelector("[type=file]") as HTMLInputElement).disabled).toBe(true);
    expect((node.querySelector("#text-tab") as HTMLButtonElement).disabled).toBe(true);
    rejectRead(new TypeError("network"));
    await vi.waitFor(() => expect((node.querySelector("[type=file]") as HTMLInputElement).disabled).toBe(false));
    expect((node.querySelector("#text-tab") as HTMLButtonElement).disabled).toBe(false);
  });

  it("reuses the final screenshot request key on retry and replaces it after a text edit", async () => {
    vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValueOnce("key-11111111").mockReturnValueOnce("key-22222222") });
    const fetchMock = vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ upload_id: "upload-1", status: "uploaded" }, 201))
      .mockResolvedValueOnce(jsonResponse({ redacted_text: "First claim." }))
      .mockRejectedValue(new TypeError("network"));
    const node = screenshotForm();
    const form = node.querySelector("form") as HTMLFormElement;
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect((node.querySelector("#screenshot-text") as HTMLTextAreaElement).value).toBe("First claim."));
    for (let retry = 0; retry < 2; retry++) {
      form.dispatchEvent(new Event("submit", { cancelable: true }));
      await vi.waitFor(() => expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(false));
    }
    const review = node.querySelector("#screenshot-text") as HTMLTextAreaElement;
    review.value = "A different claim.";
    review.dispatchEvent(new Event("input"));
    form.dispatchEvent(new Event("submit", { cancelable: true }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    const keys = fetchMock.mock.calls.slice(2).map(([, options]) => (options?.headers as Record<string, string>)["Idempotency-Key"]);
    expect(keys).toEqual(["key-11111111", "key-11111111", "key-22222222"]);
    expect(JSON.parse(fetchMock.mock.calls[4][1]?.body as string).input.reviewed_text).toBe("A different claim.");
  });

  it("accepts a recognized extension when the browser omits MIME, and rejects empty images", () => {
    const node = screenshotForm();
    const input = node.querySelector("[type=file]") as HTMLInputElement;
    Object.defineProperty(input, "files", { configurable: true, value: [new File(["png"], "screen.PNG")] });
    input.dispatchEvent(new Event("change"));
    expect(node.textContent).toContain("screen.PNG");
    expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(false);
    Object.defineProperty(input, "files", { configurable: true, value: [new File([], "empty.png", { type: "image/png" })] });
    input.dispatchEvent(new Event("change"));
    expect(node.textContent).toContain("This image file is empty");
    expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(true);
  });

  it("removes an undecodable preview and prevents submission", () => {
    const node = screenshotForm();
    (node.querySelector(".upload-image") as HTMLImageElement).dispatchEvent(new Event("error"));
    expect(node.textContent).toContain("This image couldn't be opened");
    expect((node.querySelector("[type=submit]") as HTMLButtonElement).disabled).toBe(true);
  });
});
