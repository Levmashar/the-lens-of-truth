import { navigate } from "../lib/navigation";

const principles = [
  {
    title: "Atomic claims",
    text: "A post can contain several checkable claims. Each must be examined on its own terms.",
  },
  {
    title: "Traceable evidence",
    text: "Future reports will identify the evidence passages that support each explanation.",
  },
  {
    title: "Appropriate uncertainty",
    text: "Insufficient evidence is a valid outcome, especially for high-risk health claims.",
  },
];

export function LandingPage(): React.JSX.Element {
  return (
    <section className="space-y-16">
      <div className="grid gap-10 rounded-3xl bg-teal-950 px-7 py-12 text-white shadow-sm md:grid-cols-[1.3fr_0.7fr] md:px-12 md:py-16">
        <div>
          <p className="mb-4 text-sm font-semibold tracking-[0.16em] text-teal-200 uppercase">
            Medical information verification
          </p>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight md:text-6xl">
            Trace the evidence behind a health claim.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-teal-100">
            The Lens of Truth will decompose public health claims, retrieve evidence,
            cross-check it independently, and communicate uncertainty clearly.
          </p>
          <button
            className="mt-8 min-h-11 rounded-lg bg-white px-5 py-3 font-semibold text-teal-900 transition hover:bg-teal-100"
            onClick={() => navigate("/submit")}
          >
            Start a verification
          </button>
        </div>
        <aside className="self-end rounded-2xl border border-teal-700 bg-teal-900/60 p-6 text-sm leading-7 text-teal-50">
          <p className="font-semibold text-white">Not a binary fact checker</p>
          <p className="mt-2">
            Evidence can support, contradict, or remain insufficient for a specific claim.
            The system may also decline to verify unreliable input.
          </p>
        </aside>
      </div>

      <div>
        <p className="text-sm font-semibold tracking-[0.14em] text-teal-700 uppercase">Method</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">
          Evidence before conclusions
        </h2>
        <div className="mt-7 grid gap-5 md:grid-cols-3">
          {principles.map((principle, index) => (
            <article key={principle.title} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-sm font-semibold text-teal-700">0{index + 1}</p>
              <h3 className="mt-3 text-xl font-semibold text-slate-900">{principle.title}</h3>
              <p className="mt-3 leading-7 text-slate-600">{principle.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
