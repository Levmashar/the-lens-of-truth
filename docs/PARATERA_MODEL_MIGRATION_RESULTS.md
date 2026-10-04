# Judge and validator migration results

Measured 2026-10-03 in local development. This is a bounded engineering smoke,
not a clinical benchmark or production qualification. **Final acceptance is
blocked by AIMLAPI API-key lifetime quota, despite positive account balance.**
Paid requests stopped after the explicit `ALL_TIME_LIMIT_EXCEEDED` diagnostic.

## Integration and current configuration

Authenticated Paratera `/v1/models` returned 86 entries. Its base is
`https://llmapi.paratera.com/v1`; `/chat/completions` accepts OpenAI-shaped
messages, Bearer auth, response-format JSON schema, choices and usage. Small
schema requests returning HTTP 200 did not guarantee schema-conformant full
requests. No account timeout guarantee was established from its catalog;
existing local bounds remain 60 seconds per judge attempt, 110 seconds per
slot, 75 seconds per joint check and 420 seconds per claim.

The named `paratera` provider reuses the existing OpenAI-compatible transport.
Optional explicit `VALIDATOR_*` settings select the development/test checker;
absent settings retain prior behavior. No automatic model substitution occurs
during a claim. Provider/model, returned snapshot, prompt/input versions and
failures remain append-only. This migration changed no prompts, retrieval,
selection, numeric policy, semantic axes, verdict thresholds or production
qualification. The repository already used judge prompt 2.13 when this work
began; it was not rolled back to the request's older 2.12.1.

| Role | Immediately preceding local setting | Initial Paratera trial | Current setting, via AIMLAPI |
| --- | --- | --- | --- |
| Judge 1 | Paratera `Qwen3.5-35B-A3B` | `DeepSeek-V4-Flash` | `x-ai/grok-4-3`, family `xai` |
| Judge 2 | AIMLAPI `openai/gpt-6-luna` | Unchanged | Unchanged model, endpoint, key and family |
| Judge 3 | Paratera `ERNIE-4.5-Turbo-128K` | `GLM-4.6` | `anthropic/claude-sonnet-5.5`, family `anthropic` |
| Joint checker | Inherited Paratera ERNIE | Explicit `GLM-5.2` | Explicit `anthropic/claude-haiku-4-5-20251001` |

Current AIMLAPI base: `https://api.aimlapi.com/v1`, with Bearer auth. Extraction
remains `inclusionai/ling-3.0-flash`. Ling/Gemini Lite judge settings are historical,
not the immediately preceding local settings. Paratera credentials remain inactive
locally; no keys are documented.

### Exact requested IDs and fallbacks

- `DeepSeek-V3.2-Exp`: listed but actual small chat request returned HTTP 404.
  Used the specified first fallback `DeepSeek-V4-Flash` initially.
- `GLM-4.6`: listed and callable; small request HTTP 200 in 8.8 seconds, fenced JSON.
- `Baichuan-M2`: listed but actual request HTTP 429. Used the specified first
  checker fallback `GLM-5.2`; small request HTTP 200 in 3.1 seconds.
- Full normal requests exposed DeepSeek timeouts and GLM-5.2 timeouts/schema
  failures. Its initial fenced arrays lacked required joint object fields;
  stripping the fence would still fail the contract.
- After the user expressly authorized other models, actual frozen requests
  guided substitutions. AIMLAPI non-thinking DeepSeek parsed some requests but
  exhausted deadlines on carrots and Vitamin C. Grok replaced it after two
  parsed smoking responses in 9.6/10.6 seconds. Six-case Grok stability remains
  unverified; both smoking proposals still failed material numeric preflight.
- MiniMax-M3 passed one checker probe but repeatedly emitted string
  `evidence_ids` instead of arrays during normal smoke. Pinned Haiku replaced it.
- No DeepSeek-V4-Pro or Qwen Thinking model was used. No validation rule was
  weakened for a candidate.

## Specific user analysis and diagnostics fixes

