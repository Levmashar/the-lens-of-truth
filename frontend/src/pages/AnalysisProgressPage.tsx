import { useEffect, useState } from "react";

import { navigate } from "../lib/navigation";

const stages = [
  "Analysis request accepted",
  "Awaiting OCR and claim extraction",
  "Awaiting evidence retrieval",
  "Awaiting independent evaluation",
];

type AnalysisProgressPageProps = {
  analysisId: string;
};

export function AnalysisProgressPage({ analysisId }: AnalysisProgressPageProps): React.JSX.Element {
  const [currentStage, setCurrentStage] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentStage((previous) => Math.min(previous + 1, stages.length - 1));
    }, 750);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">Analysis progress</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">Your analysis is queued</h1>
      <p className="mt-4 leading-7 text-slate-600">
        This screen establishes the progress UX for future SSE pipeline events. No claim extraction,
        evidence retrieval, or medical evaluation runs in Phase 1.
      </p>

      <ol aria-live="polite" className="mt-8 space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {stages.map((stage, index) => {
          const isComplete = index < currentStage;
          const isCurrent = index === currentStage;
          return (
            <li key={stage} className="flex items-center gap-4">
              <span
                aria-hidden="true"
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold ${
                  isComplete || isCurrent ? "bg-teal-700 text-white" : "bg-slate-200 text-slate-600"
                }`}
              >
                {isComplete ? "✓" : index + 1}
              </span>
              <span className={isCurrent ? "font-semibold text-slate-900" : "text-slate-600"}>{stage}</span>
            </li>
          );
        })}
      </ol>

      <div className="mt-6 rounded-xl bg-amber-50 p-5 text-sm leading-6 text-amber-900">
        <p className="font-semibold">Implementation placeholder</p>
        <p className="mt-1">Analysis ID: <code>{analysisId}</code></p>
        <p className="mt-1">The result page contains no verdict until the evidence pipeline exists.</p>
      </div>

      <button
        className="mt-6 min-h-11 rounded-lg bg-teal-800 px-5 py-3 font-semibold text-white hover:bg-teal-700"
        onClick={() => navigate(`/analyses/${analysisId}/result`)}
      >
        View result placeholder
      </button>
    </section>
  );
}
