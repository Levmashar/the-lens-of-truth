# Structured numeric evidence references V2.4 results

Implemented 2026-10-04. **Offline implementation and software checks passed;
live semantic acceptance is pending the user's manual run. Zero paid calls.**

V2.4 removes generated prose from machine-critical numeric source fidelity.
It does not establish medical correctness or semantic qualification.

## 1. Exact old rejection path

Normal development `orchestration/worker.py:validation` routed decision 2.3 to
`validation/joint23.py:validate_joint23`. It first called
`validate_v2(judge, pack, None)` for frozen provenance, then
`numeric23.numeric_issues23`. That function separately checked statement.text,
qualitative_finding, each numeric_details item and both conclusion explanations.
Its nested `check` called `compare_assertion_numbers`, then for materiality 1.3
`numeric_effects.source_fidelity` / claim_references / parse_quantities and
numeric_occurrences. A material warning or mismatch returned
`material_preflight_failure` before `validator.assess_joint23` ran.

`numeric_findings23` separately reparsed repeated generated fields, so equivalent
content could yield verified and not_found diagnostics. `relation_flow` also
derived preliminary claim magnitude alignment from finding prose. Those old
functions remain for recorded 2.3 replay; V2.4 bypasses them entirely.

## 2. Backend-owned catalog and frozen identity

Contract: `source-quantity-catalog-1.0`. Container:
`judge-input-2.4.source_quantity_catalog = {version, items}`. It is covered by
the existing canonical input snapshot hash. The Evidence Pack is not changed.

Each item has quantity_id, source_unit_id, evidence_id, start/end, literal,
measure, values, unit, binding and normalization_reason. Offsets are zero-based,
half-open Unicode character offsets relative to the complete frozen unit.
Per-unit quantities are ordered by spans and typed identity, deduplicated, then
assigned `<unit>.Q1`, Q2, etc. IDs do not depend on model output or a run UUID.

The existing source extractor's current followup behavior is used on frozen
source text only. Overlapping residual matches cannot reinterpret a typed
decimal. Unlocated results cannot become typed estimates; otherwise-unbound
source numerals receive explicitly unknown catalog entries. Extraction changes
must use a new catalog version and preserve recorded-version dispatch.

For the synthetic smoking source regression:

| Reference | Values | Measure / binding | Comparison with submitted +85% |
| --- | --- | --- | --- |
| E1.U1.Q1 | 20, 40 | fold_change, risk_multiple; literal times-higher ambiguity | lifelong scope narrower; no magnitude vote |
| E1.U1.Q2 | 90 | population_attributable_fraction, male | different_measure |
| E1.U1.Q3 | 79 | population_attributable_fraction, female | different_measure |

These IDs are conditional fixture IDs. The user must inspect the IDs actually
frozen in the next live input. No PAF/OR/HR to RR, percentage-point to relative
percent or times-higher to invented percent conversion occurs in the catalog.

## 3. New judge content contract

New input: `judge-input-2.4`; materialized decision: `2.4`;
validation: `judge-validation-2.4`.
Judge prompt: `judge-2.14-structured-numeric-development-2026-10-04`.

Provider-facing `JudgeContent24` retains label, 1–5 source-attributed statements,
conclusion and uncertainty_reasons. Each statement carries statement_id, text,
qualitative_finding, kind, source_unit_ids, source_quantity_ids and
numeric_dependency. Quantity refs may be [] and are the only model-controlled
numeric transport. `numeric_details` and numeric value fields are forbidden.
Every quantity must exist and belong to a cited unit; duplicates are defects.

Conclusion retains based_on_statement_ids, justification,
qualitative_justification and numeric_dependency. Its schema forbids independent
quantity refs. Prose is retained exactly for semantic attribution/audit; numbers
in conclusion prose never create or revalidate a numeric premise.

## 4. New numeric path and failure semantics

`validation/joint24.validate_joint24` performs frozen Pack/unit/input/catalog,
prompt and raw/canonical response provenance checks plus quantity membership
and ownership checks. Invalid references or tampering fail closed under
`reference_preflight_failure`, with zero checker attempts and explicit
`skipped_due_to_reference_preflight` blocking references.

Numeric contracts: `numeric-reference-fidelity-2.4` and
`numeric-reference-comparability-2.4`. `numeric24` constructs fidelity directly
from the referenced backend quantity. No assertion parser is called on any
statement, qualitative finding, numeric_details or conclusion prose. Even the
old relation payload's prose-based magnitude alignment is bypassed for 2.4.

