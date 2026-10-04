# Numeric fidelity and claim comparability results

Measured 2026-10-03 in local development. **Offline repair checks passed;
normal live acceptance remains incomplete.** One normal smoking request used
five of the authorized maximum eight model calls. All models responded, but
only Luna qualified. Grok and Claude still failed numeric preflight on new
conclusion wording. No further implementation repair or paid run followed
that result, as requested.

## Scope and unchanged configuration

This repair separates source-number validation from numeric claim comparison
inside the existing development 2.3 path. There is no architecture redesign,
new retrieval, evidence manifest, model substitution, prompt edit, confidence
calculation, threshold change, hardcoded NEI result or production qualification.
The repository's existing judge prompt 2.13 and joint prompt 2.4 remain.

| Role | Model, unchanged through AIMLAPI |
| --- | --- |
| Extraction | `inclusionai/ling-3.0-flash` |
| Judge 1 | `x-ai/grok-4-3` |
| Judge 2 | `openai/gpt-6-luna` |
| Judge 3 | `anthropic/claude-sonnet-5.5` |
| Joint validator | `anthropic/claude-haiku-4-5-20251001` |

## 1. Old failure

Retained analysis `3e050b5b-f6ee-47e0-8bfa-fb20941e2383` submitted:

> Smoking increases lung cancer risk by 85%.

Its frozen E2 passage contained a lifelong-smoker risk range and attributable
fractions. Claude's S1 risk range was rejected under numeric 1.1 as
`NUMERIC_UNCERTAIN`; its conclusion also failed. Grok's conclusion failed;
Luna's NEI assessment qualified. Different source-grounded estimates were
being checked through the same numeric alignment result that answered whether
they established the submitted claim's magnitude. This conflated fidelity and
comparability. Explicit references to the user's magnitude also needed to be
kept separate from asserted source values.

A read-only current-contract replay of these retained responses produced no
numeric preflight issues for any of the three. The original rows were not
modified. This establishes coverage of those retained responses, not coverage
of every paraphrase a model can produce. The new normal run below exposed
additional wording failures.

## 2. Explicit versioned contracts

New numerical validation: `numeric-materiality-1.2`; diagnostic contract:
`numeric-fidelity-comparability-1.0`. Implementation:
`backend/app/validation/numeric_effects.py` and `numeric23.py`.

Each frozen `NumericFinding` has version, target ID, materiality, typed source
fidelity, typed claim comparability, numeric effect, semantic-scope-check flag
and output structure status. Quantities store exact decimal strings, measure,
unit, original literal, normalization reason and optional binding (for example,
male/female). Diagnostics do not mutate the raw judge response.

| Stage | Status contract | Meaning |
| --- | --- | --- |
| Source fidelity | `verified`, `mismatch`, `uncertain`, `not_found` | Does the asserted quantity and binding match cited frozen source content? |
| Claim comparability | `aligned`, `compatible_but_narrower`, `different_measure`, `different_comparator`, `different_population`, `different_exposure`, `different_endpoint`, `different_timeframe`, `not_comparable`, `uncertain` | Is a verified source quantity usable at the submitted measure/scope? |
| Numeric effect | `supports_magnitude`, `opposes_magnitude`, `noncomparable`, `unresolved` | Candidate numeric contribution, subject to existing semantic/design/qualification gates |
| Output structure | `structured`, `embedded_numeric_assertions`, `mixed_measures_in_qualitative_finding` | Retained model-field discipline, without a fabricated split |

Fidelity stores the assertion, matched source quantity if available, evidence
IDs, reason and conversion records. Comparability stores claim measure,
differences, reasons, conversions and magnitude relation (`matching`,
`different`, `uncertain`). `semantic_scope_checked=false` explicitly identifies
preflight diagnostics before semantic assessment. Preflight source verification
does not establish semantic attribution or judge qualification.

### Measure taxonomy

`percent_change`, `percentage_points`, `risk_ratio`, `odds_ratio`,
`hazard_ratio`, `rate_ratio`, `absolute_risk`, `risk_difference`,
`population_attributable_fraction`, `attributable_fraction_exposed`,
`prevalence`, `incidence_rate`, `event_count`, `fold_change`, `duration`,
`dose`, `unknown`.

