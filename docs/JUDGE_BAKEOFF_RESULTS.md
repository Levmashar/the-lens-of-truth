# Slice 4 judge bake-off — 2026-10-02

## Continuation decision (120 additional calls, 2026-10-02)

The following section supersedes the **initial investigation decision**, without
rewriting its measurements. Winner: existing V2 decision 2.2 with compact
qualitative findings and one dual-target development checker, current selection,
current Ling/Luna/Gemini Lite judges. Checker: configured slot 3, Gemini Lite.
No model replacement or `.env` change. V3 remains evaluation-only.

Additional accounting: **120/120 initiated, all HTTP 200**; 72 judge requests
(including retries), 39 joint checks, 8 extractions, 1 decisive V3 checker.
Models: Ling 34, Luna 28, Lite 58 requests. These include an interrupted normal
run's late responses. The persistent ledger is exhausted; do not reset it.
Successful HTTP responses are NOT semantic/schema/medical successes.

| Focused measurement | V2 joint | Hardened V3 + decisive-only check |
| --- | --- | --- |
| Three old failure controls, 3 judges | 2/9 usable, no false decisive | 6/9 usable, no false decisive |
| Calls on those controls | 18 | 10 (only one preliminary decisive required checking) |
| Same real smoking Pack, 3 judges | 1/3 usable, authoritative causal source qualified | 0/3 usable; purpose/schema exclusions |
| Calls on that real Pack | 6 | 4, including Ling format retry |
| Adoption | Existing V2 retained, batching integrated | Rejected: authority/schema gate failed |

The additional 12 joint-V2 positive/inverse/carrot/numeric rows yielded 5 usable
positions; together the 21 synthetic rows had **0/18 false-support positions,
0/15 false-contradiction positions**, but substantial false rejection. They used
different compact prompt versions during diagnosis; do not call them one clean
final-version matrix. The original 40-case baseline still has the stronger
coverage denominator; no eliminated candidate was rerun. The newer finalists
still lack a clean held-out superiority result, so none replaced a judge.

Offline subsets on the four new controls (unchanged policy): best prior two
Lite/Luna produced Unable 4/4; adding Ling produced two NEI, one Contradicted,
one Unable, with no false decisive. Together with prior 40-case subset results,
this supports retaining judge 3, not lowering production counts. The reviewer
is not counted as a fourth judge or an independent family.

Optional qualitative statistics are now excluded at the new format boundary.
Some gateways still ignore instructions/schema constraints and exhaust their
single format retry; this is a visible unresolved provider-compliance exclusion,
not NUMERIC_UNCERTAIN laundering. Genuine numeric controls still fail closed.
Normal completed cases used 6-7 post-retrieval requests versus 38 in the exact
saved smoking decomposition. Old normal active qualifications: 3/12 (25%). New
smoking/sunscreen/carrot/clarified-inverse/numeric qualifications: 6/15 (40%),
on a DIFFERENT case mix, NOT a paired accuracy improvement claim.
The earlier compact synthetic probes also missed 8/9 expected decisive positions;
zero false acceptance alone is not a satisfactory overall reliability metric.

Final semantic acceptance is partial: smoking Supported, clarified inverse
Contradicted, invasive sunscreen Contradicted, carrots Unable, numeric magnitude
Unable; all non-production-qualified. The repeated smoking run was interrupted
by a software health test's shared-DB startup reconciliation, now isolated.
No clean final exact-input flip-rate claim is possible at the exhausted ceiling.
Earlier Lite-only synthetic repeatability remains 0/20 observed position flips;
that does not certify the real three-judge pipeline. Full traces, reasons,
remaining blockers and commands: [continuation results](RELIABILITY_SLICE4_RESULTS.md).

## Initial investigation decision and measurement limits (historical)

**No replacement or new judge contract passed the adoption gates.** Normal
development remains V2/current evidence selection/current validator selection.
V3, minimal-V2 and lean selection are opt-in evaluation implementations only.
`.env` was not changed. This is a bounded engineering investigation, not clinical
qualification or a completed final acceptance matrix.

The provider exhausted its account-wide quota during three overlapping sweeps.
After the user restored quota and asked not to overuse it, additional measurements
were bounded. Four normal analyses alone exposed 155 model calls. Further paid
sweeps stopped; completing the missing matrix needs an explicit call budget.
Missing/failed measurements are not evidence that a model is clinically wrong.

