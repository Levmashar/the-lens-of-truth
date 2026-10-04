# Reliability Slice 4.1 — implemented repair, partial semantic acceptance

Measured 2026-10-02. Architecture work and paid testing stop here.
This is an engineering evaluation, NOT a clinical gold benchmark or production
medical qualification. No V3/model/selector adoption, threshold lowering, `.env`
edit, source expansion, historical rewrite or automatic benchmark launch.

## 1. Outcome and call budget

Implemented V2 decision 2.3 and independent evidence axes, optional-number
handling, comparator semantics, immutable audit reconstruction and a PostgreSQL
canonical JSON repair. Software checks pass. Normal HTTP analyses now produce
usable development results. **The complete semantic acceptance gate has NOT
passed:** the final checker still emitted inconsistent null direction/basis,
source-unit ID noncompliance occurred, and the numeric HTTP control failed
upstream normalization before evidence validation.

New ledger: `runtime/slice4_1-20261002.sqlite3`, immutable ceiling 150.
**146 reservations used; 4 unused. No further paid calls planned.** All model
extraction, judge, validator and retry transports reserved before HTTP. The old
`runtime/slice4-continuation-20261002.sqlite3` remains exhausted at 120 and untouched.

| Purpose | Reservations |
| --- | ---: |
| Atomic extraction | 16 |
| Judge decisions, including format retries | 56 |
| Joint evidence-axis checks | 74 |
| Total | 146 |

By experiment: focused probes 35; normal HTTP analyses 94; identical-Pack fresh
assessment repeats 17. 145 responses were HTTP 200; one initiated request ended
without an HTTP status (bounded final Ling validator timeout). HTTP success is
not structured/semantic success. The preferred ≤100 target was exceeded because
the first two normal batches exposed numeric-dependency and database audit defects.
No discovery, replacement model or renewed V2/V3 bake-off was run.

## 2. Exact retained manual failure

Analysis `20dbe32f-7a58-43a3-a627-a009e639c34b` was exported read-only, not
reconstructed: `baseline-20261002T132859337687.json`. Its original expiry is
2026-10-03T11:53:37.330868Z; no retention deadline was extended.

Confirmed causes:

1. Ling and Gemini returned optional statistics for a qualitative claim, then
   failed the compact 2.11 `optional_numeric_content` format rule after retry.
   Their original rejected content was retained; this was not a source shortage.
2. Luna's daily-versus-discretionary invasive-melanoma trial description survived,
   but the checker encoded it as insufficient/mismatch/uncertain because it did
   not compare use versus no use. The submitted PICO comparator was null. The
   checker invented a stronger comparator obligation than the claim specified.
3. Initial 4.1 focused probes exposed attribution checking whether the **user
   claim** was established, rather than whether the cited source established the
   **judge's accurate limited/null description**.
4. Initial normal 4.1 batches exposed a new audit integration defect: SQL JSON
   arrays differed from in-memory tuples under ordinary Python equality despite
   identical canonical content. The aggregator returned AUDIT_RECORD_MISMATCH,
   excluding even validated Luna results. Canonical hash comparison fixes it.
5. Later live inspection exposed a remaining semantic error: some imprecise null
   meta-analyses were described as precise null/opposition. This motivated the
   final source-grounded precision guard and prompt 2.2, not a forced label.

## 3. Old contract versus new contract

Old relation combined supports/contradicts/insufficient/context/uncertain with
scope/materiality. New raw assessments independently record:

| Axis | Values |
| --- | --- |
| Direction | supports_claim, opposes_claim, neutral, mixed, unclear |
| Scope | aligned, compatible_but_narrower, broader_or_indirect, incompatible, uncertain |
| Strength | decisive, strong, supporting, weak, insufficient, uncertain |
| Role | direct, synthesis, contextual, mechanistic, background, uncertain |

`scope_basis` and `finding_basis` make gradient/dose/population/alternative/endpoint
and null/association/reverse/conflict distinctions explicit. The model never
receives the proposed verdict, conclusion or other judges' votes. Backend Python
maps these axes into existing question/design/integrity/risk qualification.
It never flips a failed judge proposal into another label.