The enum expresses the required distinctions; the conservative lexical parser
does not recognize every possible natural-language rendering. Residual/unknown
material quantities still face strict source checks. Existing CI, p-value and
auxiliary-number checks remain.

## 3. Stages and eligibility

1. Identify asserted quantities and explicit references to the user's magnitude.
2. Check values/measure/bindings against only their cited frozen quotations.
3. Fail closed on wrong, absent or unresolved material source quantities.
4. Retain verified quantities, then compare claim measure and audited scope.
5. Send numeric alignment and a magnitude eligibility map into the existing
   qualifier; preserve raw semantic axes and existing thresholds.

A verified noncomparable quantity is retained as source-grounded evidence.
It cannot power a magnitude vote. Numeric disagreement becomes a candidate
opposition only for comparable quantities; it is not automatically a final
Contradicted verdict. Unknown scope remains unresolved. Existing permitted
exposure-gradient checks still govern compatible narrower findings.

### Times-higher wording

“20–40 times higher” can be verified literally against the same frozen phrase.
The assertion/source carries
`literal_times_higher_no_arithmetic_convention`. No choice between “20 times
the risk” and “20 additional times the risk” is invented. No +2000% or other
percentage is synthesized. At unrestricted aligned scope the numeric effect
remains unresolved; the retained lifelong-smoker scope is additionally narrower
than generic smoking, yielding noncomparable magnitude diagnostics.

An unambiguous RR or risk multiple may be compared with a risk percent change
using the recorded `1 +/- value/100` claim-to-RR conversion. A complete ordered
absolute-risk pair may derive relative change or percentage-point difference
with recorded formulas. A bare range is not an ordered baseline/exposed pair;
a missing or zero baseline cannot supply a relative increase.

### Attributable fractions and other measures

90% male / 79% female attributable fractions can pass fidelity with their
bindings intact. They receive `different_measure` against an 85% relative
increase and cannot become RR magnitude evidence. OR, HR, rate ratios,
prevalence and other distinct measures likewise cannot silently substitute
for RR. Wrong values and swapped male/female bindings fail.

## 4. Claude, Grok and Luna controls

| Pattern | Offline outcome |
| --- | --- |
| Claude S1 range, S2 causal, S3 PAF | Verified quantities survive preflight and reach the offline semantic checker. PAF remains different-measure; no forced final label. |
| Grok range and PAF inside qualitative finding, empty numeric details | Raw fields remain identical, mixed-measure defect is recorded, and the backend does not invent separated findings or magnitude eligibility. |
| Luna explicitly separated range plus qualified NEI | Source fidelity verified, narrower magnitude unresolved, existing NEI qualification retained. Historical Luna audit reconstruction remains valid. |

These are conditional plumbing fixtures, not medical gold. Actual retained
responses were separately replayed read-only. The fresh live response varies
from both fixtures and the older response, as documented below.

## 5. Persistence, historical replay and explanation

Diagnostics are added to the existing validation result JSONB. No database
migration or append-only trigger change is needed. PostgreSQL tests exercise
roundtrip, a second appended validation and rejected in-place update.
Historical numeric 1.0/1.1 retain their original parser/input shape and omit
new stored fields. Recorded-version reconstruction verifies the matching
contract; historical audits, model responses and reports are not rewritten.

Verdict Explanation 1.0 reads qualified new numeric diagnostics descriptively.
It adds no vote, model request, retrieval or scientific inference from rejected
judges. The existing offline smoking explanation remains:

> Validated evidence supports an increase in lung cancer risk with Smoking.
> The retrieved evidence does not establish the claimed 85% magnitude at a
> sufficiently comparable scope, so the specific magnitude could not be verified.

That is an offline regression output. The actual live final explanation below
is operational because the minimum number of qualified judges was not met.

## 6. Development UI and raw text

Development `debug_judge_runs.numeric_findings` exposes only compact audit
fields: fidelity, source/claim measures, comparability, numeric effect,
materiality, target/evidence IDs, differences/conversions, structure and scope
check flag. Raw parser dumps are not displayed by default. No new diagnostics
appear with development debug disabled.

`.debug-response-text` now has neither `max-height` nor `overflow:auto`.
Expanded raw-response excerpts flow as wrapping plain text in the page.
Existing collapsed disclosure, text escaping and response excerpt caps remain;
this UI change does not promise an uncapped provider response API.

