# Context-aware document mode and analysis 326b6a1c repair

Local development/evaluation results, 2026-10-08. Production qualification remains
false. This implements the document-mode request, including the existing vanilla
TypeScript/Vite frontend; it is not a clinical validation or production certification.

## Exact failure and subsequent fixes

Analysis `326b6a1c-c1e4-4960-a036-bf3e2c173224` failed after one successful
13,099-ms planner response. OCR had succeeded at 96.37%. The exact exception was
`ValueError: Group attribution does not match assertion study`:
commentary assertions A8/A11 retained study S1 while discussion group G2 had no
study ID. Factual ownership and non-evidentiary commentary were incorrectly
treated alike. The saved response also attached the uniquely grounded reference
“The analysis” to A5 although its literal location belonged to A4, and omitted
trailing punctuation from assertion spans.

Factual study ownership still fails closed. Commentary keeps its original study
attribution and produces an audit warning instead of crashing the whole plan.
Reference ownership is repaired only for a unique literal location inside exactly
one assertion. Contiguous trailing punctuation is retained; words, numbers,
negation and ambiguous references are never synthesized. The exact saved planner
response now replays with 11 assertions, seven factual checks, preserved original
coverage and grounded context links. Historical failed analyses are not rewritten.

Full live testing then exposed other generic document-contract defects:

- Count only ready factual claims against the approved-source adapter's eight-item
  group limit; keep commentary in the plan/report.
- Remove repeated abstracts/reference lists from prompts and encode the complete
  quantity catalog as a lossless columns/rows table. All frozen units, quantity
  IDs, values, offsets, ownership and unknown entries remain available.
- Treat assertion coverage as guaranteed inclusion, not an exclusive citation
  allowlist. Exact frozen source ownership, semantic relevance and scope checks
  remain mandatory.
- State the grouped JSON array shape explicitly, include the provider-required
  word JSON, and require full qualitative sentences and strict boolean dependency
  flags. Accept only one exact outer JSON fence in the new input contract; no
  prose, wrong envelope, foreign IDs, null boolean or corrupt item is salvaged.
- Separate reporting source attribution from clinical semantic axes. Report facts
  can be source-validated without pretending an observational study proves causation.
- The final validator contract returns frozen source/quantity IDs, not generated
  quotes. The backend materializes literal quotations from those units. Previous
  contracts retain their original literal-quote acceptance rules.
- Under the new contract, a purported numeric match cannot select a mixture of
  incompatible point values and pass merely because one equals the claim. Preserve
  OR/HR/RR, bounds, direction and source-quantity checks.
- Retry a transient validator connection/429/5xx failure at most once within one
  shared 75-second deadline. Do not retry schema/citation defects or ordinary 4xx
  failures. Record both attempts and audit the selected final response.
- Clarify that a completed judge item means assessable attributed findings, not a
  true claim. Unsupported or noncomparable assertions can still have valid findings.

No model change, medical threshold relaxation, per-claim exception, verdict cache,
quorum reduction or production-gate change was made.

## Delivered workflow

Paragraph-sized inputs (at least 250 characters and two sentences) use one
versioned document plan. Every source character remains represented by exact
assertion spans or an explicit unresolved item. Related study assertions share
source identification, bounded approved retrieval, full-text methods/results/table
passages, integrity checks and a frozen evidence snapshot. Literal repeats retain
their spans but share a check; different studies/endpoints remain distinct.

Three blind judge requests run concurrently, with at most three in-flight requests
per provider account. Each judge's validator starts when its own response is ready.
Database checkpoints use separate short-lived sessions. Slow/failed siblings do
not cancel valid results. Groups run serially and share public-source retrieval
reuse; model assessments are never cached. Transport queue wait is distinct from
provider latency.

One readable document overview contains expandable topics/assertions, source
identity/uncertainty, source reporting, exact citations, scientific interpretation
limits and honest unavailable details. Reporting fidelity and clinical conclusions
are separate. There is no averaged score or forced document verdict. Partial
progress preserves disclosure/focus state. Development notices/raw-response copy,
consent/redaction, screenshot review, 24-hour retention and production gates remain.
Ordinary short claims retain their existing pipeline.

Append-only document artifacts are hash-bound to the analysis, plan, shared evidence
and judge slot. GET reconstructs source provenance and deterministic qualification
offline; mismatched parents, modified replies/quantities or changed results return
503. Read-time audits cannot trigger retrieval or model calls. Partial reports use
only parents present at the saved report's timestamp.

## Versions and active models

