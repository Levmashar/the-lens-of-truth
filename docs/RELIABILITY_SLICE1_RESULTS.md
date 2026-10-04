# Reliability reset — Slice 1 results

Date: 2026-10-01. Scope: replay, backend-owned source references, numerical
attribution and bounded measurement only. No source-coverage/policy rewrite,
frontend change, environment change or clinical qualification.

## Original artifacts and confirmed causes

Both named analyses were retained, not reconstructed. Captures were made
before their existing retention deadlines into ignored `runtime/reliability/`:

- Smoking: `75b56567-dd52-4e92-806d-ea2471bf6dc7-20261001T072128129150.json`.
- Sunscreen: `1e58f2e8-f1cc-4e05-94af-1e008c22307d-20261001T072128220124.json`.

Capture includes claim/checkpoint, queries/retrieval diagnostics, full Pack,
all judge inputs/decisions/revisions and validation results, aggregation/report
records, numerical comparisons, quote divergences and a rejection ledger.
Historical semantic request bodies and the failed smoking revision's raw
response/schema paths were **not persisted**. The process-local debug traces
were unavailable. Their absence is a diagnostic limit, not evidence of a
particular missing field or reasoning error. No deleted data was recovered.

Compact ledger of the active artifacts:

| Run / judge | Affected finding | Confirmed failure | Classification / effect |
|---|---|---|---|
| Smoking / 1 | required statement | `statement_validator_unavailable` | Provider/validation failure; no eligible conclusion |
| Smoking / 2 revision | entire response | `schema_violation`; raw response absent | Contract failure; exact rejected field unknown |
| Smoking / 3 revision | S2/E10, S7/E1 | `QUOTE_NOT_IN_FROZEN_PASSAGE` | Unicode whitespace differences; required premises failed |
| Sunscreen / 1 revision | S2/E2 | quote mismatch | Unicode whitespace; required premise failed |
| Sunscreen / 1 revision | S3 | `NUMERIC_UNCERTAIN` | Parser uncertainty, separate from its quote defect |
| Sunscreen / 2 | S2/E29 | only `NUMERIC_UNCERTAIN` | Reproducible HR/CI parser false rejection; attributions and conclusion otherwise passed |
| Sunscreen / 3 revision | S2/E2, S6/E2 | quote mismatch | Unicode whitespace; required premises failed |
| Sunscreen / 3 revision | S4 | numerical uncertainty | Optional detail outside conclusion dependencies; still unqualified explanation |

Earlier sunscreen judge-1 quotes inserted ellipses into noncontiguous source
text. Earlier smoking judge-3 also failed E9 whitespace before its revision.
The utility records proposed/source text and aligned first-divergence offsets
only in developer files. These categories do **not** authorize fuzzy acceptance.

### Exact sunscreen numerical defect

Judge 2's S2 asserted event counts 3 versus 11, HR 0.27, and 95% CI 0.08–0.97.
Its own frozen E29 used `HR, 0.27; 95% CI, 0.08 to 0.97`. Legacy extraction
missed the comma-form HR and CI and classified `95%` as a generic percentage.
It could not bind the correctly asserted quantities and returned uncertainty.
The before/after deterministic regression retains the old result and verifies
the repaired statement-local result is aligned. No medical label is forced.

### What was actually selected and sent

Both original Packs are version 1.4, with unchanged hashes:

- Smoking: `5b8abcdf8a76a11af2a7d60f32d010e66fc7e7ac07e71669f70bf30a8af0d51e`.
- Sunscreen: `b9906c8b3473ec46ca35df93f312e81cd765c4c43f12d4a6e3b528cd79262a92`.

Smoking selected representatives E10, E21, E25, E40 and E1: PMIDs 38268471
(smoking-pattern changes), 41402808 (methylation clocks), 41956131 (latency),
38214107 (stigma/emotional functioning) and 40059777 (genetic mediation).
These documents really were in the frozen judge bundles, not merely neutral
report cards. Better causal source coverage is a remaining Slice 2 issue;
this repair does not alter the selection or impose a smoking verdict.