## 7. One normal live acceptance — incomplete

Analysis `8e1b7b38-ec1d-49ca-b30e-182a7cdda9cc`, claim
`5362f452-16d9-495b-a149-38897ce5830d`:

> Smoking increases lung cancer risk by 85%.

Normal API submission, normalization, retrieval/selection, judging, validation,
aggregation and report persistence completed. Eight selected documents
(two authoritative/six PubMed) were frozen. End-to-end capture: 63.469 seconds.
Only one semantic request was made because the other two judges stopped at
preflight. All five HTTP calls returned 200; there were no provider errors,
timeouts, schema failures, retries, model switches or extra probes.

| Role | Proposed label | Numeric/source diagnostics | Qualified? |
| --- | --- | --- | --- |
| Grok | Contradicted | S1 20–40 range verified/narrower; S2 30–50% and 10 years verified, mixed structure. Conclusion `20-40x` remained unclassified, `NUMERIC_UNCERTAIN`. | No: `unable_to_validate`, `material_preflight_failure`, `VALIDATION_UNAVAILABLE` |
| Luna | NEI | S2 range verified, `compatible_but_narrower`, `noncomparable`, semantic scope checked. Both findings source-attributed; causal direction and narrower range assessed. | Yes: `validated`; `ONLY_INSUFFICIENT_OR_CONTEXT` |
| Claude | Contradicted | S1 range verified/narrower; S3 90%/79% PAF verified/different-measure. Conclusion's negated claim 85% was misclassified as PAF, `STATEMENT_NUMERIC_MISMATCH`. | No: `invalid`, `material_preflight_failure`, `VALIDATION_FATAL_ISSUE` |

Thus the source-grounded S1/S3 quantities are no longer the failing values,
but **the fresh Claude assessment still did not reach semantic comparison as
a whole**. The new claim-reference wording failure means live acceptance of
the requested Claude path is not established.

Waterfall: **3/3 usable responses; 1/3 source attribution; 1/3 semantic
classification; 1/3 judge qualification.** Final verdict:
`unable_to_verify_reliably`. Exact saved `short_summary` and Verdict Explanation:

> 2 assessments could not be completed or validated, leaving too few qualified
> assessments for a reliable conclusion.

This is not scientific NEI. Aggregation reasons:
`VALIDATION_UNAVAILABLE`, `VALIDATION_FATAL_ISSUE`,
`INSUFFICIENT_QUALIFIED_JUDGES`, `INSUFFICIENT_VALIDATED_JUDGES`, `EVALUATION_ONLY`.
Production qualification remains false.

### Exact remaining failure observations

Grok's raw conclusion justification:

> S1 reports 20-40x risk elevation; S2 and S3 confirm causation without the claimed magnitude.

Its material conclusion diagnostic is `uncertain`, reason
`source_fidelity_only`, version `numeric-materiality-1.2`. The detailed fidelity
records retain `20` and `40` as `unknown` with
`unclassified_asserted_numeral`, no source match and no conversion. ASCII `x`
was not recognized as the supported risk-multiple notation. This is a remaining
lexical coverage failure, not evidence of incorrect source numbers.

Claude's raw conclusion justification:

> Smoking is a established cause of lung cancer (S2). However, the reported relative risk in lifelong smokers is 20-40 times that of non-smokers (S1), far above an 85% increase. Attributable fractions of 79-90% (S3) are a different metric. The claimed 85% increase in risk is therefore not supported by the sources and is contradicted in magnitude.

Its material conclusion diagnostic is `mismatch`, reason
`source_fidelity_only`, version `numeric-materiality-1.2`. The range
`20-40 times` is verified, and `90%` is verified as PAF. The last claim-reference
`85%` remains unmasked and receives `population_attributable_fraction`; the
checker compares it with the male 90% source PAF and records
`different_value_or_measure_in_cited_source`. This is a remaining negated
claim-reference/context-binding failure. The model's contradiction inference
also remains unqualified; repairing source parsing alone would not establish
that inference as medically or numerically valid.

