# Retrieval V2 results — 2026-10-19

Implemented and deployed locally. Retrieval/query-plan/Evidence Pack **2.0** adds
adaptive scholarly and official-source discovery. Existing medical positions,
independent judges, validation, quantity ownership, integrity requirements,
qualification thresholds and production gates remain. This is a development
evaluation, not clinical or production qualification.

**Original diagnosis.** Analysis `f0b25b24-8c5c-4095-b5fa-51e354ac4651` actually
stored: “Using your phone while laying down on your side, increases deterioration
of myopia.” Normalization retained the full exposure and the Myopia concept;
the exposure was unresolved terminology. Query-plan 1.6 turned its first six
words into mandatory abstract terms:

```text
"using" AND "your" AND "phone" AND "while" AND "laying" AND "down"
```

Every term was field-restricted. The six-token cutoff omitted “side”. All four
recorded PubMed queries returned total_count=0; the automatic variant retained
the same conversational wording. No relevant approved-manifest source was
configured for this topic. The frozen pack was empty, so judging and validation
were deliberately skipped. This was poor search recall, not an extractor or
judge transport failure. The old run completed in 6.56s without an evidence
assessment. Relevant smartphone/myopia research was already indexed in PubMed.

**Search and source contracts.** `retrieval/adaptive.py`, `retrieval/v2.py`,
`adapters/discovery.py` and `adapters/official_web.py` implement:

- Search-only grammar removal, confidently linked terminology labels and bounded
  vocabulary variants. Medical concepts remain atoms, including lettered vitamins;
  single-digit doses/durations are retained. Full exposure qualifiers remain in
  the original PICO and in conservative relevance checks.
- Specific exposure/outcome searches, a broader exposure-core fallback, endpoint
  stage searches (incidence/prevention versus progression), and design recall.
  Search expansion never rewrites the claim or infers its effect direction.
- Europe PMC and OpenAlex discovery in parallel with PubMed and official-source
  work. Supplementary leads enter clinical evidence only after canonical NCBI
  hydration and matching PMID/title plus DOI when supplied. Publication types,
  complete available passages, retraction signals and the existing Crossref
  integrity merge come from verified records. A discovery abstract/snippet is
  never substituted for canonical content.
- Canonical PMID deduplication before hydration and cross-provider provenance
  merging. Discovery queries are retained in hash-bound document metadata;
  lead-level verification/exclusions and provider timings remain in diagnostics.
  Different study versions are not merged merely because their topics match.
- Native NHS search and the documented NLM MedlinePlus health-topic API.
  Search results supply URLs only. Fetch exact allowlisted HTTPS origins;
  require matching canonical identity, a page title and substantive visible
  medical-body content. Reject redirects, noncanonical URLs, unapproved domains,
  unusable pages and oversized responses. One additional hop may follow an
  approved society/NIH reference published within verified official content.
- Newly discovered guidance is background-only with unknown clinical currency
  and integrity approval; it cannot become a decisive clinical source just
  because it is official. Existing reviewed-manifest assessments retain their
  existing source roles and qualification rules.
- Source classification is direct / related indirect / background guidance /
  irrelevant. “Direct” is a search-relevance classification, not medical support.
  Missing exposure, population, comparator, timeframe or endpoint details reduce
  relevance. Findings citing only indirect/background sources receive a
  deterministic context ceiling even if the validator supplies strong axes.
- All-provider technical failures yield an unavailable assessment. Successful
  bounded searches without usable sources remain distinguishable from a
  scientifically assessed inconclusive result. The read-only reading guide
  explains coverage, names missing PICO detail, separates source failures, and
  exposes research/guidance links without changing the saved verdict.

Bounds: at most five PubMed queries, two searches per scholarly discovery
provider, forty canonical publications, two official index searches and three
official page fetches (including the one-hop limit). The existing eight-source
selection and maximum two contextual documents remain. Crossref retains its
three-request concurrency and total deadline. Public query/metadata/page caches
retain six-hour bounds; existing Crossref freshness remains. No verdict cache
or query-planning model was introduced. PubMed search diagnostics are read
sequentially under the NCBI throttle, avoiding mutable-diagnostics races.

Document groups use document-evidence-2.0, a twelve-query round-robin union and
at most two distinct supplementary discovery questions; omitted coverage is
explicit. They retain the shared frozen catalog, source ownership and assertion
records. Earlier document-evidence 1.0/1.1 and Evidence Pack 1.0–1.5 remain
supported by their historical audit paths.

