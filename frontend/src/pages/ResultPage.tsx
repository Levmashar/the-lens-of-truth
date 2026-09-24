import { useEffect, useState } from "react";

import { ApiError, type AnalysisDetail, getAnalysis } from "../lib/api";
import { navigate } from "../lib/navigation";

type ResultPageProps = {
  analysisId: string;
};

export function ResultPage({ analysisId }: ResultPageProps): React.JSX.Element {
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getAnalysis(analysisId)
      .then((detail) => {
        if (active) setAnalysis(detail);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof ApiError ? caught.message : "The analysis could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [analysisId]);

  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">Extracted claims</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">No medical verdict yet</h1>
      <div className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-7 text-amber-950">
        <p className="text-lg font-semibold">Phase 2 stops after claim extraction</p>
        <p className="mt-3 leading-7">
          The claims below are not fact-checked. Evidence retrieval, independent evaluation,
          citation validation, and the final risk-aware verdict belong to later phases.
        </p>
      </div>

      {error ? (
        <p role="alert" className="mt-7 rounded-xl bg-rose-50 p-5 text-rose-800">
          {error}
        </p>
      ) : null}
      {!analysis && !error ? <p className="mt-7 text-slate-600">Loading extracted claims…</p> : null}
      {analysis ? (
        <div className="mt-8 space-y-4">
          {analysis.claims.length === 0 ? (
            <p className="rounded-xl border border-slate-200 bg-white p-5 text-slate-700 shadow-sm">
              No externally verifiable atomic claims were extracted from this input.
            </p>
          ) : (
            analysis.claims.map((claim) => (
              <article key={claim.claim_id} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm font-semibold text-teal-700">Claim {claim.ordinal}</p>
                <p className="mt-3 text-lg leading-7 text-slate-900">{claim.raw_text}</p>
                {claim.normalized_text ? (
                  <p className="mt-3 leading-7 text-slate-600">Normalized: {claim.normalized_text}</p>
                ) : null}
                <dl className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
                  <div>
                    <dt className="font-semibold text-slate-800">Type</dt>
                    <dd>{claim.claim_type ?? "Unspecified"}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-800">Verifiability</dt>
                    <dd>{claim.verifiability === null ? "Unspecified" : `${Math.round(claim.verifiability * 100)}%`}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-800">Coreference</dt>
                    <dd>{claim.coreference_uncertain ? "Uncertain" : "Clear"}</dd>
                  </div>
                </dl>
                <div className="mt-5 border-t border-slate-200 pt-4">
                  <p className="text-sm font-semibold text-slate-800">PICO framing for evidence search</p>
                  <dl className="mt-3 grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                    {([
                      ["Population", claim.population],
                      ["Intervention or exposure", claim.intervention_or_exposure],
                      ["Comparator", claim.comparator],
                      ["Outcome", claim.outcome],
                      ["Timeframe", claim.timeframe],
                    ] as const).map(([label, value]) => (
                      <div key={label}>
                        <dt className="font-semibold text-slate-800">{label}</dt>
                        <dd>{value ?? "Not stated"}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </article>
            ))
          )}
        </div>
      ) : null}

      <button
        className="mt-7 min-h-11 rounded-lg bg-teal-800 px-5 py-3 font-semibold text-white hover:bg-teal-700"
        onClick={() => navigate("/submit")}
      >
        Submit another claim
      </button>
    </section>
  );
}
