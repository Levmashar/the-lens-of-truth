# Document report clarity and correctness — 2026-10-08

The deployed reading view is `document-report-1.3`. It explains qualified results
without another model call, a document verdict, changed medical requirements or
changed models. This is a development evaluation build, not production approval.

## Main retained regression

Analysis `42f64be8-dde4-4b0d-a43a-d9990631f99a` was replayed from still-retained
plan, evidence, raw judge/validator responses and report artifacts. Its original
`document-report-1.0` audit and exact projection still reconstruct. The saved
report hash remains
`33c1559f0fda3ed673b44fd3934217c15c168610e3530f6910039bcf5d4b6726`.
No original records, positions, labels, spans or raw captures were rewritten.

| Before | After |
| --- | --- |
| Generic introduction; eleven of eleven appeared checked | Three traced takeaway sentences; seven assessed, one unavailable, three background, zero pending |
| Bare Supported for source-reporting accuracy | Matches the paper; canonical Supported remains unchanged |
| Unresolved number and adjustment details buried among fragments | What needs attention appears first, with detail-specific explanations |
| G2 adapter failure appeared as source not found | Source search failed; processing failure remains distinct from scientific NEI |
| Citation note appeared as its own investigation | Explicitly linked source note folds under its topic, retaining its ID and original text |
| Long repeated source passages | Exact whole-sentence excerpts link to full frozen passages pooled once per topic/owner |

The takeaway identifies the UK Biobank topic, five matching reported details,
unresolved effect-size/adjustment details and the unavailable interpretation.
Every source-based summary line lists assertion/group IDs and qualified source
unit references. Unavailable checks supply no evidence vote. Background wording,
including comparative superlatives excluded from evaluation, is not shown as
verified. There is no overall truth score.

## Root causes and fixes

1. **Completion accounting:** terminal processing, commentary and assessments
   were counted together. API/UI now derive disjoint assessed, unavailable,
   background and pending counts from actual assertion states. A completed NEI
   counts as assessed; a failed check does not. Reports use Finished with
   limitations where relevant, including reports with no completed assessment.

2. **Empty retrieval group:** G2 had no eligible assertions after grounding,
   but the authoritative adapter treated an empty tuple as an oversized group.
   Empty retrieval returns no results and issues no HTTP request. Oversized
   groups still fail, and the original eight-assertion/TTL bounds remain.
   The orchestrator skips searches/fetches when no grounded eligible question
   exists; it does not invent PICO fields. Historical G2 stays failed rather
   than being retroactively assessed. Source status now distinguishes identified,
   uncertain, pending, searched/not found, not applicable and failed.

3. **Generic reporting explanations:** the reading projection now uses qualified
   field checks/reason codes, not arbitrary judge rationale. Reporting fidelity
   has separate display labels; medical assessments retain the four public
   labels. Relevant association caveats appear beside the visible result and
   within its detail, without creating an unsubmitted causal proposition.

4. **292% interpretation:** A4's frozen quantity `E169.U1.Q25` contains `3.92`
   but has measure `unknown`; `E169.U1.Q24` contains the `RR=1.36` bound. The
   cited frozen methods describe multinomial logistic regression and
   exponentiated log-odds against a reference category. These are not automatically
   ordinary disease risk ratios or changes in a person's disease probability.
   The existing `reported_effect_measure_not_comparable` result remains NEI.
   The explanation says that the number exists but its claimed conversion is
   unverified. No new conversion, catalog retagging or judge-prose numeric parser
   was added; ordinary RR, OR, HR and category-relative estimates remain distinct.

5. **Adjustment claim:** A6 remains NEI with `VALIDATED_JUDGE_DISAGREEMENT`.
   Qualified checks disagree about the claimed adjustment set. Mentioning or
   separately analyzing variables does not establish their simultaneous inclusion
   in the model producing the estimate. The reading view does not assert definite
   non-adjustment or promote either judge's explanation into a source fact.

6. **Two live planner ownership failures:** one fresh paragraph placed a
   study-owned assertion in an unattributed group despite a unique exact resolved
   study-reference link. One unidentified-source request put unattributed
   bibliographic wording inside a study-owned group. Normalization 1.2 restores
   only a uniquely linked existing study owner and separates unattributed details.
   It preserves study IDs, exact spans and content; ambiguous, unlinked and foreign
   study mismatches still fail. No new planner/model prompt was used.

7. **Unavailable document presentation:** the analysis page no longer says the
   document could not be read when an audited report is available but its checks
   failed. Partial validated limitations may be displayed explicitly as partial
   findings without converting an unavailable group into NEI or Supported.

## Presentation and accessibility

Page order is Main takeaway, What needs attention, What matches the source,
Important interpretation limits, then collapsed Detailed checks and sources.
Each detail retains its short heading, submitted wording, result, explanation,
source ownership and all original occurrences. Explicitly linked commentary and
source notes are folded into their topic; unnamed experts are not assumed to be
paper authors. Literal duplicates stay traceable, and different endpoints/topics
remain separate.

The existing vanilla TypeScript/Vite stack uses native disclosures, explicit
status text, meaningful source links, visible focus, fluid text/mobile wrapping
and reduced-motion styling. Local citation links open their owning topic and full
passage and focus its disclosure. Full passages remain exact, including table
headers/footnotes, negations and qualifiers. Development notice, Copy all
diagnostics and full raw responses remain; request payloads/credentials are excluded.

