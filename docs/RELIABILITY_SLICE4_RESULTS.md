# Reliability Slice 4 — bounded investigation and implemented probes

## Continuation outcome (2026-10-02; additional ceiling reached)

Implemented winner: **V2 decision 2.2**, compact development prompt 2.11, one
Gemini Lite dual-target semantic request per parsed judge, unchanged qualifier,
three current judge slots, current Slice 3 selection. V3 was rejected, not
integrated. No `.env`, key/account/URL, production count/qualification, extraction,
MeSH/PICO, source selector or clinical label rule was changed. This is a delivered
bounded engineering repair with **partial final semantic acceptance**, not a
clinical release or a successful clean repeatability gate.

### Request accounting and exact call explosion

**120/120 additional model requests initiated; no more paid requests permitted
in this continuation.** Atomic SQLite reservations precede HTTP transport and
survive restarts. Both the API server and evaluation modules shared
`runtime/slice4-continuation-20261002.sqlite3`. All received HTTP 200, including
schema/semantic failures. Totals: 72 judge requests, 39 joint checks, 8 extraction
requests and 1 V3 decisive checker. Requested models: Ling 34, Luna 28, Lite 58.
Tokens/latency are recorded when returned; no money, credentials or prompts are
stored in this counter. An exhausted counter is not reset or refunded.

Retained smoking `1d0f0c50-2a27-4531-90bb-069b30b67c45`:

| Post-retrieval operation | Requests |
| --- | ---: |
| Initial judges | 3 |
| Initial statement attribution (6 + 2 + 5 findings) | 13 |
| Initial relation batches | 3 |
| Semantic judge revisions | 3 |
| Revision statement attribution (6 + 2 + 5 again) | 13 |
| Revision relation batches | 3 |
| Total judging/validation | **38** |

These are not 38 essential independent votes. Per-finding attribution and
revalidation of revised findings dominate. Backend-owned units eliminate quote
copying, NOT the need to check paraphrases. Source attribution and relation are
both retained, now in one request per judge. Four saved normal cases had 12
semantic revisions, only 3 usable (25%); development revisions are disabled.
The old debug unique-call counter omitted extraction (no extraction call_id):
38 is explicitly POST-retrieval, not a complete HTTP total. The new persistent
counter includes extraction and all schema retries.

### Every known false-decisive V3 pattern

Old one-hour raw bake-off responses expired. They were NOT recovered or given a
new TTL. Earlier aggregates identify the following cases/models/outcomes; tests
are honestly **reconstructed response-pattern fixtures**, not original responses.
Fresh focused V3 responses below reproduce some failures without pretending to
recover the expired records. All control sources are synthetic, not publications.

| Pattern / exact frozen unit | Earlier failure | Root classification / failure point |
| --- | --- | --- |
| `X increases Y risk.` / `The randomized estimate for Y was RR 1.10 (95% CI 0.40-3.00), nonsignificant.` | Ling derived Contradicted instead of insufficient | A/B/E/G: wrong relation and decisiveness; derivation ignored null reason consistency |
| `X increases Y.` / `A randomized high-dose X trial increased incident Y; lower doses were not tested.` | Lite and Gemini Pro derived Supported instead of benchmark NEI | B/C/E, also H: broad-wording annotation is provisional; scope limits were promoted to decisive |
| `X increases Y.` / `One randomized X-placebo trial increased Y; another trial reported opposite findings.` | Ling derived Contradicted instead of uncertain | A/B/E/G: combined conflict became one selected direction |

Original expired evidence_basis/reason/scope fields are unavailable where not
preserved in earlier summaries; do not fill them in as if observed. Fresh exact
responses on those SAME controls:

- Ling wide-null: contradicts, aligned, decisive, randomized_intervention,
  `IMPRECISE_NULL`; hardened result None/SEMANTIC_GUARD_FAILED, reviewed NEI.
- Lite narrow-dose: supports, aligned, decisive, randomized_intervention,
  `DIRECT_FINDING`; preliminary support passed local guards because the model
  also misreported scope. One Luna checker returned invalid; final None, reviewed
  NEI. Ling/Luna returned narrower/supporting and derived NEI.