| Component | Version |
| --- | --- |
| Document workflow / plan / evidence / report | 1.0 |
| Document planner prompt | document-planner-1.1-2026-10-08 |
| Group model input | document-group-input-1.1 |
| Group judge contract | document-judge-1.0 |
| Group validator contract | document-validation-1.2 |
| Reporting position | reporting-fidelity-position-1.0, dispatched by validator contract |
| Quantity table transport / quantity catalog | source-quantity-table-1.0 / source-quantity-catalog-1.0 |
| Database migration | 20261007_0019 (head) |
| Existing clinical architecture / quantity transport | V2.5 / V2.4 |
| Existing query plan / evidence position / question policy | 1.6 / 1.8 / 2.1 |
| Existing semantic prompt / judge prompt / verdict policy / Pack | 2.7 / 2.15 / 1.4 / 1.5 |

Provider base remains `https://llmapi.paratera.com/v1`:

| Role | Active model |
| --- | --- |
| Extraction/document planner | DeepSeek-V4.1-Flash |
| Judge 1 | DeepSeek-V4.1-Flash |
| Judge 2 | Qwen3.5-Plus (provisional) |
| Judge 3 | GLM-4.7 |
| Semantic/reporting validator | Qwen3.8-Flash, thinking disabled |

APP_ENV=development and DEBUG_MODE=true. Historical group-input 1.0 and validator
1.0/1.1 audits keep their original behavior; older V2.4/V2.5 records are unchanged.

## Before/after real web API flow

Both final requests used the complete primary UK Biobank paragraph, consent and
normal POST/poll/document GET API path. The repeat performed fresh model calls;
only public-source caches were reused. One final wording clarification between
runs corrected completed-versus-unavailable semantics and reduced repetitive
validator prose. Source/quantity rules and quorum were identical.

| Metric | Original atomic analysis | Grouped primary | Grouped repeat |
| --- | --- | --- | --- |
| Analysis ID | df65e1bc-261f-42b2-b3ae-b08fa839ad9a | 2d52018e-90e6-446b-b167-85f8c278d5c3 | 680690e9-a651-4d51-8526-b4df78d8bcf4 |
| Backend elapsed | 758,228 ms | 130,197 ms | 112,217 ms |
| Client flow incl. polling/final audit | Not retained | 147,667 ms | 129,353 ms |
| Investigations | 5 disconnected claims; 4 packs | 11 assertions; 1 study group | 11 assertions; 2 planned groups, 1 retrieved/evaluated |
| Factual checks completed | Different atomic target | 6 of 7 | 7 of 8; remaining interpretation explicitly unavailable |
| Judge attempts | 13 | 3 | 3 |
| Validator attempts | 11 | 3 | 3 |
| Planner attempts | Not included in dedicated old counters | 1 | 1 |
| Final requests | At least 24 judge/validator attempts, planning additional | 7 | 7 |
| Extra attempts in final run | 1 judge retry | 0 | 0 |
| Judge input/output tokens | 178,748 / 11,792 (11/12 usage coverage) | 104,072 / 5,108 | 104,059 / 6,600 |
| All recorded model input/output tokens | Validator usage not in dedicated old columns; total not comparable | 232,275 / 18,014 | 233,676 / 18,220 |
| Actual source HTTP attempts | Not instrumented; unknown | 59 | 10 |
| Retrieval elapsed | Not retained in this export | 27,965 ms | 8,001 ms |
| Selected passages / publications inspected | Separate atomic packs | 17 / 51 | 17 / 51 |
| Public document GET | Not applicable | 200, audit verified | 200, audit verified |
| Overall state | partially_completed | partially_completed | partially_completed |

The first new source view shrank from 295,033 to 88,751 JSON characters without
losing its 475 quantities or source units. Cold Crossref enrichment explains much
of the primary/repeat retrieval difference. Logical enrichment calls can be cache
hits; actual source HTTP attempts are counted separately. Billing/cost was not
returned by the provider, so tokens are not presented as an invoice estimate.

The under-90-second backend target was not reached. Provider validator calls
(about 42–59 seconds), the slowest judge, source cache misses and read-time audit
work remain the main latency contributors. No checks were removed to meet a target.

## Actual concurrency (repeat, UTC)

| Chain | Judge start → finish | Its validator start → finish |
| --- | --- | --- |
| 1 | 11:28:00.808 → 11:28:15.997 | 11:28:18.427 → 11:29:02.736 |
| 2 | 11:28:00.814 → 11:28:41.525 | 11:28:44.033 → 11:29:25.776 |
| 3 | 11:28:00.819 → 11:28:44.038 | 11:28:46.153 → 11:29:28.804 |

All three judges overlapped. Validator 1 began while judges 2/3 were in flight.
Validators also overlapped. Account queue waits were 2–4 ms. Old atomic retained
timestamps show serial judges, followed by serial validators, across separate claims.

## Per-assertion results

