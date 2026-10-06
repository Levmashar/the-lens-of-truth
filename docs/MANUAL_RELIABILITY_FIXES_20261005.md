# Manual reliability fixes and live acceptance (2026-10-05)

All six requested cases ran through the real backend worker: fresh extraction,
retrieval/selection, judges, checker, deterministic qualification, aggregation,
report and append-only persistence. All finished with 3/3 qualified assessments.
An additional severe-exercise case ran on the final build. No model was changed.

## Before and after

Baseline: the latest ten retained manual analyses. NEI = Not Enough Evidence.

| Claim | Before (qualified) | Live after (qualified) | Total latency |
| --- | --- | --- | --- |
| Smoking increases lung cancer risk by 85%. | NEI (2/3) | NEI (3/3) | 166.8s |
| Lifelong smokers have 20 to 40 times the lung cancer risk of non-smokers. | Unable (0/3) | NEI (3/3) | 148.6s |
| Vitamin C reduces common-cold incidence in people undergoing severe physical exercise. | NEI (3/3) | Supported (3/3) | 172.4s |
| Regular vitamin C supplementation shortens common-cold duration in adults. | Unable (0/3) | Supported (3/3) | 150.2s |
| Smoking causes lung cancer. | Supported (3/3) | Supported (3/3) | 143.9s |
| Daily sunscreen use reduces invasive melanoma risk. | Supported (3/3) | Supported (3/3) | 178.1s |
| Vitamin C reduces common-cold incidence in people undergoing severe physical exercise. (final build repeat) | NEI (3/3) | Supported (3/3) | 111.7s |

The range claim now stores `kind=fold_change`, `lower_value=20`, `upper_value=40`
and `raw_text=20 to 40 times`, with literal exposure and endpoint recovery when
omitted. It remains NEI under the unchanged quantity rule: the cited review says
"20-40 times higher", frozen as `literal_times_higher_no_arithmetic_convention`.
That source wording is faithfully referenced but does not license choosing an
arithmetic convention. PAF percentages cannot replace individual risk ratios.

## Root causes and changes

### Integrity

The range baseline `b93ec0fb-55f2-4d2d-8060-b05dd2ee2e9a` cited
`authoritative:iarc-tobacco-code`. The duration baseline
`76a90ef6-e3c9-40fd-abf3-6d631137e66b` cited
`authoritative:nccih-cold-evidence`. Both frozen documents have `checks=[]`,
`integrity.status=unknown`, `updated_at=null`, `currency=unknown` and the warning
`source_currency_unknown`. These cases failed because the approved pages were
undated, rather than because their material research failed a DOI check.

The qualifier globally checked every finding's integrity before determining
whether it could participate. This let unused context veto independently
verified research. The versioned qualification projection now ignores only
unknown integrity on nonparticipating context and retains the raw statuses and
ignored statement IDs in its audit. These pages cannot establish a material
direction or satisfy a causal gate. Unknown material sources, retractions and
expressions of concern still block qualification. No integrity requirement for
material evidence was removed.

### Numeric normalization

The parser covered trailing `by N%` / `N-fold`, RR points and double/triple verbs,
but missed inline `20 to 40 times`. It now preserves fold/RR ranges, their literal
notation and both bounds. Old single-value serialization remains unchanged when
bounds are absent, preserving historical hashes. Reversed ranges and ambiguous
"times higher" wording stay uncertain. Exact comparable ranges match, disjoint
ranges oppose, and partial overlap or a lone point inside the range stays
unresolved. No approximation tolerance or metric substitution was introduced.

### Causal review design

The exercise baseline `d45b02e8-0860-4840-9e04-823ef5b835c4` correctly froze
PubMed 23440782 as `meta_analysis`, with `exposure_assignment=synthesized`.
Its abstract says the majority of included trials were randomized, double-blind,
and excluding nonrandomized/nonblinded trials did not change the conclusions.
The bug was using the retrieval document's `contextual` role as the individual
finding's eligibility decision, despite the attributed, aligned direct result.

The qualification projection recognizes affirmative randomized-trial methods
from frozen synthesis text, then admits an aligned validated direct/synthesis
finding as direct evidence. It preserves the document's original retrieval role,
review design and synthesized assignment. It does not rewrite a review into a
single randomized trial or change source selection. Objective trial-synthesis
facts can establish materiality with strength=`supporting`; scope, semantic
direction, finding basis, numeric eligibility and integrity guards still apply.
Final causal aggregation uses the same reconstructed finding facts instead of
reverting to the document-level role.

Final build: `validated-evidence-position-1.2`. Historical 1.0 and intermediate
1.1 audits remain reconstructable; original metadata, raw axes, design overrides,
materiality promotions and ignored context IDs remain auditable. V2.4 replay,
quantity references, prompt instructions and production gates are unchanged.