Null comparator is **unspecified**, not placebo/never exposure. Tested greater
versus lesser exposure to the same substance and endpoint may be compatible
directional evidence for a frequency claim. This does not prove a universal
causal statement. True active alternatives, endpoint mismatch, untested dose and
restricted population cannot receive this exception automatically.

Imprecise-null/reverse-causation findings cannot create a decisive vote. Conflict
retains opposing directions and prevents unilateral decisive qualification. A
model's `precise_null` classification needs affirmative precision/equivalence/
effect-exclusion wording in the frozen units; its own assertion of absence is
insufficient. This conservative lexical necessary check is not clinical proof.
Raw classifier outputs remain auditable, including mistakes.

## 4. Numeric behavior

New judge fields retain original `text`, separately generated
`qualitative_finding`, optional `numeric_details`, and `numeric_dependency`.
Conclusions retain both explanations and the dependency flag. These are model
fields, not backend text deletion or unrestricted rewriting.

Every numeric assertion is checked. Wrong/unparseable optional details produce
`OPTIONAL_NUMERIC_DETAIL_INVALID`/`OPTIONAL_NUMERIC_DETAIL_UNCERTAIN`; an
independently attributed qualitative proposition may survive. The joint checker
must confirm independence where a warning affects a required premise. Raw content,
failed statistic, numeric diagnostic and qualitative proposition remain separate.

Material quantities include a quantitative user claim, quantity-bearing critical
proposition, explicit numeric dependency and quantitative transformation. Wrong
material numbers are fatal; uncertain material assignments remain unqualified.
RR 0.85 is not an 85% reduction. Failed statistics never become opposite votes.
Source-only numbers are not assertions. Legacy numeric checks are unchanged;
new 2.3 uses its own materiality pass rather than duplicate legacy checks.

Observed improvement: Ling's qualitative smoking/inverse/sunscreen assessments
survived optional uncertain/invalid figures with independent attribution. No new
2.3 judge failed the obsolete optional-number **format** rule. However, Gemini
sometimes falsely marked numeric independence unavailable or placed quantities
in a critical field. Those are still safely rejected, and the remaining false
rejections must not be represented as fully fixed.

## 5. Versions and persistence

- Decision/input/validation: 2.3, still V2.
- Judge: `judge-2.12.1-compact-development-2026-10-02` (2.12 retained).
- Joint checker: `joint-evidence-axes-2.2-2026-10-02` (2.0/2.1 retained).
- Axes: `evidence-claim-axes-1.0`.
- Numeric diagnostics: `numeric-materiality-1.0`.
- Pure qualifier: `conclusion-qualifier-1.3` (1.2 reconstruction retained).
- Pack/selector/verdict policy: existing 1.5/current/1.4, unchanged.

No migration: existing JSONB holds the new objects. Append-only triggers still
reject UPDATE. Raw output must rematerialize the same decision; frozen snapshot,
source units, actual request/hash/response and qualifier are rechecked. Canonical
JSON removes representation-only tuple/list differences, not content differences.
Historical 2.2 and earlier 4.1 artifacts are not reinterpreted under new versions.

## 6. Software verification (separate from model evaluation)

- Full Docker Python 3.13 backend + isolated PostgreSQL: **622 passed**.
- Local Python 3.14: **611 passed, 11 opt-in DB tests skipped**.
- Slice 4.1 offline controls: **32 passed**; no paid/live dependency.
- PostgreSQL round-trip, repeat insert and append-only judge/validation/verdict tests pass.
- Ruff `check .`: pass. mypy `app`: **158 modules clean**.
- Alembic `check`: no new upgrade operations. Current head `20261001_0018`.
- Frontend: **43 tests pass**, TypeScript/Vite build passes.
- Backend/frontend Docker builds pass; `git diff --check` passes.

Deprecation warnings concern Starlette/HTTPX and old HTTP-422 naming. They are
not failures. Tests used the existing isolated `lens_slice4_tests` database;
no startup reconciliation or reset was performed against active live analyses.

