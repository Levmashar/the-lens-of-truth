# Current reliability baseline - 2026-10-06

Frozen as the current **development** reliability baseline after cleanup, full
suite verification and two fresh full analyses. Medical logic, prompts, model
configuration, production gates and retrieval/position rules were not changed.

## Full test-suite status

- Deployed backend with `RUN_DB_TESTS=1`: **990 passed, 0 failed, 0 skipped**
  (162.66 seconds). This includes every PostgreSQL append-only/persistence test.
- Local backend: 975 passed, 15 database tests skipped (196.91 seconds).
- Frontend: **52 passed, 0 failed**; TypeScript/Vite build passes.
- Ruff passes; mypy passes for all 173 application modules. Docker services rebuilt.
- Two dependency deprecation warnings remain; neither is a test failure.

The Miri-default test now explicitly selects Miri and disables dotenv loading
with `_env_file=None`; the existing fixture clears provider environment variables.
The debug test now checks full 5,000-character response equality, analysis scope
and disabled capture, preserving the intentional full-response behavior.
The shared parser/retry flag `normalize_miri_labels` is renamed to
`discard_verifiability_labels` without a behavior change. Actual Miri adapter,
provider configuration and historical audit names remain provider-specific;
Paratera and AIMLAPI are not renamed to Miri.

## Two fresh live results

| Claim | Final result | Qualified | Seconds | Analysis ID |
|---|---|---:|---:|---|
| Blue light from smartphones causes leukemia. | Not Enough Evidence | 3/3 | 139.3 | `1cace1e8-e622-4110-ace9-3381198997de` |
| Carrots improve eyesight. | Not Enough Evidence | 2/3 | 131.9 | `bcaaedcc-5a0a-47d0-931d-36d2b9785dd3` |

Both ran the real deployed `run_background` pipeline, including extraction,
retrieval, selection, judges, semantic validation and report generation. Both
saved query plans are **1.4** and all five successful position audits are
`validated-evidence-position-1.4`. These are fresh calls, not saved replay.
There were **14 paid model requests**, below the 18-request cap; all returned
HTTP 200. Returned total usage is 57,889 tokens; no price is inferred.

## Regression assessment

No medical/result regression appeared. Blue-light retrieval preserved the Blue
Light and Smartphone concepts and selected the WBC-counting diagnostic record
(PubMed 39794386), not methylene-blue treatment. The existing disease-stage
endpoint guard kept every attributed diagnostic finding contextual/incompatible
with leukemia onset. All three source validations passed; no material support
or opposition was manufactured from the diagnostic findings.

Carrots retained outcome `eyesight`; the selected night-vision observational
study (PubMed 10484191) does not establish the broad causal benefit. The two
validated assessments treated the subgroup associations as insufficient and
reverse-causation/methodology findings as context, with no decisive contradiction.

**Operational reliability limitation:** Qwen3.5-Plus omitted the mandatory
`numeric_dependency` fields for S3/S4 in both carrots attempts. Exact local
schema checks report `statements[2].numeric_dependency` and
`statements[3].numeric_dependency`: `missing / Field required`. It was excluded
as `schema_violation`, not repaired or counted as NEI. This reduces qualification
from the prior run's 3/3 to 2/3 even though the final result is unchanged. The
remaining two independently validated NEI positions satisfy the unchanged
development gate. Freeze does not imply all models are consistently schema-valid
or production qualified. Models remain unchanged; Qwen stays provisional.

## Final versions and active model lineup

| Component | Frozen version |
|---|---|
| Architecture / judge decision | V2.5 validated evidence position; decision `2.5` |
| Structured source/quantity references | V2.4; `source-quantity-catalog-1.0` |
| Judge input / validation contract | `judge-input-2.5` / `judge-validation-2.5` |
| Judge prompt | `judge-2.15-validated-evidence-position-2026-10-05` |
| Semantic prompt | `joint-evidence-axes-2.5-structured-numeric-2026-10-04` |
| Query plan | `1.4` |
| Position | `validated-evidence-position-1.4` |
| Numeric fidelity / comparability | `numeric-reference-fidelity-2.4` / `numeric-reference-comparability-2.4` |
| Final verdict policy | `verdict-policy-1.4` |

| Role | Provider | Model |
|---|---|---|
| Extraction | Paratera, OpenAI-compatible adapter | DeepSeek-V4.1-Flash |
| Judge 1 | Paratera | DeepSeek-V4.1-Flash |
| Judge 2, provisional | Paratera | Qwen3.5-Plus |
| Judge 3 | Paratera | GLM-4.7 |
| Semantic validator | Paratera, thinking disabled | Qwen3.8-Flash |

Base API: `https://llmapi.paratera.com/v1`. No model/prompt changes or AIMLAPI calls.
The current four public labels, historical audit versions and production gates
are unchanged. Both live results retain `production_qualified=false`.

The [machine-readable baseline](RELIABILITY_BASELINE_20261006.json) records all
versions, model IDs, source hashes, image IDs, live IDs and compact diagnostics.
Source-manifest SHA-256: `c804ff9ac8bbc7d3fd8c4e318b7765787eca048d9517e7bf0f0ffcbefc72015b`.
Backend image: `sha256:fc263e59bc89a3e69a7f15e6b48c6fd3735ceb7222c323f391ba3a065200d33a`.
Frontend image: `sha256:012eb32ffdb11803a7e7d0a2a1c615fb119ab0ed2ebea6b2319f1a768a235a2a`.
Full raw responses/packs/audits are retained locally in
`%LOCALAPPDATA%/Temp/lens_reliability_baseline_live_20261006.json`.
