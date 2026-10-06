# Selected scope, setting and polarity fixes - 2026-10-06

All seven requested claims completed through the real frontend HTTP flow:
POST /v1/analyses, status/claim polling and GET report. Final reports all returned
HTTP 200. One additional laboratory repeat verified final experiment binding.
These are engineering observations on retrieved evidence, not clinical validation.

## Before / after

NEI means Not Enough Evidence. Unable denotes the earlier normalization failure.
Qualified counts include usable NEI assessments and do not imply unanimity.

| # | Claim | Before | After | Qualified | Backend latency |
| -- | -- | -- | -- | -- | -- |
| 3 | Persistent high-risk HPV infection can cause cervical cancer. | NEI | NEI | 3/3 | 211.4 s |
| 6 | Antibiotics can treat bacterial pneumonia. | NEI | Supported | 3/3 | 150.1 s |
| 9 | Blue light can induce apoptosis in some leukemia cell lines under laboratory conditions. | Unable | Supported | 3/3 | 127.0 s |
| 12 | High blood pressure lowers the risk of stroke. | NEI | Contradicted | 2/3 | 199.9 s |
| 15 | HIV is commonly transmitted by mosquito bites. | Unable | NEI | 3/3 | 153.5 s |
| control | Smoking causes lung cancer. | Supported | Supported | 3/3 | 143.3 s |
| control | Daily sunscreen use reduces invasive melanoma risk. | Supported | Supported | 3/3 | 167.7 s |

## Root causes and changes

### 9 - Laboratory blue light / apoptosis

Completeness required the setting word laboratory as a core medical concept.
Ignore explicit setting-only phrases in the missing-concept audit, preserving
the exact claim. Laboratory workers and laboratory exposures/outcomes still
require grounding.

The first resumed live run exposed a second generic problem: actual cell-exposure
experiments were routed to clinical causal-design eligibility. Explicit cellular
questions now retain relevant in-vitro evidence and use source-stated, actual
laboratory interventions bound to the finding. The final repeat is Supported,
three Supported positions. Controls/comparators are not invented when absent.
Reviews, planned/speculative experiments and background cannot establish primary
experiments. Laboratory facts never qualify human clinical causation.

### 15 - HIV / mosquito transmission

The extractor returned HIV transmission; literal-only outcome matching lost HIV.
Strip a transmission/infection relation annotation only when the exact disease
substring and corresponding relation are present in the raw claim. No disease
or subtype is invented. Fresh PICO keeps outcome HIV and exposure mosquito bites.

Normalization, retrieval, attribution and semantic classification now pass.
The fresh final result is NEI, not the expected Contradicted: selected sources
oppose transmission, but their narrative/mechanistic review discussions and
reported experimental/probability conclusions lack eligible finding-bound study
design under current causal policy. Knowledge surveys are contextual. This
remaining coverage/design limitation is explicit; no policy exception was added.

### 3 - HPV / cervical cancer

No disease-normalization bug was found: cervical cancer and its MeSH endpoint
were preserved. The original outcome warning came from incidental progression
context and obscured causal-design insufficiency. Selected causal assertions
are narrative/background; a systematic review studies cofactors of persistence/
progression, not the introductory causal assertion as its primary exposure result.

Add one bounded design-focused PubMed query when existing query capacity permits,
retaining lexical/MeSH queries and source-selection rules. The report now gives
the actual causal/conflict qualification reason priority over incidental scope
warnings. The fresh run remains NEI, three qualified assessments: retrieved
findings still lack eligible causal design. This remains a coverage/design
limitation, not a fixed Supported result.

### 6 - Antibiotics / bacterial pneumonia

Can treat is an existential capability claim without an explicit universal
population. Adult treatment evidence was artificially treated as a population
gap. Also, actual randomized named-drug arms stayed contextual/unknown when the
claim named a treatment class. Accept a validated compatible-but-narrower
population only for existential treatment without explicit population, comparator,
numeric restriction or universal/permanent qualifiers, with the same endpoint.

