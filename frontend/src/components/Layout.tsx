import type { ReactNode } from "react";

import { HealthStatus } from "./HealthStatus";
import { navigate } from "../lib/navigation";

type LayoutProps = {
  children: ReactNode;
};

export function Layout({ children }: LayoutProps): React.JSX.Element {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4">
          <button
            className="text-left"
            onClick={() => navigate("/")}
            aria-label="Go to The Lens of Truth home page"
          >
            <span className="block text-lg font-semibold tracking-tight text-teal-800">
              The Lens of Truth
            </span>
            <span className="block text-xs text-slate-500">Evidence-based health verification</span>
          </button>
          <HealthStatus />
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-5 py-10">{children}</main>
      <footer className="mx-auto max-w-6xl px-5 pb-8 text-sm text-slate-500">
        This tool verifies public health claims; it does not provide diagnosis or individual treatment advice.
      </footer>
    </div>
  );
}
