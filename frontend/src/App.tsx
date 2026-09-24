import { useEffect, useState } from "react";

import { Layout } from "./components/Layout";
import { AnalysisProgressPage } from "./pages/AnalysisProgressPage";
import { LandingPage } from "./pages/LandingPage";
import { ResultPage } from "./pages/ResultPage";
import { SubmissionPage } from "./pages/SubmissionPage";

function usePathname(): string {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const onLocationChange = (): void => setPathname(window.location.pathname);
    window.addEventListener("popstate", onLocationChange);
    return () => window.removeEventListener("popstate", onLocationChange);
  }, []);

  return pathname;
}

function contentForPath(pathname: string): React.JSX.Element {
  if (pathname === "/submit") {
    return <SubmissionPage />;
  }

  const progressMatch = pathname.match(/^\/analyses\/([^/]+)\/progress$/);
  if (progressMatch) {
    return <AnalysisProgressPage analysisId={progressMatch[1]} />;
  }

  const resultMatch = pathname.match(/^\/analyses\/([^/]+)\/result$/);
  if (resultMatch) {
    return <ResultPage analysisId={resultMatch[1]} />;
  }

  return <LandingPage />;
}

export function App(): React.JSX.Element {
  return <Layout>{contentForPath(usePathname())}</Layout>;
}