Bind affirmative source-stated randomized assignment to findings naming an
assigned arm. A parent RCT cannot randomize an unrelated measured exposure.
Fresh result Supported: two Supported positions and one NEI. Universal efficacy,
explicit child populations, different endpoints and nonrandomized assignments
remain guarded.

### 12 - Inverse blood pressure / stroke

One frozen semantic response treated lowers like the familiar increases claim,
creating a wrong supporting direction. Cross-check the same named exposure,
outcome and unambiguous literal effect direction in claim, finding and source.
Record SOURCE_GROUNDED_POLARITY_CORRECTION without rewriting the raw axes.
Mixed, null, ambiguous, different-endpoint and lowering-the-exposure sentences
cannot use this correction.

All three saved inverse assessments now derive Contradicted; the same saved
positive claim 2 remains Supported for all three. Fresh inverse result is
Contradicted, two qualified assessments. GLM-4.7 exhausted its transport deadline;
that failure remains visible and was not repaired or converted to NEI.

## Verification, versions and cost

- Full deployed backend suite with PostgreSQL enabled: 1,032 passed, zero failed,
  zero skipped; two existing Starlette deprecation warnings.
- Frontend: 52 tests passed and build passed. Ruff and mypy passed.
- Historical selected audits reconstruct unchanged. All 23 saved successful
  live audits reconstruct exactly under final source.
- 56 model-call starts across eight analyses of seven unique claims, including
  one laboratory repeat. This is initiated requests, not a verified invoice.
  No isolated model bakeoff occurred.
- Table latency uses backend diagnostics; inverse BP host polling time was inflated
  by an interrupted controller.
- All final reports served HTTP 200; production qualification remains false.

Architecture V2.5; judge input/decision/validation 2.5; unchanged V2.4 structured
quantities and verdict policy 1.4. Query plan 1.5; validated position 1.6;
semantic prompt joint-evidence-axes-2.6-scope-polarity-2026-10-06.
Historical position 1.0-1.5 and V2.4 remain reconstructable. The previous 1.4
baseline is retained as a historical snapshot.

Semantic prompt clarification covers literal polarity, existential scope and
cellular versus clinical endpoints. Judge prompt 2.15 is unchanged. No model,
provider configuration, threshold, public-label or production-gate change.

| Role | Active Paratera model |
| -- | -- |
| Extraction / Judge 1 | DeepSeek-V4.1-Flash |
| Judge 2 | Qwen3.5-Plus (provisional) |
| Judge 3 | GLM-4.7 |
| Semantic validator | Qwen3.8-Flash, thinking disabled |

Base URL: https://llmapi.paratera.com/v1.

## Exact final analysis IDs

- 3: 97cf639c-b2ac-4113-9b07-a71ec6d30cc2 (not_enough_evidence, not_enough_evidence, not_enough_evidence).
- 6: 9bbcef7f-cfb4-41ec-9a7b-aa883ebd76d3 (supported, supported, not_enough_evidence).
- 9: 21743512-f0f0-42e4-a65a-00d1f6de0902 (supported, supported, supported).
- 12: a992cc1a-78e1-4de4-8f5b-a27bc609ac9d (contradicted, contradicted).
- 15: 4e31ba9b-c27f-41f7-8d4f-dc09b2e12758 (not_enough_evidence, not_enough_evidence, not_enough_evidence).
- control: 14e34ae4-db72-4404-b0e8-a366bcd6815e (supported, supported, supported).
- control: 456a5a1b-81e1-4dba-99e5-8b75db240ef9 (supported, supported, supported).

The first laboratory iteration aef03776-7435-4e64-bb04-85b5a1280f64 returned NEI
under position 1.5 and remains unchanged historically. Final 1.6 replay derives
Supported for all three saved responses, confirmed by the real repeat above.
Final negative-case hardening rejects speculative/review laboratory sentences;
all actual live audits remain exact. Backend rebuilt/restarted after live work.

See [machine-readable diagnostics, guards, versions and source hashes](SELECTED_SCOPE_POLARITY_FIXES_20261006.json)
and [original failures](CLAIM_CHECK_DIVISIBLE_BY_3_RESULTS_20261006.md).