Full exact raw judge responses and full stored validation diagnostics were
captured read-only in ignored `runtime/numeric-fidelity/live-audits.json`.
The API/excerpts/report/call capture is `live.json`. They retain their explicit
one-hour `purge_after` rather than extending historical retention. The numeric
failure excerpts above document the engineering regression without copying
the full retained evidence pack into permanent documentation.

### Call accounting

An independent persistent ledger enforced maximum eight starts for this task.
The earlier task's ledger was not reset. Five calls were used:

| Call | Purpose | Latency (ms) | Input / output tokens |
| --- | --- | --- | --- |
| Ling | Extraction | 2,205 | 739 / 207 |
| Grok | Judge | 10,104 | 13,798 / 993 |
| Luna | Judge | 12,471 | 14,048 / 1,133 |
| Sonnet | Judge | 7,365 | 21,606 / 809 |
| Haiku | Joint evidence axes, Luna | 8,648 | 17,707 / 579 |

Usage is provider-reported; monetary cost was not inferred. After this result,
no remaining calls were spent and no other layer was patched. The temporary
budget server override was removed; normal uvicorn service restored. Backend
health and frontend both returned HTTP 200. The five-call ledger is preserved.

## 8. Verification

| Check | Result |
| --- | --- |
| Focused numeric fidelity/comparability controls | 32 passed |
| Full offline backend | 724 passed, 12 opt-in skipped; two existing Starlette deprecation warnings |
| Explicit PostgreSQL validation/report append-only tests | 5 passed |
| Frontend | 49 passed |
| TypeScript/Vite production build | Passed |
| Ruff app/tests | Passed |
| Mypy | 162 source files clean |
| Alembic check | No new upgrade operations |
| Docker frontend/backend builds | Passed; current backend image includes final ordered-pair fix |
| Diff whitespace check | Passed; Windows Git reports existing LF/CRLF notices |
| Restored runtime | Normal uvicorn command; backend/frontend HTTP 200 |

Controls cover RR1.85/+85%, RR2/RR20 numeric opposition candidates, narrower
lifelong estimates, PAF/HR/OR distinctions, literal times/fold notation,
ambiguous times-higher, complete/incomplete absolute risks and percentage
points, wrong/absent numbers, sex bindings, required measure families,
unstructured mixed fields, raw output preservation, historical numeric replay
and noncomparable quantities not powering contradiction. No new paid fixture
evaluation or benchmark suite was run.

## 9. Remaining limits and stop point

- Fresh live Grok ASCII-x and Claude negated claim-reference parsing still fail.
  The normal acceptance is not complete and all-three qualification is not
  established. The requested stop boundary was observed.
- The parser is conservative and English-oriented. Its taxonomy is not a
  guarantee of complete natural-language or multilingual coverage.
- Scope still relies on the existing audited semantic/design pipeline; verified
  numeric literals do not establish the final claim or validator correctness.
- Mixed unstructured quantities and ambiguous arithmetic remain ineligible
  for magnitude voting. No cleaned qualitative finding is invented.
- One request cannot establish model repeatability, clinical correctness,
  family independence, evidence isolation or production approval.

The raw-answer scrolling change is complete. The numeric separation and
offline checks are implemented; further live parser coverage needs a separately
authorized follow-up because this request explicitly required stopping after
a failed normal run.

## 10. Bounded numeric-parser follow-up (2026-10-03)

This section records the separately authorized **offline-only** follow-up.
Earlier measured live results above remain unchanged. **Zero paid calls** were
made. Models, providers, environment settings, prompts, retrieval/selection,
verdict thresholds, production gates and proposed labels remain unchanged.
No parser model, revision loop, reliability slice or bake-off was added.

### Reproduction before edits and provenance

The exact documented Grok and Claude conclusion strings were added first as
explicitly **reconstructed public regression fixtures** in
backend/tests/test_numeric_parser_followup.py, using documented risk,
attributable-fraction and causal snippets. Both failed before editing:
Grok NUMERIC_UNCERTAIN; Claude STATEMENT_NUMERIC_MISMATCH, on the conclusion.
Fixtures are not historical executions.

Actual capture/database responses were also replayed read-only while permitted.
The capture deadline remained 2026-10-03T18:12:40.555708+00:00, and its responses
matched stored responses. The final actual replay occurred before that deadline.
No TTL was reset, capture copied with a later deadline, audit/report overwritten
or expired database row recreated. Expired captures were not reopened during
the later handoff. The ignored replay helper writes no capture or audit and
calls no model adapter.