Before semantic scope, diagnostics say semantic_scope_pending and do not compare
magnitude. After scope, the existing `compare_to_claim` consumes backend quantity
+ submitted PICO numeric_effect + scope/basis and permitted gradient policy.
Exact values, direction, measure distinctions, restrictions, times-higher
ambiguity and explicitly recorded existing arithmetic remain intact.

The existing magnitude_eligible map blocks unknown, unresolved and noncomparable
quantities. A statement with no refs may establish qualitative direction but
cannot supply an exact magnitude. Valid different measures, limited scope or
insufficient magnitude never cause material_preflight_failure. Python qualifies
the proposed label; it does not flip it or force a scientific NEI.

## 5. Independent semantics and V3 boundary

Joint prompt `joint-evidence-axes-2.5-structured-numeric-2026-10-04` uses the same
configured checker and `JointResponse23` response schema. It receives all frozen
sources, the attributed findings, quantity IDs and selected catalog objects.
Attribution, direction, scope, strength, role, finding_basis, scope_basis and
omitted material evidence remain required, label-blind and non-voting.
Qualifier 1.4 and semantic axes/mapping are unchanged.

The historical V3 bake-off showed false wide-null direction and narrow-dose
materiality results. `judging/v3.py` remains an explicit evaluation probe;
normal development uses V2.4 source-attributed findings and independent checking.
No model/provider configuration, extraction, retrieval, source selection,
production qualification gate, verdict policy or judge threshold was changed.

## 6. Historical replay and append-only reconstruction

compact23/numeric23/joint23/audit23 retain recorded versions, behavior and shapes.
Historical numeric-materiality 1.0/1.1/1.2/1.3 and fidelity-comparability 1.0/1.1
are not overwritten. Legacy serialization omits absent quantity fields/catalogs.
Historical service transport tests explicitly select axes_contract=2.3; the
normal development default is 2.4. Production preparation retains its prior path.

`audit24` reconstructs the exact frozen judge snapshot/prompt, raw decision and
audited parent-ID normalization, joint input/response, numeric diagnostics and
qualifier output. Verdict aggregation verifies this reconstruction before using
a validated assessment. Existing explanation templates read the new versioned
diagnostics without voting. PostgreSQL roundtrip preserves canonical meaning.
New judge/validation artifacts append to existing JSONB; UPDATE remains blocked.
No migrations, historical response/report edits or expired capture reads.

## 7. Smoking-85 metamorphic and Luna repetition regressions

One valid V2.4 reference decision is replayed with generated statement.text,
qualitative_finding, conclusion.justification and qualitative_justification
changed to each of:

- 20-40 times higher
- 20-40x
- many-fold higher
- far above the claimed magnitude
- far above the claimed 85%
- does not establish 85%
- no support for the exact 85%
- unrelated invented numeric prose as an adversarial transport control

With references fixed, numeric fidelity/comparability and qualifier inputs are
identical. Numeric23 gates, occurrence extraction, old relation prose alignment
and V2 prose assertion checks are replaced with failing sentinels during these
tests: calling them would fail the regression. All cases reach the offline
checker once. This proves transport invariance, not semantic equivalence of
those propositions. A separately stipulated semantic rejection of false numeric
prose still makes the assessment invalid despite valid source references.

Luna-style repetition in both statement fields and both conclusion fields
produces one diagnostic for one quantity ref. Three refs produce exactly three
diagnostics, including separate male/female PAFs; prose produces no extra
verified/not_found finding. Conclusion numbers create no independent assertions.

## 8. Safety coverage and software verification

70 new offline tests cover deterministic IDs/spans and Pack immutability,
quantity existence/ownership, duplicate/missing fields, hash/catalog/source/raw
response/prompt tampering (including recomputed hashes), numeric/audit/qualifier
tampering, RR/OR/HR/PAF/percentage-point separation, exact values/direction,
explicit ordered-risk conversions, ambiguous times-higher, limited population/
exposure/scope, no refs, multiple refs, prose invariance, semantic failure,
omissions/unavailability, worker/adapter/debug routing, report/aggregation,
2.3 replay, existing false-number controls and V3 evaluation isolation.

The PostgreSQL suite exposed inherited VALIDATOR_* settings affecting two
offline tests. Test environment isolation now clears these alongside the
existing judge/extractor settings; application configuration is unchanged.
All provider transport tests use mocks, not live model requests.