**Live results.** Original passage submitted through the actual browser form;
other cases used the same public `/v1/analyses` creation, polling and report APIs.
The final phone and smoking runs exercise the final official-discovery path.
The other retained results are full V2 runs preceding the last background-only
web-discovery refinement and targeted control repair. No labels were forced.

The legacy comparison reran retrieval only on the same normalized claims; it
made no judge/validator calls. Counts below describe source coverage, not counts
of proven findings. Legacy selected sources could include indirect material.

| Claim | Legacy documents / selected | V2 direct / indirect / guidance candidates | V2 selected | Qualified | Result |
|---|---:|---:|---:|---:|---|
| Phone use lying on one's side worsens myopia | 0 / 0 | 0 / 16 / 1 | 2 | 2/3 | Not Enough Evidence |
| Regular physical activity reduces developing type 2 diabetes risk | 37 / 8 | 9 / 25 / 2 | 8 | 3/3 | Not Enough Evidence |
| Magnetic bracelet cures arthritis | 30 / 8 | 0 / 14 / 0 | 2 | 3/3 | Not Enough Evidence |
| Smoking causes lung cancer | 43 / 8 | 22 / 11 / 3 | 8 | 3/3 | Supported |
| Daily sunscreen reduces invasive melanoma risk | 28 / 5 | 1 / 30 / 1 | 3 | 3/3 | Supported |

Exact selected counts and classifications are also retained in
`runtime/retrieval_v2/metrics.json`; irrelevant candidates remain frozen but are
not clinical evidence. The activity result is still a causal-design eligibility
limitation in the selected findings, not zero retrieval. Treatment/HbA1c findings
do not resolve disease prevention. No causal policy was changed to make it pass.

Final retained IDs:

- Phone: `cc3007b2-3c9c-40d8-af50-ea0bdf92d941`.
- Activity: `be1bd9d1-c38b-4664-a5b1-c5a95a90447a`.
- Bracelet: `9e7b3405-5d68-465d-8173-09810c6eae61`.
- Smoking: `9f01aa05-2b41-46e5-af29-5c2bca459ff8`.
- Sunscreen: `b2a0677e-5085-4e8f-baa0-b13b76c7e5c4`.

The phone result uses source-validated findings from PMID 32452059 and the
prospective cohort PMID 40361066. These concern phone use/myopia or progression;
they do not establish the side-lying exposure. MedlinePlus “Refractive Errors”
is labelled background guidance. NHS search timed out at its six-second bound
in the latest run; the discovered AAO page lacked verifiable title/canonical
content and was rejected. Neither failure became medical contradiction or
invalidated the independently verified research. One judge's assessment did
not qualify (`REQUIRED_FINDING_UNAVAILABLE`); the two qualified NEI assessments
satisfied the unchanged standard-risk quorum.

**Timing and usage.** Backend times use persisted start/finish timestamps, not
the later polling attachment time. Caches were partially warm from source-only
replays. These figures are not a cold-start speed benchmark.

| Case | Retrieval seconds | Complete analysis seconds | Model requests | Reported input / output tokens | Actual source HTTP requests |
|---|---:|---:|---:|---:|---:|
| Phone | 11.133 | 116.932 | 7 | 77,381 / 6,032 | 5 |
| Activity | 8.370 | 132.489 | 7 | 192,431 / 6,200 | 19 |
| Bracelet | 2.076 | 91.644 | 7 | 62,114 / 5,256 | 5 |
| Smoking | 7.366 | 118.204 | 7 | 169,695 / 6,450 | 8 |
| Sunscreen | 6.393 | 129.746 | 7 | 96,096 / 7,231 | 16 |

These five selected runs made 35 model requests and used 628,886 reported tokens.
There were no transport timeouts/retries. Transport success is separate from
semantic qualification. Instrumented uncached search/discovery operations
overlapped at peaks of two to three; DOI requests have their separate existing
concurrency bound. Single-claim judges on the same gateway and their validators
retain existing serialization. Model work dominates overall latency.

Across the complete investigation, including intermediate regression runs:
**12 full analyses, 84 model requests, 226 public-source HTTP requests within
those analyses, and at least 1,043,986 reported model tokens**. Fifteen early
validator calls lack token usage because the old adapter did not retain it;
usage instrumentation was added and later runs capture all seven requests.
Source-only probes and five legacy retrieval comparisons are additional public
requests, with no paid model calls. Detailed per-call timings, usage and frozen
artifacts are under ignored `runtime/retrieval_v2/`.

