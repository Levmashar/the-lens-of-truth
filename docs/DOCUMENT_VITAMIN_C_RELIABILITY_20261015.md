# Vitamin C document reliability — 2026-10-15

Original frozen analysis: `699edaa0-e483-4fb2-931d-ad15c1d5c330`.
Final real frontend submission: `b40b06f3-796b-4cdd-ae59-fe621ebc833f`.

The final run is **partially completed: 8 assessed / 2 unavailable**, rather than
the original failed run with zero assessed. All 13 final model requests responded
on their first attempt. No model, qualification threshold, treatment safeguard,
public label or production gate was changed. This is not a production/clinical
release claim, and the remaining unavailable assessments were not converted to NEI.

## Root causes and bounded changes

### Study-version matching and downstream ownership rejection

The original matcher recognized exact supplied PMID/DOI or named cohort clues.
It did not establish publication identity from an unquoted publication title,
publisher metadata and distinctive reported results. Both retrieved vitamin C
review versions received only topic scores; `matched_document_ids` stayed empty.
The reporting guard then raised `reporting_check_uses_other_study` for any completed
field citing a source outside that empty set. Some saved checks also genuinely
mixed the primary paper with NCCIH or another review; those citations remain foreign
to a primary-paper reporting check and must not be silently aliased.

The new generic matcher requires an exact normalized publication title plus an
independent publisher/author/year clue and multiple literal population-bound result
fingerprints. For these frozen inputs, **8% / adults and 14% / children** distinguish
PMID 23440782 (2013) from the retrieved 2007 version's 13.6% childhood value. It does
not round that value, convert RR to percentages, choose the newest paper or identify
a source by topic overlap alone. Tied fingerprints stay uncertain; conflicting
supplied years exclude candidates. Exact PMID/DOI and named-study paths remain.
This conservative new fingerprint path currently uses literal bound percentages;
it does not promise identification when the necessary clues are absent.

Identity establishes which source is being checked, not the truth or comparability
of every reported statistic. The separate source, integrity, quantity and scope
guards still run. Existing frozen replies were replayed without inventing sources
or fixing their cross-publication citations. The original final report still passes
its historical audit with unchanged positions and counts.

### Attributed assertions and explicit medical context

The planner labelled the three commentator propositions as commentary and therefore
never independently evaluated their medical content. The planner instructions and
normalizer now retain a factual medical proposition even when quoted, attributed
or indirect. Original wording, speaker attribution, offsets and study ownership are
preserved. Pure opinion and source notes can remain commentary; reporting fidelity
and medical validity remain separate targets.

A fresh run exposed a second generic planning defect: a context reference was
attached to two assertions but only belonged to one. The old union-of-owner-spans
check passed before the final per-assertion invariant rejected the whole document.
The repair checks each owner separately. Only a uniquely adjacent literal coordinated
clause can receive its own exact dependency; unrelated/ambiguous owners stay unresolved.
An explicitly supplied, uniquely literal antecedent may span coordinated assertions.
No invented or forward reference is accepted.

Finally, atomic normalization discarded document-owned inherited context. A validated
`shared_exposure` link for “higher doses” pointed to the preceding medical assertion,
but the exposure/outcome still remained “higher doses / protection.” New document
grounding preserves literal linked fields. For a generic dose-ellipsis reference,
one unambiguous linked parent and one resolved terminology mention may supply the
agent and inherited endpoint. A speaker-only/same-topic link cannot do so. Earlier
numeric dosage is not inherited; the original stronger-dose wording stays intact.
All three medical assertions now enter evaluation and the usual readiness checks.

### Prompt size, CPU stalls and provider timing

Reporting selection fell back to every retrieved passage when no study was matched.
Generic method/participant overlap favoured huge unrelated abstracts: selected
blocks included 24,802 and 21,788 characters. The judge snapshot had 512 quantities;
sources alone occupied about 136k serialized characters. The full validator also
carried clinical-axis instructions/schema for reporting-only questions.

New selection uses the identified publication, or conservative publication-level
exposure/endpoint context when identity is unresolved. Large-block word overlap is
penalized. Complete selected passages, IDs, quantities, ownership and frozen candidate
provenance are retained; passages are not clipped to make an answer pass. Repeated
quantity-parser explanations use a lossless dictionary-coded table whose expansion
must equal the original catalog. Older table/input contracts still dispatch exactly.
Reporting-only validation omits inapplicable clinical-axis instructions and relation
preparation; clinical validation still receives the existing scientific axes.

