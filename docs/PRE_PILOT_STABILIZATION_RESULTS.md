# Pre-pilot stabilization results — 2026-10-02

## Scope and status

This is a development/test code and diagnostic pass over the existing V2 path.
No model or `.env` change, retrieval source/ranking change, verdict label or
threshold change, schema migration, semantic revision loop or live model matrix.
The three configured judge slots and current Slice 3 selector remain. Every
existing production qualification requirement remains. **Live calls used:
0/24.** The previous Slice 4/4.1 paid ledgers were not reset or reused.

Software controls pass. This is ready for **manual frontend diagnostic testing**,
not clinical calibration or a production medical result. The retained numeric
failure was inspected; its historical artifacts were not edited.

## Exact numeric failure and repair

Retained analysis `ce80184b-e7fa-43f0-8b8b-357f3ea25a49` received:

- Source span: `Smoking increases lung cancer risk by 85%.`
- Model PICO exposure: `Smoking`
- Model PICO outcome: `lung cancer risk increase by 85%`

That outcome was a paraphrase, absent verbatim from the span. `_grounded_outcome`
correctly rejected it. The persisted outcome became null, MeSH linked Smoking
but not lung cancer, the completeness audit reported missing outcome and lung
cancer concept, and `ready_for_evidence` stopped the claim at normalization.
Retrieval and judges never ran; this was not an evidence shortage.

`pipeline/numeric_effect.py` now recovers only the literal object of a simple,
explicit numeric atomic relation. It records the original notation separately
in `pico.numeric_effect` (`raw_text`, parsed/uncertain status, kind, value, unit,
direction). A source-grounded model outcome that is only a suffix of that object
is expanded to the full literal object. An omitted simple subject is recovered
verbatim. The seven offline cases cover 85% risk increase, 20% blood pressure
reduction, 50% cold-duration reduction, 10 percentage points, doubles, 2-fold,
and RR 1.5. Exposure and outcome survive; comparator stays null unless stated.
Fixture MeSH linking finds both smoking and lung cancer, and source-grounded
readiness/query planning proceeds. These are engineering fixtures, not live
PubMed results or clinical truth annotations.

Malformed `by roughly 2..%` keeps the source and `blood pressure` endpoint,
while `value=null`, `kind=unknown`, `status=uncertain`. RR values remain risk
ratios; fold changes remain multiples. For new joint 2.3 audits, a `doubles
risk` claim is compared to an explicit RR, while OR/HR and percentage points
cannot substitute. Historical magnitude checks retain their old version.
Legacy PICO JSON serializes without the new field when null so old frozen Pack
hashes are stable. A live numeric end-to-end verdict was not run here.

## Validator ID, null and comparator handling

New joint prompt `joint-evidence-axes-2.3-2026-10-02` calls `E1` a ranked passage
evidence ID, `E1.U1` its frozen child unit, and `document_id` a separate source
identifier. The checker must return the exact passage ID. The backend accepts
an `E1.U1` response only when that unit is an actual child of `E1` in the same
frozen request and belongs to the cited statement. The raw response,
`returned_id`, `resolved_id` and rule version are kept in append-only audit JSON.
Unknown, fabricated, foreign and duplicate mismatches fail closed. No fuzzy ID
matching or cross-document conversion is allowed.

Raw axes remain direction/scope/strength/role plus finding/scope bases.
`finding_diagnostics` records the frozen-source reason for a null assessment:
wide/imprecise interval, source exclusion/equivalence, mere nonsignificance,
or no precision signal. A model's unsupported `precise_null` claim remains
nondecisive. A narrow interval by itself does not prove a null effect. The
contrast diagnostic distinguishes same-exposure frequency, dose and active
alternative. Qualifier 1.4 permits a documented daily-versus-discretionary
frequency contrast even if the model mislabeled its basis `dose`; actual
high-versus-low dose and unrelated active comparators remain separate and do
not get this exception. Raw model classifications and the effective Python
qualification are both retained. Historical joint 2.0–2.2 and qualifier
1.2–1.3 behavior remains reconstructible under its original version.

For qualitative claims, an optional statistic that is wrong or unresolved can
remain a warning when the separately supplied qualitative finding is an exact
substring of a cited frozen source. This narrow deterministic fallback handles
a checker false `numeric_independent`; it never verifies the statistic itself.
Required user magnitudes, explicit numeric dependencies and material numeric
errors still block qualification. Six offline optional/required variants and
the literal independence control pass.

## Manual diagnostics and export