### Validator contract and misleading audit mismatch

The smoking +85% baseline `13c074c9-cf80-4066-adea-beacd1758dc2` excluded GLM
judge `54481328-f94e-4626-95ae-43d0bb016915`. Its failed checker response was not
persisted and its process-local raw trace expired. One paid replay of the exact
saved judge input passed. Its exact original exception cannot be recovered from
the retained data; this report does not claim otherwise.

A concrete contract bug is reproduced by regression tests: newer checker replies
first passed through `check_response23`, whose older-prompt guard skips frozen
child-unit normalization for V2.4/V2.5. A valid `E*.U*` reference therefore raised
`ValueError: Axes source references mismatch` before the newer check could accept
verified parent ownership. The adapter now dispatches to the matching contract.
Unknown/foreign, missing, reordered and duplicate IDs remain rejected. Exact
frozen child/parent conversions are recorded, with no fuzzy repair.

Schema exceptions also inherited the blanket `source_id_contract_error` label.
Rejected replies now retain their precise exception type/message and full raw
content in the validation audit, with schema and ID errors distinguished.
A failed checker remains an unavailable assessment. Aggregation no longer tries
to parse its absent position audit and adds a misleading `AUDIT_RECORD_MISMATCH`.
The fresh smoking +85% run has 3/3 qualified NEI assessments and no contract error.

## Active models and actual paid calls

All use the existing Paratera base `https://llmapi.paratera.com/v1`.

| Role | Model |
| --- | --- |
| Extraction | DeepSeek-V4.1-Flash |
| Judge 1 | DeepSeek-V4.1-Flash |
| Judge 2 | Qwen3.5-Plus |
| Judge 3 | GLM-4.7 |
| Semantic validator | Qwen3.8-Flash, thinking disabled |

52 inference HTTP requests, including the initial diagnostic
and all retries, within the 56-request cap. The six-case round needed one judge
schema retry and one extraction offset retry; existing retry behavior recovered
both. No model bakeoff was performed. Provider-reported tokens excluding the
initial diagnostic: 1,044,112
input and 47,571 output.
A billed monetary total was not returned by the provider.

The bounded harness uses the same `start_analysis` / `run_background` composition
as the API, with real configured transports. It counts every chat-completion
HTTP attempt and never captures authorization headers or keys. Results persist
normally; process-local debug events and raw replies are archived privately.
No saved response was substituted for a paid call in these live reruns.

## Verification

- 120 existing structured-reference, position and transport tests passed.
- 151 additional normalization, numeric, joint and verdict tests passed.
- 24 new regression tests cover material integrity failures, retractions/concerns,
  negated/nonrandomized methods, ranges, matching contracts and exact errors.
- Final selected 30 regression/position tests passed.
- Two migrated-PostgreSQL append-only structured/V2.5 persistence tests passed.
- All 23 previously validated manual audits reconstructed under their recorded rules.
- All 21 new live audits reconstructed, with unchanged positions under the final rules.
- Ruff and mypy (172 source files) passed; backend rebuilt/restarted and health verified.

The recorded cases demonstrate the generic fixes, not a guarantee that future
model replies cannot fail. All reports retain `production_qualified=false`.
Retrieval, source selection, final public labels and verdict thresholds are unchanged.

## Live analysis IDs

- Smoking increases lung cancer risk by 85%.: `1b7e4be5-8a87-4ab8-95e9-b2a515405c08`
- Lifelong smokers have 20 to 40 times the lung cancer risk of non-smokers.: `33af8956-6584-4080-9f2b-5e10375cfa3f`
- Vitamin C reduces common-cold incidence in people undergoing severe physical exercise.: `5a7e4762-ee04-41d7-b7ec-215709b6e8e9`
- Regular vitamin C supplementation shortens common-cold duration in adults.: `00a46990-00b2-46a4-b100-712219fc0327`
- Smoking causes lung cancer.: `a56e4986-6d1f-4532-91ef-4eea832110e0`
- Daily sunscreen use reduces invasive melanoma risk.: `5c224d0d-77d0-4f86-a6c7-2570e4dbe761`
- Vitamin C reduces common-cold incidence in people undergoing severe physical exercise. (final build repeat): `c1666d3f-21ba-48e2-b399-e513d3b6612b`

The compact audit artifact is [MANUAL_RELIABILITY_FIXES_20261005.json](MANUAL_RELIABILITY_FIXES_20261005.json).
Full raw replies, snapshots and audits are saved locally in
`C:/Users/levma/AppData/Local/Temp/lens_reliability_live_final_20261005.json`.
