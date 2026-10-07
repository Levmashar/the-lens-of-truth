# Source-bound citation preflight repair (2026-10-06)

Original analysis: `0dd023b0-bffb-4c60-863a-37dce0e04437`.
Claim: “Soy regular usage increases estrogen levels in male body.”

The six saved judge attempts failed because the backend interpreted the scientific
abbreviations **E1 (estrone) and E2 (estradiol)** as evidence citations. These
abbreviations occur in the actual frozen abstract `E7.U1`. Every structured unit
and quantity reference in the six responses was valid. No model, prompt, retrieval,
selection, semantic policy, threshold or production-gate change was needed to
repair this citation failure.

## Exact original exception and replay

The old guard extracted every bare `E` followed by digits from statement text
and conclusion justification, then required these tokens to be cited evidence
IDs. Its exception was `DecisionFailure("invalid_evidence_citation")`. The old
rejected-attempt records retained raw responses but not the precise defect;
the statement/field locations below were reconstructed from those responses.

| Judge | Attempt | Fields containing the falsely rejected E1/E2 tokens | Old result | Fixed replay |
| --- | --- | --- | --- | --- |
| DeepSeek-V4.1-Flash | 1 | S1.text, S2.text | invalid_evidence_citation | citation-valid |
| DeepSeek-V4.1-Flash | 2 | S1.text | invalid_evidence_citation | citation-valid |
| Qwen3.5-Plus | 1 | S1.text, conclusion.justification | invalid_evidence_citation | citation-valid |
| Qwen3.5-Plus | 2 | S3.text, conclusion.justification | invalid_evidence_citation | citation-valid |
| GLM-4.7 | 1 | S2.text, S3.text, conclusion.justification | invalid_evidence_citation | citation-valid |
| GLM-4.7 | 2 | S2.text, S3.text, conclusion.justification | invalid_evidence_citation | citation-valid |

All six responses retain their original bytes and SHA-256 hashes. Frozen input
and prompt hashes reconstruct exactly; replay made no paid calls or database
changes. Original failed analyses and rejected-attempt rows were not rewritten.
The V2.5 contract does not require a model label; these replies have no advisory
label to repair.

## Evidence, units, quantities and dispatch

Selected evidence: `E7`, `E15`, `E9`. The frozen judge-visible set additionally
contains the corresponding title passages: `E46`, `E35`, `E51`.

| Allowed unit | Publication | Passage |
| --- | --- | --- |
| E7.U1 | pubmed:33383165 | abstract |
| E46.U1 | pubmed:33383165 | title |
| E15.U1 | pubmed:11603644 | abstract |
| E35.U1 | pubmed:11603644 | title |
| E9.U1 | pubmed:14628433 | abstract |
| E51.U1 | pubmed:14628433 | title |

The 19-item `source-quantity-catalog-1.0` rederives exactly from these frozen
units. Every saved quantity belongs to a unit cited by its own statement. The
six saved responses need **zero parent/child ID normalizations**. Duplicate
publications are distinct abstract/title passages with their own IDs and hashes;
publication identity does not authorize borrowing a sibling passage or quantity.
V2.5 materialization/dispatch is correct. The failure occurs afterward in the
prose citation guard, not in pack selection, ownership or contract dispatch.

## Generic code change and diagnostics

`evidence-citation-preflight-1.1` uses each finding's exact materialized frozen
quotations to distinguish source vocabulary from bare citation-shaped tokens.
This contains no hormone dictionary or claim-specific branch. The exemption
does not apply to explicit citation syntax, such as `[E2]`, `source E2`,
`E2 reports`, `E2's findings`, or unit/quantity IDs. Prose unit/quantity references
must belong to that finding. Conclusions can use only sources from their declared
statement dependencies. Both ordinary and qualitative prose fields are checked.
Raw PMID/DOI citations remain rejected. Historical contracts through V2.4 keep
their original acceptance behavior.

Unknown, duplicate, cross-unit, sibling and corrupted-catalog references remain
invalid. Materialization retains the original exception categories and exact
unit/quantity/hash checks. Rejected attempts now persist:

- citation-preflight version;
- exact statement ID and reference field;
- offending evidence/unit/quantity ID;
- expected allowed IDs and ownership IDs where applicable;
- underlying exception type and precise message.

The added diagnostics contain IDs and validation messages, not statement text,
requests or credentials. They are sanitized before persistence. Existing raw
development responses remain available under the existing capture controls.

