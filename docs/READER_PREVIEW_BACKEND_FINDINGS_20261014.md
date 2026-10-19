# Backend correctness findings from the reader preview

Inspection only. No saved outcome, prompt, model, schema, retry, qualification,
quorum, retrieval, production gate, or report-generation rule was changed.

Analysis: `a897813c-5ce9-4f56-b1b6-29c50ed2480e`, captured read-only on 2026-10-14.
Frozen parents were exported read-only from the retained analysis without renewing
retention or rewriting any artifact. The final report snapshot hash is
`924d3d93aac3bb02502b90c1a43103e135b226b049497414aaefc5b833c5d30b`.

## 1. Missing reporting attribution coverage

The Qwen3.5-Plus judge produced one source-referenced statement, `S1`, for each
reporting assertion below. The semantic validator (Qwen3.8-Flash) returned HTTP 200,
`status=completed`, `semantic=null`, and **empty `attributions` arrays** for all
seven items. Reporting field checks and supportive reasons were present, but they
are not replacements for source attribution of the judge's findings.

| Assertion | Required ordered attribution IDs | Returned IDs | Saved qualification |
|---|---|---|---|
| A1 | S1 | none | unavailable |
| A2 | S1 | none | unavailable |
| A3 | S1 | none | unavailable |
| A4 | S1 | none | unavailable |
| A5 | S1 | none | unavailable |
| A6 | S1 | none | unavailable |
| A10 | S1 | none | unavailable |

`qualify_item` in `backend/app/document/evaluation.py` compares the exact ordered
attribution IDs with `prepared.statement_ids` before normalization/attribution
qualification. For each of these items the comparison is `() != ('S1',)`, raising
`ValueError: reporting_attribution_statement_ids_mismatch`. These are missing
coverage failures, not bad citation IDs from the Qwen judge and not lack of a paper.

`ValidationItem12.attributions` currently has `max_length=5` and allows an empty
array because clinical items use attribution arrays inside `semantic`. The shared
schema therefore permits this response shape; the target-specific backend check
correctly excludes it. The request already identifies `validation_target` and
provides `candidate_statements` with their IDs. The instructions require each
finding's attribution. Generic strict JSON syntax is not sufficient to enforce
the runtime target/coverage invariant.

The actual record has one validation attempt. In `evaluate_group`, the validator
loop permits at most two calls within one 75-second deadline, but only retries
transient network failures, 429 or 5xx. It breaks on a responded call. Parsing and
per-item `qualify_item` failures happen afterward and have no coverage-repair retry.
The separate judge loop can retry a failed call/envelope; it does not repair these
validator items. Valid sibling assessments from other judge chains are preserved.

DeepSeek and GLM each supplied qualified assessments. A1/A2/A6/A10 are standard-risk
items and meet the existing two-assessment requirement. A3/A4/A5 are high-risk and
require three. With the Qwen chain excluded, those three items remain unavailable:
A3/A5 each have two supported positions; A4 has two NEI positions but still lacks a
completed high-risk assessment. **Its overall result remains Unable, not NEI.**

Proposed separate fix: enforce reporting-target attribution coverage explicitly
(including the per-item expected IDs), record missing/extra IDs in diagnostics,
and consider one bounded format/coverage retry for only the invalid items within
the existing total deadline. Retain valid siblings, exact source ownership and
quorum; never fabricate attributions or turn reasons/field checks into attribution
records. Version any changed contract/replay behavior and add frozen regressions
for missing coverage, valid clinical nesting, item isolation and retry bounds.

## 2. Adjustment was inferred from a variable list and a method name

The saved A6 assertion says the links held after adjustment for age, skin type,
sunburn history and outdoor time. DeepSeek and GLM each received supported source
attributions and `adjustment_set=matches`; the standard-risk aggregation therefore
saved Supported. The Qwen chain failed coverage as described above.

The accepted evidence is `E203.U1` (methods) and `E205.U1` (results), from the
matched UK Biobank paper, PMID `37642678` / PMCID `PMC10840669`.
The methods state that analysis was performed **“for each predictor variable.”**
The results likewise describe ratios for each selected variable. The frozen text
lists predictors and names multinomial logistic regression, but it does not show
that the sunscreen coefficient was estimated in one model containing all the
claimed covariates together. Multinomial outcomes do not, by themselves, establish
simultaneous adjustment for multiple predictors.

The accepted validator rationale illustrates the inference: one attribution says
the adjusted multivariate context is *implied by the method description*; the GLM
validation calls the listed variables sufficient to match the adjustment claim.
The backend verifies exact source ownership, integrity and the required field
checks, but does not independently require a source-grounded joint-model proof
for `adjustment_set=matches`. This semantic correctness gap can survive schema
and citation validation.

A scan of the retained full-text passages found the relevant disease-environment
methods/results, but no formula, model specification or table note demonstrating
simultaneous adjustment of the **same sunscreen estimate**. Figure 1/Table S2 are
referenced in the results; that reference alone supplies no adjustment proof.
No live supplementary download was used to change the result. Further online
inspection encountered source-access restrictions. The cited primary text is at
[the paper's methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC10840669/).

**Conclusion:** simultaneous adjustment is not established by the available frozen
evidence. This is not proof that the paper used no adjustment. A model formula,
analysis code, or explicit table/model description connecting the sunscreen
estimate to the full joint covariate set would be required to settle it.

Proposed separate fix: distinguish variables collected/analyzed from variables
jointly included in the model producing the cited estimate. Require traceable
same-model joint-adjustment evidence before `matches`; use `unresolved` when that
documentation is missing, and reserve `mismatch` for positive contrary evidence.
Do not infer adjustment from a regression name or an unconnected list, or infer
its absence merely from missing documentation. Evaluate any versioned change on
saved inputs without rewriting historical reports.

The preview preserves A6's saved Supported label in the original report and adds
a visible review flag in the reader layer. It does not summarize joint adjustment
as an established fact. Neither of these proposed backend fixes was implemented
in this UI task.