- Lite conflict: uncertain, aligned, decisive, randomized_intervention, `CONFLICT`;
  guard rejects inconsistent decisiveness. Ling/Luna returned supporting uncertain
  classifications and NEI. The old Ling contradiction is covered by reconstruction.

Generic opt-in V3 guards reject decisive non-aligned/contextual-basis uses,
imprecise-null contradiction and decisive conflict. Existing design/integrity,
actual exposure assignment, numerical and Slice 3 sufficiency gates stay intact.
Guards cannot correct a confidently wrong aligned classification; the non-voting
checker is needed. It runs only after a preliminary Supported/Contradicted,
once per judge, with exact claim/decisive units/metadata. No recursive reviewer.

### Bounded semantic comparison and choice

Focused V3: 6/9 difficult-control positions usable, 0 false decisive, 10 calls;
joint V2: 2/9 usable, 0 false decisive, 18 calls. On the SAME retained real smoking
Pack, joint V2 qualified Luna's NCI causal assessment (1/3); hardened V3 qualified
none (0/3: Ling schema failure, Luna/Lite source-purpose/basis exclusions), 6 vs
4 calls. The authority/schema adoption gate fails; stop V3 early, retain V2.
Do not promote V3 just for fewer calls or infer clinical accuracy from controls.

The additional positive/inverse/carrot/numeric V2 batch had 5/12 usable positions.
Across both synthetic batches: 21 strict judge responses, 7/21 usable, zero false
support/contradiction positions, with significant false rejection. In particular,
numeric distortion remained unqualified rather than becoming false support.
These batches used earlier compact prompt revisions, not one final-version matrix.
Exact denominators: false support 0/18, false contradiction 0/15, annotated
position agreement 5/21, relation/scope agreement each 12/21, materiality 7/21.
Eight of nine expected decisive control positions were not obtained (8/9
provisional false rejection); six numeric issues remained in these pre-final
prompt probes. Report them, not just the zero false-acceptance headline.
The final qualitative contract adds explicit near-response guidance and local
format checks; no optional number is deleted from an immutable response. Models
that keep generating optional statistics fail format validation after one retry.

Validator choices: legacy V2 cascade remains the saved baseline; single joint
Lite retains both targets and catches failed source uses/scope/materiality/omitted
counterevidence at one request. V3 without a checker had known false decisives;
V3 decisive-only checking blocked fresh false support but failed authority/schema
coverage. Joint Lite is the operational choice, not a clinically qualified or
independently proven universally strongest validator. Other judge outputs are
never shown to it. A fresh inverse run revealed correct contradiction wrongly
labeled scope mismatch; prompt 1.1 generically separates direction from scope
and preserves negation. Both 1.0/1.1 remain audit-reconstructible.

Current judge aliases are unchanged: `inclusionai/ling-3.0-flash`,
`openai/gpt-6-luna`, `google/gemini-2.5-flash-lite`; claimed families
inclusionai/openai/google are **identity_unverified**. Prior six-model/held-out
results did not establish a replacement; no broad candidate-model sweep was redone.
Keep the current selector: lean lost a reviewed BP source; no new selector or
source provider was introduced. Earlier oracle comparisons remain diagnostic;
no unnecessary oracle matrix was rerun.

Offline two-vs-three, four new controls, unchanged Lens policy: Lite/Luna yielded
Unable 4/4; adding Ling yielded NEI 2, Contradicted 1, Unable 1, no false decisive.
This complements the earlier 40-control three-family coverage improvement without
claiming independence of gateway aliases or changing production minima.

### Normal HTTP acceptance (all production_qualified=false)