## 7. Focused semantic measurements

Fixtures are explicitly **synthetic engineer-authored conditional premises**,
not invented real papers, historical analyses or independently reviewed gold.
Expected annotations never entered model requests. Only configured Gemini Lite
was called, once per probe, with no semantic retry inside the validation path.

Initial joint 2.0: 17 calls, 17 parsed. Nine of 16 acceptable stipulated findings
were falsely rejected at attribution (null/limitation/conflict/background described
accurately but compared with user-claim truth). Numeric distortion remained
blocked by Python despite a wrong raw semantic support classification. Gradient,
smoking/inverse, precise equivalence and opposite trial qualified correctly.

Joint 2.1: 11 targeted calls; 3 ID-contract failures. All seven parsed acceptable
findings qualified; distortion stayed blocked. Three separately measured fresh
probes of those ID failures later qualified. Keep the initial failures in the
denominator: this is not a retry-until-success validation policy. Association
direction and role/scope annotations still varied even where NEI safety held.

Final joint 2.2: four focused calls. Null synthesis and gradient qualified;
the overclaimed null finding was correctly rejected; wide-null had a strict ID
failure (returned E1.U1 where E1 was required). Thus 3/4 parsed, 2/3 acceptable
controls qualified, and 0/1 invalid overclaim accepted. No decisive false
acceptance in these final parsed engineering controls. These tiny denominators
do NOT estimate clinical false-acceptance/rejection rates.

Artifacts, private and expiring under runtime/bakeoff:

- `slice41-probes-20261002T140054932994.json` — initial 17.
- `slice41-probes-20261002T140705167533.json` — targeted 11.
- `slice41-probes-20261002T140743839716.json` — three new measured probes.
- `slice41-probes-20261002T142614798770.json` — final four, including raw ID failure.

## 8. Normal /v1/analyses results

Two earlier five-case batches are retained, not hidden. Their reported medical
results were mostly Unable before the canonical JSON fix. A later five-case
batch used the repaired actual HTTP/worker/report path. Final sunscreen was
measured once more after the null guard/prompt change.

| Exact input | Result | Qualified | Structured | Latest analysis | End-to-end latency |
| --- | --- | ---: | ---: | --- | ---: |
| Smoking causes lung cancer. | Supported | 2 | 3 | 9a0d9634-2270-4abe-a9ef-fd659a16fdcd | 28.468s |
| Smoking does not cause lung cancer. | Contradicted | 2 | 2 | aea9ff2d-02c4-4026-b8d9-4c65ebc31939 | 24.373s |
| Frequent sunscreen use causes invasive melanoma. | Contradicted | 1 | 3 | 5792d92d-0154-40aa-86cc-a2ee00d3cb48 | 58.788s |
| Carrots improve eyesight. | Not Enough Evidence | 2 | 3 | 905be995-8cb2-49c3-a41b-438dbea6ea6d | 16.216s |
| Smoking increases lung cancer risk by 85%. | Normalization incomplete; no report | 0 | 0 | ce80184b-e7fa-43f0-8b8b-357f3ea25a49 | 2.061s |

Every generated report: **production_qualified=false**. Sunscreen's latest one-
assessment result uses the PRE-EXISTING provisional standard-risk development
rule; it is not a lowered threshold or production qualification. Optional BP /
vitamin-C controls were not run; budget was reserved for the observed defects.

Per-case details:

- Smoking: Ling and Luna qualify Supported. Ling's optional numeric warnings
  survive independent attribution. Gemini's findings were attributed but numeric
  independence was not established for a required optional warning; unqualified.
- Inverse: Ling and Luna qualify Contradicted with aligned opposite direction.
  Gemini fails schema validation after the one format retry. No scope mismatch
  was introduced merely because the source opposed the user claim.