The original chains **were concurrent**: all three judges started within about 17ms,
with 2–3ms account queue waits. The main delay was not a serialized judge loop.
After DeepSeek's response, synchronous validation preparation occupied about **57s**
before its validator was queued. This blocked deadline handling: nominal 60-second
judge attempts appeared to take about 87s. Deterministic per-item preparation and
qualification now run off the async event loop. Final preparation is below one second
per reporting chain. The maximum account concurrency remains three, with independent
judges and per-judge validators. Existing 60s attempt / 110s judge-total / 75s validator
deadline and bounded attempt counts remain; these were not increased to hide failures.

### Validator response contract and honest reader status

The first improved live run exposed validators returning populated reporting fields
while declaring every item unavailable and omitting finding attributions. The new
`document-validation-1.3` schema separates completed reporting items (nonempty required
attributions) from truly unavailable items (empty attribution/check arrays). Runtime
coverage requires the exact expected ordered statement IDs. A contradiction or an
unresolved scientific field does not itself mean that source attribution is unavailable.

One bounded format/coverage repair may request **only invalid items**, within the
same 75-second deadline and two-call maximum. Valid siblings are retained. Expected
and returned IDs and exact errors are recorded. Audit reconstructs the repair request,
hash and merged validated results. No source attribution is fabricated, and no failed
item is made NEI. The final live run needed no repair retry. The previous 1.0/1.1/1.2
validator paths remain available for historical reconstruction.

The reader now displays an explicit failure when backend status is failed with zero
assessed assertions. Its accessible announcement says “Check could not be completed
reliably”, and its state is failed. Partial results announce incomplete assessments.
Changes in terminal status are announced even if the pipeline stage did not change.

## Before/after results

| Submitted detail | Original | Final |
|---|---|---|
| Cochrane review's identity and subject | Unavailable | Supported reporting check |
| Thousands of trial participants over decades | Unavailable | NEI: timeframe not fully established |
| Approximately 50% reduction in severe-exercise subgroups | Unavailable | NEI: effect-measure comparability guard |
| Around 8% shorter colds in adults | Unavailable (combined statement) | NEI: effect-measure comparability guard |
| Around 14% shorter colds in children | Unavailable (combined statement) | Supported reporting check |
| Interpretation about protecting the immune system | Unavailable | Unavailable: insufficient qualified assessments |
| 1,000 mg daily halves everyone's cold risk | Uncheckable commentary | NEI after independent medical evaluation |
| Higher doses provide stronger protection | Uncheckable commentary | Unavailable: two qualified NEI assessments; third excluded with `REQUIRED_FINDING_UNAVAILABLE`; high-risk quorum preserved |
| Proven prevention of respiratory infections generally | Uncheckable commentary | NEI after independent medical evaluation |
| Source note | Background | Supported source/reporting check |

The planner separated adult/child findings, so nine original records became ten;
this is not a one-to-one change in the count of medical claims. Reporting Supported
does not become a general treatment/prevention recommendation. Numerical and clinical
positions above are the unchanged backend policy's results, not forced sanity labels.
The broader medical correctness of conservative NEI outcomes was not retuned here.

One final DeepSeek-chain finding for the review description was excluded with
`reporting_attribution_evidence_ids_mismatch`; the other two chains qualified that
standard-risk check. The two final unavailable assertions remain visible. All final
judges/validators responded; transport success is not semantic qualification.

## Measured execution

| Metric | Original | Final |
|---|---:|---:|
| Backend analysis time | 284.214s | 202.381s |
| Completed assessments | 0 | 8 |
| Unavailable assessments | 5 | 2 |
| Background records | 4 | 0 |
| Model requests including planner | 7 | 13 |
| Judge timeouts | Qwen twice; GLM twice | None |
| Provider-reported judge input tokens | DeepSeek 40,955 | 6,364–7,952 across groups/models |
| Provider-reported validator input tokens | 51,436 | 8,433–12,021 |
| Actual peak concurrent model requests | 3 | 3 |

