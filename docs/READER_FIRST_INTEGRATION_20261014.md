# Reader-first document screen integration — 2026-10-14

User's “continue” approved integrating the reviewed preview. The normal document
result screen now uses the same vanilla TypeScript renderer. No React, model call,
summary model, retrieval/prompt/medical change or historical outcome rewrite.

## Open locally

- Normal application: http://localhost:5173/ (new document reports use the reader screen).
- Three-state development preview: http://127.0.0.1:5174/reader-preview.html?fixture=incomplete
  (selector switches completed/inconclusive/incomplete; synthetic scopes remain labelled).

Use `localhost:5173` for the deployed application: the existing local CORS setup
allows that origin. Opening the deployed build on `127.0.0.1:5173` fails its API
requests under the unchanged CORS configuration. The development preview is independent.

The retained analysis URL used for live screenshots was
`/analysis/a897813c-5ce9-4f56-b1b6-29c50ed2480e`. During the interruption it expired
under existing retention; the final post-restart read returns 404 and its DB artifacts
are absent. It was not restored or given extended retention. The frozen preview
remains available, explicitly labelled as a retained capture rather than a new run.

## What changed

`backend/app/document/reader.py` adds an ephemeral, deterministic `reader-view-1.0`
after the original report passes its existing audit/reconstruction. Sentences trace
to report fields/assertions and owned sources; explicitly unverified numeric wording
uses the existing structured plan claim, not a new numeric parser. No artifact is
written. Question-based checks distinguish reporting fidelity from medical evidence,
and operational incompleteness from completed scientific uncertainty.

The shared frontend renderer leads with the answer and visible limits. It reveals
exact excerpts and full passages, retains distinct assertions/endpoints and preserves
disclosure/focus state across polling. The advanced view keeps the original complete
report, every assertion, source passage, wording trace and development-only raw reply.
Copy all diagnostics is preserved. Older payloads fall back to the original renderer.
Fixture JSON is excluded from the normal build. Single-claim screens are unchanged.

## Exact retained first-screen wording

124 words, excluding controls and development notice:

> We found the study, but couldn't finish checking its main claims.
>
> The study's participant count and subject match the submitted description.
> We did not finish verifying the main findings, including the claimed “up to a 292%”
> effect. A completed broad description does not confirm a more specific unfinished claim.
>
> The claim about other risk factors also needs review. Its saved result has not been
> changed, and the evidence issue is flagged below.
> This is an incomplete check, not evidence that the unfinished claims are true or
> false. Available source passages do not turn an unfinished assessment into a completed one.
> This checks how accurately the paragraph describes a paper. Matching its reporting
> does not, by itself, establish a medical cause, treatment benefit or recommendation.

Controls: “See the evidence”, “Read the study”. Visible notice:
“Development result · Not approved for public release.”

The generic projector derives this from actual states and fields; the example claim
or analysis ID is not hardcoded. The other preview states retain their approved
[exact wording and provenance](READER_FIRST_PREVIEW_20261014.md).

## Preservation and verification

After removing only `reader_view`, the integrated GET response equals the complete
pre-integration captured projection, including debug records. The retained report
still has **4 assessed / 3 unavailable / 4 background / 0 pending**, 11 original
assertions and status `partially_completed`. A3/A4/A5 remain Unable, not NEI.
A6 remains saved Supported with a visible review flag; it is excluded from approved
summary facts. The stored report hash is unchanged:
`924d3d93aac3bb02502b90c1a43103e135b226b049497414aaefc5b833c5d30b`.
These exact live projection/hash checks passed before the interruption/expiry.
After resuming, the final enriched trace projection was rechecked offline against
the frozen inputs and backend tests; no current live read of an expired result is claimed.

- Full frontend suite: **122 passed**, 8 files; TypeScript/Vite production build passes.
- Relevant backend suite: **126 passed** (reader, API, clarity, audit, evaluation,
  packaging); one existing Starlette/httpx deprecation warning. The complete backend
  suite was not rerun for this presentation change.
- Ruff checks all app/tests; mypy **199 modules** passes.
- Actual Chrome: integrated screen at 1440×1000 and 390×1000, light/dark, keyboard
  Tab/Enter/Space, visible 3px disclosure focus, exact excerpt/full-passage controls.
- No horizontal overflow or empty visible headings/bullets. Minimum measured
  reader text contrast **5.9:1 light / 7.9:1 dark**. 200% text at 320px reflows
  without horizontal overflow. This checks text zoom, not browser chrome zoom.
- Actual clipboard: **383,146 characters**, 11 assertions, full raw replies and
  successful copy feedback (before final trace enrichment; contents remain complete).
- Earlier three-state desktop/mobile fixture screenshots remain available. No human
  comprehension testing. External PubMed rendering encountered HTTP 403 during preview
  QA; links target the exact paper, local frozen-source controls work. No access bypass.
- After the interruption, all three shared-renderer fixture states were checked again
  at desktop/mobile widths: layout, contrast, actual keyboard disclosures and 200%
  text reflow passed in all six combinations. The local preview server was restarted.
- Backend/frontend rebuilt and restarted after checking there were no queued/running
  analyses. Database/Redis were left running. Health remains development/debug enabled.

## Screenshots

- [Integrated desktop](assets/reader-integration-20261014/integrated-desktop.png)
- [Integrated mobile](assets/reader-integration-20261014/integrated-mobile.png)
- [Evidence and keyboard focus on mobile](assets/reader-integration-20261014/integrated-evidence-mobile.png)
- [Dark mobile](assets/reader-integration-20261014/integrated-dark-mobile.png)

## Separate correctness work remains open

See [frozen diagnosis and proposed fixes](READER_PREVIEW_BACKEND_FINDINGS_20261014.md).
The Qwen judge's validator returned no required S1 reporting attributions for seven
items; responded-but-invalid coverage has no repair retry. High-risk A3/A4/A5 lacked
the required third assessment and remain unavailable. No attributions were invented.

Available methods say “for each predictor variable”; a variable list and multinomial
regression name do not establish joint covariate adjustment for the same sunscreen
estimate. The frozen evidence does not settle that adjustment, nor prove its absence.
This integration flags the issue without changing the saved result. Neither backend
correctness fix was implemented; production/clinical release remains unapproved.

## Exact versions and models

New presentation extension: **reader-view-1.0**. Saved report **document-report-1.3**,
workflow/plan/evidence 1.0, plan normalization 1.2, group input 1.1, document judge 1.0,
document validator 1.2, reporting position 1.0. Clinical query-plan **1.6**, position
**1.8**, question policy **2.1**, judge prompt **2.15**, semantic prompt **2.7**, verdict
policy **1.4** remain unchanged.

All active providers remain Paratera: planner/extraction/Judge 1 **DeepSeek-V4.1-Flash**,
Judge 2 **Qwen3.5-Plus** (provisional), Judge 3 **GLM-4.7**, validator **Qwen3.8-Flash**
with thinking disabled. No model/configuration change and no paid calls in this task.
