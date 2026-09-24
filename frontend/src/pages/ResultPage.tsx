import { navigate } from "../lib/navigation";

type ResultPageProps = {
  analysisId: string;
};

export function ResultPage({ analysisId }: ResultPageProps): React.JSX.Element {
  return (
    <section className="mx-auto max-w-3xl">
      <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">Analysis result</p>
      <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-900">No medical verdict yet</h1>
      <div className="mt-7 rounded-2xl border border-amber-200 bg-amber-50 p-7 text-amber-950">
        <p className="text-lg font-semibold">Phase 1 result placeholder</p>
        <p className="mt-3 leading-7">
          This analysis ({analysisId}) has not been processed. The foundation intentionally does not
          fabricate claims, evidence, model judgments, citations, or a final verdict.
        </p>
      </div>

      <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-semibold text-slate-900">What a completed report will contain</h2>
        <ul className="mt-4 space-y-3 leading-7 text-slate-600">
          <li>Atomic claims with preserved source spans and normalized PICO context.</li>
          <li>Traceable evidence cards with source, study type, date, and passage IDs.</li>
          <li>A risk-aware, evidence-cited conclusion or an appropriate abstention.</li>
        </ul>
      </div>

      <button
        className="mt-7 min-h-11 rounded-lg bg-teal-800 px-5 py-3 font-semibold text-white hover:bg-teal-700"
        onClick={() => navigate("/submit")}
      >
        Submit another claim
      </button>
    </section>
  );
}