Analysis `26ff08a7-76b9-4cef-93a6-f88b438baf2a` had two DeepSeek-V4-Flash
attempts exhausting 110 seconds, a parsed Luna proposal followed by a 75-second
GLM-5.2 timeout, and a parsed GLM-4.6 proposal blocked by numeric preflight.
This explains 2/3 usable judges and 0/3 qualified, independently of UI state.

Cancelled semantic HTTP calls now emit a terminal unavailable event with the
original call ID. The debug API reconstructs checker identity and terminal
status from saved validation audits when transient events are absent/stale.
After restart, the historical analysis correctly shows
`GLM-5.2 / unavailable / joint_axes_timeout`, instead of Calling.
Historical rows continue to name models that actually ran. Explicit billing/key
quota responses now produce `quota_exceeded` without retry. Historical generic
provider errors are not rewritten.

## Software verification

Before paid smoke: 85 focused provider/configuration/V2 tests passed; full suite
then had 668 passing tests. After diagnostics and quota fixes:

- **671 passed, 11 opt-in database tests skipped**, two Starlette deprecation warnings.
- Ruff passed; Mypy passed for 160 app modules; Docker backend build passed.
- `git diff --check` passed.
- Backend restarted with ordinary Uvicorn command; temporary smoke budget
  wrapper removed. Health endpoint returned HTTP 200.

## Initial six-case normal Paratera smoke

Each case used normal HTTP analysis, unchanged retrieval/selection,
DeepSeek-V4-Flash / Luna / GLM-4.6 and GLM-5.2 checker. All six final results
were `unable_to_verify_reliably`; all 18 judge slots were unqualified.
Calls include one extraction plus saved judge/checker attempt counts.
Missing token usage is not zero. Persisted stage clocks are not treated as
provider latency; the carrots record includes a large wall-clock gap.

### Smoking does not cause lung cancer.

Analysis `792dfcdb-3b08-4033-a3e7-88886a5b7cd2`. Result `unable_to_verify_reliably`. Calls **7**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | contradicted | No | `joint_axes_timeout` | 25365 / 1 | 14141 / 1931 | 75108 |
| 2 | contradicted | No | `joint_axes_validator_unavailable` | 9479 / 1 | 13162 / 757 | 44111 |
| 3 | contradicted | No | `joint_axes_validator_unavailable` | 39523 / 1 | 13369 / 1362 | 44596 |

### Frequent sunscreen use causes invasive melanoma.

Analysis `44c30e72-a601-4786-b41b-7b129b925506`. Result `unable_to_verify_reliably`. Calls **6**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `timeout` | 110005 / 2 | not exposed / not exposed | not called |
| 2 | contradicted | No | `joint_axes_timeout` | 22930 / 1 | 9704 / 2616 | 75031 |
| 3 | contradicted | No | `material_preflight_failure; OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x3, NUMERIC_UNCERTAIN x4` | 49276 / 1 | 9866 / 1693 | 6 |

### Daily sunscreen use reduces invasive melanoma risk.

Analysis `3df2d924-bf8b-42ae-ab69-746a858a1553`. Result `unable_to_verify_reliably`. Calls **7**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `timeout` | 110004 / 2 | not exposed / not exposed | not called |
| 2 | supported | No | `joint_axes_timeout` | 20253 / 1 | 9876 / 2350 | 75030 |
| 3 | none | No | `timeout` | 110007 / 2 | not exposed / not exposed | not called |

### Vitamin C prevents the common cold.

Analysis `aecc70b7-9da6-4db1-a0b9-a40f8e4cdad4`. Result `unable_to_verify_reliably`. Calls **6**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `timeout` | 110006 / 2 | not exposed / not exposed | not called |
| 2 | contradicted | No | `joint_axes_timeout` | 9867 / 1 | 11932 / 1078 | 75022 |
| 3 | contradicted | No | `material_preflight_failure; OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x2, NUMERIC_UNCERTAIN x1` | 46152 / 1 | 12110 / 1846 | 5 |

### Smoking increases lung cancer risk by 85%.