| Input / analysis | Result | Qualified judges | Actual total requests | Elapsed |
| --- | --- | ---: | ---: | ---: |
| Smoking / `5b0d8988-931f-4838-91a1-5af0db75b096` | Supported | 2/3 | 8 | 26.8s |
| Inverse smoking before direction clarification / `52a88c31-efcb-4cdd-9c0c-15e274af8e5f` | Unable | 0/3 | 7 | 24.6s |
| Invasive sunscreen / `d76107f2-d2dc-4a3a-939e-043a14d28aa2` | Contradicted | 2/3 | 7 | 32.8s |
| Carrots / `014c948d-de1f-42fc-9a31-61ec68a66c6e` | Unable | 1 NEI/3 | 7 | 19.1s |
| Clarified inverse / `c1144df2-4aa2-411b-8eb0-c1032450e41d` | Contradicted, existing provisional development rule | 1/3 | 7 | 26.8s |
| Repeated smoking / `f387ac84-cb69-4d4f-99ac-3a919c85cfcb` | worker_interrupted; NOT a medical result | none finalized | 7 including late worker calls | client saw failure at 15s |
| Smoking increases lung cancer risk by 85% / `0b10b1d2-72d1-4e0a-b3d4-5284d5ffe215` | Unable | 0/3 | 8 | 30.8s |

An earlier integration accounting probe `9741b9e1-7208-458d-bdd7-5aca7ab7a346`
used 7 total calls but excluded two valid checks because aggregation required two
HTTP requests. The development-only audited dual-target exception fixes that
accounting assumption, NOT medical/judge-count thresholds. This probe remains
unchanged. Eight normal requests account for 58 paid model calls; frozen probes
account for 62. Debug counts may omit extraction and unfinished late calls; the
atomic ledger is authoritative.

Smoking report used frozen CDC and NCI causal assessment units. Sunscreen used
PMIDs 21135266 and 40876975. Current source selection and immutable Pack hashes
are preserved. Carrot had one qualified NEI, not enough for an NEI ensemble; source
attribution failure/uncertainty excluded others. Numeric claim assessments retained
NUMERIC_UNCERTAIN/missing material evidence, never converted to support. Prior
four normal active qualifications were 3/12; five final completed claims (smoking,
clarified inverse, sunscreen, carrot, numeric) were 6/15. Different case mixes:
this is NOT a paired medical accuracy gain.

The repeated smoking interruption was self-caused measurement interference:
`test_health` created development/production TestClients using the shared database,
triggering startup `mark_interrupted` while the real worker was active. It now
mocks reconciliation/retention side effects. No production recovery code or old
analysis was changed. Original late judge/validation artifacts remain append-only.
No additional paid rerun is permitted at 120. Real three-judge exact-input flip
rates and clean final positive/inverse repeatability therefore remain UNCONFIRMED.
Earlier Lite-only 5-repeat synthetic controls had 0/20 position flips; that is
not a real-world three-judge stability certificate.

### Actual implementation / software verification

New: `validation/joint.py`, evaluation `call_budget.py`/`server.py`, budget Compose
override, joint/budget tests. Updated: judge prompt/service/transport, semantic
adapter, relation audit, verdict audit/accounting, development worker, explicit
acceptance inputs and health-test isolation. No DB migration needed. No frontend
code changed in this continuation. Existing unrelated dirty work is preserved.

Final checks: Docker Python 3.13 backend/PostgreSQL **589 passed**, local **579
passed / 10 DB skips**, Ruff clean, mypy **150 app files**, Alembic head 0018 and
no upgrade operations, frontend **42 passed** plus TypeScript/Vite build, both
Docker images built, diff whitespace checks clean. Software tests use mocks and
are distinct from the 120 paid semantic requests.
The final PostgreSQL run also migrated a new isolated `lens_slice4_tests` database
through head 0018; it did not reconcile live acceptance analyses. The normal
backend is restored without the task-only budget command for user handoff; this
starts no model analysis and does not reset the completed on-disk ledger.

### Exact PowerShell reproduction / handoff

From the monorepo root, normal development configuration (uses existing `.env`):

```powershell
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/healthz
$body = @{ schema_version = '1.0'; client = 'web'; lang = 'auto'; input = @{ type = 'text'; text = 'Smoking causes lung cancer.' }; consent = @{ privacy_notice_version = '2026-09-01'; accepted = $true } } | ConvertTo-Json -Depth 5
$a = Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/analyses -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://localhost:8000/v1/analyses/$($a.analysis_id)"
Invoke-RestMethod "http://localhost:8000/v1/analyses/$($a.analysis_id)/claims" | ConvertTo-Json -Depth 10
```