Forty synthetic conditional controls use a pre-fixed development/held-out split
of 30/10. Their sources are explicitly NOT publications. Expected relations,
scope and materiality are engineer-authored. Expected *positions* are derived
from those annotations through the existing policy: this is a policy-regression
oracle, not an independent medical truth reference. Labels never enter prompts.
Real-source cases have no medical accuracy denominator unless annotated.

## Catalog and identity

The configured gateway returned 976 catalog entries: 373 eligible chat IDs,
599 non-chat endpoints and four search/browser modes excluded. Search-mode
classification is conservative name/endpoint filtering, not verified provider
isolation. No tools, search parameters or browsing were supplied.

Six exact catalog IDs were actually called:

| Candidate ID | Claimed family | Reason included |
|---|---|---|
| `inclusionai/ling-3.0-flash` | inclusionai | Current judge 1 |
| `openai/gpt-6-luna` | openai | Current judge 2 |
| `google/gemini-2.5-flash-lite` | google | Current judge 3 |
| `openai/gpt-6-astra` | openai | Stronger gateway candidate |
| `google/gemini-2.5-pro` | google | Stronger gateway candidate |
| `anthropic/claude-sonnet-5.5` | anthropic | Additional claimed family |

These are gateway labels, not verified first-party model/snapshot identities.
Other discovered IDs were not called. Temperature 0 was requested; successful
HTTP responses do not prove it was honored. Seed and top_p were not supplied.
Returned aliases/request IDs were recorded where available; no usable fingerprint
established pinned identity. Pricing/billing rates were unavailable, so dollar
cost is unknown. No clinical or production model-family qualification follows.

## Corrected, clean eight-case paired pilot

Artifact: `bakeoff-20261002T082250704543.json`. Six candidates, eight identical
controls each, V2 and V3: 96 rows, 215 HTTP calls, all HTTP 200; 326,221 input
and 56,980 output tokens. V2 uses the same schema/validation service but one
assessment, **not the normal pipeline's additional semantic revision**.

| Model | V2 usable | V2 first-relation agreement | V2 calls | V3 usable | V3 first-relation agreement | V3 calls |
|---|---:|---:|---:|---:|---:|---:|
| Ling | 4/8 | 8/8 | 27 | 8/8 | 6/8 | 8 |
| Luna | 5/8 | 6/8 | 28 | 8/8 | 7/8 | 8 |
| Flash-Lite | 7/8 | 8/8 | 24 | 8/8 | 8/8 | 8 |
| Astra | 6/8 | 4/8 | 30 | 8/8 | 8/8 | 8 |
| Gemini Pro | 5/8 | 8/8 | 29 | 8/8 | 8/8 | 8 |
| Claude | 4/8 | 5/8 | 29 | 8/8 | 8/8 | 8 |

No false decisive V2 position was observed here. V3 Ling falsely contradicted
the wide/imprecise-null control (1/5 negative-contradiction opportunities), despite
including an IMPRECISE_NULL reason. V3 eliminates generated finding numbers by
schema, but cannot infer reliable semantics merely from schema compliance.
Eight cases do not qualify any replacement on both splits.

An earlier 48-row/168-call pilot (`081502239387`) exposed expected-direction
words through fixture document IDs and used random Pack UUIDs between models.
It is **diagnostic only, excluded from adoption evidence**. Corrected fixtures
use opaque UUID IDs and stable Pack UUIDs derived from Pack hashes. Existing
pilot artifacts were preserved, not rewritten.

## Quota-contaminated 40-case sweeps

| Artifact timestamp | Experiment | Rows | HTTP calls | HTTP 200 / 403 |
|---|---|---:|---:|---:|
| 082622483944 | Current 3, V3 and decisive cross-check | 240 | 288 | 199 / 89 |
| 082629132650 | Stronger 3, V3 | 120 | 120 | 23 / 97 |
| 082629551778 | Current 3, V2 | 120 | 228 | 148 / 80 |