Native disclosure/focus, safe text rendering and clipboard behavior passed DOM
tests. **Desktop/mobile visual inspection could not be completed:** this session
has no enabled browser surface. No screenshots or visual approval are claimed.

## Live normal-API checks

Requests used the same consent-required POST, status polling and document GET
used by the frontend. There were five submissions and **26 paid requests total**,
including two one-call failed planner submissions. No summary-writing calls,
model changes, bakeoff or retry-until-agreement loop were used.

| Request / analysis ID | Result | Calls | Backend time | Client time through report |
| --- | --- | ---: | ---: | ---: |
| Initial paragraph — `82d4929d-102f-4258-8b7a-460aa3cb506f` | Planner ownership failure; exact saved proposal now passes bounded offline repair | 1 | 14.792 s | 29.766 s |
| Exact original retained paragraph — `14b340d7-946f-4212-8013-e616146b6a90` | HTTP 200 report; five assessed matches, three unavailable, three background | 7 | 128.636 s | 141.223 s |
| Initial unidentified source — `3ff839fa-ed9c-4e78-abcf-f5b6f3dcd4c0` | Planner attribution failure; exact saved proposal passes separation repair | 1 | 5.503 s | Client capture overwritten by the explicit rerun; original backend artifacts retained |
| Unidentified Aurora Notebook Study — `070aef60-2150-4b2e-a3f7-00e8934f7d3f` | HTTP 200 report; zero assessed, two unavailable, one background; searched source not found | 4 | 24.564 s | 36.916 s |
| Smoking plus antibiotics document — `b23b81eb-06d9-408c-8cbe-523a671d2cc9` | HTTP 200 report; two separate topics, two unavailable medical checks, two background items | 13 | 74.122 s | 79.874 s |

The paragraph's fresh A4 could not reach group qualification: one validator
attribution reason exceeded the unchanged 1,200-character bound and another
returned mismatched attribution statement IDs. A remaining qualified assessment
found its measure noncomparable; this partial limitation is identified as partial,
not upgraded into a complete result. Fresh A5 lacked the required three usable
high-risk assessments. A6's planned source reference was unresolved. These are
fresh model/planning limitations, not changes in scientific policy.

The mixed-topic test exposed a genuine unresolved **clinical validator contract
failure**: all six replies returned `semantic.attributions=[]` and
`semantic.assessments=[]`. `JointResponse23` requires nonempty axes and attribution
for the supplied findings. Exact exceptions report both minimum-length failures.
The prose claimed support but cannot substitute for those checks; both medical
assessments remain unavailable. The clinical requirements, validator/model and
prompt were retained rather than weakening validation to force successful labels.

Consequently, this pass improves the handling and explanation of failures; it
does **not** establish reliable medical qualification for every document.
The original retained report's scientific results are unchanged. The fresh
paragraph's fewer completed checks reflect the specific new failures above.

## Verification and deployed versions

Final full PostgreSQL-backed backend suite: **1,491 passed**, zero failures/skips,
239.24 seconds. Four existing Starlette deprecation warnings remain.
Frontend: **102 passed**, six files, 2.22 seconds; TypeScript and Vite production
build pass. Ruff passes; mypy passes all **198** modules. Historical report
contracts 1.0/1.1/1.2 reconstruct before a read-only 1.3 view is returned, and
source/audit ownership, retention and production rejection remain covered.
The retained main regression replays with unchanged labels and exact excerpt
offsets. Both Docker services rebuilt/restarted on the final source.

After restart, backend health and the served frontend return HTTP 200 with
development diagnostics enabled and final frontend asset `index-DMdErCu0.js`.
All four retained/fresh report GETs above return 1.3 with unchanged saved hashes.
The two larger audited reports each took 25.659 seconds during a concurrent
two-request check; unidentified/mixed reports took 2.079/3.120 seconds. Read-time
audit cost is still a performance limitation, separate from paid generation time.

| Contract | Current version |
| --- | --- |
| Document workflow / plan / evidence | 1.0 |
| Document planner prompt | document-planner-1.1-2026-10-08 |
| Document plan normalization | 1.2 |
| Shared group input / source view | 1.1 / 1.0 |
| Group judge / validator / reporting position | 1.0 / 1.2 / 1.0 |
| Document reading report | 1.3; historical 1.0, 1.1 and 1.2 retained |
| Clinical judge / source quantities | V2.5 / V2.4 |
| Query plan / validated position | 1.6 / 1.8 |
| Question evidence / verdict policy | 2.1 / 1.4 |
| Clinical judge / semantic prompts | 2.15 / 2.7 |
| Document persistence migration | 20261007_0019, unchanged |

Paratera lineup remains extraction/planner/J1 **DeepSeek-V4.1-Flash**, J2
**Qwen3.5-Plus** (provisional), J3 **GLM-4.7**, validator **Qwen3.8-Flash**
with thinking disabled. `.env`, provider URLs/credentials, clinical eligibility,
structured quantity rules, quorum and production gates are unchanged.

Remaining limits: clinical validator empty axes, occasional reporting validator
contract violations and planner-reference uncertainty; primary-document latency
above the prior 90-second target; visual browser QA unavailable; production/clinical
release qualification remains unmet. Expired raw captures are not restored.