The POST is a user-initiated future paid analysis, NOT a command executed beyond
this continuation's ceiling. Do not use it to claim an already performed repeat.
Inspect the exhausted counter without paid traffic:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.evaluation.call_budget --ledger ../runtime/slice4-continuation-20261002.sqlite3
.\.venv\Scripts\python.exe -m pytest tests/test_joint_validation.py tests/test_slice4_budget.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
cd ..
```

PostgreSQL checks should use an isolated test database, not an active acceptance
DB. Create once (if it exists already, reuse it; no DROP):

```powershell
docker compose exec postgres psql -U lens -d postgres -c 'CREATE DATABASE lens_slice4_tests;'
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://lens:lens@postgres:5432/lens_slice4_tests -v './backend/tests:/app/tests:ro' backend sh -c 'alembic upgrade head && alembic check && RUN_DB_TESTS=1 pytest -q && ruff check . && mypy app'
cd frontend
npm test -- --run
npm run build
cd ..
docker compose build backend frontend
git diff --check
```

Historical frozen artifacts used here (ignored/private, retention enforced):
`bakeoff-20261002T110938148125.json`, `bakeoff-20261002T111042621670.json`,
`bakeoff-20261002T111220315657.json`, `bakeoff-20261002T111357771964.json`,
`acceptance-20261002T111811652312.json`, `acceptance-20261002T112230447277.json`,
`acceptance-20261002T112531175429.json`. After their original TTLs expire, use
the explicitly synthetic fixtures; do not recover or silently TTL-extend them.

## Initial investigation report (historical, superseded decision above)

Date: 2026-10-02. **Adoption gates did not pass; complete final acceptance is
still open.** No medical policy, normal judge contract, extraction/MeSH/PICO,
production qualification or local configuration was changed. This report
separates implemented evaluation tools, measured results and unperformed work.
See [JUDGE_BAKEOFF_RESULTS.md](JUDGE_BAKEOFF_RESULTS.md) for model/metric tables.

## 1. Confirmed baseline failure decomposition

Retained original smoking `9400e193-32c4-483d-b136-d14c2dbbc56c` actually ended
Supported through the existing single-validated-assessment development rule.
Only Luna qualified; claiming it ended Unable would be inaccurate. Retained
skin-cancer `4e574a81-1aaf-49db-8f5d-e942c29e7298` ended Unable; Ling invalid,
Luna NEI validated, Gemini unable. Captures are read-only originals, not recreated
historical runs. Expired artifacts are refused, not recovered or granted new TTLs.

Exact NUMERIC_UNCERTAIN causes were inspected before implementing probes:

- Smoking E69.U1 included CDC ratios/multiples (`9 out of 10`, `25 times`) and
  reference-marker numerals. Optional judge-generated findings repeated these;
  the existing parser could not confidently type/bind all asserted numerals.
- Smoking E11.U1 described a 20% reduction and CI .71–.90 alongside other RR
  comparisons. Ling emitted inferred RR .80, which was not printed in that exact
  source unit; magnitude binding could not establish it among other estimates.
- Sunscreen E31.U1 was a vitamin-D/SPF endpoint, not cancer. Judge findings
  introduced `D3`, `25(OH)D` and SPF numerals into relied-on statements, creating
  parser uncertainty plus endpoint/context dilution.

Source numbers alone are not model assertions. The current protocol still lets
optional *generated findings* become essential conclusion premises. Neither
disabling numeric checks nor silently deleting failed statements is a safe fix.
Existing V2 already uses backend-owned quotations; V3 additionally prohibits
model-written findings/statistics, rather than rebuilding the attribution split.

## 2. Implemented changes

New modules:

- `app/adapters/model_catalog.py`: sanitized configured catalog discovery;
  chat/search filtering, exact supported IDs, no credentials in returned metadata.
- `app/evaluation/artifacts.py`, `freeze.py`: exclusive sanitized ignored-runtime
  artifacts and read-only explicit retained-analysis export with expiry guards.
- `app/evaluation/cases.py`: fixed 40-case conditional suite, opaque source IDs,
  stable Pack hashes, fixed 30/10 split; expected annotations never enter prompts.
- `app/evaluation/source_suite.py`, `oracle.py`, `selection.py`: source-grounded
  public controls and evaluation-only lean/manual-source subsets. Original text,
  document metadata, units and provenance remain intact; subset hashes change.
- `app/evaluation/judge_bakeoff.py`: opt-in bounded V2/minimal-V2/V3/checker
  measurements, safe row call/token accounting, per-response append-only
  checkpoints, explicit preparation failures and incomplete planned-row counts.
- `app/evaluation/results.py`, `ensemble.py`: offline metrics, identical-input
  repeatability and one/two/three V2 subsets through unchanged audit/policy checks.
- `app/evaluation/end_to_end.py`: normal frontend HTTP contract, resumable control
  offset, bounded admission of new analyses. An already-admitted analysis may
  exceed the observed-call admission cap; this is NOT a server-wide call limit.
- `app/judging/v3.py`: strict unit-only relation/scope/materiality/basis/reasons;
  pure local identity/hash/integrity/design/numeric checks and position derivation;
  optional one batched decisive, non-voting checker.
- `tests/test_reliability_slice4.py`: offline safety/protocol/retention regressions.

Small changes to existing modules:

- `adapters/judge.py` chooses the V3 schema only for a V3 evaluation input and
  parses safe response identity metadata. V2 remains the normal path.
- `judging/models.py` adds optional provider-response fingerprint/response ID.
- `judging/prompt.py` exposes evaluation-only `prepare_minimal_v2`; the default
  prompt is unchanged. `judging/service.py` records the prepared prompt version.
- `validation/evaluation_budget.py` counts per-row calls/tokens, retains only
  bounded safe identity/usage metadata and stops sweeps after quota exhaustion.

No migration is needed: probes write ignored development artifacts, not normal
judge rows. No V3 endpoint, public schema change, production flag, environment
key or frontend redesign was introduced. The migration at head `20261001_0018`
and other dirty files predate this slice and were preserved.

## 3. V3 derivation and unresolved safety

Model output has no quote, new PMID/DOI/URL, statistic, free medical finding or
top-level verdict. Backend-owned protocol metadata is not requested from models.
Every supplied source/unit is checked against the exact frozen Pack, source
ownership, passage/document hashes, text offsets, accepted integrity and actual
exposure assignment/purpose. Unknown IDs are fatal operational defects.

Python reuses question-evidence/conclusion qualification for exact claim type,
scope, integrity and design. Submitted numeric claims still undergo deterministic
numeric comparison. Provider/schema/reference failures stay operational inability,
not scientific NEI. The checker cannot create relations, prose or extra votes.

This is an implemented **probe**, not an approved repair of the normal pipeline.
V3 still accepted some erroneous semantic direction/materiality classifications
on imprecise null and narrow-scope controls. Required cross-check/scope safety,
complete measured model selection and final stability gates remain unpassed.

## 4. Normal frontend-contract acceptance, unchanged configuration

These requests used normal `/v1/analyses` with web consent/input shape, extraction,
retrieval, configured three judges, normal validators/revisions and reports.
This was actual backend HTTP acceptance; no controllable browser surface was
available, so visual browser acceptance was **not** claimed.

| Claim | Analysis ID | Development result | Observed model calls | Elapsed |
|---|---|---|---:|---:|
| Smoking causes lung cancer | `1d0f0c50-2a27-4531-90bb-069b30b67c45` | Supported | 38 | 77.273 s |
| Regularly smoking cigarettes causes lung cancer | `b9dd302b-1c33-4261-b2de-dbf20f8f72f5` | Supported | 41 | 81.221 s |
| Smoking does not cause lung cancer | `f86f9f95-a7d0-4247-bf83-3c71700d084d` | Contradicted | 36 | 65.048 s |
| Frequent sunscreen use causes invasive melanoma | `b8d43a7b-d75f-48bc-9b64-e4b60ea5f450` | Unable | 40 | 95.546 s |

All were technically completed and **none production qualified**. The configured
models remain Ling / Luna / Gemini Flash-Lite, with unverified underlying identity.
Every case produced three initial responses and three append-only revisions.
Smoking/regular active positions were all Supported, but only Luna's revision
validated. Inverse active positions were all Contradicted; only Ling's revision
validated. Their final decisive labels relied on the pre-existing provisional
single-decisive rule, NOT newly reduced thresholds.

Invasive sunscreen active positions: Ling Contradicted, Luna NEI, Gemini NEI.
All three active revisions were unable to validate with NUMERIC_UNCERTAIN.
The result is operational inability, not proof of harm or absence of sources.
The original rows and revisions were exported read-only before their retention
expires; none was edited or silently replaced.

Broad skin cancer, BP/stroke, Vitamin C, carrots and the soy pair were frozen for
source/probe evaluation but **not run as final normal HTTP acceptance** in this
bounded continuation. The 120-call admission cap stopped new analyses after the
fourth finished at 155 observed calls. Five repeats for all three judges and the
final Lens verdict on real frozen smoking/inverse/sunscreen/carrot/numeric packs
also remain unrun. Synthetic Lite-only stability is not a substitute.

## 5. Safety/error conclusions and selections

The corrected clean eight-case pilot observed no false decisive V2 position,
but V3 Ling falsely contradicted an imprecise null. The complete minimal-V2 set
observed one shared false support per model (1/32 negative-support opportunities)
and no false contradiction (0/34). Missed provisional decisive annotations were
5/14 Ling, 6/14 Luna, 2/14 Lite. No independent clinical false-rejection rate exists.

In the repeat subset, both architectures wrongly classified the numeric-distortion
relation as support 5/5, but backend magnitude checks blocked all decisive positions.
For real unannotated cases, false-acceptance/error rates are **unknown**, not zero.

Selected normal configuration is the existing baseline: V2/current selection/
current validator strategy, original three claimed model families. No `.env`
changes. V3/minimal-V2/lean and replacements were not adopted because the specified
safety/recall/paired held-out gates failed or were not established. The normal
3–6-call goal is unmet; 36–41 observed calls/claim is a confirmed blocker.

No after-integration speedup can be claimed. Probe speedups are reported separately
in the bake-off document. Existing production 2 standard / 3 high-risk qualified
judge minimums, identity/isolation/approval gates and append-only audit constraints
remain unchanged. No fabricated claim-specific medical labels were introduced.

## 6. Software verification

After the last source changes:

- Docker Python 3.13, full backend + PostgreSQL/append-only tests: **575 passed**.
- Local Python 3.14: **565 passed, 10 DB-gated skips**; the Docker run covers DB tests.
- New Slice 4 regression file: **28 offline tests** included in those totals.
- Ruff `check .`: passed; mypy `app`: passed, 147 source files.
- Alembic: head `20261001_0018`; `check` found no new upgrade operations.
- Frontend: **42 passed**; TypeScript/Vite production build passed.
- Backend/frontend Docker builds passed; rebuilt services were restarted.
- `git diff --check`: passed. Existing unrelated dirty work was not reverted.

Software tests are offline and separate from live paid evaluation. Deprecation
warnings from Starlette/HTTPX and HTTP 422 names do not indicate test failures.

## 7. Exact reproduction commands (PowerShell)

From repository root; these do not print `.env` or credentials:

```powershell
Set-Location 'C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth'
docker compose build backend frontend
docker compose up -d postgres redis backend frontend
docker compose run --rm --no-deps -v './backend/tests:/app/tests:ro' backend sh -c 'alembic current && alembic check && RUN_DB_TESTS=1 pytest -q'
Push-Location backend
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
.\.venv\Scripts\pytest.exe -q
Pop-Location
Push-Location frontend
npm test
npm run build
Pop-Location
git -c core.safecrlf=false diff --check
```

Read-only capture of a retained normal analysis, no paid model calls:

```powershell
docker compose run --rm --no-deps -v './runtime:/app/runtime' backend python -m app.evaluation.freeze --runtime /app/runtime --analysis b8d43a7b-d75f-48bc-9b64-e4b60ea5f450
```

Catalog discovery plus latest retained baseline export (GET catalog, not completions):

```powershell
docker compose run --rm --no-deps -v './runtime:/app/runtime' backend python -m app.evaluation.freeze --catalog --runtime /app/runtime
```

Paid opt-in examples, **not automatically part of tests/CI**. These are bounded
small reproductions, not commands that silently finish the full outstanding matrix:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.evaluation.judge_bakeoff --run --model google/gemini-2.5-flash-lite --architecture v2 --architecture v3 --limit 8 --max-calls 80 --deadline 300
.\.venv\Scripts\python.exe -m app.evaluation.judge_bakeoff --run --model google/gemini-2.5-flash-lite --architecture v3 --case regular-smoking --case inverse-smoking --case opposite-trial --case reverse-carrot --case numeric-overclaim --repeats 5 --limit 5 --max-calls 50 --deadline 300
Pop-Location
```

