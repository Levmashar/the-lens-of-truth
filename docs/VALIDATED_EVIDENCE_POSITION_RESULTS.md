# Validated evidence position: frozen replay

Implemented 2026-10-05. These are engineering checks against already captured
evidence/responses, not clinical validation or live-model repeatability.

New development/test calls use judge contract V2.5. The provider schema requests
findings, source-unit/quantity references, rationale and uncertainty reasons;
it does not request a final label. Optional advisory label text is recorded
unchanged by the new local parser, including `conflicting_evidence`. The same
field remains invalid under historical V2.4; no old parser or row is normalized.

## Saved results

| Frozen claim / saved judge | Original proposal | Backend validated evidence position |
| --- | --- | --- |
| Smoking increases lung cancer risk by 85% / DeepSeek-V4.1-Flash | Not Enough Evidence | Not Enough Evidence |
| Smoking does not cause lung cancer / DeepSeek-V4.1-Flash | Contradicted | Contradicted |
| Daily sunscreen use reduces invasive melanoma risk / DeepSeek-V4.1-Flash | Not Enough Evidence | Supported |
| Same sunscreen input / GLM-4.7 | Contradicted | Supported |
| Vitamin C prevents the common cold / Qwen3.5-Plus | Contradicted | Contradicted |

All five captured responses pass new source/reference checks, receive a validated
assessment and reconstruct from the new audit. The same findings/checker outputs
produce the same position with advisory Supported, Contradicted, NEI,
`conflicting_evidence` or no advisory label. No provider call is made by replay.

The sunscreen input is the retained pack from analysis
`1f91174c-5d24-4d47-88e2-7b1b5899ea0e`. Its invasive-melanoma randomized direct
result remains material support. Observational imprecise null findings cannot
supply material opposition. An offline control using the same result with
`strength="supporting"` also derives Supported and records the backend materiality
promotion. Weak materiality on a randomized design produces an evidence gap,
not `CAUSAL_DESIGN_INSUFFICIENT`. A separate guard control with observed exposure
assignment correctly fails causal design even with a randomized parent label.

The smoking +85% finding references retain their original V2.4 catalog, scope,
measure and ambiguity rules. Noncomparable/ambiguous quantities cannot establish
the submitted magnitude, and qualitative causal direction alone does not verify it.

The vitamin C saved assessment derives material opposition from the applicable
general-population review conclusion. The imprecise incidence estimate is not
promoted into a decisive null. Narrow physically stressed subgroup findings do
not erase general-population evidence, even when their raw axes describe strong
support. Existing deterministic scope mismatches remain ineligible.

## Deterministic audit and integration

`validated-evidence-position-1.0` uses the original source attribution and semantic
axes with backend relation/scope, relationship design, integrity, null precision
and numeric eligibility guards. It evaluates positions through the existing
qualifier gates without taking the judge's proposal as an input vote. All validated
findings participate, including material findings omitted from model conclusion
dependencies. Only eligible material directions can establish conflict.

Source-validation, transport/schema, integrity and missing-material-evidence
failures leave the position absent and the assessment unavailable. This cannot
become NEI. Contextual/insufficient evidence or material conflict derives NEI.
Design supplies materiality/sufficiency, never direction or an invented null.

New append-only validation JSONB stores raw checker axes, deterministic input,
guarded relations, design-materiality promotions, output and position. Aggregation
reconstructs the saved request/response and audit before counting the position.
Tampered position/audit/provenance is rejected. Causal sufficiency checks also
use the backend material findings; model conclusion dependencies cannot undo them.
Reports and development diagnostics display the position, with the proposal
separately available for disagreement analysis.

Historical V2.4 replay retains its original prompt/parser/qualifier and labels.
Old analysis/report rows are not regenerated. In particular, the original sunscreen
analysis still records its original Unable result; the table describes an explicit
in-memory adoption replay, not an overwrite of that historical report.

No retrieval, source selection, V2.4 quantity catalog/fidelity/comparability,
aggregation thresholds, public labels or production gates changed. Production
remains blocked for this development contract. No migration is needed.

Models remain extraction/Judge 1 DeepSeek-V4.1-Flash, Judge 2 Qwen3.5-Plus,
Judge 3 GLM-4.7, and semantic validator ERNIE-4.5-Turbo-128K via the same providers.
Zero paid model calls, no new full analyses and no model bakeoff.

## Reproduce

From `backend`:

```powershell
.venv/Scripts/python.exe -m app.evaluation.validated_position --input tests/fixtures/validated_position_frozen.json.gz --output ../docs/VALIDATED_EVIDENCE_POSITION_REPLAY.json
.venv/Scripts/python.exe -m pytest tests/test_validated_evidence_position.py tests/test_structured_numeric_references.py tests/test_judging.py -q
```

The compressed fixture preserves the exact frozen packs, captured judge responses
and saved ERNIE results for the four requested claims. See
[machine-readable audit results](VALIDATED_EVIDENCE_POSITION_REPLAY.json).

Verification includes the four-case replay, advisory-label invariance, wrong-label
recovery, causal/design and null guards, subgroup/conflict controls, unavailable
failure cases, numeric IDs, audit tampering, aggregation/report reconstruction,
historical V2.4 compatibility and unchanged production gating: 142 backend checks
passed. Seven explicit
PostgreSQL append-only tests passed. Frontend: 52 tests and build passed.
Ruff and mypy passed. Backend/frontend rebuilt and restarted; both HTTP health
checks passed. The same five saved responses replayed inside deployed Python 3.13
with identical reconstructed audits. The deployed default development contract is
2.5; the old sunscreen report still retains its recorded Unable result.

The broader backend run recorded 907 passed and 15 opt-in skips, with one unrelated
pre-existing failure: `test_debug_trace_is_scoped_bounded_and_disabled` expects
3,000-character truncation, while the already existing full debug-response feature
retains the 5,000-character fixture. Debug trace code is byte-identical to the
pre-task baseline; this task does not change it.

This change removes model-label dependency. Source attribution and semantic axes
still depend on the configured checker; frozen engineering acceptance does not
establish medical correctness or guaranteed future operational reliability.
