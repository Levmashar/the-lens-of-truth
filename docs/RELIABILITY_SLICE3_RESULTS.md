# Reliability Slice 3 results

Date: 2026-10-01. Scope: curated authoritative coverage, relationship-design
metadata, question-specific sufficiency, and document-level report grouping.
Slice 2 attribution → claim relation → deterministic qualification remains.
No V3 rewrite, environment/model edits, relaxed judge counts, production release
qualification, arbitrary URL retrieval, search, or crawler was introduced.

## Outcome

The engineering repair is implemented and software checks pass. Approved smoking
evidence now reaches all judges in a combined frozen Pack. This is **not** a claim
that medical reliability improved: in the six-case live comparison, qualified
assessments fell from **6/18 to 3/18**. One smoking control produced a provisional
development `supported` result; frequent smoking, sunscreen, hypertension and
Vitamin C remained `unable_to_verify_reliably`. Carrots remained
`not_enough_evidence`. Every result was evaluation-only, not production qualified.

## 1. Original smoking replay: confirmed cause

These are retained original artifacts, not reconstructed fixtures:

- Analysis: `b3219a2d-9504-4fd8-91e2-e5384a9d7ea4`
- Claim: `28c2ee9d-554a-47aa-9e63-72255c6d2b61`
- Pack: `ba32d2a6-90bf-41f5-a634-2c0044646337`, version `1.4`
- Pack hash: `bd8269f715e27b8606dcaf241a9f2047c6bc7a08c6f2d0531effda87f7876e15`
- Verdict: `923e4a3f-10e1-45fc-a3c1-a2167f05919a`
- Original expiry: `2026-10-02T16:16:35.255638Z`

| Judge | Original outcome | Qualification |
|---|---|---|
| Ling | Supported; smoking findings from ATBC | Validated/justified, but the parent-RCT design conferred inappropriate causal strength |
| GPT Luna | Not Enough Evidence | Validated/justified; `CAUSAL_DESIGN_INSUFFICIENT` |
| Gemini | Supported | Invalid/not justified; context/insufficient findings did not establish a material proposed direction |

The final NEI was primarily a **policy gate**: two assessments qualified, but
only one qualified decisive assessment supported the claim. The unchanged
standard threshold requires two. Reasons included `VALIDATION_FATAL_ISSUE`,
`INSUFFICIENT_DECISIVE_EVIDENCE`, and `EVALUATION_ONLY`. Three structured model
responses existed; this was neither an empty retrieval nor a protocol outage.
There was no demonstrated contradiction between qualified decisive directions.

Secondary causes: evidence coverage/indirectness, exposure-design sufficiency,
and a material semantic/qualification failure. The result alone does not prove
that a medical claim is false or that every excluded assessment is a false rejection.

Sanitized ignored captures:

- `runtime/debug/b3219a2d-9504-4fd8-91e2-e5384a9d7ea4-20261001T162718046915.json`
- `runtime/debug/slice3-smoking-trace-20261001T170740816046.json`

The second artifact traces every selected document through queries, candidate
PMID, normalized source, ranks/selection, all judge-visible sibling E IDs,
findings, attribution, relations and deterministic qualification. It adds a
read-only corrected-design annotation; it does not rewrite the original Pack.

## 2. Original evidence weaknesses and recall audit

| Selected E | PMID | Source topic / limitation |
|---|---|---|
| E11 | 38268471 | Changes in smoking and lung cancer in ATBC; smoking exposure was observed, not assigned |
| E23 | 41402808 | Methylation clocks; indirect mechanistic/biomarker framing |
| E31 | 42021368 | Epigenetic age/internal dose; not a comprehensive causal assessment |
| E40 | 38214107 | Stigma/emotional function; background for the asserted causal endpoint |
| E1 | 40059777 | SNP mediation; narrower mechanistic question |
| E24 | 41731520 | Air pollution with residual smoking eliminated; a different exposure question |
| E26 | 41738161 | Transomics interactions; narrower research framing |

This source set does not summarize the established body of causal evidence.
Its seven sections/documents must not be mistaken for seven directly decisive
causal replications. Visible sibling Methods/Results/Conclusion units remain
available for exact audit; they are not independent publications.