| Check | Result |
| --- | --- |
| New structured-reference controls | 70 passed |
| Local full backend, Python 3.14 | 857 passed, 14 DB-opt-in skips |
| Docker Python 3.13 + isolated PostgreSQL full suite | 871 passed |
| PostgreSQL append-only/JSONB | Covered in full suite, including V2.4 second appended validation and rejected UPDATE |
| Ruff app/tests | Passed |
| Mypy | 168 source files clean |
| Alembic upgrade/check | Existing head 20261001_0018; no new upgrade operations |
| Frontend tests | 49 passed |
| Frontend TypeScript/Vite build | Passed |
| Docker backend/frontend builds | Passed |
| Git whitespace check | Passed |
| Normal services | Restarted; backend health and frontend HTTP 200 |
| Paid model calls | 0 |

Checks use isolated `lens_structured_numeric_tests`; no live analysis POST was
made. Existing Starlette deprecation warnings remain. Software fixture axes
are stipulated engineering annotations, not measured medical truth.

## 9. Files changed

New:

- backend/app/judging/compact24.py
- backend/app/judging/source_quantities.py
- backend/app/validation/numeric24.py
- backend/app/validation/joint24.py
- backend/app/validation/audit24.py
- backend/tests/test_structured_numeric_references.py
- docs/STRUCTURED_NUMERIC_REFERENCES_RESULTS.md

Updated:

- backend/app/judging/models.py, source_units.py, prompt.py, service.py
- backend/app/adapters/judge.py
- backend/app/validation/models.py, numeric_effects.py, relation_flow.py, v2.py,
  service.py, joint23.py (shared exact ID-normalization helper only)
- backend/app/orchestration/worker.py
- backend/app/verdict/service.py
- backend/app/api/routes/analyses.py, backend/app/schemas/analysis.py
- backend/tests/conftest.py, test_parent_source_unit_repair.py,
  test_pre_pilot_stabilization.py, test_validation_persistence_db.py
- frontend/src/types/api.ts
- docs/PROJECT_CONTEXT.md, DECISIONS.md, TODO.md, ARCHITECTURE.md, API_SPEC.md

No change to numeric23/numeric_occurrences parsing, axes/qualification policy,
report explanation templates, v3.py, model settings, Evidence Pack or DB schema.

## 10. Exact next manual live acceptance

The following POST is the user's next paid normal analysis; it was **not executed
in this task**. Use the normal development UI at http://localhost:5173, enable
Development diagnostics and submit exactly:

> Smoking increases lung cancer risk by 85%.

Equivalent PowerShell from the repository root:

```powershell
$body = @{
  schema_version = '1.0'; client = 'web'; lang = 'auto'
  input = @{ type = 'text'; text = 'Smoking increases lung cancer risk by 85%.' }
  consent = @{ privacy_notice_version = '2026-09-01'; accepted = $true }
} | ConvertTo-Json -Depth 5
$a = Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/analyses -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://localhost:8000/v1/analyses/$($a.analysis_id)"
Invoke-RestMethod "http://localhost:8000/v1/analyses/$($a.analysis_id)/claims" | ConvertTo-Json -Depth 20
```

Poll GET until complete; retain the new analysis ID. Inspect normal Development
diagnostics/raw responses and saved audit versions. Acceptance criteria:

1. New input/decision/validation is 2.4; configured Grok/Luna/Sonnet and Haiku
   identities remain as configured, with no V3 normal path.
2. Judges select actual frozen quantity IDs; a referenced times-higher literal
   is verified regardless of model paraphrase. PAFs retain separate IDs and
   different_measure. Repeated prose creates no duplicate diagnostic.
3. Every successfully parsed, reference-valid assessment reaches its independent
   semantic checker. Different-measure/narrower/ambiguous quantities do not skip
   it or produce material_preflight_failure. Provider/reference failures remain
   visible operational defects, with no manufactured NEI.
4. Compare raw semantic axes and qualification; unresolved/noncomparable/no-ref
   magnitude cannot support an exact 85% vote. Do not require all judges to
   qualify or prescribe a final medical label to make this transport test pass.
5. Conclusions introduce no independent numeric premises; old runs/reports remain
   immutable. Record semantic failures separately from transport acceptance.

Stop after this manual acceptance and review its audits. Further model runs,
semantic changes, English numeric patches and V3 adoption are outside this task.