Changed implementation: `backend/app/judging/service.py` owns versioned prose
preflight and rejected-attempt recording; `source_units.py` and
`source_quantities.py` attach exact reference ownership diagnostics;
`citation_errors.py` supplies shared typed defects without changing existing
ValueError/KeyError category behavior. No evidence-pack or validator payload
rewrite is used.

## Fresh full frontend-path run

Fresh analysis: `baaf532a-c58a-455a-a752-e40140764842`.
Submitted through the normal HTTP frontend API flow; extraction, normalization,
retrieval, source selection, judging, semantic validation, qualification,
aggregation and report serving all ran. Report HTTP status: **200**.

| Stage/result | Original | Fresh run |
| --- | --- | --- |
| Judge citation preflight | 0/3 usable, six rejected attempts | 3/3, first attempt each |
| Semantic validator | never called | 3/3 completed |
| Source attribution | not reached | all 12 findings validated |
| Qualified assessments | 0/3 | 3/3 |
| Final public result | Unable to Verify Reliably | Not Enough Evidence |

Seven paid calls: one extraction, three judges and three paired semantic checks.
There were no citation retries. Recorded progress duration: 177.613 seconds.

| Judge | Judge latency | Validator latency | Validated position |
| --- | ---: | ---: | --- |
| DeepSeek-V4.1-Flash | 19.149 s | 46.306 s | not_enough_evidence |
| Qwen3.5-Plus | 44.665 s | 13.738 s | not_enough_evidence |
| GLM-4.7 | 21.697 s | 15.988 s | not_enough_evidence |

The final minor grammar refinements were tested after this live run. On final
deployed source, all three saved live replies remain citation-valid, exactly
match persisted decisions, and pass complete `audit_matches25` reconstruction.
No second paid run was necessary for those grammar refinements.

### Remaining qualification/report limitation

NEI is the actual result, not proof that the underlying medical assessment is
fully resolved. All three positions have `ONLY_INSUFFICIENT_OR_CONTEXT`.
The frozen exposure remains unresolved as “Soy regular usage”; its lexical
guard requires every word, so source descriptions of soy protein/isoflavone
intake trigger `CLAIMED_EXPOSURE_NOT_ESTABLISHED`. This demotes J1 S1/S3,
J2 S1/S2/S3 and J3 S1/S2/S3 despite the validator's aligned male-population axes.
Null findings also carry `nonsignificance_only`, so fixing exposure grounding
alone would not automatically establish material contradiction.

The report's `population_mismatch` explanation is misleading in this run: it
prioritizes J1's weak animal/cell mechanistic S5 population warning over the
exposure guard affecting the main findings. These separate normalization and
report-priority issues are recorded for follow-up. They were not bypassed to
force a result during this citation repair.

## Verification and exact versions

Added **88 citation regressions**, including all six original frozen responses,
source-token collisions, explicit invalid citations in all four prose fields,
local ownership, conclusion dependencies, duplicate publications, ambiguous
parent IDs, catalogue corruption, diagnostics persistence and historical labels.
Final deployed full backend suite: **1,154 passed, zero failures/skips**, including
PostgreSQL tests, in 565.54 seconds. Two existing dependency deprecation warnings
remain. Frontend: **56 passed**, production build passed. Ruff passes; mypy passes
all 177 application source files. Final live saved audit replay: **3/3 exact**.
After the final restart and suite, health and saved report both return HTTP 200;
the saved analysis remains completed with NEI.

Versions unchanged except citation preflight: V2.5 / validation contract 2.5;
V2.4 structured quantities; quantity catalog 1.0; query-plan 1.6; validated
position 1.8; question-evidence policy 2.1; semantic prompt 2.7; judge prompt
2.15; verdict policy 1.4; approved-source manifest 1.1; citation preflight 1.1.

Active models unchanged, all through Paratera:

- extraction / Judge 1: DeepSeek-V4.1-Flash;
- Judge 2: Qwen3.5-Plus (provisional);
- Judge 3: GLM-4.7;
- semantic validator: Qwen3.8-Flash, thinking disabled.

Final local backend image config digest:
`sha256:c289ab222f31bbe46a5564d5d91429c887bac464e4145caee0b41150a490a47a`.
Backend rebuilt/restarted. Existing development-only V2.5 production gates remain
in force; this repair and one successful operational rerun are not production
certification. See the adjacent JSON for exact replay hashes and owned IDs.