No paid retrieval vendor or additional retrieval/planning model was configured.
The public/anonymous discovery endpoints supplied no billed charge. Exact model
dollar spend is not available from the retained provider responses; no dollar
estimate or fabricated price is presented.

**Regressions found and corrected during implementation.** An early V2 classifier
downgraded reviewed authoritative assessments to background along with newly
discovered pages. A subsequent guard incorrectly treated the sibling/title
diversification code `direct_title_evidence_available` as a document-wide medical
scope mismatch. The smoking control exposed both. Current selection preserves
reviewed direct roles, applies medical exclusions to the representative source
unit, and excludes title-diversification reasons from medical scope. The last
fresh smoking run is Supported with all three qualified assessments. Intermediate
NEI reports remain unchanged in their own frozen history. No threshold or source
integrity requirement was weakened.

The general-search RSS experiment ignored domain restrictions in live probes.
All unapproved results were rejected; that route was removed. Final discovery
uses NHS/NLM indexes and a single allowlisted official-reference hop.

**Verification.** Full PostgreSQL-backed backend: **1,534 passed, 5 skipped**
(270.81s). The five skips are existing Windows-native OCR/Tesseract variants;
OCR was not changed. Frontend: **125 tests**, TypeScript/Vite build pass.
Ruff and mypy (204 source modules) pass. Twenty-four new retrieval regressions
cover scope and numeric qualifiers, medical atoms, endpoint stage, provider
failure/cache behavior, identity conflicts, duplicate hydration, hash binding,
old hashes, unapproved URLs/snippets, verified one-hop society discovery,
document catalogs and strong-validator indirect-evidence ceilings. The report-read
test now guards the new retrieval entry point and still rejects tampering.

Real Chrome desktop (1440×1000) and mobile (390×1000) screenshots inspected.
Evidence disclosure works with Enter; Tab focuses the actual source links with
a visible three-pixel outline. Mobile document width equals viewport width;
no empty headings or bullets. Source statuses have explicit text. No human
comprehension testing was performed.

- [Desktop evidence view](assets/retrieval-v2-20261019/phone-desktop.png)
- [Mobile view](assets/retrieval-v2-20261019/phone-mobile.png)
- Local result: <http://localhost:5173/analysis/cc3007b2-3c9c-40d8-af50-ea0bdf92d941>.

**Historical reconstruction.** The original f0b25b24 report still reads HTTP 200;
its pack hash remains
`86cad7142f1c9ae05431e240cf3e4babe8af248c5d0b1a254f02721b9841949f`.
The older 699edaa0 document had already passed its normal October 16 retention
deadline and is no longer served from the database. Its retained frozen export
passed the full offline audit in 152.161s with zero source/model HTTP calls;
its original 0 assessed / 5 unavailable / 4 background and stored report hash
remain unchanged. No expired record was restored or historical result rewritten.

**Versions and models.** Retrieval/query plan/Evidence Pack 2.0;
document-evidence-2.0; retrieval-coverage-2.0. Existing V2.5 judges, clinical
position 1.8, question policy 2.1, verdict policy 1.4, group input 1.2,
document validator 1.3 and report/reader contracts are retained. All models are
unchanged on Paratera: extraction/J1 DeepSeek-V4.1-Flash, J2 Qwen3.5-Plus,
J3 GLM-4.7, validator Qwen3.8-Flash with thinking disabled. Development/debug
remain enabled; production qualification remains unmet.

**Limits.** This is bounded discovery, not an exhaustive systematic review.
Non-PMID scholarly leads are recorded but not yet admitted as clinical evidence;
they require a separate reviewed content/integrity path. Official coverage is
limited to the explicit domain registry and extractable canonical pages. Blocked
or unidentifiable pages remain excluded. Terminology, relevance and source
selection remain conservative; evidence can still be medically insufficient
after successful retrieval. The activity case and one excluded phone assessment
are retained limitations, not silently changed labels.

Provider references: [Europe PMC API](https://europepmc.org/RestfulWebService),
[OpenAlex API](https://help.openalex.org/api/),
[NLM MedlinePlus service](https://medlineplus.gov/about/developers/webservices/).