Analysis `e969aec4-1b00-4bfc-ac64-506de4d3e2ad`. Result `unable_to_verify_reliably`. Calls **7**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `timeout` | 110006 / 2 | not exposed / not exposed | not called |
| 2 | not_enough_evidence | No | `joint_axes_validator_unavailable` | 7553 / 1 | 14048 / 908 | 6167 |
| 3 | contradicted | No | `material_preflight_failure; NUMERIC_UNCERTAIN x4` | 67154 / 2 | 14358 / 2387 | 199 |

### Carrots improve eyesight.

Analysis `4f131147-0e2e-445f-ad1d-fb88bdd5667e`. Result `unable_to_verify_reliably`. Calls **7**.

| Slot | Proposal | Qualified | Failure | Judge ms / attempts | Input / output tokens | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | not_enough_evidence | No | `joint_axes_timeout` | 57390 / 1 | 3740 / 4585 | 75050 |
| 2 | not_enough_evidence | No | `joint_axes_timeout` | 7172 / 1 | 2950 / 560 | 75041 |
| 3 | not_enough_evidence | No | `joint_axes_timeout` | 42347 / 1 | 2584 / 1540 | 75059 |

Checker tokens were not exposed in retained initial audit metrics. Schema
failures are recorded as `joint_axes_validator_unavailable`; the first inverse
smoking responses were inspected as invalid fenced arrays. Other unavailable
responses are not relabeled as specific schema/ID failures without evidence.
No source-ID failure was recorded in the six initial normal cases.

## Replacement normal smoke: non-thinking DeepSeek / Luna / Sonnet + MiniMax

These are actual completed frontend reports. Later Haiku evaluations append
new audit rows; they do not replace these historical reports.

| Claim | Normal result | Qualified | Calls | End-to-end ms | Analysis ID |
| --- | --- | ---: | ---: | ---: | --- |

| Smoking does not cause lung cancer. | contradicted | 1/3 | 7 | 163612 | `a95ddb5e-05e9-4333-8c5c-b425fbc55bfc` |
| Frequent sunscreen use causes invasive melanoma. | contradicted | 1/3 | 7 | 145427 | `e09f006f-abe4-41f5-be71-89e0dcf8496d` |
| Daily sunscreen use reduces invasive melanoma risk. | unable_to_verify_reliably | 1/3 | 7 | 133368 | `643c962c-cab2-4323-bd2f-2f286570cd0c` |
| Vitamin C prevents the common cold. | normalization_incomplete | 0/3 | 1 | 2072 | `b05643b1-c4ca-42cb-9505-01653d15efeb` |
| Smoking increases lung cancer risk by 85%. | unable_to_verify_reliably | 1/3 | 6 | 145383 | `67ac96c8-be08-4800-90a8-81f5d020d056` |
| Carrots improve eyesight. | unable_to_verify_reliably | 0/3 | 7 | 167536 | `9f461c8d-9ee1-4aef-be0b-dc5ed38bfbb1` |

Vitamin C failed `normalization_incomplete`: extraction omitted the outcome.
It never reached judges in this normal run. Extraction/normalization was not
modified to force a pass. The frozen Vitamin C evaluation below uses an earlier,
still-retained valid Pack; it is not successful normal-path Vitamin C acceptance.

## Haiku checker recheck of six frozen cases

Normal-smoke decisions/Packs were checked once by Haiku, without feedback,
judge revisions, retrieval or source expansion. Vitamin C uses fresh judges
and the earlier Pack from `aecc70b7-9da6-4db1-a0b9-a40f8e4cdad4`.
New Judge/Validation/Verdict rows were appended; original report pointers were
not changed. Judge 1 here is **intermediate non-thinking DeepSeek**, not Grok.

All 13 Haiku checker calls returned HTTP 200 and passed strict joint schema and
exact IDs. No schema/source-ID failure occurred in this recheck. Six slots
qualified. Other exclusions are numeric preflight or semantic classification.
This demonstrates contract feasibility, not medical classification accuracy.


### Smoking does not cause lung cancer.

