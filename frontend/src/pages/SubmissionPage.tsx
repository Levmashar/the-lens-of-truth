import { useState } from "react";
import type { FormEvent } from "react";

import { createMockAnalysis } from "../lib/api";
import { navigate } from "../lib/navigation";

export function SubmissionPage(): React.JSX.Element {
  const [text, setText] = useState("");
  const [hasConsent, setHasConsent] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const content = text.trim();

    if (!content) {
      setError("Enter a health claim before submitting.");
      return;
    }
    if (!hasConsent) {
      setError("Please acknowledge the privacy notice before submitting.");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      const analysis = await createMockAnalysis(content);
      navigate(`/analyses/${analysis.analysis_id}/progress`);
    } catch {
      setError("The request could not reach the API. Check the API connection and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">New analysis</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">Submit a health claim</h1>
      <p className="mt-4 max-w-2xl leading-7 text-slate-600">
        Paste a public claim that can be checked against medical evidence. Do not include names,
        medical record numbers, addresses, or other personal information.
      </p>

      <form className="mt-8 space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" onSubmit={handleSubmit}>
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
          <p className="mt-2 text-sm text-slate-500">{text.length.toLocaleString()} / 20,000 characters</p>
        </div>

        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5">
          <p className="font-semibold text-slate-700">Screenshot upload</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            The Phase 1 interface reserves this input. Secure upload, OCR, and PII redaction are
            deliberately not active yet.
          </p>
          <button
            type="button"
            disabled
            className="mt-3 min-h-11 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-500 disabled:cursor-not-allowed"
          >
            Upload screenshot (coming in Phase 2)
          </button>
        </div>

        <label className="flex cursor-pointer items-start gap-3 rounded-xl bg-teal-50 p-4 text-sm leading-6 text-slate-700">
          <input
            type="checkbox"
            checked={hasConsent}
            onChange={(event) => setHasConsent(event.target.checked)}
            className="mt-1 h-4 w-4 accent-teal-700"
          />
          <span>
            I understand this tool is for public information verification, not diagnosis or personal
            treatment advice, and I have not included unnecessary personal information.
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
            {isSubmitting ? "Creating analysis…" : "Continue"}
          </button>
          <p className="text-sm text-slate-500">The current API response is explicitly marked as a mock.</p>
        </div>
      </form>
    </section>
  );
}