Fresh source-only controls use current configured contacts/adapters and no claim
extraction; external NCBI/Crossref/approved-authority calls still occur:

```powershell
docker compose run --rm --no-deps -v './runtime:/app/runtime' backend python -m app.evaluation.source_suite --run --limit 11 --runtime /app/runtime
```

Select the exact new artifact and manually reviewed source-ID manifest. Never
reuse expired files or represent fresh retrieval as a retained original:

```powershell
Push-Location backend
$capture = '..\runtime\bakeoff\public-controls-<new-timestamp>.json'
$selection = '..\runtime\bakeoff\<reviewed-selection>.json'
.\.venv\Scripts\python.exe -m app.evaluation.oracle $capture $selection
.\.venv\Scripts\python.exe -m app.evaluation.judge_bakeoff --run --capture $capture --oracle $selection --selection current --selection lean --selection oracle --model google/gemini-2.5-flash-lite --architecture v2 --architecture v3 --limit 4 --max-calls 120 --deadline 600
$bakeoff = '..\runtime\bakeoff\bakeoff-<new-timestamp>.json'
.\.venv\Scripts\python.exe -m app.evaluation.results $bakeoff
.\.venv\Scripts\python.exe -m app.evaluation.ensemble $bakeoff
Pop-Location
```

The manifest is a JSON object mapping frozen claim UUIDs to reviewed document-ID
arrays. Oracle requires actual retained IDs, not invented labels or source text.
`ensemble` compares available V2 conditional-case audit subsets only; real/V3 rows
are not coerced into votes. Artifacts are expiring private development data.