### Exact causes and affected functions

- parse_quantities lacked ASCII risk-multiple shorthand; normalization also
  missed spaced Unicode range dashes. Endpoints became unknown scalars.
- claim_references missed the final negated claimed quantity and Luna's
  “claim's exact” wording. A percentage's measure window could span a preceding
  PAF sentence, assigning a claim reference the wrong source measure.
- source_fidelity pooled conclusion dependency citations without resolving a
  quantity's explicit S1 link. It now restricts that result to S1's actual
  frozen citations.
- validate_joint23 obtained preliminary attribution reasons with no checker,
  then returned them after preflight blocking. This left a misleading
  missing-configuration reason even with a configured checker.

### Occurrence roles, local binding and versioning

New numerical behavior: **numeric-materiality-1.3**. Diagnostic contract:
**numeric-fidelity-comparability-1.1**. The new numeric_occurrences internal
helper is deterministic. Each original occurrence retains exact half-open
offsets, spelling, values, local measure hint, direction, reference-match status
and explicit statement link. Roles are source_assertion, claim_reference,
derived_assertion, identifier and ambiguous.

Classification precedes source matching. Existing validation JSONB additionally
saves numeric_occurrences for statement fields, numeric-detail indices and both
conclusion fields. A reference excluded from source-own-estimate checking
remains in this metadata and unchanged raw text for existing comparability and
inference checks. It needs wording plus matching submitted value/measure/
direction; wrong references fail closed and uncertain roles remain explicit.

Risk-attached ASCII x, Unicode ×, decimals, whitespace and hyphen/Unicode-dash
ranges become one typed multiple/range with original offsets. S/E/unit IDs are
identifiers, not statistics. The matched source's times-higher ambiguity remains;
recognition cannot invent a percentage conversion or establish claim scope.

Binding stays within sentence/semicolon boundaries, preserving decimals and
unit-ID dots. Explicit local change measures take precedence over unrelated
PAF wording. Equal values can have different roles in separate occurrences.
Alleged source reporting/confirmation, including “source did not find,” still
needs grounding. Quoting, negation, the word “claimed,” equality to the user
value and dependency=false are not global exemptions. “No source supports
85%” remains ambiguous: missing literal text does not rule out equivalent RR.

A literal 79–90% PAF summary needs both distinct bound source fractions in one
actual frozen quotation, retaining male/female bindings. Different papers or
separate quotations of the same evidence ID cannot supply a coincidental range.
No RR interval or percentage increase is synthesized.

### Exact before/after occurrence record

Spans are zero-based half-open offsets in each original conclusion justification.
All rows target conclusion. Numeric 1.2 had no persisted occurrence-role
metadata, so its inferred handling is described explicitly.

| Occurrence | Original span | Before, numeric 1.2 | After, numeric 1.3 |
| --- | --- | --- | --- |
| Grok 20-40x | [11,17); old scalars [11,13), [14,16) | Unknown 20 and 40; no source match; NUMERIC_UNCERTAIN | One source-assertion fold range [20,40], S1 → E2 frozen range, verified, no issue |
| Grok S1/S2/S3 | [0,2), [34,36), [41,43) | Known IDs ignored by legacy guard | Explicit identifier roles; no study values |
| Luna 85% | [99,102) | Masked reference; no issue | Matched claim reference, percent change/increase 85; no source-estimate comparison |
| Claude 20-40 times | [111,122) | Verified fold range [20,40], E2 | Source assertion linked S1 → E2, verified, source ambiguity retained |
| Claude earlier 85%, “far above an” | [162,165) | Masked comparison reference | Separate matched claim reference, percent change/increase 85 |
| Claude 79-90% | [202,208) | Typed 90% PAF matched male 90%; 79 remained uncovered residue | Source assertion linked S3 → E2; both endpoints verified in one quote, male:90/female:79, different measure |
| Claude final claimed 85% | [250,253) | Misbound PAF 85%, selected male source PAF 90%; STATEMENT_NUMERIC_MISMATCH | Matched claim reference, percent change/increase 85; no source PAF selected or compared |
| Claude S2/S1/S3 | [47,49), [144,146), [210,212) | Known IDs ignored by legacy guard | Explicit identifier roles; no study values |