These are study-reporting evaluations, not general medical advice.

| Detail | Primary | Repeat |
| --- | --- | --- |
| Over 470,000 UK Biobank participants | Supported reporting | Supported reporting |
| Study examined sunscreen and skin cancer | Supported reporting | Supported reporting |
| Reported higher skin-cancer associations among users | Supported reporting | Supported reporting |
| “Up to 292% increased risk” of invasive melanoma | Unable: Qwen declined a finding; only two qualified high-risk assessments | NEI: three validated assessments, two noncomparable-measure NEI positions and one reporting-mismatch contradiction |
| Higher basal/squamous cell carcinoma associations | Supported reporting | Supported reporting |
| Reported adjustment variables | Supported reporting | Supported reporting |
| Study describes sunscreen/skin-cancer associations | Supported reporting | Supported reporting |
| Biggest-study/discussion/source-description prose | Retained commentary | Retained commentary |
| Unattributed expert explanation about application/behavior | Retained commentary | Unavailable interpretation: unresolved/nonclinical reference; not dropped or forced into a factual vote |

The numeric detail is not accepted as an exact risk increase by treating an odds
ratio as a risk ratio. Validators disagree about mismatch versus noncomparability;
the existing policy yields NEI on the repeat. Every public detail has a result or
explicit commentary/unavailable status. Scientific caveats identify the study's
observed exposure and potential confounding; reporting support is never presented
as proof that sunscreen causes skin cancer.

## Failed attempts and bounded probes

Earlier failed runs remain retained: b98df58b (planner spans), 326b6a1c (commentary
ownership), 139d0c77 (large packaging/JSON/fence/boolean/citation defects), 0f83a836
(commentary counted in approved-source bound), af273d98 (array envelope and
reporting-target/generated-quote defects), bcf44616 (punctuation-only findings plus
validator connection closures). The latter includes a long host/network interruption:
UTC timestamps and process monotonic latency disagree; its 967,312-ms wall time is
not used as a stable speed benchmark.

One failed Qwen transport replay verified the provider's missing-JSON-word error.
A two-call frozen Qwen judge/validator probe verified array compliance and exposed
literal-quote defects. One validator-only replay, reusing that saved judge output,
then completed all six items without contract failures: five reporting support and
one noncomparable-measure NEI. No retrieval was rerun for those model probes.
The final two full runs each used exactly seven model calls with no retries.

## Regression verification and limitations

Final full PostgreSQL-backed backend suite: **1,469 passed, 0 failed, 0 skipped**
in 257.77 seconds with `RUN_DB_TESTS=1`. The initial complete run found one fixture
inheriting the active DEBUG_MODE=true; explicitly fixing its public-response setting
made the final rerun green. Four existing Starlette deprecation warnings remain.
Frontend: 94 passed; TypeScript and Vite production build passed. Ruff passed;
mypy passed for 196 application modules. Backend/frontend rebuilt and migration
0019 applied. Backend `/healthz`, the frontend analysis route, and both old/new
document audit GETs return HTTP 200. Browser inventory was empty, so visual browser QA was unavailable;
DOM/component and real HTTP-flow checks are recorded instead.

Regression coverage includes the exact saved 326 planner response, punctuation and
unique link ownership, retained ambiguity, literal repeats, separate studies,
unrelated claims, method/sample checks, mixed factual/commentary adapter bounds,
shared hashes and lossless quantities, wrong/duplicate/missing IDs, foreign units
and quantities, corrupt envelopes, one failed judge, false adjustments/statistics,
contrary trials versus accurate observational reporting, numeric-measure and bound
guards, source-attribution failure, separate clinical/reporting targets, historical
validation/source-view dispatch, read-time tampering, independent concurrency,
transport retry deadlines, database persistence/privacy, single-claim paths and UI
disclosure/progress/XSS/development-gate/copy behavior.

Source identification matched PMID 37642678 / PMC10840669 using study/cohort and
exposure/endpoint clues. No exact publication ID was supplied, so that discrepancy
remains visible. Candidate search is bounded at 12 queries/50 fetched PubMed IDs;
unfetched candidates and inaccessible supplements/figures are explicitly recorded.
Group study identity is evidence-based, not hardcoded to the sunscreen paper.

Retained metrics: [before](DOCUMENT_MODE_METRICS_BEFORE_20261008.json),
[primary](DOCUMENT_MODE_METRICS_PRIMARY_20261008.json),
[repeat](DOCUMENT_MODE_METRICS_REPEAT_20261008.json).
Full public/development projections: [primary](DOCUMENT_MODE_LIVE_FINAL_PRIMARY_20261008.json),
[repeat](DOCUMENT_MODE_LIVE_FINAL_REPEAT_20261008.json).