Remaining normal-flow controls (paid; admission cap may be exceeded by an already
running analysis). This resumes at broad skin cancer, avoiding the first four:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.evaluation.end_to_end --run --offset 4 --limit 5 --max-observed-calls 120 --analysis-deadline 300
Pop-Location
```

This may stop before all five. Do not claim a hard provider-call cap. Neither a
failed source nor a development guard should be bypassed to make acceptance pass.

## 8. Remaining blockers and next work

1. Full clean paired V2/V3/validator model comparison and all-three real-Pack
   five-repeat final stability are incomplete; budget/quota interruption matters.
2. Narrow-dose scope/materiality and wide-null/conflict false decisive classifications
   prevent V3/minimal-V2 adoption. Changing labels/thresholds is not a repair.
3. Optional generated numeric findings still invalidate normal qualitative claims.
   Ratio/multiple/chemical-name numeric typing needs assertion-specific regression.
4. Reviewed source recall for broad skin cancer, carrot limitations and lean BP
   selection is insufficient. Oracle cases require independent label/source review.
5. Gateway aliases/fingerprints do not establish pinned identity or production
   model isolation/validator qualification.
6. No visual browser acceptance surface was available; no claim of browser QA.

Do not start WeChat, calibration, another source family or public clinical release.
The next work is a strictly budgeted completion/repair of these Slice 4 gates,
then independent reviewed benchmark work. The full reliability task is **not
finished** merely because software checks pass.
