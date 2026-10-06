# Manual tests 11-15: generic fixes and seven live reruns

Implemented on 2026-10-05. Reviewed the five pasted analysis objects and their
retained judge/validator/evidence-pack records. The main live rerun went through
the real `run_background` worker with deployed settings, extraction, PubMed,
Crossref, source selection, three judges, semantic validation and reporting.
There were **57 paid requests**, including bounded retries and a BP repeat,
under a 64-request cap. No model or prompt-instruction changes were made.

## Roots and changes

1. **BP and stroke: review design was lost at qualification.** In the original
   run `fdb11fc3-1287-471c-8892-f5dc26716c92`, PubMed 31243539 explicitly says
   completed randomized clinical trials demonstrate a stroke benefit from BP
   reduction. Its document remains `study_design=review`, analysis design and
   exposure assignment unknown. The qualifier could not use that trial synthesis.
   New optional `completed_randomized_result_synthesis` records an affirmative
   completed result from frozen review text. An attributed, aligned causal/direct
   finding can use an audited `causal_evidence_synthesis` projection, including
   objective materiality, and final aggregation uses those same facts. A mere
   trial mention, future trial, negation, nonrandomized trial, fact sheet or generic
   review does not receive this eligibility. Design supplies no direction.

2. **Magnet cure: literal grounding rejected a relation annotation.** Extraction
   returned `diabetes (cured)`, which was absent verbatim from the source. Endpoint
   grounding now removes only known relation annotations and recovers the literal
   object of cures/treats/prevents/reverses when needed. Disease qualifiers are
   preserved; missing qualifiers are not invented. The live outcome is `diabetes`.
   Truly incomplete normalization now exposes `unable_to_verify_reliably` in the
   claim summary and frontend. Its technical failed status remains available for
   diagnostics; it does not fabricate a report, pack or medical verdict record.
   The previous failed magnet run now also exposes that operational public label.

3. **Invalid opposition was merely weak/contextual by accident.** Source-owned
   guards now record missing claimed exposure/endpoint, omission or alternative-
   cause inference, and ecological/time-trend context. These cannot become material
   contradiction merely because the validator says aligned/decisive/direct. Frozen
   unit text plus cited-document terminology supplies a necessary concept-presence
   check, with inflection/reordered nouns; it supplies no medical direction.
   A mortality word alone is not an ecological trend.

4. **Existing-disease effects are not incident disease.** Cell killing, treatment,
   progression and diagnostic-process findings are projected to neutral/contextual
   and incompatible endpoint for an onset claim. Incident diagnoses in a prevention
   result remain comparable. The blue-light laboratory findings are no longer
   opposition. Original model axes and findings remain in each audit, together with
   `semantic_guard_overrides`; there is no destructive rewrite of the saved reply.

5. **Retrieval split an entity and discarded its source qualifier.** Blue Light
   was correctly linked to MeSH, but the lexical query searched independent blue
   and light words and omitted Smartphone. Linked concepts now use phrase atoms;
   additional confident exposure entities are retained across query families.
   Ranking no longer calls methylene-blue-plus-light a Blue Light match. The live
   blue-light pack selected one smartphone WBC diagnostic paper, rather than
   unrelated dye/treatment records; it remains context, not leukemia-onset evidence.
   Eyesight search adds recorded visual-acuity/visual-function variants while
   preserving the broad original endpoint and existing seeing/sight recognition.
   It does not invent a specific eye disease or equate a nutritional mechanism
   with improved eyesight.

## Live results

| Claim | Before | After | Qualified | Seconds | New analysis ID |
|---|---|---|---:|---:|---|
| High blood pressure increases the risk of stroke. | Not Enough Evidence | Supported | 3/3 | 133.1 | `c7f33931-41a6-466e-ae34-2770d386cb11` |
| High blood pressure causes lung cancer. | Not Enough Evidence | Not Enough Evidence | 3/3 | 159.0 | `809b2176-ef01-42e7-b421-5c67db214a0f` |
| Carrots improve eyesight. | Not Enough Evidence | Not Enough Evidence | 3/3 | 118.1 | `38c77573-c523-4328-9dbc-5bad48a86d59` |
| Sleeping with a magnet under your pillow cures diabetes. | Failed normalization; null label | Not Enough Evidence | 3/3 | 168.3 | `6bd26325-107e-4898-8bbf-65b81d2b2606` |
| Blue light from smartphones causes leukemia. | Not Enough Evidence | Not Enough Evidence | 3/3 | 93.7 | `4420f5b3-9f8d-4d0a-ab87-a360dfd36ba8` |
| Smoking causes lung cancer. | Supported | Supported | 3/3 | 136.3 | `604230ec-bc2f-4f8a-9af1-89f415b326e9` |
| Daily sunscreen use reduces invasive melanoma risk. | Supported | Supported | 2/3 | 286.8 | `7e4be04a-21e4-4527-9c42-9038ff56ea31` |

