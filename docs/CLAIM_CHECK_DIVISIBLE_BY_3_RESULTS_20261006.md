# Selected full frontend-path claim checks ? 2026-10-06

Follow-up: [generic fixes and fresh seven-case before/after results](SELECTED_SCOPE_POLARITY_FIXES_20261006.md). The original frozen observations below are retained.

The user narrowed this run to claim numbers divisible by 3: 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39. The main table covers those 13 selected cases; the saved results for claims 1-5 are included below at the user's follow-up request. Each selected claim was submitted once through the same HTTP endpoints/body as the frontend (`client=web`, `lang=auto`), followed through extraction, normalization, retrieval, selection, judging, source/semantic checks, qualification, aggregation and report serving whenever those stages could complete. Existing retries/deadlines were retained. Failed or incomplete stages are recorded; no forced verdict or fabricated report is supplied. Sanity expectations are engineering expectations supplied by the user, not a clinical benchmark.

Frozen V2.5 architecture, V2.4 quantity references, query-plan 1.4 and position 1.4; no code, prompt or model changes. All Paratera: DeepSeek-V4.1-Flash extraction/J1, Qwen3.5-Plus J2, GLM-4.7 J3, Qwen3.8-Flash validator (thinking disabled).

Completed cases: 13/13. Reported match count: 8/13. A match is only a label comparison.

| # | Claim | Actual final result | Qualified | Expectation match | Individual report |
|---|---|---|---|---|---|
| 3 | Persistent high-risk HPV infection can cause cervical cancer. | Not Enough Evidence | 3/3 | No | [03](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/03.md) |
| 6 | Antibiotics can treat bacterial pneumonia. | Not Enough Evidence | 3/3 | No | [06](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/06.md) |
| 9 | Blue light can induce apoptosis in some leukemia cell lines under laboratory conditions. | Unable to Verify Reliably | ? | No | [09](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/09.md) |
| 12 | High blood pressure lowers the risk of stroke. | Not Enough Evidence | 3/3 | No | [12](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/12.md) |
| 15 | HIV is commonly transmitted by mosquito bites. | Unable to Verify Reliably | ? | No | [15](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/15.md) |
| 18 | Smoking protects people from developing lung cancer. | Contradicted | 3/3 | Yes | [18](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/18.md) |
| 21 | Smoking increases lung cancer risk by exactly 85%. | Not Enough Evidence | 2/3 | Yes | [21](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/21.md) |
| 24 | Blue light from smartphones causes leukemia. | Not Enough Evidence | 3/3 | Yes | [24](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/24.md) |
| 27 | Eating dark chocolate prevents Alzheimer's disease. | Not Enough Evidence | 3/3 | Yes | [27](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/27.md) |
| 30 | Sleeping nine hours every night prevents cancer. | Not Enough Evidence | 0/3 | Yes | [30](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/30.md) |
| 33 | Daily multivitamin use prevents all cancers. | Not Enough Evidence | 3/3 | Yes | [33](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/33.md) |
| 36 | A treatment that shrinks an existing tumor proves that it prevents that cancer from developing. | Not Enough Evidence | 3/3 | Yes | [36](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/36.md) |
| 39 | This treatment reduces the risk by 40%. | Unable to Verify Reliably | ? | Yes | [39](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/39.md) |

## Completion and limitations

All 13 requested multiples-of-three cases are complete. **8/13** match the
user-supplied engineering expectations. Ten scientific reports were served via
the normal frontend report endpoint (HTTP 200); three cases stopped at incomplete
normalization and expose operational Unable, with no fabricated scientific report.
The five mismatches are **3, 6, 9, 12 and 15**.

- **3:** NEI rather than Supported; saved explanation reports an outcome mismatch.
- **6:** NEI rather than Supported; saved explanation reports a population/scope gap.
- **9:** Unable rather than Supported. PICO preserved `apoptosis` and `some leukemia
  cell lines`, but the coverage audit flagged `laboratory` as an unrepresented
  explicit medical concept, producing `normalization_incomplete`.
- **12:** NEI rather than Contradicted. Aggregation records
  `VALIDATED_JUDGE_DISAGREEMENT`; the displayed summary also mentions an outcome gap.
- **15:** Unable rather than Contradicted. Normalized PICO lost the HIV outcome
  (`outcome=null`); the audit reports missing `HIV` and the required outcome slot.
- **21:** NEI as expected, with 2/3 qualified; Judge 2 was excluded as
  `VALIDATION_UNAVAILABLE`. This partial validation is visible in the report.
- **30:** NEI as expected after two retrieval candidates and zero selected documents;
  no judges/checkers were called. This is evidence shortage, not 3/3 validation.
- **39:** Unable as expected; the treatment and risk endpoint remain unspecified.

The normal pipeline was allowed to stop at its existing gates; failing early is
reported as such, rather than claiming every downstream check ran. Source/
semantic validation and judge qualification are independent from expectation
matching. These outputs do not establish clinical correctness.

Model-call starts observed in the selected cases: **70**. Including the four
nonselected runs already started before the scope change (1, 2, 4, 5): **98**.
These are debug request-start counts, not provider billing amounts. No extra
probes, full-analysis repeats, model swaps or policy adjustments were made.
The in-flight case 5 was allowed to finish before case 6 was submitted.
All frozen baseline source hashes still match. V2.5 / query-plan 1.4 / position
1.4 and all five configured model roles remain unchanged.

[Machine-readable results and diagnostics](CLAIM_CHECK_DIVISIBLE_BY_3_RESULTS_20261006.json).
Full raw frontend responses, including model answers, are retained locally in
`%LOCALAPPDATA%/Temp/lens_40_full_api_raw_20261006.json`. Individual JSON files
contain the served report, claim diagnostics and normalization state; failed cases
contain their actual frontend API failure information instead of an invented report.

## Claims 1-5: saved full checks

Added from the full frontend-path runs already completed before the scope change.
No new submissions or model calls were made. All five reports were served with
HTTP 200. Four of five match the Supported expectation; claim 3 remains NEI.
Claim 3 appears in both tables and is counted only once in the combined total.

| # | Claim | Actual final result | Qualified | Expectation match | Individual report |
|---|---|---|---|---|---|
| 1 | Cigarette smoking causes lung cancer. | Supported | 2/3 | Yes | [01](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/01.md) |
| 2 | High blood pressure increases the risk of stroke. | Supported | 3/3 | Yes | [02](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/02.md) |
| 3 | Persistent high-risk HPV infection can cause cervical cancer. | Not Enough Evidence | 3/3 | No | [03](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/03.md) |
| 4 | Smoking cessation reduces lung cancer risk over time. | Supported | 3/3 | Yes | [04](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/04.md) |
| 5 | Regular physical activity reduces the risk of developing type 2 diabetes. | Supported | 3/3 | Yes | [05](CLAIM_CHECK_DIVISIBLE_BY_3_20261006/reports/05.md) |

Claim 1 qualified 2/3; Judge 2 was excluded as `VALIDATION_UNAVAILABLE`.
Claims 2, 4 and 5 qualified 3/3. Claim 3 qualified 3/3 but the saved explanation
reports an outcome mismatch. Individual reports include sources, explanations,
analysis IDs, normalization diagnostics and the exact returned report JSON.

Across both sections: **17 unique cases**, **12/17 expectation matches**, fourteen
served scientific reports and three normalization failures. These are the same
previously observed runs; no extra checks were performed for this addition.
