# Claim-type causal evidence follow-up - 2026-10-06

The two requested mismatches were confirmed as evidence-policy and authoritative
retrieval coverage problems, not lost disease endpoints or model transport errors.
All checks used the real frontend HTTP submission/polling/report flow. Labels are
engineering observations on the retrieved evidence, not clinical validation.

## Root causes

**HPV/cervical cancer:** The taxonomy defaulted unfamiliar causal exposures to
intervention_causality. The selected findings described established etiology,
but could not satisfy intervention-style design eligibility. The reviewed
registry contained no HPV document, even though the [NCI causes assessment](https://www.cancer.gov/types/cervical/causes-risk-prevention)
and [professional PDQ synthesis](https://www.cancer.gov/types/cervical/hp/cervical-prevention-pdq)
explicitly establish the causal role of persistent high-risk infection and
describe the underlying epidemiologic evidence. Both are now fetched, frozen
and selected; their shared evidence body is not counted as independent sources.
Both retrieval coverage and qualification mattered; endpoint normalization was
already correct.

**HIV/mosquito transmission:** The same taxonomy error applied. PubMed material
explicitly opposing transmission was present, but unknown-design discussion and
belief surveys could not establish eligible causal evidence. The reviewed
registry omitted [CDC's explicit transmission guidance](https://hivrisk.cdc.gov/what-is-hiv/).
The bounded adapter also needed visible abbreviated dates and negative list
introductions to preserve this document accurately. The CDC route-exclusion
assessment now reaches qualification; no RCT of human HIV exposure is required.
Qualification was the principal obstacle to previously retrieved material;
retrieval coverage supplied the reviewed explicit exclusion that resolves it.

## Bounded changes

- Classify natural disease/organism exposures through linked ontology categories
  and transmission through question semantics. Manipulation, treatment and
  prevention remain intervention questions. No disease-specific policy branch.
- Admit explicit current reviewed causal/transmission assessments only when the
  actual cited text establishes the matching exposure, endpoint and relation.
  Source prestige, omission, speculative assertions and ordinary opinion fail.
- Allow eligible convergent source-grounded epidemiology with independent
  cohort/case-control evidence and temporality, or empirical synthesis with
  the required converging components. Mechanism alone is insufficient.
- Bind eligibility and any causal-relation correction to validated findings and
  their frozen source units. Preserve attribution, numeric, integrity, scope,
  endpoint, null and production gates. Explicit causal disclaimers block the
  new nonrandomized route.
- Add three reviewed NCI/CDC documents; preserve the CDC negative introduction
  together with its list. Support visible abbreviated update dates, while
  rejecting comments/site footers. Existing freshness limits remain unchanged.
- Improve approved-document entity matching for word order and plurals; retain
  PubMed phrase matching and existing selection quotas/weights. Extend the
  existing bounded design query to cohort/case-control evidence for these types.
- Clarify these distinctions in semantic prompt 2.7. Judge prompts and all
  models remain unchanged. Final policy 2.1 delegates clinical treatment and
  prevention to the established eligibility rules.

An intermediate 2.0 policy unintentionally tightened existing synthesis
eligibility; the full suite caught nine vitamin-C failures. The final 2.1
policy restores existing clinical behavior. Its separate historical dispatch
preserves exact intermediate 1.7/2.0 audit reconstruction.

## Live results

| Claim | Before | After | Validated positions | Backend latency |
| -- | -- | -- | -- | -- |
| Persistent high-risk HPV infection can cause cervical cancer. | NEI | Supported | 3 Supported | 151.6 s |
| HIV is commonly transmitted by mosquito bites. | NEI | Contradicted | 3 Contradicted | 194.4 s |
| High blood pressure increases the risk of stroke. | Supported | Supported | 3 Supported | 210.5 s |
| Antibiotics can treat bacterial pneumonia. | Supported | Supported on final-build repeat | 3 Supported | 156.2 s |
| Daily sunscreen use reduces invasive melanoma risk. | Supported | Supported | 3 Supported | 168.9 s |

Each report returned HTTP 200, with 3/3 qualified assessments and unchanged
production gating (evaluation only). Counts above describe positions, not merely
operational qualification. Final-model proposals are advisory under V2.5.

The initial five live runs used intermediate position 1.7/policy 2.0. Replaying
all 15 saved validations on final position 1.8/policy 2.1 preserves their exact
historical audits and positions, including the two target fixes and BP/sunscreen
controls. The final-build antibiotics repeat used position 1.8/policy 2.1 live.
The other four claims were not billed again solely to regenerate identical
saved positions.

The first antibiotics run was NEI (two NEI positions, one Supported; 229.5 s).
Its saved response remains NEI under final 2.1: the blockers were endpoint and
active-comparator scope limitations, not the stricter intermediate synthesis
dispatch. The repeat returned three Supported positions with eligible treatment
findings. This is observed response variability, not evidence that treatment
safeguards were weakened or that all future runs are guaranteed to agree.

Six total full runs, only one repeat, recorded 43 provider call starts including
retries/revisions; no separate model bakeoff or paid probes. See the
[compact diagnostics](CLAIM_TYPE_CAUSAL_EVIDENCE_RESULTS_20261006.json).

Analysis IDs:

- HPV: c99943f5-5972-46b4-8023-a26dd4fcae6c
- HIV: ca420da0-b379-42de-a2e4-ceaf2a3205e0
- BP: c846a29e-c911-467a-af84-08a4fedd5a41
- Antibiotics first: d671f726-fbd1-41b3-b056-a60de923597e
- Antibiotics final: 8f0d0707-61b0-471a-aad0-65c9343b96d0
- Sunscreen: 96ff7b45-7b1d-44ef-8293-bfc935feab58

## Verification and versions

- Full backend: **1,066 passed**, RUN_DB_TESTS=1, no skips (333.87 s).
- Frontend: **52 passed**, TypeScript/Vite build passed.
- Ruff and mypy: passed, 176 source files checked by mypy.
- 34 new policy/retrieval/guard tests cover generic taxonomy, real frozen
  reviewed-source recall, causal evidence convergence, disclaimer rejection,
  source currency/integrity, speculation/omission/wrong endpoint, negative list
  preservation and unchanged intervention eligibility.
- Seven previous live cases retain 23 exact historical audit reconstructions.
  The new initial five cases retain 15 exact reconstructions and unchanged
  final-source replay positions. Final-repeat audit results are recorded below.
- Fresh deployment reports position 1.8/policy 2.1; health endpoint HTTP 200.

Final-repeat audits: all three reconstruct exactly and remain Supported. Total
checked historical/new audit records: 41 (23 previous, 15 initial, 3 final).
Complete source packs and responses are saved locally in
`C:/Users/levma/AppData/Local/Temp/lens_etiologic_live_frozen_20261006.json`;
frontend reports/raw development responses in
`C:/Users/levma/AppData/Local/Temp/lens_etiologic_api_raw_20261006.json`.

Current source: V2.5 validated evidence architecture; contracts 2.5; V2.4
structured quantity references; evidence pack 1.5; query-plan 1.6; validated
position 1.8; question-evidence policy 2.1; semantic prompt 2.7; judge prompt
2.15; verdict policy 1.4; approved-source manifest 1.1. Historical position
versions, including the intermediate 1.7, remain reconstructable.

Models unchanged, all through Paratera: extraction/J1 DeepSeek-V4.1-Flash,
J2 Qwen3.5-Plus (provisional), J3 GLM-4.7, validator Qwen3.8-Flash with thinking
disabled. Final backend image is rebuilt and restarted before the control
repeat. No full analyses outside the two requested claims and three controls.