Evaluation result `contradicted`; qualified **2/3**. New calls **2**. Verdict audit `72c2c731-c813-4ee1-ad72-682e37512dd7`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | contradicted | No | `unable_to_validate / material_preflight_failure` | NUMERIC_UNCERTAIN x2 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x1 | 96782 / 2 | 7 |
| 2 | contradicted | Yes | `validated / MATERIAL_CONTRADICTION` | 0 / 0 | 6363 / 1 | 6690 |
| 3 | contradicted | Yes | `validated / MATERIAL_CONTRADICTION` | 0 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x2 | 6857 / 1 | 11082 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 59986 | not exposed / not exposed |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | 200 | 36733 | 13005 / 501 |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 6311 | 13163 / 667 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 6799 | 20495 / 765 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 6618 | 16326 / 472 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 11019 | 17120 / 991 |

### Frequent sunscreen use causes invasive melanoma.

Evaluation result `unable_to_verify_reliably`; qualified **0/3**. New calls **3**. Verdict audit `445068c3-c4c5-44df-898b-174359e820d9`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | not_enough_evidence | No | `unable_to_validate / ONE_SIDED_DECISIVE_FINDINGS` | 0 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x2 | 34417 / 1 | 12644 |
| 2 | contradicted | No | `unable_to_validate / NO_MATERIAL_PROPOSED_DIRECTION` | 0 / 0 | 14929 / 1 | 12458 |
| 3 | contradicted | No | `unable_to_validate / NO_MATERIAL_PROPOSED_DIRECTION` | 0 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x3 | 7412 / 1 | 12737 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | 200 | 34377 | 9510 / 603 |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 14891 | 9710 / 1697 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 7382 | 15206 / 890 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 12569 | 13889 / 1035 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 12396 | 12829 / 939 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 12651 | 14163 / 1078 |

### Daily sunscreen use reduces invasive melanoma risk.

Evaluation result `supported`; qualified **1/3**. New calls **3**. Verdict audit `25635ad5-d9c0-4533-a945-ec59aabed516`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | not_enough_evidence | No | `unable_to_validate / ONE_SIDED_DECISIVE_FINDINGS` | 0 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x1 | 28031 / 1 | 14153 |
| 2 | supported | Yes | `validated / MATERIAL_SUPPORT` | 0 / 0 | 15330 / 1 | 15468 |
| 3 | not_enough_evidence | No | `invalid / REQUIRED_FINDING_UNAVAILABLE` | 0 / OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x4 | 9117 / 1 | 16917 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | 200 | 28001 | 9691 / 626 |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 15302 | 9884 / 1778 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 9091 | 15451 / 1264 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 14070 | 13818 / 1128 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 15398 | 13464 / 962 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 16802 | 15095 / 1577 |

### Vitamin C prevents the common cold.

Evaluation result `unable_to_verify_reliably`; qualified **0/3**. New calls **6**. Verdict audit `8ed35c48-baf6-4ab1-b392-2fdd1781b7fc`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `not called / timeout` | 0 / 0 | 110052 / 2 | not called |
| 2 | contradicted | No | `unable_to_validate / MATERIAL_RELATION_UNCERTAIN` | 0 / 0 | 13825 / 1 | 10181 |
| 3 | contradicted | No | `unable_to_validate / MATERIAL_RELATION_UNCERTAIN` | 0 / OPTIONAL_NUMERIC_DETAIL_INVALID x1, OPTIONAL_NUMERIC_DETAIL_UNCERTAIN x4 | 10165 / 1 | 18788 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 60032 | not exposed / not exposed |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 49948 | not exposed / not exposed |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 13778 | 11932 / 1481 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 10121 | 18570 / 1208 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 10127 | 15256 / 888 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 18672 | 17635 / 1525 |

### Smoking increases lung cancer risk by 85%.

Evaluation result `unable_to_verify_reliably`; qualified **1/3**. New calls **1**. Verdict audit `2f5e2eb1-d46c-448a-ba12-482ab378102a`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | not_enough_evidence | No | `unable_to_validate / material_preflight_failure` | NUMERIC_UNCERTAIN x2 / 0 | 102451 / 2 | 8 |
| 2 | not_enough_evidence | Yes | `validated / ONLY_INSUFFICIENT_OR_CONTEXT` | 0 / 0 | 9759 / 1 | 6859 |
| 3 | contradicted | No | `unable_to_validate / material_preflight_failure` | NUMERIC_UNCERTAIN x4 / 0 | 7150 / 1 | 7 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 59987 | not exposed / not exposed |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | 200 | 42403 | 13969 / 443 |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 9729 | 14053 / 1154 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 7123 | 21605 / 755 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 6777 | 17399 / 543 |

