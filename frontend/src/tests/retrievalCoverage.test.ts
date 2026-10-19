// @vitest-environment jsdom
import { expect, it } from "vitest";
import { createClaimResult } from "../components/claimResult";
import { analysisId, claimId, report } from "./fixtures";
import type { ReportReadingGuide } from "../types/report";

it("shows indirect coverage distinctly and keeps source links in a disclosure", () => {
  const saved = report("not_enough_evidence");
  const guide: ReportReadingGuide = { version: "report-reading-guide-1.0",
    verdict_run_id: saved.verdict_run_id, report_semantic_hash: saved.semantic_hash,
    findings: [], highlights: [], retrieval: { version: "retrieval-coverage-2.0",
      state: "related_only", explanation: "Related findings do not settle the specific claim.",
      sources: [{ title: "A related study", url: "https://pubmed.ncbi.nlm.nih.gov/123/",
        classification: "related_indirect", missing_qualifiers: ["exposure:side"] },
        { title: "Bad link", url: "javascript:alert(1)", classification: "background_guidance",
          missing_qualifiers: [] }] } };
  const node = createClaimResult(saved, analysisId, claimId, false, guide);
  expect(node.textContent).toContain("Related evidence has limits");
  expect(node.textContent).toContain(guide.retrieval?.explanation);
  const details = Array.from(node.querySelectorAll("details")).find(d =>
    d.querySelector("summary")?.textContent === "Explore the sources found");
  expect(details?.open).toBe(false);
  expect(details?.querySelector("a")?.href).toBe("https://pubmed.ncbi.nlm.nih.gov/123/");
  expect(details?.textContent).toContain("Related, indirect research");
  expect(details?.textContent).not.toContain("Bad link");
});

it("does not describe a search failure as scientific inconclusiveness", () => {
  const saved = report("unable_to_verify_reliably");
  const guide: ReportReadingGuide = { version: "report-reading-guide-1.0",
    verdict_run_id: saved.verdict_run_id, report_semantic_hash: saved.semantic_hash,
    findings: [], highlights: [], retrieval: { version: "retrieval-coverage-2.0",
      state: "search_incomplete", explanation: "The source search could not be completed.", sources: [] } };
  const node = createClaimResult(saved, analysisId, claimId, false, guide);
  expect(node.textContent).toContain("The search was incomplete");
  expect(node.textContent).toContain("The source search could not be completed.");
});