Grok's typed quantity includes its noun, [11,22), “20-40x risk”.
The E2 source literal remains “20-40 times higher” with
literal_times_higher_no_arithmetic_convention and empty conversions.
Claude's two 85% occurrences are separately recorded. Its actual source's
distinct male/female fraction bindings remain intact.

### Exact saved-response deterministic preflight acceptance

Actual saved responses from analysis 8e1b7b38-ec1d-49ca-b30e-182a7cdda9cc
were replayed through real numeric_issues23 and validate_joint23 preflight
read-only within capture retention.

| Judge | Before, 1.2 | After, 1.3 | Offline checker boundary |
| --- | --- | --- | --- |
| Grok | Conclusion NUMERIC_UNCERTAIN | Zero numeric issues; source assertions aligned | Reached once |
| Luna | Zero numeric issues | Zero numeric issues; claim-reference-only conclusion not applicable to source-estimate matching | Reached once |
| Claude | Conclusion STATEMENT_NUMERIC_MISMATCH | Zero numeric issues; range/fractions source-verified | Reached once |

The explicitly labeled test double intentionally stops at checker entry.
It performs **no semantic evaluation**, is not saved as a historical result and
cannot establish qualification or a new verdict. Proposed labels are unchanged:
Grok/Claude Contradicted, Luna NEI. Luna's saved numeric 1.2 audit still
reconstructed successfully with its original input hash and qualification.
Versions 1.0/1.1/1.2 retain original semantics, defects and payload shapes;
old diagnostic shape remains 1.0 and new fields are omitted from old payloads.

### Accurate skipped-check diagnostics

For new audits with a configured checker blocked by numeric preflight,
semantic_validation.state is skipped_due_to_numeric_preflight. It records
configured provider/model and stable blocking issue references:
target_id:issue_code:ordinal in the retained issue list. Statement/conclusion
reasons and provenance describe this skip. No call occurs (attempt_count=0);
attribution remains unable to assess. The state is not missing configuration,
provider failure or semantic success. Other deterministic blocking has a
separate skipped state. Genuine missing configuration remains distinct.
Historical diagnostic records were not rewritten.

### Verification and adversarial coverage

**63 follow-up controls passed**, including:

- Exact failures and varied numbers; ASCII/Unicode multiplication, ranges,
  decimals/whitespace, exact spans, changed endpoints and unrelated dose/
  dimension/magnification contexts; ambiguity retained without conversion.
- Positive/negative claim commentary, multiple roles for equal values, quoted
  assertions, alleged confirmation, negated source findings, wrong claim
  values/direction/measure and ambiguous absence-of-support wording.
- Adjacent/reversed PAF sentences, different measures sharing a value, sex
  bindings, S/E/unit IDs, S1 citation isolation and same-quotation range checks.
- Unsupported new/derived assertions with false dependency flags; PAF/RR
  separation and narrower lifelong-smoker scope.
- Honest offline checker entry, unchanged raw responses/evidence/proposals,
  configured skips, true missing configuration and historical 1.2 replay.

Final backend: **787 passed, 13 opt-in skipped**, two existing Starlette
deprecation warnings. Explicit PostgreSQL: **six passed**, including numeric
occurrence/skip JSONB roundtrip, blocking references, second appended validation
and rejected update. Ruff passed; mypy clean on 163 source files; Alembic found
no new upgrade operations. No migration or append-only trigger change.
Diff whitespace check passed. Frontend tests/build were not rerun because
rendering did not change.

The backend image was rebuilt and normal service restarted. Its package-index
connection stalled with an SSL EOF warning; local packaging then succeeded
without a code workaround. This delay happened after the retained offline
replay and did not justify reopening or extending expired captures.

### Remaining uncertainty and stop

Parser acceptance is complete for these bounded regressions/counterexamples.
The English lexical classifier is conservative, not a general semantic parser.
Unknown quantities/roles remain unresolved. No claim is made that all judges
now qualify, that Contradicted is correct or that the final verdict is NEI.
Existing semantic attribution, scope/design and deterministic qualification
must decide those questions in a separately authorized evaluation. The saved
live report remains Unable and immutable. **Zero paid calls** in this follow-up;
implementation and verification stop here.