### Carrots improve eyesight.

Evaluation result `not_enough_evidence`; qualified **2/3**. New calls **2**. Verdict audit `6a459b7c-4f1b-4747-a08e-d8bbf90c4295`.

| Slot | Proposal | Qualified | Checker outcome / exact reason | Material numeric / optional issues | Judge ms / attempts | Checker ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | No | `not called / timeout` | 0 / 0 | 110015 / 2 | not called |
| 2 | not_enough_evidence | Yes | `validated / CAUSAL_DESIGN_INSUFFICIENT` | 0 / 0 | 5836 / 1 | 8573 |
| 3 | not_enough_evidence | Yes | `validated / CAUSAL_DESIGN_INSUFFICIENT` | 0 / 0 | 6500 / 1 | 9186 |

Original judge calls below are from the normal run; checker calls are fresh. Vitamin C includes fresh judge attempts. Missing usage is not zero.

| Model / purpose | HTTP or outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 59984 | not exposed / not exposed |
| `deepseek/deepseek-non-thinking-v3.2-exp` / evidence_judge_decision | response_failed | 49972 | not exposed / not exposed |
| `openai/gpt-6-luna` / evidence_judge_decision | 200 | 5805 | 2947 / 611 |
| `anthropic/claude-sonnet-5.5` / evidence_judge_decision | 200 | 6464 | 5476 / 615 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 8521 | 5313 / 707 |
| `anthropic/claude-haiku-4-5-20251001` / joint_evidence_axes | 200 | 9139 | 5331 / 641 |

Sunscreen exclusions are semantic: Haiku's scope/direction assessments led to
`NO_MATERIAL_PROPOSED_DIRECTION` or `ONE_SIDED_DECISIVE_FINDINGS`. Vitamin C
produced `MATERIAL_RELATION_UNCERTAIN`. Daily sunscreen's Sonnet S4 attribution
failed (`STATEMENT_ATTRIBUTION_FAILED`). No code changed for these medical outcomes.


## Bounded candidate contract observations

Candidates used the actual frozen smoking-85% request, not toy prompts.
These are compatibility probes, not a clinical benchmark.

| Candidate / role | Outcome | Seconds | Input / output tokens |
| --- | --- | ---: | --- |
| Paratera GLM-4-Flash / checker | HTTP 200, strict schema failed | 5.36 | 15407 / 324 |
| Paratera MiniMax-M3 / checker | Probe schema/IDs passed; later normal schema failures | 15.53 | 15627 / 651 |
| Paratera MiniMax-M3 / judge | Unknown evidence citation E15 | 17.97 | 14478 / 658 |
| Paratera GLM-5.3-Flash / judge | Timeout | 60.06 | Not exposed |
| Paratera Baichuan-M3 / judge | HTTP 429 | 4.4 | Not exposed |
| Paratera Kimi-K2.7 / judge | Schema violation: empty required source-unit IDs | 58.4 | 14197 / 2596 |
| AIMLAPI Haiku 4.5 / judge | Parsed NEE; material numeric mismatch | 13.69 | 16023 / 822 |
| AIMLAPI Gemini 3.8 Flash / judge | Parsed NEE after timeout retry; numeric uncertainty | 72.08 total | 17813 / 1684 |
| AIMLAPI non-thinking DeepSeek V3.2 Exp / judge | Parsed NEE; numeric uncertainty | 54.4 | 13964 / 540 |
| AIMLAPI Sonnet 5.5 / judge | Parsed contradicted; numeric uncertainty | 10.16 | 21604 / 836 |
| AIMLAPI pinned Haiku / checker of saved Luna smoking85 | Schema/IDs passed; qualified NEE | 10.68 | 17400 / 498 |
| AIMLAPI pinned Haiku / checker of saved Luna inverse smoking | Schema/IDs passed; qualified contradicted | 6.77 | 16326 / 529 |
| AIMLAPI Grok 4.3 / judge | Parsed NEE; material numeric preflight | 9.649 | 13795 / 1105 |

