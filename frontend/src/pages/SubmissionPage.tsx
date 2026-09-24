import { useState } from "react";
import type { FormEvent } from "react";

import { ApiError, createAnalysis, uploadScreenshot } from "../lib/api";
import { navigate } from "../lib/navigation";

const acceptedImageTypes = ["image/jpeg", "image/png", "image/webp"];
const maximumClientFileBytes = 10 * 1024 * 1024;

type SubmissionMode = "text" | "screenshot";

export function SubmissionPage(): React.JSX.Element {
  const [mode, setMode] = useState<SubmissionMode>("text");
  const [text, setText] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [hasConsent, setHasConsent] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function selectScreenshot(file: File | null): void {
    setError(null);
    if (!file) {
      setScreenshot(null);
      return;
    }
    if (!acceptedImageTypes.includes(file.type)) {
      setScreenshot(null);
      setError("Choose a PNG, JPEG, or WebP screenshot.");
      return;
    }
    if (file.size > maximumClientFileBytes) {
      setScreenshot(null);
      setError("Choose a screenshot smaller than 10 MB.");
      return;
    }
    setScreenshot(file);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const content = text.trim();
    if (mode === "text" && !content) {
      setError("Enter a health claim before submitting.");
      return;
    }
    if (mode === "screenshot" && !screenshot) {
      setError("Choose a screenshot before submitting.");
      return;
    }
    if (!hasConsent) {
      setError("Please acknowledge the privacy notice before submitting.");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      if (mode === "text") {
        setStatusMessage("Redacting structured identifiers and extracting atomic claims…");
        const analysis = await createAnalysis({ type: "text", text: content });
        navigate(`/analyses/${analysis.analysis_id}/progress`);
        return;
      }

      if (!screenshot) {
        return;
      }
      setStatusMessage("Validating and safely re-encoding your screenshot…");
      const upload = await uploadScreenshot(screenshot);
      setStatusMessage("Reading the screenshot, redacting identifiers, and extracting claims…");
      const analysis = await createAnalysis({ type: "screenshot", uploadId: upload.upload_id });
      navigate(`/analyses/${analysis.analysis_id}/progress`);
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : "The request could not reach the API.";
      setError(`${message} No medical verdict has been generated.`);
    } finally {
      setIsSubmitting(false);
      setStatusMessage(null);
    }
  }

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">New analysis</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">Submit a health claim</h1>
      <p className="mt-4 max-w-2xl leading-7 text-slate-600">
        Paste a public claim or upload its screenshot. Do not include names, medical record
        numbers, addresses, or other personal information.
      </p>

      <form
        className="mt-8 space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        onSubmit={handleSubmit}
      >
        <fieldset>
          <legend className="text-sm font-semibold text-slate-800">Source</legend>
          <div className="mt-3 flex flex-wrap gap-3">
            {(["text", "screenshot"] as const).map((option) => (
              <label
                key={option}
                className={`cursor-pointer rounded-lg border px-4 py-2 text-sm font-semibold ${
                  mode === option
                    ? "border-teal-700 bg-teal-50 text-teal-900"
                    : "border-slate-300 text-slate-700"
                }`}
              >
                <input
                  className="sr-only"
                  type="radio"
                  name="source"
                  checked={mode === option}
                  onChange={() => setMode(option)}
                />
                {option === "text" ? "Paste text" : "Upload screenshot"}
              </label>
            ))}
          </div>
        </fieldset>

        {mode === "text" ? (
          <div>
            <label className="block text-sm font-semibold text-slate-800" htmlFor="claim-text">
              Claim text
            </label>
            <textarea
              id="claim-text"
              name="claim-text"
              rows={8}
              maxLength={20_000}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Example: A post claims that a supplement prevents a specific illness."
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 leading-6 text-slate-800 placeholder:text-slate-400"
            />
            <p className="mt-2 text-sm text-slate-500">
              {text.length.toLocaleString()} / 20,000 characters
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5">
            <label className="block font-semibold text-slate-700" htmlFor="screenshot">
              Screenshot
            </label>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              PNG, JPEG, or WebP up to 10 MB. The server verifies the decoded image, removes
              metadata by re-encoding it, and holds the raw screenshot for at most 24 hours.
            </p>
            <input
              id="screenshot"
              className="mt-3 block w-full text-sm text-slate-700 file:mr-4 file:rounded-lg file:border-0 file:bg-teal-800 file:px-4 file:py-2 file:font-semibold file:text-white hover:file:bg-teal-700"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => selectScreenshot(event.target.files?.[0] ?? null)}
            />
            {screenshot ? (
              <p className="mt-3 text-sm text-teal-800">
                Selected: {screenshot.name} ({Math.ceil(screenshot.size / 1024)} KB)
              </p>
            ) : null}
          </div>
        )}

        <label className="flex cursor-pointer items-start gap-3 rounded-xl bg-teal-50 p-4 text-sm leading-6 text-slate-700">
          <input
            type="checkbox"
            checked={hasConsent}
            onChange={(event) => setHasConsent(event.target.checked)}
            className="mt-1 h-4 w-4 accent-teal-700"
          />
          <span>
            I understand this tool verifies public information, not diagnosis or personal treatment
            advice, and I have not included unnecessary personal information.
          </span>
        </label>

        {error ? (
          <p role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
            {error}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={isSubmitting}
            className="min-h-11 rounded-lg bg-teal-800 px-5 py-3 font-semibold text-white transition hover:bg-teal-700 disabled:cursor-wait disabled:bg-teal-600"
          >
            {isSubmitting ? "Processing…" : "Extract claims"}
          </button>
          <p aria-live="polite" className="text-sm text-slate-500">
            {statusMessage ?? "Phase 2 extracts claims only; it does not issue a medical verdict."}
          </p>
        </div>
      </form>
    </section>
  );
}