- Latest sunscreen: Luna qualifies Contradicted; trial opposes/aligned/strong/
  direct/exposure_gradient. Its two null syntheses wrongly emit raw opposition,
  but `finding_basis=imprecise_null` makes them insufficient in Python. Gemini
  emits neutral/insufficient nulls and a narrower opposite trial, but wrongly
  gives that trial dose basis, so no decisive direction qualifies. Ling's one
  joint request times out. This is **not full semantic acceptance**.
- Carrot: Luna and Gemini qualify NEI; neutral, insufficient, contextual/
  background/observational findings cannot establish causal improvement. Ling's
  joint response is unavailable/unusable. No decisive causal support is created.
- Numeric control: stored normalization is partial, missing outcome and explicit
  lung-cancer concept; retrieval/judging never run. This is NOT proof of numeric
  end-to-end validation. Offline material/distortion controls pass separately.

The earlier sunscreen run `940dcc52-f30a-4bf4-8402-85cda3da6964` had two qualified
assessments and Contradicted. Inspection showed Ling's null/precise-null overreach,
which drove the final generic guard. That earlier assessment is not rewritten.

## 9. Repeatability and call count

One extra assessment set per smoking/inverse/sunscreen reused the EXACT retained
Pack, Pack UUID/hash, selection and current judge prompt, without retrieval or
extraction. These are fresh evaluation artifacts, not semantic child revisions
or edits to historical DB runs. Artifact:
`slice41-repeatability-20261002T142258816814.json`.

| Input | Original + one same-Pack fresh repeat | Qualified-count distribution |
| --- | --- | --- |
| Smoking | Supported 2/2 | 2: 2/2 |
| Inverse smoking | Contradicted 2/2 | 2: 2/2 |
| Sunscreen | Contradicted 2/2 | 2: 2/2 |

Exact-input verdict flips: zero in these pairs. Smoking and inverse main causal
directions stay respectively supporting/opposing with aligned scope. Strength
varies strong/decisive; findings/counts differ, so S IDs are not exact semantic
identity across judge generations. Sunscreen scope varies aligned/narrower; null
findings sometimes flip neutral→opposition or insufficient→strong. Do not hide
those classifier defects behind stable final labels.

These pairs use joint 2.1/qualifier 1.2 and precede the FINAL null guard. They do
not establish repeatability of joint 2.2/qualifier 1.3. The final new sunscreen
run is a third same-text but fresh-retrieval observation, not the same-Pack pair;
its qualified count fell to one. No statistical calibration is claimed.

Slice 4's retained long smoking path used 38 post-retrieval judge/validation
calls; its compact continuation reached 6–7. Slice 4.1 uses three judge requests
+ up to three joint requests + at most one format retry per judge. No per-
statement checks or semantic revisions. Actual corrected five-case batch:
28 reservations (four progressed, numeric stopped upstream); final sunscreen
7 including extraction, hence 6 post-retrieval, one joint timed out. Observed
debug terminal-event counts can omit a canceled request; the persistent ledger
is the authoritative call count. Same-Pack repeats used 17 total across 3 sets.

## 10. Files and boundaries

Created: `judging/compact23.py`; `validation/axes.py`, `numeric23.py`, `joint23.py`,
`audit23.py`; `evaluation/slice41_cases.py`, `slice41.py`, `slice41_repeat.py`;
`tests/test_reliability_slice4_1.py`; budget Compose override; this results file.
Extended existing judge models/materialization/adapter/service, semantic adapter,
validation dispatch/preflight, verdict audit recheck, development worker, budget
utility, debug API/types/rendering and DB/frontend regression tests. Updated
PROJECT_CONTEXT/TODO/ARCHITECTURE/API_SPEC/DECISIONS. Preserved unrelated dirty work.

No migrations, `.env` changes, credentials/catalog queries, clinical label table,
model replacement, source/query/selector/manifest change, production approval or
threshold change. The budget wrapper is opt-in task infrastructure, not a new
permanent model/billing architecture.

## 11. Exact reproduction commands (PowerShell)

Software checks make no paid model calls:

```powershell
Set-Location 'C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth'
Push-Location backend
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
Pop-Location
docker compose run --rm --no-deps -v './backend/tests:/app/tests:ro' -e RUN_DB_TESTS=1 -e DATABASE_URL=postgresql+psycopg://lens:lens@postgres:5432/lens_slice4_tests backend pytest -q
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://lens:lens@postgres:5432/lens_slice4_tests backend alembic check
docker compose exec -T backend alembic current
Push-Location frontend
npm test
npm run build
Pop-Location
docker compose build backend frontend
git -c core.safecrlf=false diff --check
```

The PostgreSQL commands use the existing migrated isolated test DB, not a live
acceptance DB. On another machine prepare that dedicated database first.

Read-only retained capture (no paid calls, no TTL extension):

```powershell
docker compose run --rm --no-deps -v './runtime:/app/runtime' backend python -m app.evaluation.freeze --runtime /app/runtime --analysis 5792d92d-0154-40aa-86cc-a2ee00d3cb48
```

Inspect budget without resetting it or printing secrets:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.evaluation.call_budget --ledger ../runtime/slice4_1-20261002.sqlite3 --limit 150 | ConvertFrom-Json | Select-Object ceiling,initiated,remaining
Pop-Location
```

The following are the exact PAID evaluation invocation forms used. They are NOT
an instruction to rerun a matrix now: only four existing reservations remain.
Do not reset/replace ledgers or recover expired captures to evade that ceiling.

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.evaluation.call_budget --ledger ../runtime/slice4_1-20261002.sqlite3 --limit 150 --module app.evaluation.slice41 -- --run --limit 4 --case sunscreen-null --case sunscreen-gradient --case wide-null --case overstated-null
.\.venv\Scripts\python.exe -m app.evaluation.call_budget --ledger ../runtime/slice4_1-20261002.sqlite3 --limit 150 --module app.evaluation.slice41_repeat -- --run --capture ../runtime/bakeoff/baseline-20261002T142140883738.json --capture ../runtime/bakeoff/baseline-20261002T142141037877.json --capture ../runtime/bakeoff/baseline-20261002T142141188039.json --repeats 1
Pop-Location
```

For normal HTTP acceptance, the SERVER must be guarded before the client starts;
the client-side observed count alone is not a transport ceiling. Do not recreate
the backend while an analysis is active. The task used this opt-in override:

```powershell
docker compose -f docker-compose.yml -f infrastructure/docker-compose.slice4_1-budget.yml up -d --no-deps --force-recreate backend
Invoke-RestMethod http://localhost:8000/healthz
Push-Location backend
.\.venv\Scripts\python.exe -m app.evaluation.end_to_end --run --text 'Smoking causes lung cancer.' --text 'Smoking does not cause lung cancer.' --text 'Frequent sunscreen use causes invasive melanoma.' --text 'Carrots improve eyesight.' --text 'Smoking increases lung cancer risk by 85%.' --max-observed-calls 40 --analysis-deadline 180
Pop-Location
```

That full paid command is historical reproduction, not admitted by four remaining
reservations. When task work is finished and no analyses are active, ordinary
local operation is restored with `docker compose up -d --no-deps --force-recreate
backend frontend`; it does not authorize further task evaluation calls.

## 12. Acceptance and next boundary

Software repair delivered; functional development results improved. Comparator
invented-zero rejection is repaired, optional-number format failures removed,
material-number/reverse/conflict safety retained, and bounded call path preserved.
But semantic decomposition is not consistently emitted by the live checker:
final null raw direction and gradient basis still err, and exact-ID response
compliance is imperfect. Numeric normal-API acceptance is incomplete. Therefore
**Slice 4.1 full semantic gate: partial / not passed**, not all green.

Stop backend architecture work. Do not start another model bake-off, source
expansion, calibration, WeChat or the 300-claim benchmark. The next useful step
is an independently reviewed SMALL diagnostic pilot of the new contract's
remaining failures, not a claim that broad benchmark/public adoption is ready.
Production model identity/isolation/validator approval remain unverified. No
promise to return a binary medical answer for every claim is made.