Sunscreen selected E4, E2 and E8, from PMIDs 40876975, 29620003 and 21135266.
E29, the randomized follow-up's RESULTS, is an included contextual sibling of
selected E8; E7 is its METHODS. Its use was authorized by the existing 2.0
document-bundle contract. It was not an invented or out-of-input reference.

## Implemented repair

- Retain the existing attribution/conclusion split. New input/decision/
  validation contracts are 2.1; prompt is `judge-2.5-2026-10-01`, semantic
  prompt `semantic-validation-2.5`. Historical contracts remain readable.
- Add backend-created whole-section units `E#.U1` with exact offsets, source
  text, original E ID, document/passage hashes, section and content version.
  Document context and the prior inclusion/omission budgets remain intact.
  No decimal, interval or negation splitting; every judge sees identical units.
- Model output is semantic content and unit IDs. Backend materializes quotes,
  protocol version and invocation metadata. Unknown IDs, forged materialized
  quotes, altered units/offsets/hashes and broken provenance still fail.
- Check only asserted numbers in each statement's own units, plus assertions
  in the conclusion against its referenced findings. Recognize comma HR/CI,
  correct event-count pairs, study/population counts and age ranges. Bind CI
  to its estimate; distinguish OR/RR/HR. Verify RR arithmetic, not a guessed
  risk conversion. Source-only numerals do not become model assertions.