Final requests include a second group that was previously skipped. Public-source cache
state also differs; elapsed time is an observed run comparison, not an isolated speed
benchmark. Final judge latencies were **10.561–41.317s**, validator latencies
**32.772–67.278s**, and account queue waits **1–4ms**. Final usage including planning:
**106,603 input + 29,097 output = 135,700 reported tokens**, all 13 calls on attempt 1.
The final audited document GET returned HTTP 200 in 6.718s under concurrent test load.

All paid work in this task is accounted for: an accidental first-paragraph submission
(4 calls), a full-passsage planner failure (1 call), the intermediate full run (13),
one saved-judge validator probe (1), and the final full run (13): **32 requests**.
Known usage is **286,884 tokens**, plus the failed planner's unrecorded usage. That
older failure path did not retain provider usage before plan validation failed; no
zero usage or precise monetary cost is invented. The original run's four timeouts
also have unknown usage. No model bakeoff or unrelated paid control was run.

## Verification and remaining limits

- Frozen original replay and final historical audit passed with original failure,
  positions, counts and stored artifacts unchanged. No retention extension or DB rewrite.
- Regression coverage includes ambiguous versions, conflicting dates, exact numeric
  bindings/interval exclusion, unrelated giant abstracts, quoted/indirect claims,
  per-owner/coordination references, literal linked PICO without dosage transfer,
  both lossless table contracts, exact coverage repair and tampered repair rejection,
  preserved valid siblings, and failed-reader announcements.
- Frontend: **123 tests passed**, TypeScript/Vite production build passed.
- Full PostgreSQL-backed backend suite: **1,510 passed, 5 skipped**, 277.44s;
  no failures. An initial Windows invocation used the Docker-only `postgres`
  hostname and failed 16 database tests. The rerun changed only the process-local
  connection host to the existing `127.0.0.1:5432` port, preserving credentials
  without printing them or changing `.env`. Ruff passed; mypy **200 modules** passed.
  The five skips are native Windows OCR smoke variants: no local Tesseract binary
  is installed. They are unrelated to this document task; no OCR test success is
  claimed for those skipped cases. Docker's existing OCR installation is unchanged.
- Real Chrome submission verified all 1,245 original characters before POST, followed
  normal polling and audited report GET. Desktop/mobile screenshots inspected; no
  horizontal overflow/empty headings. Minimum measured reader contrast 5.9:1.
  A real zero-assessed failed report displays the explicit failure notice.
- Existing repository-local Playwright and Lens reader-review skills were used.
  This was engineering/browser QA, not human comprehension testing.

Screenshots: [final desktop](assets/document-vitamin-c-20261015/vitamin-c-final-desktop.png),
[final mobile](assets/document-vitamin-c-20261015/vitamin-c-final-mobile.png),
[zero-assessed failure](assets/document-vitamin-c-20261015/zero-assessed-failure-desktop.png).

Reproduction artifacts, raw replies, exact per-call latency/usage and preserved hashes
remain under ignored `runtime/document_reliability_20261015/`. The original passage
hash agrees between the frozen original and the final submitted plan. The final
build uses the repository's normal Dockerfiles; no Dockerfile, dependency, global
tool/configuration, credential or model-setting change is part of this fix.

## Versions and unchanged model lineup

New document contracts: evidence **1.1**, planner prompt **1.2-2026-10-15**, plan
normalization **1.3**, group input **1.2**, dictionary quantity-table view **1.1**,
validator **1.3**. Document plan/workflow **1.0**, grouped judge **1.0**, reporting
position **1.0**, saved report **1.3**, reader view **1.0** remain.

Clinical query-plan **1.6**, position **1.8**, question policy **2.1**, judge prompt
**2.15**, semantic prompt **2.7** and verdict policy **1.4** remain unchanged.
All active providers remain Paratera: planner/extraction/Judge 1 **DeepSeek-V4.1-Flash**,
Judge 2 **Qwen3.5-Plus** (provisional), Judge 3 **GLM-4.7**, semantic validator
**Qwen3.8-Flash**, thinking disabled. Development/debug stays enabled; production
and clinical release remain unapproved. The separate joint-adjustment-proof issue
documented on 2026-10-14 is not changed by this task.