Only with development debug enabled, the existing technical details section
shows extraction/PICO/numeric notation; candidate and selected source counts;
per-judge proposal, structure, findings, attempt failure categories, numeric
warnings/failures, attribution, axes and bases, qualification/exclusion reasons,
latency, tokens when reported and identity flags; and final aggregation reason.
Raw model JSON is behind an additional collapsed section. The waterfall is:

```text
Extraction                 PASS / FAIL / UNKNOWN
Medical concept / PICO     PASS / FAIL / UNKNOWN
Evidence retrieval        PASS / FAIL / UNKNOWN
Evidence selection        PASS / FAIL / UNKNOWN
Judge response            N/3 usable
Source attribution        N/3
Semantic classification   N/3
Judge qualification       N/3
Final aggregation         recorded result / UNKNOWN
```

PASS means the pipeline stage completed; it does not mean the medical finding
is correct. Judge qualification is read from the persisted verdict's
`judge_qualifications`, so a validated but excluded judge is not counted as
qualified. Per-judge success, safe retry categories, source-ID errors,
unsupported findings, numeric warnings/failures, semantic qualification,
latency and available token usage remain inspectable. No product “best judge”
score is calculated. Live process call totals are shown when the bounded debug
trace is available. After that trace expires, the export shows audited
judge/validator attempts and explicitly marks exact total unavailable.

`app.evaluation.manual_report` is development/test only and read-only. Its JSON
or Markdown contains only the retained claim, PICO, selected bibliographic
metadata/IDs, model aliases, proposal, axes, qualification reasons and result.
It omits prompts, response prose, credentials and unrelated submissions. An
expired analysis is refused; export does not change its purge deadline. A
read-only export of the retained numeric failure succeeded.

## Verification and remaining limits

The offline set includes the requested smoking/inverse/sunscreen/carrot,
numeric magnitude, wide/precise null, frequency/dose/alternative comparator,
wrong endpoint, narrow population, conflicting results, optional bad statistic,
and valid/invalid ID cases. These are deterministic policy fixtures, not
clinical outcome labels. No paired live semantic error rate is claimed.

- Full local backend: **640 passed, 11 opt-in database tests skipped**.
- Python 3.13 Docker + isolated PostgreSQL: **651 passed**, including
  append-only validation and audit round trips.
- Frontend: **44 tests passed**, TypeScript/Vite production build passed.
- Ruff `check .`, mypy `app`, Alembic `check`, backend/frontend Docker builds,
  and `git diff --check`: passed. No migration required.
- Rebuilt local development containers are serving `GET /healthz` and the
  frontend root with HTTP 200. A retained completed analysis returned a
  `2/3` qualification waterfall matching its persisted verdict; this was a
  read-only diagnostic check, not a new model evaluation.
- Live model calls: **0/24**.

Known limits: no new normal API numeric claim was submitted to a live model,
so numeric end-to-end medical qualification remains unmeasured. Source-text
null precision is a conservative necessary check, not statistical proof.
The checker may still classify null direction or contrast basis inconsistently;
new diagnostics make those errors visible. Exact call totals are unavailable
after the process-local debug trace expires. Production model identity,
evidence isolation and validator approval remain unverified; do not interpret
development results as trusted medical reports. Retained historical Slice 4
and 4.1 results are unchanged.

## Exact PowerShell reproduction

From the repository root:

```powershell
Set-Location 'C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth'
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_pre_pilot_stabilization.py
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe app
Pop-Location
docker compose build backend frontend
docker compose run --rm --no-deps -v './backend/tests:/app/tests:ro' -e RUN_DB_TESTS=1 -e DATABASE_URL=postgresql+psycopg://lens:lens@postgres:5432/lens_slice4_tests backend python -m pytest -q
docker compose run --rm --no-deps -e DATABASE_URL=postgresql+psycopg://lens:lens@postgres:5432/lens_slice4_tests backend alembic check
Push-Location frontend
npm test
npm run build
Pop-Location
git -c core.safecrlf=false diff --check
```

The isolated `lens_slice4_tests` database must already exist and be migrated;
the command does not prepare/reset a shared database. To inspect one retained
analysis without paid calls:

```powershell
docker compose run --rm --no-deps backend python -m app.evaluation.manual_report --analysis ce80184b-e7fa-43f0-8b8b-357f3ea25a49 --format json
docker compose run --rm --no-deps backend python -m app.evaluation.manual_report --analysis ce80184b-e7fa-43f0-8b8b-357f3ea25a49 --format markdown
```

That example expires with its existing retention window; substitute a current
analysis UUID afterward. For the browser pilot, use the existing frontend at
`http://localhost:5173`, submit claims normally, expand Technical details →
Development diagnostics, and record each analysis UUID before expiry.