ESearch now records actual query, explicit `sort=relevance`, `retmax`, total
count when returned, PMID count and cache state. The evaluation used `retmax=10`.
Older cached search tuples did not retain total result counts: those totals stay
null rather than being guessed or described as fresh live ESearch measurements.
The hypertension query totals were 8,752 / 8,898 / 6,167; Vitamin C totals were
274 / 280 / 78. Each returned ten PMIDs. Query provenance is in the captures.

Sentinels PMID 38268471 (ATBC), 21135266 (sunscreen randomized follow-up), and
29620003 (sunscreen synthesis) were candidate → normalized → selected in their
respective paired controls. Sentinel IDs are evaluation tracing, not selection
or verdict hardcoding.

## 3. Actual changes

### Design and source independence

`study_design` remains the parent publication/container design.
`relationship_analysis` separately records `analysis_design`,
`exposure_assignment`, source basis and explicit Methods evidence. Actual exposure
assignment drives the new sufficiency policy. An observed smoking analysis inside
ATBC is `secondary_observational_analysis` / `observed`, not a randomized smoking
intervention. Unknown design stays unknown; an “As Topic” MeSH term is not proof
of the publication's own systematic-review design.

Explicit randomized exposure assignment, prospective cohorts, case-control,
cross-sectional, synthesis and diagnostic/reference-standard evidence have
offline controls. This is a conservative text/metadata classifier, not a complete
study-design adjudicator. Some relevance ranking still uses parent publication
features; qualification does not rely on that feature as proof of randomization.

Judge input includes document bundles containing exact source units. Report `1.2`
groups all qualified excerpts of a document into one card. E/unit IDs and hashes
remain distinct. New grouped excerpts retain full frozen passage text; legacy
preview fields retain their explicitly marked short prefixes. The frontend prefers
actual analysis design and shows approved publisher/purpose/update/currency.
Missing design is not displayed optimistically as an RCT.

Known summary PMID relationships and shared independence groups prevent obvious
double counting. Unknown underlying references are explicitly unknown, not assumed
independent. This is not a complete citation graph or clinical replication count.

### Approved-source adapter and corpus

The generic HTML adapter accepts only server-manifest IDs at exact approved HTTPS
organization hosts. No arbitrary user URLs, credentials, query/fragment/port URLs,
redirect following, JavaScript, web search or link crawling. It does not bypass
access restrictions. Bounds: four candidate sources, concurrency two, 12 seconds
per fetch, 2 MB streamed response cap, eight retained complete paragraphs and
8,000 retained characters per document. A body version hashes canonical extracted
visible text/metadata/reference links; exact retained subsets and omission counts
are also frozen in the Pack. HTML entities and whitespace normalization are
documented, not falsely represented as original HTML byte offsets.

`approved-sources-1.0` contains seven reviewed development documents:

| Organization/document | Purpose | Supplied update/review date observed |
|---|---|---|
| [NCI Tobacco](https://www.cancer.gov/about-cancer/causes-prevention/risk/tobacco) | public_health_guidance | 2017-01-23 |
| [NCI professional smoking PDQ](https://www.cancer.gov/about-cancer/causes-prevention/risk/tobacco/quit-smoking-hp-pdq) | systematic_evidence_summary | 2025-02-21 |
| [CDC cigarettes and cancer](https://www.cdc.gov/tobacco/about/cigarettes-and-cancer.html) | fact_sheet | 2024-09-17 |
| [NCI Sunlight](https://www.cancer.gov/about-cancer/causes-prevention/risk/sunlight) | public_health_guidance | 2023-04-26 |
| [WHO Hypertension](https://www.who.int/news-room/fact-sheets/detail/hypertension) | fact_sheet | 2025-09-25 |
| [NIH/NCCIH common-cold evidence](https://www.nccih.nih.gov/health/providers/digest/the-common-cold-and-complementary-health-approaches-science) | systematic_evidence_summary | unknown |
| [IARC tobacco/code research summary](https://www.iarc.who.int/reference/european-code-against-cancer-4th-edition-tobacco-and-cancer/) | research_report | unknown |

All seven approved URLs returned usable live HTML. The IARC page is **not** mislabeled
as an IARC monograph/causal assessment. Restricted alternative pages were not
bypassed. The manifest is a topic/source index, not a claim-to-label table.

Currency requires supplied document date plus recent manifest review. Defaults
are 3,650 days since document update and 90 days since review; these are configurable
engineering windows, **not clinical currency approval**. A successful URL fetch
alone is insufficient. Site footer dates are not document dates. NCCIH/IARC remain
unknown; future dates are unknown. Unknown/stale sources cannot satisfy the
authoritative decisive design gate. Page changes produce new source/Pack versions.

### Combined Pack and evidence roles

Pack `1.5` stores both `pubmed` and `authoritative_public_health`, frozen before
judging. Every judge gets the same prepared evidence; no browsing tools are supplied.
Approved sources do not fabricate PMID/DOI. Persistence/report PMID is null; the
shared internal document envelope retains an empty PMID string for compatibility.
New provenance includes canonical URL, publisher, purpose, date, verification,
currency, content version/hash, references, source lineage and exact sections.
Historical `1.3`/`1.4` semantic hashing remains compatible.

Selection hints are `direct`, `contextual`, `incompatible`; none means supports or
contradicts. At most two direct approved documents reserve slots alongside research.
At most two contextual documents use otherwise free slots and cannot independently
justify a decisive conclusion. Retraction, nonhuman and incompatible exposure-arm
exclusions remain hard. Missing endpoint, unstated comparator and indirect/reverse
relations can remain clearly nondecisive context. Multiple populations discussed
inside a summary are not treated as one never-smoker cohort.

Migration `20261001_0018` widens section headings from 128 characters to Text.
A real NCCIH heading exceeded 128 characters and caused the preserved pilot failure.
Downgrade refuses truncation. PostgreSQL round-trip tests preserve earlier content
versions/Packs and verify long headings; append-only audit protections remain.

### Question-appropriate sufficiency

For harmful-exposure causal questions, a direct current causal assessment or
systematic evidence summary may satisfy the **design** gate without a randomized
harmful-exposure trial. This does not automatically establish support direction.
Unreviewed convergence of individual observational studies is deliberately not enabled.

Treatment/prevention and other intervention causality still need applicable actual
randomization or synthesis; diagnostic claims need explicit diagnostic accuracy
with a reference standard. Essential quantitative alignment remains mandatory.
Fact sheets, general guidance, press releases and organizational authority alone
cannot pass a causal design gate. Relations, applicability, numeric materiality,
provenance and original judge-count/production requirements remain checked.

Versions: Pack `1.5`, judge content/attribution contract `2.2` unchanged,
judge prompt `2.8`, relation prompt `claim-relation-1.3-2026-10-01`, qualifier `1.1`,
verdict policy `1.4`, report `1.2` / builder `1.4`. Older audits are not rewritten.
The existing policy-1.3 development single-validated-assessment provisional behavior
is preserved, **not** a newly lowered judge-count threshold.

## 4. Software verification — offline, separate from live evaluation

- Docker Python 3.13 full suite: **547 passed**, including PostgreSQL integration,
  append-only checks, source version round trips and >128-character section headings.
  Two pre-existing Starlette deprecation warnings remain.
- Slice 3 focused controls: **41 passed**; the database version test is additional.
- Ruff: clean. `mypy app`: clean, **134 source files**.
- Alembic upgrade to `20261001_0018`: successful; schema check: no new operations.
- Frontend: **42 tests / 4 files passed**; TypeScript/Vite and Docker builds passed.
- `git diff --check`: clean.
- Local backend/frontend rebuilt and restarted; `/healthz` returned `status=ok`.

Ordinary tests disable live approved retrieval and use mocks/fixtures. None of the
following paid/source evaluation is silently part of CI. Original dirty work and
historical records were preserved; no commits/reset/environment edits were made.

## 5. Separately bounded live before/after evaluation

Six explicit, source-grounded claims/PICO objects bypassed extraction/OCR and used
the existing retrieval → judging → validation/revision → aggregation → report
callbacks. These are engineer-authored controls, **not independently human-reviewed
medical ground truth**, and not a full frontend extraction acceptance test.

The first paired pilot is retained, including mistakes/failures:
`runtime/runtime/debug/slice3-coverage-20261001T171629539826.json`.
It used 471 HTTP calls within a 480-call/2,400-second budget and took 931.342 seconds.
Besides provider failures, it exposed the long-heading database failure and the
overbroad source-wide population exclusion. Both were fixed rather than hiding the pilot.

The repaired combined run reused the pilot's **identical retained PubMed content**:
`runtime/debug/slice3-coverage-20261001T172956009700.json`.
It completed all six cases in 465.761 seconds, using 238/300 bounded HTTP calls
(227 model calls + 11 approved fetches), within 1,200 seconds and 150 seconds/case.
It retained new audit rows rather than altering any pilot/original row.
Final audit-reason wording and full grouped-excerpt display were tightened after
these measurements; evidence selection, semantic inputs and thresholds were unchanged.

### Paired outcomes

“Unable” means `unable_to_verify_reliably`; “NEI” means `not_enough_evidence`.
Direct/context counts are algorithmic role hints, not clinical annotations.

| Claim | PubMed docs (same before/after) | Approved docs after | Before selected docs / qualified | After direct / context / qualified | Before → after result | Stage seconds before → after | Model HTTP calls before → after |
|---|---:|---:|---|---|---|---|---|
| Smoking causes lung cancer | 28 | 4 | 7 / 1 | 8 / 0 / 1 | Unable → provisional Supported | 99.744 → 80.190 | 41 → 43 |
| Frequent smoking causes lung cancer | 28 | 4 | 7 / 1 | 8 / 0 / 0 | Unable → Unable | 62.097 → 84.533 | 30 → 41 |
| Frequent sunscreen use causes invasive melanoma | 26 | 1 | 3 / 0 | 3 / 2 / 0 | Unable → Unable | 75.735 → 91.352 | 37 → 43 |
| High blood pressure causes stroke | 29 | 1 | 5 / 1 | 6 / 2 / 0 | Unable → Unable | 80.831 → 81.825 | 38 → 37 |
| Vitamin C prevents the common cold | 26 | 1 | 5 / 1 | 5 / 2 / 0 | Unable → Unable | 74.452 → 90.433 | 27 → 41 |
| Carrots improve eyesight | 12 | 0 | 1 / 2 | 1 / 0 / 2 | NEI → NEI | 28.068 → 30.114 | 20 → 22 |

Approved-topic retrieval sentinel coverage rose from 0/11 to **11/11** across the
six cases (repeated smoking-source appearances included). Only **5/11** reached
judge-visible selection: NCI PDQ + CDC in each smoking case, WHO in hypertension.
This is coverage of the reviewed development manifest, not recall over the web.

Selected smoking research remained ATBC, methylation/epigenetic, SNP, stigma and
air-pollution papers: at least two obvious background/different-question documents
(stigma and air pollution) remained selected. There is **no independently annotated
irrelevant-source count** for all six controls; direct-role counts must not be
reported as clinically measured precision. Source titles/designs, purposes, exact
judge input, exclusions and selection reasons are inspectable in the artifacts
and `slice3_results` output. This remaining ranking weakness was not hidden.

### Smoking and sunscreen interpretation

Smoking's NCI PDQ evidence summary and CDC fact sheet are direct/visible and have
exact frozen units despite lacking PMID/DOI. NCI's purpose can satisfy the design
gate; CDC's fact-sheet purpose cannot do so independently. Case 1's Supported
uses the **pre-existing provisional evaluation rule with one qualified assessment**,
not production acceptance or two independent verified judges. Its other validators
were unavailable. Case 2 had zero qualified assessments, despite improved coverage.

For sunscreen, PMID 21135266 is characterized by actual randomized sunscreen
assignment; PMID 29620003 is a meta-analysis. NCI Sunlight was retrieved/frozen as
broader public-health guidance, not an invasive-melanoma causal trial. It was
contextual and **not judge-visible** because two higher-ranked contextual documents
filled the quota. Do not claim the authoritative sunscreen channel already has
optimal judge-visible coverage. No contradiction label was forced.

WHO Hypertension reached the judge as a direct fact sheet, not a causal-design
shortcut. NCCIH's date stayed unknown; its Vitamin C material was retrieved but
not selected, despite the relevant synthesis metadata. Carrots had no approved
manifest source; one PubMed source (10484191) with unknown relationship design
reached judges. Two NEI assessments qualified; this does not adjudicate the claim.

The repaired analysis IDs, in case order, are:

```text
91fca7fe-8e0c-44f6-8b29-400cf4b9dd17
31a9a932-26cc-422d-a105-744932fed74c
07081825-1647-42b4-807b-8b54a400be46
896e13fe-9585-4015-ad46-0166e733d125
ec6da8ed-bd46-4de3-8bbc-74fb3689b78e
eed5061b-1b9c-47b6-b144-6688eaf54df7
```

These evaluation rows use one-hour retention. Captures are ignored development
artifacts, not permanent public reports; reproduction refuses expired originals.

### Qualification, latency and usage

- Qualified rate: **33.3% → 16.7%** (6/18 → 3/18), not an improvement.
- Non-operational-label coverage: 1/6 → 2/6, with one provisional decisive result.
  Higher coverage is not demonstrated higher accuracy. Production coverage stayed zero.
- Mean judge-to-report stage latency: 70.155 → 76.408 seconds (**+8.9%**).
- Model HTTP calls: 193 → 227 (**+17.6%**).
- Provider-reported input tokens: 627,428 → 1,087,461 (**+73.3%**).
- Provider-reported output tokens: 67,310 → 69,702 (**+3.6%**).
- Repaired source-fetch times per case: 2.354, 1.619, 0.268, 0.382, 1.614, 0.018 seconds.
  These reuse frozen PubMed and measure approved-channel work, not a fresh full
  PubMed network latency comparison. Dollar costs are unknown: no verified billing
  rates were available. Tokens include judges, validators and revisions, not only
  three initial judge completions.

## 6. Separately measured semantic false acceptance/rejection

Relation prompt 1.3 was tested on the existing 32 frozen conditional controls per
configured model: 96 physical calls / 120 maximum, 78.872 seconds / 360 maximum,
120,483 input and 20,249 output tokens. No stability repetitions were requested.

Artifact: `runtime/debug/slice2-relations-20261001T173249389024.json`.
The retained tool filename says Slice 2, but its metadata records the new prompt.
These are **engineer-annotated conditional controls**, not independently reviewed
clinical cases or a full authoritative-source qualification benchmark.

| Model | Usable / 32 | Relation agreement | False support | False contradiction | Over-abstention | Schema failures |
|---|---:|---:|---|---|---|---:|
| Ling | 28 | 27/32 (84.4%) | 0/25 | 1/26 | 0/13 | 4 |
| GPT Luna | 32 | 30/32 (93.8%) | 0/25 | 0/26 | 1/13 | 0 |
| Gemini Flash Lite | 32 | 31/32 (96.9%) | 1/25 | 0/26 | 0/13 | 0 |

Prior Slice 2 relation agreements on the same control definitions were 29/32,
29/32, 31/32. False support was 0/25, 1/25, 1/25; false contradiction 1/26,
0/26, 0/26; over-abstention 0/13, 2/13, 0/13. Repeated live outputs/prompt versions
vary; these are observations, not statistically established improvements.

Read-only replay of those model outputs through the **legacy conditional qualifier**
is separate from the modern source-aware design policy:
`runtime/debug/slice2-qualification-20261001T173837954798.json`.

| Model | False qualified proposals | False decisive qualified | False rejected proposals |
|---|---|---|---|
| Ling | 2/64 | 1/52 | 6/32 |
| GPT Luna | 1/64 | 0/52 | 1/32 |
| Gemini | 1/64 | 0/52 | 1/32 |

Earlier Slice 2 false-decisive counts were 1/52, 2/52, 1/52 and false-rejected
counts 4/32, 4/32, 2/32 respectively. Do not extrapolate these proposal-level
conditional errors to real medical verdict accuracy. Synthetic new-policy fixtures
pass, but no independent clinical false-acceptance rate has been established.

## 7. Remaining failures and V3 decision

An exact observed `NUMERIC_UNCERTAIN` cause is the CDC passage paraphrase using
natural-language ratios/multiples: “9 out of 10” and “25 times”. The parser reported
`unclassified_asserted_numeral`, with no typed candidates for 9/10/25. The finding
was conclusion-required, so the uncertainty remained material. This is **not**
lack of sources, wrong frozen provenance, or a medically disproven smoking claim.
The parser/gate was not weakened in this slice. Future typed arithmetic support
needs positive and adversarial fixtures, not blanket suppression of uncertainty.

Other residuals: unavailable numeric/semantic validators; material source attribution
and conclusion-qualification defects; scope/materiality errors; background papers
still ranking as direct; missing authoritative update dates and contextual slot
competition. Ling had four malformed relation responses on the controls; it falsely
contradicted an explicitly unknown causal relationship. Gemini falsely supported
a numeric overclaim (RR 0.85 is not an 85% reduction); the deterministic replay
blocked that decisive conclusion. GPT over-abstained on a compatible numeric control.

**V3 is not justified as the next automatic repair by these measurements.** The
current source-unit/Slice 2 protocol can complete all six analyses. Better coverage
alone did not resolve numeric typing, relevance and semantic-classification errors;
a rewrite would not itself prove those fixed. Prioritize separately scoped ratio/
multiple parsing, reviewed relevance annotations/context selection, and repeated
semantic/provider qualification. A V3 experiment can remain a future hypothesis,
not implemented or declared clinically validated here.

## 8. Files and exact reproduction

New task files:

- `backend/app/adapters/authoritative.py`
- `backend/app/retrieval/{authoritative_manifest.json,analysis_design.py,evidence_roles.py,sufficiency.py}`
- `backend/app/validation/{slice3_eval.py,slice3_replay.py,slice3_results.py}`
- `backend/alembic/versions/20261001_0018_exact_source_headings.py`
- `backend/tests/{test_reliability_slice3.py,test_reliability_slice3_db.py}`
- `docs/RELIABILITY_SLICE3_RESULTS.md`

Changes connect the adapter/config/dependencies to retrieval, preview, orchestration
and smoke; extend retrieval/Pack/judge/qualification/verdict/report metadata and
hashing; add PubMed diagnostics; update evidence cards/types/tests and test isolation;
add `.env.example` options; update PROJECT_CONTEXT, TODO, ARCHITECTURE, API_SPEC,
DATABASE and append ADR-039 to DECISIONS. Numerous other dirty files predated this
slice; `git status` is not a list of changes authored by this task.

Run from the repository in PowerShell. Database tests must not run concurrently
with live analysis workers processing claims:

```powershell
cd "C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth"
docker compose up -d postgres redis
docker compose build backend frontend
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps backend alembic check
docker compose run --rm --no-deps -e RUN_DB_TESTS=1 -v "${PWD}/backend/tests:/app/tests:ro" backend python -m pytest -q
docker compose run --rm --no-deps -v "${PWD}/backend/tests:/app/tests:ro" backend python -m ruff check .
docker compose run --rm --no-deps backend python -m mypy app
Push-Location frontend
npm test
npm run build
Pop-Location
git diff --check
docker compose up -d --no-deps backend frontend
Invoke-RestMethod http://localhost:8000/healthz
```

Read-only retained original export/trace (no model calls, fails after retention expiry):

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m app.validation.replay --database-url postgresql+psycopg://lens:lens@localhost:5432/lens --analysis b3219a2d-9504-4fd8-91e2-e5384a9d7ea4 --output ../runtime/debug
# Use the new capture path printed above, or the retained capture while unexpired:
.\.venv\Scripts\python.exe -m app.validation.slice3_replay ../runtime/debug/b3219a2d-9504-4fd8-91e2-e5384a9d7ea4-20261001T162718046915.json
.\.venv\Scripts\python.exe -X utf8 -m app.validation.slice3_results ../runtime/debug/slice3-coverage-20261001T172956009700.json
Pop-Location
```

Fresh bounded live paired comparison — **paid requests and new evaluation rows**:

```powershell
docker compose run --rm --no-deps -v "${PWD}/runtime:/app/evaluation/runtime" backend python -m app.validation.slice3_eval --run --limit 6 --max-calls 480 --deadline 2400 --variant-deadline 150 --runtime /app/evaluation/runtime
```

Combined-only replay of this task's pilot — allowed only while its original
one-hour rows are retained; thereafter run a fresh paired comparison above:

```powershell
docker compose run --rm --no-deps -v "${PWD}/runtime:/app/evaluation/runtime" backend python -m app.validation.slice3_eval --run --limit 6 --max-calls 300 --deadline 1200 --variant-deadline 150 --runtime /app/evaluation/runtime --pilot /app/evaluation/runtime/runtime/debug/slice3-coverage-20261001T171629539826.json
```

Bounded semantic control calls, then offline qualification replay:

```powershell
docker compose run --rm --no-deps -v "${PWD}/runtime:/app/evaluation/runtime" backend python -m app.validation.relation_eval --run --limit 32 --stability 0 --max-calls 120 --deadline 360 --runtime /app/evaluation/runtime --prompt-version claim-relation-1.3-2026-10-01
Push-Location backend
# Replace this path with the new artifact printed by the live command if repeating:
.\.venv\Scripts\python.exe -m app.validation.relation_qualification_eval ../runtime/debug/slice2-relations-20261001T173249389024.json
Pop-Location
```

**Stop boundary:** Slice 3 only. No ClinicalTrials.gov, whole-web retrieval,
V3 judge rewrite, automatic model change or production approval follows from this task.
