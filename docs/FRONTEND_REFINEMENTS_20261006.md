# Gradual frontend refinement, second pass

## Interface

- Smaller supplied logo: 224px desktop, 180px small screens; left-aligned and
  vertically centered in the header.
- Loading uses a floating scan/lens, moving document lines and phase-specific
  motion. A compact seven-stage rail replaces numbered checkmarks. Stage headings
  and the real step indicator receive stronger type hierarchy. Actual backend
  progress controls every state; no invented percentage or timing. Persistent
  nodes preserve animation between polls; reduced motion disables the effects.
  Follow-up correction: preceding milestones fill from the current backend stage
  when the analysis completion list lags. Filled dots and animated connector
  overlays now reach the active milestone instead of leaving gaps.
- Repeated generic NEI paragraphs are removed. The saved explanation remains,
  followed by up to three source-validated model findings for that specific claim.
  Citation anchors link each finding to the corresponding source card without
  reloading the report.
- Exact cited quotations receive a distinct inset treatment and text emphasis.
  Full source passages remain available in expandable context, with every
  character preserved. Highlights are literal quoted spans from successful source
  attributions. Where those are absent, a conservative structural rule can quote
  an entire sentence explicitly written as the source's own findings/conclusion.
  These are labeled as source conclusions, not new decisive proof. No keyword
  similarity or claim-direction inference chooses a highlight.

## Case-specific presentation data

New read-only endpoint:
`GET /v1/analyses/{analysis_id}/claims/{claim_id}/report/reading-guide`.

It uses the existing report provenance/release check, named frozen artifacts and
exact `audit_matches25` reconstruction. Only qualified, source-supported findings
whose complete unit set is visible in that report may appear. Historical/failed
assessments cannot supply a new explanation. Quotes belong to those exact units.
The frontend also checks the verdict ID and report semantic hash before displaying
the response. Missing/unavailable guide data does not hide the saved report.

This endpoint does not re-run models, retrieve sources, rebuild a historical
report, qualify findings, aggregate evidence or change a verdict. Saved report
contracts/hashes, medical logic, prompts and model configuration are unchanged.
The reader can distinguish what a source found from the final claim position.

## Public presentation and runtime

Production frontend builds hide development panels and technical details.
`DEBUG_MODE=false` disables backend trace responses. Non-production-qualified
reports retain a plain “Verification status” notice explaining that public-release
checks have not been met; their actual qualification is not relabeled.

`APP_ENV` remains development. Strict production currently blocks V2.5 reports
under the existing release gate. A clarification offered public presentation vs.
strict production runtime; no answer was received during this pass. The deployed
public interface keeps verification working while preserving the server gate.
No strict-production activation or production certification is asserted.

## Verification

- Full frontend suite: **64 passed** after the header/progress correction;
  production frontend build passed. Regressions cover a lagging completion list,
  active-stage precedence, and queued states without invented completion.
- Final saved-case/source-quote reading-guide suite: **13 passed**. Four existing
  frozen engineering cases exercise case-specific data without paid calls.
- Relevant backend report/API suite: **35 passed** before the final structural
  source-summary addition; its final regressions above passed separately.
- Ruff passes; mypy passes **178** application source files.
- Both local services rebuilt/restarted while no analysis was running.
- Real existing analysis `baaf532a-c58a-455a-a752-e40140764842`: report and reading
  guide HTTP 200; **three saved case findings, one exact source conclusion**,
  zero unowned/altered highlights; saved report hash unchanged. Guide measured
  4,208ms including audit reconstruction on the checked request.
- Progress reports debug disabled and no development-event payload. Frontend
  HTTP 200. **Zero paid model calls** during this task.

Browser visual QA could not run: neither the in-app browser nor Chrome is enabled
for automation in this session. DOM/behavior/build and real API verification are
complete; visual review of the second pass remains open.

Final image config digests:

- frontend after header/progress correction: `sha256:7444f63d604c1f43b98a19aa60641ce43e3d7879d416f5e39bc2f97177788d45`;
- backend: `sha256:68631891f33769beaa0779c3f3912cc2256382d200239640cec614d7dba13188`.

Medical versions remain V2.5/quantities V2.4, query-plan 1.6, validated position
1.8, question-evidence policy 2.1, semantic prompt 2.7, judge prompt 2.15, verdict
policy 1.4, approved manifest 1.1 and citation preflight 1.1. Active models remain
Paratera DeepSeek-V4.1-Flash extraction/J1, provisional Qwen3.5-Plus J2, GLM-4.7
J3 and Qwen3.8-Flash validator with thinking disabled.
