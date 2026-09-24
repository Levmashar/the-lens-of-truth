import { useEffect, useState } from "react";

import { ApiError, getAnalysis } from "../lib/api";
import { navigate } from "../lib/navigation";

type AnalysisProgressPageProps = {
  analysisId: string;
};

export function AnalysisProgressPage({ analysisId }: AnalysisProgressPageProps): React.JSX.Element {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [claimCount, setClaimCount] = useState(0);
  const [isScreenshot, setIsScreenshot] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getAnalysis(analysisId)
      .then((analysis) => {
        if (!active) return;
        setClaimCount(analysis.claims.length);
        setIsScreenshot(analysis.input_type === "screenshot");
        setState("ready");
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "The analysis could not be loaded.");
        setState("error");
      });
    return () => {
      active = false;
    };
  }, [analysisId]);

  const stages = [
    "Input ingested",
    ...(isScreenshot ? ["Screenshot OCR completed"] : []),
    "Structured identifiers redacted",
    "Atomic claims extracted",
  ];

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">Analysis progress</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">Claim extraction</h1>
      <p className="mt-4 leading-7 text-slate-600">
        This analysis has completed only the Phase 2 intake steps. Evidence retrieval, model
        evaluation, and medical verdicts have not run.
      </p>

      {state === "loading" ? <p className="mt-8 text-slate-600">Loading extraction status…</p> : null}
      {state === "error" ? (
        <p role="alert" className="mt-8 rounded-xl bg-rose-50 p-5 text-rose-800">
          {error}
        </p>
      ) : null}
      {state === "ready" ? (
        <>
          <ol aria-live="polite" className="mt-8 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            {stages.map((stage, index) => (
              <li key={stage} className="flex items-center gap-4">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-700 text-sm font-semibold text-white">
                  ✓
                </span>
                <span className="font-semibold text-slate-900">{stage}</span>
                <span className="ml-auto text-sm text-slate-500">{index + 1}</span>
              </li>
            ))}
          </ol>
          <div className="mt-6 rounded-xl bg-teal-50 p-5 text-sm leading-6 text-teal-950">
            <p className="font-semibold">{claimCount} atomic claim{claimCount === 1 ? "" : "s"} extracted</p>
            <p className="mt-1">The extracted spans are redacted where structured identifiers were detected.</p>
          </div>
          <button
            className="mt-6 min-h-11 rounded-lg bg-teal-800 px-5 py-3 font-semibold text-white hover:bg-teal-700"
            onClick={() => navigate(`/analyses/${analysisId}/result`)}
          >
            Review extracted claims
          </button>
        </>
      ) : null}
    </section>
  );
}