The first ten probes initiated 11 calls including Gemini's retry; two Haiku
confirmations followed. Grok used one frozen request plus one normal request.
The separate normal/recheck ledger used **58 of its 60-call ceiling**, including
failed/cancelled requests and the final access diagnostic. Planned six-case
Grok recheck was not launched after the key quota failure. NEE abbreviates
`not_enough_evidence`.

## Final normal request and external blocker

The current Grok / Luna / Sonnet / Haiku configuration was loaded for fresh
normal analysis `b1af1d15-7500-48d6-b143-096bb8851699`, smoking increases lung
cancer risk by 85%. It completed in 28.4s with `unable_to_verify_reliably`,
0/3 qualified, four calls:

| Role | Outcome | Provider ms | Input / output tokens |
| --- | --- | ---: | --- |
| Extraction | HTTP 200 | 2034 | 739 / 205 |
| Grok judge 1 | HTTP 200, NEE; material numeric preflight failure | 10618 | 13804 / 1197 |
| Luna judge 2 | HTTP 403, no proposal | 942 | Not exposed |
| Sonnet judge 3 | HTTP 403, no proposal | 642 | Not exposed |
| Haiku checker | Not called | Not called | Not exposed |

A subsequent tiny Luna diagnostic returned HTTP 403 with the exact message
`API key quota exceeded (ALL_TIME_LIMIT_EXCEEDED).` The read-only billing
endpoint returned positive balance, `status=current`, `lowBalance=true`, with
automatic top-up disabled. Account balance alone does not remove the key's
lifetime quota. Raise that configured key's limit or replace the key locally,
then resume bounded acceptance. No keys, billing settings or payment methods
were changed to bypass this condition. Historical failed rows were not rewritten.

## Cost research and interpretation

Exact IDs were verified in the authenticated catalogs; callable full requests
informed selection. Public AIMLAPI list rates at inspection were Grok 4.3
$1.625/$3.25 per million input/output tokens and non-thinking DeepSeek
$0.371358/$0.563914. Haiku's family page listed $1.3754/$6.877 but also had an
inconsistent FAQ output rate; pinned-model/account charges are unverified.
These are public rates, not invoices. Timeout usage is unknown. Grok's frozen
request is about $0.026 at its uncached list rates. Paratera account pricing
was not exposed by its catalog; direct MiniMax rates are not Paratera prices.

Sources: [Paratera API access](https://www.paratera.com/news_des/122.html),
[AIMLAPI Grok 4.3](https://aimlapi.com/models/grok-4-3),
[AIMLAPI DeepSeek non-thinking](https://aimlapi.com/models/deepseek-v3-2-exp-non-thinking),
[AIMLAPI Haiku](https://aimlapi.com/models/claude-4-5-haiku),
[AIMLAPI quota errors](https://help.aimlapi.com/article/31-what-errors-might-occur-when-using-the-api),
[AIMLAPI account balance](https://docs.aimlapi.com/api-references/service-endpoints/account-balance).

**Reliability conclusion:** Haiku's strict contract handling improved over the
observed GLM-5.2/MiniMax failures. Luna/Sonnet parsed all six retained/fresh judge
cases before the quota failure. Non-thinking DeepSeek was unstable at existing
full-Pack deadlines. Grok parsed two smoking requests quickly; that is
insufficient to declare it better than Ling or DeepSeek. Baichuan was uncallable,
so no reduction in false rejections was measured. Final all-three-judge normal
repeatability is unproven and currently blocked. The setup is not established
as clearly reliable or production qualified.

Remaining blockers: API-key lifetime quota; uncompleted Grok six-case acceptance;
material numeric failures on smoking85; sunscreen/Vitamin C semantic uncertainty;
Vitamin C's normal extraction outcome omission; unverified production identity,
family independence, search isolation and checker qualification.

Private runtime captures retain expiry metadata. This document preserves
aggregate engineering measurements and audit IDs, not full frozen evidence or keys.