All seven requested cases completed. Production qualification remains false.
Sunscreen Judge 1 (DeepSeek) exhausted its configured 110-second judge deadline
across two attempts; extraction also required its existing timeout retry. Qwen
and GLM responded, validated and independently yielded Supported. That exclusion
remains unavailable, never NEI. No timeout, retry, quorum or production gate was
weakened to make the test pass.

The first BP rerun (`aa6448b2-e842-4f0f-892e-c58866f585f7`) remained NEI: an
initial canonical-synonym OR expansion in Title/Abstract crowded out the explicit
randomized-result review. Query-plan 1.4 retains canonical recall in MeSH but uses
the stated phrase in lexical queries when both MeSH anchors exist. A direct
PubMed preflight recovered 31243539, and the full paid BP repeat then returned
Supported for all three judges. This failed iteration is retained, not hidden.
The six other live reruns used query-plan 1.3; the corrected query planner's 1.4
regressions pass. The final BP repeat used query-plan 1.4.

## Scope, versions and validation

- Final position version: `validated-evidence-position-1.4`. Version 1.3 is retained
  exactly for the new live audits; 1.4 refines diagnosis and trend-word guards.
- All 23 successful live audits reconstruct exactly and their saved replies/axes
  replay to the same positions under final 1.4. This last replay made zero new
  paid calls; the observations above came from the 57 real requests.
- All 33 retained pre-task position audits reconstruct without modification.
  Historical position 1.0/1.1/1.2/1.3 and V2.4 contracts remain supported. New
  synthesis metadata is confined to V2.5; invalid historical labels are not mapped.
- V2.4 source units/quantity catalogs, selection rules/limits, numeric rules,
  verdict thresholds, causal/integrity gates and four public labels are retained.
  Retrieval query semantics and topical phrase matching were changed as requested.
- 112 targeted normalization/retrieval/orchestration/manual tests passed; the
  four frozen cases retain position independence from advisory labels; two
  PostgreSQL append-only audit tests passed; all 52 frontend tests passed.
  Ruff and mypy pass for all 173 application modules; both Docker builds pass.
- Broader suite before the last narrow guard refinements: 970 passed, 15 skipped,
  two unrelated failures remain. The Miri-default test reads the active Paratera
  `.env` instead of an isolated default fixture. The debug-trace test still expects
  the older 3,000-character truncation after the earlier full-response change.
  Neither was resolved by altering application models or truncating debug output.

## Files

- `backend/app/pipeline/pico.py`: literal disease endpoint grounding/recovery.
- `backend/app/retrieval/query_planner.py`, `ranking.py`, `lexical.py`, `models.py`:
  versioned phrase/qualifier preservation and bounded lay retrieval vocabulary.
- `backend/app/retrieval/sufficiency.py`: affirmative completed trial-synthesis fact.
- `backend/app/validation/relationship_guards.py`, `axes.py`, `position.py`,
  `relation_flow.py`, `joint24.py`: versioned guards, raw-context audit and factual
  synthesis eligibility; historical contract dispatch preserved.
- `backend/app/verdict/service.py`: aggregation uses the same audited design facts.
- `backend/app/api/routes/analyses.py`, `frontend/src/pages/analysis.ts`: operational
  Unable label for incomplete normalization.
- `backend/tests/test_manual_11_15.py` and saved fixture, normalization/retrieval/
  orchestration/frontend regressions: generic adversarial cases and real inputs.

## Active models

| Role | Provider | Model |
|---|---|---|
| Extraction | Paratera, OpenAI-compatible adapter | DeepSeek-V4.1-Flash |
| Judge 1 | Paratera | DeepSeek-V4.1-Flash |
| Judge 2 | Paratera | Qwen3.5-Plus |
| Judge 3 | Paratera | GLM-4.7 |
| Semantic validator | Paratera, thinking disabled | Qwen3.8-Flash |

Base API remains `https://llmapi.paratera.com/v1`. No AIMLAPI calls were made.
Returned usage totals 850,107 tokens; canceled requests have no returned usage,
so this is not a complete billing estimate. Raw provider replies, saved packs,
judges, validators and the failed iteration are retained locally in
`%LOCALAPPDATA%/Temp/lens_manual_11_15_live_20261005.json`. The compact checked-in
[result summary](MANUAL_TESTS_11_15_FIXES_20261005.json) records IDs, raw proposals,
positions, guard reasons, projected design facts, models and timings. Services
were rebuilt and restarted; later guard refinements are checked using the saved
live replies, rather than making unnecessary further paid calls.

## Cleanup and current baseline (2026-10-06)

The two unrelated test failures above are now fixed. Full deployed backend suite:
990 passed, zero failures/skips, with PostgreSQL tests enabled. Frontend: 52 passed;
build/Ruff/mypy pass. Fresh blue-light and carrots runs both use final query-plan
1.4 and position 1.4 and both return NEI. Blue light qualifies 3/3; carrots 2/3,
with Qwen's two missing-field schema failures explicitly excluded. No medical
logic/model/prompt changes. This is the frozen development baseline with the
Qwen limitation retained. See [exact current results and versions](RELIABILITY_BASELINE_20261006.md).