V3 without a checker usable rates were Ling 23/40, Luna 24/40, Lite 22/40;
with a checker 14/40, 20/40, 14/40. Ling produced false contradictions of null/
conflict cases; Lite produced false support of the narrow-dose case. A decisive
checker did not reliably remove these mistakes in this interrupted comparison.
Stronger V3 candidates were usable Astra 2/40, Pro 10/40, Claude 9/40. Pro also
produced narrow-dose false support. Current V2 was usable 10/40, 10/40, 11/40;
Luna produced narrow-dose false support. **Do not rank these as clean clinical
accuracy comparisons:** quota failures contaminated planned denominators.

## Fully answered minimal-V2 candidate

Artifact: `bakeoff-20261002T084005198182.json`. Current three models × 40 cases;
364 calls, all HTTP 200; 512,584 input and 64,638 output tokens. This candidate
asks for the smallest sufficient qualitative finding, no optional statistics,
while preserving genuinely numeric claims and genuine opposing evidence.

| Model | Schema | Usable | Relation | Scope | Materiality | Position agreement | False support | False contradiction | Numeric issues | p50 / p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Ling | 40/40 | 30/40 | 32/40 | 26/40 | 29/40 | 28/40 | 1/32 | 0/34 | 4 | 4,884 / 9,289 |
| Luna | 40/40 | 33/40 | 29/40 | 28/40 | 25/40 | 31/40 | 1/32 | 0/34 | 2 | 6,307 / 13,596 |
| Lite | 40/40 | 33/40 | 35/40 | 32/40 | 32/40 | 32/40 | 1/32 | 0/34 | 3 | 3,845 / 4,426 |

Each false-support position was the same narrow-dose overgeneralization control.
All three failures remain visible; no benchmark label was changed to improve
scores. Missed annotated decisive positions were 5/14, 6/14 and 2/14 respectively.
These are provisional false rejections/abstentions, not clinical error estimates.

Development usable rates: 22/30, 26/30, 25/30. Held-out usable rates: 8/10, 7/10,
8/10; held-out relation agreement: 6/10, 5/10, 8/10. No false decisive position
was observed in the ten-case held-out subset. That small result does not cancel
development failures or repair the missing clean paired baseline.

## Reviewed development evidence oracle and selection

Eleven fresh PubMed/approved-authority controls were frozen without extraction
model calls. Four explicitly synthetic numeric/causal/null/conflict controls
bring the baseline to 15. These are fresh controls, not historical analyses.
An engineer inspected exact retrieved abstracts/source blocks for eight claims
across six topics; there was no independent clinician review.

Reviewed sources include NCI professional causal assessment and PMID 38268471
(observed smoking exposure, NOT randomized smoking); melanoma trial 21135266,
syntheses 29620003/40876975; skin-cancer syntheses 30447006/14678916; BP/stroke
15746450/42339173; Vitamin C 23440782/9059230; and carrot-methodology 34555021.
The carrot source is observational/reverse-causation context, not a causal trial.
No approved contrary or guidance document was fabricated to fill a quota.

| Control | Current reviewed-source precision / recall | Lean precision / recall |
|---|---|---|
| Three smoking formulations | .25 / 1.0 | .50 / 1.0 |
| Invasive melanoma | .60 / 1.0 | .75 / 1.0 |
| Broad skin cancer | 0 / 0 | 0 / 0 |
| BP/stroke | .25 / 1.0 | .333 / .50 |
| Vitamin C/cold | .25 / 1.0 | .50 / 1.0 |
| Carrot/eyesight | 0 / 0 | 0 / 0 |

Precision is membership in this limited reviewed set, NOT exhaustive relevance
annotation; oracle 1.0/1.0 is true by construction, not independent performance.
Lean dropped a reviewed BP/stroke source, failing the recall gate. Broad skin
search did not retrieve the direct trial present in the invasive-melanoma Pack.
Carrot selection included a school fruit/vegetable programme rather than the
reviewed limitations source. Retrieval/selection is not solved.

An initial full oracle pilot aborted at existing incompatible-source visibility
validation; console progress survived but its structured responses did not.
It is not a completed comparison. The harness now checkpoints each response
append-only and records preparation exclusions instead of crashing. Existing
incompatible roles are preserved: oracle selection does NOT bypass provenance
or upgrade contextual/incompatible evidence to decisive.