- Preserve explicit user-magnitude attribution (for example, an observed 15%
  versus the user's claimed 80%). Scope, endpoint, comparator, timeframe and
  essential claim magnitude still require independent semantic checking;
  matching arithmetic alone does not certify them.
- Record exact asserted tokens/offsets, typed candidates, source units, reason
  and actual conclusion dependency. Definite false numbers stay fatal.
  Required unresolved numbers prevent reliance. Optional unsupported detail
  stays unqualified until a fresh decision passes complete validation under
  the existing single revision budget and unchanged frozen input. No silent
  deletion, parent mutation, double voting or source removal.
- Request two/three material findings by default, maximum eight. Expansion
  needs necessary context/conflict and an explanation in the stored
  justification; count/expansion diagnostics are logged without medical prose.
- Preserve bounded sanitized failed judge content and safe Pydantic field
  paths/types in existing audit JSONB. Successful response JSON remains the
  canonical decision. No new public provider-output endpoint or migration.
- A captured smoking validator response had correct IDs and fields but a
  685-character rationale, over the old 600-character limit. The semantic
  response/audit reason maximum is now 1200, with a shorter preferred prompt
  target, exact identifier/status checks and no silent truncation. Daily/per-
  day cigarette counts are typed equivalently; CI confidence level and integer
  estimate binding have additional false-statistic rejection tests.

New files: `app/judging/source_units.py`, `app/validation/assertion_numeric.py`,
`app/validation/replay.py`, `app/validation/slice1_eval.py`,
`app/core/diagnostics.py`, `tests/test_reliability_slice1.py`, and this report.
Adapter/prompt/service/models, v2 validation, revision eligibility, version-aware
report/aggregation readers and their tests were updated. Existing unrelated
retrieval/frontend work was preserved, not included as a Slice 1 change.

## Separate bounded semantic measurement

Models were the existing configured aliases: judge slot 2
`openai/gpt-6-luna`, validator slot 3 `google/gemini-2.5-flash-lite`, both
OpenAI-compatible. Aliases/family names are **not verified model identities**.
No environment values were changed. Frozen probes used one fresh judge, not
a complete three-judge ensemble or a new persisted medical report.

The 10 controls are explicitly engineer-authored synthetic attribution tests:
five correct uses and five fabricated/overstated uses. They are not reconstructed
analyses or reviewed clinical labels. Controls include source-only CIs, valid
and false RR conversions, OR substitution, wrong study/value, user-magnitude
contrast, missing dose, wrong CI binding, comma CI and literal negation.

| Measurement | Positive / negative controls | Semantic false rejection / acceptance | Combined numeric + semantic false rejection / acceptance | Calls / elapsed |
|---|---|---|---|---|
| Initial diagnostic pass | 5 / 5 | 1/5 / 1/5 | 2/5 / 0/5 | 18 / 51.746 s |
| Final completed control pass | 5 / 5 | 0/5 / 0/5 | 0/5 / 0/5 | 19 / 37.775 s |

Initial errors exposed a correct RR transformation being rejected, a false
85% conversion being semantically accepted (blocked numerically), and the
user-magnitude contrast being incorrectly unresolved numerically. Parser and
explicit arithmetic/attribution instructions were repaired. This is a small
development set used during repair, not held-out performance or clinical
validator qualification.

Final completed control artifact: `slice1-eval-20261001T083631009488.json`.
Reported provider usage: 34,948 input / 4,608 output tokens for controls plus
both frozen probes. All 10 control transports/structures succeeded. Both fresh
judge responses were structured and all their references passed provenance.
All six fresh attributions were supported. The invasive-melanoma numbers
passed; sunscreen S3 still had an explicitly unclassified publication year,
not an alleged false treatment effect. **Zero of two conclusions qualified**:
smoking's conclusion checker returned a negative status while describing why
its inconclusive label was sensible; sunscreen's year warning required fresh
reassessment instead of silent acceptance.

Final same-evidence, single-budget revision measurement:
`slice1-eval-20261001T084009146590.json`, 20 calls / 58.777 s / 66,465 input and
7,505 output tokens. Both initial and child judge responses were structured,
with the identical input hash retained in each parent/child pair. All six
active attributions passed, with no quote or numerical warnings; **zero of
two active conclusions qualified**. Both conclusion checks returned
`not_justified` even though their rationales described limitations consistent
with the proposed `not_enough_evidence` label. No status was rewritten based
on prose, no threshold was changed, and no historical row was mutated. This
measurement exercises the existing one-child correction budget; it is not a
three-judge ensemble, a medical gold-standard comparison or release approval.

Repeated measurements expose instability, not a dependable success rate:
`slice1-eval-20261001T082950425824.json` used 18 calls / 31.021 s / 31,979 input
and 3,304 output tokens, with 10/10 controls matched and **one** eligible
sunscreen assessment. Smoking's response was rejected for the inspected
685-character reason, and its daily cigarette wording was initially untyped;
both shape/parser issues were subsequently fixed and regressed. The sunscreen
model's returned label was `contradicted`; that is an unqualified development
assessment, not a forced or production medical verdict. Another complete
pass (`slice1-eval-20261001T081353396348.json`, 19 calls / 44.901 s) had 10/10
matched controls but an attribution disagreement and unavailable conclusion
check. Retain those failures rather than reporting only the successful probe.

A preceding exact-Pack-only probe (`slice1-eval-20261001T080234048580.json`)
used 9 calls / 26.603 s / 28,549 input and 2,731 output tokens. Smoking's
validator returned `not_justified` while its rationale said justified;
sunscreen had one unavailable statement check. This is direct evidence of
remaining semantic/provider inconsistency, not a provenance defect.

An intermediate invocation (`slice1-eval-20261001T080017548602.json`) completed
the 10 controls with zero final-control errors but hit its overall deadline
before completing either Pack probe. It used 14 calls; observed wall time was
891.732 s despite a 300 s configured deadline, coincident with an abnormally
long Docker-build wait. The precise host/process-delay cause is unconfirmed.
It is **not a completed frozen-case evaluation**. The evaluator now also
checks monotonic time before every HTTP call, retains interrupted case state
and exits nonzero on deadline/call-budget/provider-format failure. Cooperative
timeouts cannot interrupt a suspended host process.

Across all seven recorded development invocations: 117 actual HTTP calls,
237,564 reported input / 29,686 output tokens. Include the interrupted run when
accounting for usage; do not count it as an additional successful case set.

## Software verification

Python 3.13 Docker: **453 tests passed**, including migrated PostgreSQL tests
and append-only triggers. Ruff clean; `mypy app` clean (117 modules); Alembic
check found no new upgrade operations. Deprecation/import-rewrite warnings
remain, not test failures. Unit semantic fixtures test software behavior only.

No production/high-risk counts or provider approval changed. Regression tests
exercise 2.1 through existing aggregation: standard production still requires
two qualified judges, high risk three; actual provider approval remains empty.
The existing standard-risk single-judge development path is unchanged.

## Exact PowerShell reproduction

From the repository root; Docker Desktop must be running. Build/start only
PostgreSQL for read-only replay, avoiding API startup cleanup of old artifacts.
No command below edits `.env`:

```powershell
cd "C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth"
docker compose up -d postgres
docker compose build backend
docker compose run --rm --no-deps backend alembic check

# Isolate unit/DB tests from live provider settings without editing .env.
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 -v "${PWD}/backend/tests:/app/tests:ro" backend python -c "import os,sys; from app.core.config import Settings; keep={'DATABASE_URL','RUN_DB_TESTS'}; [os.environ.pop(str(f.validation_alias),None) for f in Settings.model_fields.values() if str(f.validation_alias) not in keep]; import pytest; sys.exit(pytest.main(['-q','--tb=short']))"
docker compose run --rm --no-deps -v "${PWD}/backend/tests:/app/tests:ro" backend ruff check .
docker compose run --rm --no-deps backend mypy app

# Read-only export; timestamped originals stay outside version control.
docker compose run --rm --no-deps -v "${PWD}/runtime:/runtime" backend python -m app.validation.replay --analysis 75b56567-dd52-4e92-806d-ea2471bf6dc7 --analysis 1e58f2e8-f1cc-4e05-94af-1e008c22307d

$smokingCapture = (Get-ChildItem -LiteralPath .\runtime\reliability -Filter "75b56567-dd52-4e92-806d-ea2471bf6dc7-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name
$sunscreenCapture = (Get-ChildItem -LiteralPath .\runtime\reliability -Filter "1e58f2e8-f1cc-4e05-94af-1e008c22307d-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).Name

# Opt-in live cost: capped at 24 HTTP calls / 180 seconds for this invocation.
docker compose run --rm --no-deps -v "${PWD}/runtime:/runtime" backend python -m app.validation.slice1_eval --run --max-calls 24 --deadline 180 --capture "/runtime/reliability/$smokingCapture" --capture "/runtime/reliability/$sunscreenCapture"

# Controls only, if originals are no longer retained.
docker compose run --rm --no-deps -v "${PWD}/runtime:/runtime" backend python -m app.validation.slice1_eval --run --max-calls 12 --deadline 120

# Frozen probes with one existing semantic revision each, no new controls.
docker compose run --rm --no-deps -v "${PWD}/runtime:/runtime" backend python -m app.validation.slice1_eval --run --controls-limit 0 --revise --max-calls 20 --deadline 180 --capture "/runtime/reliability/$smokingCapture" --capture "/runtime/reliability/$sunscreenCapture"

# Inspect the newest bounded measurement, without echoing configuration keys.
$resultPath = (Get-ChildItem -LiteralPath .\runtime\reliability -Filter "slice1-eval-*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$result = Get-Content -LiteralPath $resultPath -Raw -Encoding UTF8 | ConvertFrom-Json
$result.metrics
$result | Select-Object http_calls, elapsed_seconds, input_tokens, output_tokens, evaluation_failure
$result.frozen_runs | Select-Object analysis_id, state, conclusion_eligible
```

Replay refuses expired original DB analyses; evaluation refuses expired
captures. Never bypass that check or reclassify controls as original data.
Developer exports contain sensitive submitted claim text: keep them private,
do not commit/share them, and remove them at the original retention deadline.
Capture files are not a backup permission or a retention extension. Existing
captures were left untouched to preserve the diagnostic history during this
task. Future evaluation output carries the original `purge_after` deadline.
Exact historical outputs need not recur with nondeterministic live providers.

## Remaining blockers — stop here

1. Semantic validator status/rationale consistency, nonliteral methodological
   limitations, response references/format and intermittent unavailability
   need reviewed measurement and diagnosis. A correct reference is not a
   semantic certification; the two probes still have no eligible conclusions.
2. Smoking's actually selected sources include indirect/secondary endpoints.
   Authoritative causal coverage and sufficiency policy belong to Slice 2,
   not a topical hardcoded verdict or threshold reduction.
3. Model identity/family/isolation and semantic provider approval remain
   unverified/unapproved. None of these runs is production-qualified.
4. Other numeric syntax may remain explicitly unresolved. Do not blanket-ignore
   uncertainty or erase essential dose/effect quantities in later work.

Slice 1 implementation and measurement are complete. Slices 2/3 were not begun.