The completed four-claim subset (`084322116770`, Lite only) compared current/
lean/oracle under V2/V3: 24 rows, 87 calls, all HTTP 200; 282,895 input and
22,560 output tokens. V2 usable 3/12, V3 6/12; numeric issues 10 versus zero
generated numeric findings by V3's schema. Two oracle preparation blocks per
architecture remain. BP/stroke V3 oracle produced provisional support while
current/lean were NEI; Vitamin C/carrot remained incomplete or NEI. Without
reviewed medical labels, no real-source false-acceptance rate can be inferred.
The paired condition is incomplete for all candidates, not a replacement gate.

## Repeatability and validators

Artifact `084351243260`: Lite only, five identical-input repeats for five
synthetic controls, V2 and V3, 50 rows/100 calls, all HTTP 200; 138,410 input
and 13,673 output tokens. All within-case input hashes match.

| Conditional control | V2 position distribution | V3 position distribution |
|---|---|---|
| Regular smoking | supported × 5 | supported × 5 |
| Inverse smoking | contradicted × 5 | contradicted × 5 |
| Opposite randomized direction | contradicted × 5 | contradicted × 5 |
| Carrot reverse causation | NEI × 5 | NEI × 5 |
| Numeric distortion | operational inability × 5 | numeric-blocked × 5 |

The opposite-trial control is **not real sunscreen evidence**. Both models'
numeric-distortion relations were wrongly supportive five times, but backend
checks blocked those decisive positions. Position and relation flip rates were
0/20 transitions per architecture; this says stable, not necessarily correct.
V2 used 75 calls (p50 3,877 ms), V3 25 (p50 1,333 ms); both usable 20/25.
Zero generated V3 numerals is not zero numeric risk in the submitted claim.

V2 probe validation uses a configured non-self checker (reverse slot order),
not necessarily the normal worker's exact rotation. The optional `--validator`
supports a single checker experiment, but a complete, clean same-input current-
rotation-versus-best-checker comparison was **not run**. The quota-contaminated
V3 checker experiment cannot establish a superior checker. Keep normal selection.
Reviewers are never judge votes. Production validator approval remains false.

## Single/two/three judge offline policy comparison

The existing `VerdictService(POLICY_V4)` rechecks original V2 audit provenance;
no votes are manufactured and no threshold is lowered. Lite is a measured single
baseline, not a certified strongest model. Subsets use existing claimed families.
V3 probe responses are not coerced into V2 validation rows.

| Minimal-V2 subset, 40 cases | Supported | Contradicted | NEI | Unable | False decisive | Policy-position agreement |
|---|---:|---:|---:|---:|---:|---:|
| Lite only | 9 | 4 | 0 | 27 | 1 | 14/40 |
| Lite + Luna | 8 | 4 | 21 | 7 | 1 | 33/40 |
| All current three | 9 | 4 | 23 | 4 | 1 | 37/40 |

Three versus two reduces inability on these conditional controls, not their
shared false-support case. The single baseline's NEI abstentions are often
Unable because existing standard-risk minimums still apply to inconclusive
results. Only the pre-existing development single-*decisive* provisional rule
applies. All production qualification flags are false. Held-out agreement was
3/10, 8/10, 8/10 respectively. This is not a verified-family production ensemble.

## Adoption gates

- V3: fewer calls and no generated assertion statistics, but observed false
  decisive positions and incomplete paired/stability/validator measurements;
  **not adopted**.
- Minimal-V2: useful schema/usability results, but numeric failures and one
  shared false-support control; clean full paired baseline missing; **not adopted**.
- Lean: reviewed relevant-source recall fell for BP/stroke; **not adopted**.
- Models: no stronger candidate established improvement across both splits and
  five-run stability; **no replacement**.
- Validators: no clean superior-checker result; **no configuration change**.

Normal call count has not improved. Architecture selection remains the existing
baseline pending safer evidence. The remaining controlled matrix and independent
annotation review must not be described as completed or clinically qualified.

## Cost/accounting boundary

The seven completed corrected bake-off artifacts above contain **1,402 measured
HTTP calls** (including 403 failures); four normal acceptance cases add **155
observed model calls**. The discarded methodological pilot adds 168 calls, and
the aborted oracle pilot incurred additional calls without a complete structured
usage artifact. Therefore 1,557 is NOT the all-session billing total. Catalog GETs,
retrieval-provider calls and polling are also separate. No dollar total can be
established from this gateway metadata. Further full sweeps were stopped rather
than silently treating restored quota as permission for unbounded spending.
