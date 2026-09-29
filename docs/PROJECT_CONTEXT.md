# Project Context

## Purpose

The Lens of Truth verifies individual, externally verifiable medical claims
from text, screenshots, URLs, articles, and AI-generated medical answers. It
does not judge an author, diagnose a person, prescribe treatment, or reduce
medical truth to a binary score.

The full primary design specification is retained as
[`the_lens_of_truth_implementation_report_EN.md`](the_lens_of_truth_implementation_report_EN.md).
This document is the concise implementation context for day-to-day development;
when a conflict appears, the full specification takes precedence until a
documented architecture decision resolves it.

The product pipeline is:

```text
Input → OCR/text extraction → atomic claims → entity linking → PICO
normalization → evidence retrieval → immutable Evidence Pack → independent
model evaluation → citation validation → disagreement analysis → risk-aware
verdict → human-readable report
```

The unit of evaluation is an atomic `Claim`. A post can therefore yield
multiple claims with different outcomes; an association must never be silently
treated as proof of causation.

## Architecture decisions

- The backend is pipeline-first. Models receive one fixed, logged Evidence Pack
  and cannot browse independently while judging a claim.
- Verdicts are limited to `supported`, `contradicted`,
  `not_enough_evidence`, and `unable_to_verify_reliably`.
- `unable_to_verify_reliably` means the claim or verification process is unreliable;
  `NOT_ENOUGH_EVIDENCE` means retrieval worked but cannot justify a conclusion.
- High-risk medical topics use a stricter abstention policy. Future phases must
  favor `NOT_ENOUGH_EVIDENCE` over a decisive result when thresholds are not met.
- Evidence is provenance-first: source identifiers are created by retrieval,
  not by a model. Store metadata and minimal permitted passages, not paywalled
  full text.
- External integrations belong behind adapters. No provider API calls are made
  in Phase 1.
- Health information is treated as sensitive. Raw uploads and URL HTML have
  short retention; logs must not contain full inputs, screenshots, or secrets.

## Technology stack

| Area | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, Pydantic v2, HTTPX |
| Persistence | SQLAlchemy 2, Alembic, PostgreSQL, pgvector |
| Cache | Redis |
| Frontend | Vanilla HTML, CSS, TypeScript, Vite |
| Testing | Pytest |
| Local runtime | Docker Compose |

## Current implementation status

Phase 1 foundation, Phase 2 intake, Phase 3A normalization, Phase 3B
terminology resolution, Phase 3C hardening, and Phase 4A/4B PubMed retrieval
and evidence-integrity metadata are implemented:

- FastAPI initialization, configuration, structured error boundary, request
  logging, health endpoint, and a typed analysis lifecycle contract.
- Database models, initial migration, and the Phase 2 screenshot-upload
  migration.
- Secure screenshot intake: decoded-image validation, byte/pixel limits,
  single-frame enforcement, metadata-safe PNG re-encoding, and private
  short-lived filesystem storage for local/container use.
- A local Tesseract adapter (English, Simplified Chinese, Traditional Chinese)
  with OCR confidence metadata; raw OCR text is never persisted.
- A development/test-only OCR preview endpoint that returns ephemeral redacted
  output for diagnostics; it is unavailable in staging and production.
- Position-preserving structured-PII masking before extraction and persisted
  redacted atomic claim spans.
- A `miri-api` claim-extraction adapter that requests ChatGPT Auto, validates
  returned JSON and source offsets locally, and fails closed if the configured
  gateway is unavailable. The generic structured-output adapter remains
  available for approved providers.
- Nullable PICO fields are extracted with each claim and redacted before
  persistence. They describe the submitted claim, not supporting evidence.
- Phase 3A grounds those model-produced fields in each exact redacted atomic
  span, preserves the original claim in a validated PICO object, and persists
  explicit `pending`, `unresolved`, `pico_only`, `partially_linked`, or
  `normalized` status. Unstated PICO fields are discarded.
- MeSH descriptors and entry terms are imported from NLM's official annual XML
  into a read-only local SQLite index. Matching records exact preferred names,
  synonyms, optional tree numbers, source and release. Ambiguous or fuzzy/weak
  suggestions remain unassigned, with at most three candidates. The official
  file SHA-256 and import metadata are retained in the index.
- UMLS remains a separate optional provider. Without licensed data there is no
  CUI; a confident MeSH assignment is preserved independently. If the MeSH
  index is not installed, mentions remain unresolved instead of receiving
  fabricated identifiers.
- A dry-run-by-default batch command re-normalizes only untouched `pending`
  claims from stored, source-grounded PICO fields. It never calls an LLM and
  skips any claim carrying existing mapping or PICO JSON.
- New claims use a controlled ten-label claim taxonomy. Explicit English
  `causes` versus `is associated with` / `linked to` wording overrides a
  conflicting model label. Known old labels are mapped to a canonical label;
  unsupported model labels fail schema validation. Claim type describes the
  assertion, not whether it is true.
- A deterministic completeness audit compares high-confidence exact/official
  synonym MeSH mentions in the atomic source span with grounded PICO slots and
  entity mentions. Required intervention/outcome slots are checked for causal,
  association, prevention, treatment, diagnostic, and safety claims. Fuzzy
  suggestions do not trigger omissions. `normalization_quality` stores lexical
  coverage, missing concepts/slots, ambiguity, and warnings. `normalized` now
  requires those checks to pass and all identified mentions to be linked;
  `partial` exposes a detected omission or incomplete source scan. Prior
  `normalized` rows are marked `partial` until separately re-audited.
- Extractors retry at most once on malformed output or retryable provider
  failures, using the same redacted source and a strict-JSON repair instruction
  without replaying the invalid answer. They retain strict JSON/Pydantic and
  offset checks. Each request has a 55-second attempt limit and a 115-second
  total deadline by default. Exhausted attempt timeouts and total deadlines
  return typed 504 failures without claims; empty replies remain retryable once.
  Diagnostics record provider/model, attempt number, failure class, elapsed
  time, whether a retry occurred, and a sanitized upstream request ID when
  supplied. Logs do not contain source text or credentials.
- The extraction adapter now validates exact source offsets inside that same
  one-retry budget. A first valid response with an omitted exposure/outcome in
  an explicit relation receives one source-grounded repair request; an omission
  still present afterward remains `partial`, never a fabricated slot. A narrow
  coordinated-clause rule can carry the verbatim shared subject into the next
  atomic PICO only when source offsets and adjacent `, and` syntax verify it.
  The original atomic span and coreference flag remain auditable.
- Complete PICO with only partial MeSH linking can proceed through lexical
  retrieval and judging as `partially_linked`; missing PICO/source concepts
  (`partial`) still stop. Unresolved terms keep null MeSH/UMLS identifiers.
  This does not relax judge, citation, or production qualification gates.
  On 2026-09-28 the exact soy sentence passed a PostgreSQL-backed offline
  full-chain regression with synthetic evidence (two completed claims). Two
  configured live `chatgpt-auto` previews returned typed attempt-timeout 504s;
  live provider acceptance remains open and is not represented as passed.
- A later frontend run failed before extraction with two immediate Miri HTTP
  provider errors. A direct, minimal configured chat probe returned HTTP 429
  even though `/models` listed `chatgpt-auto`. The adapter now records the safe
  HTTP status, respects a bounded `Retry-After`, and returns a distinct
  `claim_extractor_rate_limited` failure if a 429 exhausts the budget. The web
  page distinguishes provider unavailability/rate limiting from a medical
  verification result. No automatic model substitution is performed.
- A Phase 7B web flow for text or screenshot submission, polling, independent
  claim progress, and frozen LensReport display. It uses plain TypeScript DOM
  modules and Vite; React was removed because its original screen was only a
  Phase 2 shell and no framework is needed for this bounded MVP.
- Docker Compose services for API, web, PostgreSQL/pgvector, and Redis.
- GitHub Actions checks for API tests/static analysis and frontend typecheck,
  DOM tests, and production build.
- Phase 4A creates a deterministic, bounded PubMed QueryPlan from claim PICO,
  source wording, and confident MeSH links. Broad, lexical, relation-specific,
  and distinctive numeric variants retain their input-field provenance and
  causal/association distinction.
- The official NCBI ESearch/EFetch adapter fetches typed PubMed documents via
  HTTPX with tool/contact identification, bounded timeout/retry/throttling,
  optional API key, and best-effort hourly Redis search-result caching. It
  never scrapes HTML or sends secrets to diagnostics.
- PubMed titles and abstracts yield exact, source-labeled passages. Ranking is
  deterministic lexical relevance with exposed factors, **not** evidence
  quality, confidence, or probability of medical truth. Phase 4A.1 keeps every
  ranked passage in the append-only Evidence Pack (version 1.1), but separately
  records ordered `selected_evidence_ids` for future judges. The default is
  eight selected passages and at most one per document, configurable through
  `PUBMED_SELECTED_EVIDENCE_LIMIT` and `PUBMED_MAX_PASSAGES_PER_DOCUMENT`.
  Relevant abstracts are preferred to title-only passages. Exposure/outcome
  coverage and a conservative generic-background penalty are visible factors;
  this is still topical ranking, not a causal or evidence-quality assessment.
  E IDs, source/query provenance, selection, and the canonical hash are frozen
  together. Historical version 1.0 packs remain readable, but have no selected
  set and must not silently be treated as judge-ready.
- A development/test-only evidence preview retrieves for one *stored* claim,
  persists the run and pack, and returns no verdict. Live CLI smoke requires
  a real `NCBI_EMAIL`; it can use an existing claim ID or explicit
  source-grounded PICO fields without persisting a test-only claim.
- The Phase 4A.1 live sunscreen/melanoma smoke used a temporary contact email
  at runtime and returned 18 documents, 42 auditable passages, and five
  distinct PMIDs in the selected top five. One PMID is a PubMed book record
  outside the article-only normalizer, so the status remains
  `partial_metadata`; no medical conclusion was produced.
- Phase 4B parses PubMed publication types and correction/retraction links,
  then optionally enriches DOI-bearing documents through the official Crossref
  REST API under a bounded 30-second total enrichment budget. Every check has
  its own status and version. `valid` means no
  integrity signal was found after all applicable checks completed; failed or
  unavailable checks make an otherwise signal-free record `unknown`.
  Retractions from either provider take precedence and remain in the audit
  snapshot but are excluded from selected evidence by default.
- Evidence Pack version 1.2 freezes integrity references/provenance, Crossref
  bibliographic enrichment, deterministic study design, quality prior/factors,
  applicability warnings, and selection. The quality prior is a transparent
  methodological heuristic, not a truth probability; topical retrieval scores
  stay separate. Phase 4B.1 adds directness to selection as described below.
- Diagnostics now count optional DOI/abstract/date gaps separately from missing
  or incomplete EFetch records, unsupported PubMed book records, and
  Crossref/check unavailability. Optional
  omissions alone do not make PubMed retrieval `partial_metadata`.
- The Phase 4B sunscreen/melanoma live smoke returned 18 normalized articles,
  16 DOI-bearing records with successful Crossref checks, two DOI-less records,
  and 42 auditable passages. All 18 had no detected integrity signal after
  their applicable checks; this is not an assessment of claim truth. The one
  unnormalized PMID was a `PubmedBookArticle`, not a missing EFetch response.
- Phase 4B.1 adds deterministic, claim-specific `relationship_directness` to
  each document and passage in Evidence Pack 1.3. The score measures whether
  source text addresses the PICO exposure/outcome relationship, **not** whether
  the paper supports, contradicts, or proves the claim. Direction is `aligned`,
  `reverse`, `incidental`, or `unknown`, with reasons and numeric factors.
  Exact source-grounded PICO wording and confident MeSH labels provide bounded
  aliases; structured RESULTS/CONCLUSIONS carry more weight than BACKGROUND.
  Post-outcome management, background-only mentions, explicit exposure
  exclusion, never-smoker populations, screening/cessation-only framing, and
  adjustment-covariate mentions are conservatively demoted, never deleted.
  Selection uses an exposed priority of 30% topical retrieval, 45% passage
  directness, 20% document directness, 5% methodology prior, minus an explicit
  applicability penalty. Retractions remain ineligible; one passage per PMID
  remains the default. No medical verdict or model judging is produced.
- Four live Phase 4B.1 smoke claims found 18 sunscreen, 23 Vitamin C, 23
  hypertension/stroke, and 29 smoking/lung-cancer articles in the configured
  backend run. The selected leaders are direct question matches; the observed
  zinc review, post-stroke BP papers, screening/cessation paper, and
  never-smoker cohorts are retained but demoted. PubMed results and enrichment
  status can change over time; these counts are an observed check, not a gate.
- Phase 5A judges one persisted, hash-verified Evidence Pack 1.3 without
  retrieval calls. A canonical prompt contains the exact atomic claim,
  controlled type, PICO/terminology framing, and only ordered
  `selected_evidence_ids` with their frozen passages and document metadata.
  The same prompt/hash is sent concurrently to up to three explicitly
  configured provider/model/model-family slots. Distinct families are required
  unless a development/test-only override is set; a gateway alias is not
  evidence of independent underlying families.
- A judge can return only `supported`, `contradicted`, or
  `not_enough_evidence`; the typed schema requires short reasoning, cited and
  opposing selected E IDs, assessed claim strength, sufficiency, and controlled
  uncertainty reasons. Unsupported labels, malformed JSON, unknown/duplicate
  citations, and missing fields fail closed. Association alone cannot justify
  a causal claim in the versioned canonical instructions. This is model
  judgment, not validated citation entailment or a final Lens verdict.
- Per-slot requests use 45-second attempt and 80-second total defaults, one
  retry, bounded parallelism, and a process-local circuit breaker. Failed slots
  do not suppress successful peers. An append-only `judge_run` row stores the
  pack ID/hash, prompt version/hash, provider/model/family, timestamps,
  latency/attempts, canonical validated response, token usage when available,
  and a typed failure category. Descriptive label counts/agreement never vote
  or produce a final verdict. The CLI is development/test-only.
- Judge prompt `judge-1.6-2026-09-29` asks for the smallest set of passages
  that directly justifies each cited use; generic background, indirect
  estimates, and title-only overlap are not cited merely for topicality.
  Citation validation remains unchanged: an unsupported extra citation still
  excludes a decisive assessment. If a provider omits only the fixed
  `schema_version` key, the adapter may supply `1.0` after strict validation
  of every other field and citation. The append-only judge row explicitly
  records `schema_version_inferred=true`. Such a run is evaluation-only and
  cannot qualify for a production verdict. Missing medical fields, invalid
  labels, and unknown citations are never repaired.
  An invalid E-ID or unlisted E mention may trigger the existing one retry;
  only a fully valid new response can succeed.
  For a single exposure-outcome relationship, the prompt asks for one directly
  sufficient passage when available, not auxiliary mechanism/progression or
  risk-context citations. This affects citation selection, not what source
  material the judge may consider or the validation policy.
  A fresh development replay on the original smoking/lung-cancer Pack 1.3
  produced three structured judgments. Independent one-passage validation
  qualified Ling (E18/E4) and GPT Luna (E4), but marked Gemini's extra E7
  citation insufficient, leaving that judge partially validated. The new
  evaluation-only aggregation therefore had 2 qualified judges and returned
  `supported` with `production_qualified=false`. Ling's fixed protocol key
  was inferred and explicitly audited. This is a plumbing/regression result,
  not a trusted medical report or a change to the original analysis.
  A separate full API run (`5c131a68-3bb7-4db8-b018-a29b391ef281`)
  completed extraction through report generation and returned the same
  evaluation-only result: two qualified assessments, one excluded for partial
  citation validation, and two frozen evidence excerpts. Its development
  notice remains visible; production qualification is false.
- A search-enabled gateway model mode remains blocked by default and is always
  blocked in staging/production. `JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT=true`
  permits a development/test plumbing smoke only. The canonical prompt still
  forbids browsing/search/outside sources, and the adapter supplies no tools,
  but provider-native search isolation cannot be verified through Miri.
  Every run in that ensemble stores `search_override_active=true` and
  `search_isolation_verified=false`; search-mode slots also store
  `search_guard_bypassed=true`, including failed runs. The CLI warns before
  sending requests. These results are not verified same-evidence evaluations.
- The 2026-09-28 development Miri smoke reused frozen sunscreen Evidence Pack
  `156f0f74-55e2-40ef-8910-503a1e008c2d` and judge prompt
  `judge-1.3-2026-09-27`. The configured OpenAI/ChatGPT and Qwen slots each
  returned one schema-valid judgment; the Google/Gemini slot returned
  `malformed_json` on both attempts. All three append-only runs were persisted.
  The two successful slots both labeled the claim `contradicted`, but agreement
  describes only those two responses, not a three-judge result or medical truth.
  Search-guard bypass was recorded and isolation remained unverified. This
  plumbing result is sufficient to begin Phase 6 implementation using frozen
  packs and offline validated fixtures, not to enable a live final verdict.
- Phase 6A validates each successful judge decision separately against its
  exact frozen Pack 1.3. It rechecks pack/passage hashes, selected E IDs,
  document provenance, frozen integrity, material numbers, explicit PICO/scope,
  and causal-vs-association strength before optional one-passage entailment.
  Cited and opposing passages have separate typed records. Association-only
  evidence is fatal to a decisive causal use but may correctly explain a
  `not_enough_evidence` decision. A numeric difference that forms the basis
  of contradiction is not automatically a judge error; a number misstated in
  the judge's own reasoning is.
- Entailment has a strict provider-independent, one-passage interface with
  source text confined to untrusted data. Phase 6A uses offline deterministic
  fixtures, not an approved live semantic provider. Without one, the CLI
  reports `unable_to_validate` unless a deterministic fatal defect exists.
  Later development/test orchestration can cross-check a cited passage with a
  different configured model family through a no-tools entailment adapter.
  This is an unapproved evaluation aid, not production certification.
  Each execution inserts a new `judge_validation_run` with version/prompt
  provenance, timing, results, and typed failure category. A database trigger
  rejects updates; claim-retention cascades still apply. No final aggregation,
  verdict, report, or public Phase 6A endpoint is implemented.
- Phase 6B adds an internal deterministic `verdict-policy-1.1` aggregator over
  explicit claim, Pack ID/hash, judge-run IDs, and validation-run IDs. It
  recomputes Pack 1.3's semantic hash, checks normalization/retrieval/selection
  and every audit linkage, then excludes failed, invalid, partial, or
  unavailable judge validations from decisive counts. In evaluation mode
  only, an inconclusive assessment may qualify with partial scope if every
  cited use is semantically entailed and no other material warning is present.
  Partial validation never qualifies a decisive label or production result.
  Two fully validated,
  independent judges can support a standard-risk decisive label only with no
  validated opposite label; high-risk claims require three unanimous fully
  validated decisions. Validated disagreement, weaker/indirect evidence, or
  successful retrieval with no results yields `not_enough_evidence`. Technical
  failure or too few qualified judges yields `unable_to_verify_reliably`.
- Production qualification requires verified model identity/snapshot and
  family, verified search isolation without a bypass, and a policy-approved
  entailment provider. These audit fields default false and Phase 6B approves
  no live entailment provider, so current Miri rows and all current live
  Phase 6A runs cannot become production-qualified decisive verdicts. An
  offline `fixture_or_evaluation` mode can exercise the decision table but
  always marks its output non-production. Each execution adds an immutable
  `verdict_run` with typed reasons, explicit IDs, and a semantic result hash.
  No model chooses the final label, no numeric truth confidence is emitted,
  and no public verdict API or frontend display exists yet.
- Phase 6C converts one explicitly named, persisted VerdictRun into an
  internal, typed `LensReport`. A pure builder reads only that run's frozen
  Evidence Pack and named judge/validation audits; it never re-aggregates the
  verdict, calls a model, fetches new evidence, or selects latest rows.
  Controlled templates translate reason codes and four display labels.
  Source cards quote bounded exact selected passages only when qualified,
  validated decisions cited them (including evaluation-only, checked
  partial-scope inconclusive use); PMID, DOI, title, date, design,
  integrity, URL, citation role, and audit IDs come from frozen provenance.
  Numeric, causal-strength, material-scope, and integrity failures are
  surfaced as limitations, not new medical conclusions. Operational inability
  shows no evidence cards. Every report carries a separate health-information
  safety notice and an unhideable development/evaluation marker when
  `production_qualified=false`; current Miri-like runs remain non-production.
  A semantic hash excludes only report-generation time, and each execution
  inserts a new PostgreSQL update-protected `report_run`. The CLI is
  development/test-only; there is no public report API or frontend exposure.
- Phase 7A adds durable `analysis_run` and per-claim `claim_analysis_run`
  checkpoints. `POST /v1/analyses` now returns HTTP 202 with an opaque run ID
  before any slow provider call; the existing sanitized screenshot/OCR and
  redacted extraction service runs in a single-process FastAPI background
  task. After extraction, each atomic claim gets its own frozen Evidence Pack,
  JudgeRuns, JudgeValidationRuns, VerdictRun, and ReportRun. The orchestrator
  calls existing stage services and stores their exact IDs; it performs no
  medical reasoning and never selects a "latest" audit row.
- Polling `GET /v1/analyses/{id}` exposes stage, completed stages, per-stage
  times, claim count, completed claims, and safe failure code. `GET .../claims`
  gives claim-scoped status and artifact IDs. `GET .../claims/{claim_id}/report`
  serves the already-persisted LensReport after verifying its hash and
  explicit provenance; it never retrieves sources. Staging/production return
  403 for non-production-qualified reports. Development/test inspection retains
  the mandatory evaluation notice and now uses `fixture_or_evaluation` mode
  rather than falsely applying production-only identity gates. Current gateways
  and absent approved live entailment mean reports remain non-production.
- `Idempotency-Key` is now supported: a bounded opaque key is hashed and
  uniquely reserved with a canonical request digest. A repeated identical
  POST returns the same run without rescheduling work; key reuse for another
  request returns 409. Without a key, each POST intentionally creates a new
  run. A restart marks queued/running work failed without replaying model
  requests. A failed run can be inspected but is not automatically resumed.
  This intentionally favors duplicate prevention over seamless recovery in
  the MVP; stage artifacts can be inspected by their frozen IDs.
- Extraction is limited by its existing deadline; Phase 7A adds configurable
  retrieval (180s), per-claim (300s), and whole-analysis (900s) ceilings.
  A failure in one claim leaves completed peers intact; technical failure is
  never relabeled Not Enough Evidence. A genuine successful empty Evidence
  Pack follows the existing Not Enough Evidence policy. The SSE route emits
  a safe one-shot progress snapshot; clients poll for ongoing work. The
  Phase 7B replaces the earlier React-only extraction screen with a real
  claim-scoped web client. It polls the Phase 7A endpoints rather than treating
  the one-shot SSE snapshot as a stream. Browser refresh resumes a known
  analysis ID without creating a new run. Every completed claim fetches its
  checkpointed report once; failed claims remain separate. Development
  reports visibly retain the backend's evaluation notice, while a 403 release
  gate is displayed as an access/qualification issue, never as a medical label.
  The UI creates no medical conclusions and uses text-only DOM insertion for
  submitted claims and evidence excerpts. Anonymous access and the in-process
  backend worker still require public-deployment review.
- The `APP_ENV=test` developer smoke uses only conspicuously synthetic
  extraction, evidence, and validation fixtures. It exercises the full
  persistence chain without PubMed, Crossref, Miri, or invented live medical
  conclusions. Supported and Unable fixtures are explicitly evaluation-only.

Licensed UMLS source integration, non-PubMed evidence retrieval, hybrid/vector
search, approved live citation entailment, calibration, and public verdicts are
not implemented. Integrity checks are not exhaustive: PubMed/Crossref metadata can
lag or omit events, and `valid` is not medical correctness or evidence quality.
MeSH linking and PICO framing are terminology operations, not medical truth
assessment. The 2026 MeSH index must be imported separately in each runtime;
the generated vocabulary is not committed to the repository.
Phase 4A is PubMed-only evidence retrieval; it does not judge claims.
Miri's browser-backed gateway does not guarantee a pinned underlying model or
disable all native search behavior. Phase 5A sends no tools and explicitly
forbids browsing, but production approval must verify provider-side controls.
A development smoke used three distinct configured family labels, but those
aliases are not independently verified or pinned and only two responses were
valid. No production-qualified three-family evaluation has been completed.
The subsequent soy regression hardened non-judge stages: adjacent coordinated
clauses can recover an explicitly written shared subject and omitted outcome;
generic `consumption` no longer links to MeSH `Economics`; retrieval falls back
to soy-based lexical terms and keeps explicit outcome qualifiers. Demographic
mentions inside an exposure phrase are not assigned the intervention role.
Clearly nonhuman or insufficiently focused papers remain auditable but are not selected
for judging. Two live soy PubMed smokes produced source-grounded selected
papers, but those retrieval heuristics are not medical verdicts. The exact
frontend input still needs a fresh end-to-end run when claim extraction is
available; earlier frozen runs are not rewritten.
On 2026-09-29, "High blood pressure causes cancer" retrieved relevant passages
and two judges returned `not_enough_evidence`. The original report still showed
`unable_to_verify_reliably`: no live entailment validator was configured, one
Ling response failed JSON/schema checks, and development used production
aggregation mode. New cross-family development validation, a clearer prompt
for inconclusive use, and evaluation-only partial-scope qualification yielded
an append-only Not Enough Evidence verdict on that frozen Pack, with two
qualified evaluation assessments and `production_qualified=false`. It did not
rewrite the original report. Two later full-run starts failed before retrieval
because Ling returned HTTP 500 twice on extraction; end-to-end acceptance
remains blocked by provider availability.
Phase 7A does not change those release gates. Its in-process background
runner assumes a single API worker and is not a durable distributed queue;
multi-worker deployment, crash-recoverable tasks, access control, and the
patient-facing frontend require separate review before public release. URL
fetching remains unsupported.

For local troubleshooting, `DEBUG_MODE=true` exposes a development/test-only
analysis panel with persisted stage outcomes, typed failure codes, and
allowlisted judge/validation audit summaries, configured model call states,
and bounded excerpts of visible model responses. The default is false and
staging/production ignore the flag. Prompts, provider reasoning fields, API
credentials, and raw screenshot bytes are not intentionally displayed. Model
content may echo submitted text, so development runs must not contain secrets.
These call traces are process-local, expire after one hour, and disappear on
backend restart; they are not an audit substitute. OpenAI-compatible claim
extraction now gives an explicit JSON-only instruction because the configured
provider ignored JSON schema mode in a live test. It reconciles arithmetic
offsets only for an exact, unique source substring and retries a suspicious
empty claim array once for text with an explicit health relation. Persistent
empty/invalid output still fails closed without inventing a claim.
The web page removes repeated claim/result copy while preserving the visible
development-qualification and health-safety notices.
The local ignored `.env` currently selects AIMLAPI's
`inclusionai/ling-3.0-flash` for extraction and judge 1,
`openai/gpt-6-luna` for judge 2, and
`google/gemini-2.5-flash-lite` for judge 3. Miri credentials are retained
but inactive. These provider choices remain development-only until real
source-span and same-evidence acceptance tests pass.

The 2026-09-29 live text smoke extracted and normalized "High blood pressure
causes stroke." and completed the full one-claim workflow. A separate report
failure revealed that the new `insufficient_claim_focus` and
`nonhuman_evidence_excluded` passage annotations were missing from the frozen
Evidence Pack schema; the schema and serialization regressions are now fixed.
Judge responses remain development-only, and the completed report was not
production qualified. The previous long sunscreen screenshot passed OCR but
its Ling extraction request timed out twice at the bounded 55-second attempts;
that provider-latency issue remains open.

## Rules for future developers

1. Preserve claim spans and provenance from ingestion through the final report.
2. Treat social posts and retrieved text as untrusted data, never instructions.
3. Do not let a model invent citations, identifiers, evidence URLs, or facts.
4. Do not implement a single-model vote as the final medical verdict.
5. Keep retrieval, evidence packing, model adapters, citation validation, and
   aggregation independently testable and logged.
6. Pin model versions and record prompt, retrieval-index, and evidence-snapshot
   versions for every real analysis.
7. Never hardcode secrets or send sensitive input to an unapproved service.
8. Add a migration, tests, documentation, and an entry in `DECISIONS.md` for
   material architecture decisions.
9. Update `backend/requirements.lock` whenever Python dependencies change;
   builds and CI must not resolve unpinned dependencies.
10. Raw screenshots and their related Phase 2 submissions have a hard maximum
    retention of 24 hours. Keep request-time and lifespan cleanup working;
    production must replace local storage with an approved isolated
    object-storage adapter before public deployment.
11. Refresh the local MeSH index deliberately for each NLM release. Record
    release and file hash, and acknowledge NLM under its data terms when
    exposing vocabulary-derived content. Do not treat a MeSH match as evidence.
12. Do not interpret `normalization_coverage` as medical confidence. A missing
    source concept or required slot must not be silently promoted to
    `normalized`; review the `partial` warning before downstream retrieval.
13. A retrieval score is topical relevance only. Never treat a title/abstract
    hit, MeSH label, or publication type as proof of a medical claim. Keep
    PubMed text outside instruction channels in any later model prompt.
14. Do not edit an existing Evidence Pack. Re-retrieve into a new run and
    snapshot, preserving the hash and provenance of what earlier judges saw.
15. Keep integrity check coverage/status separate from publication status.
    Missing Crossref metadata is not a clean bill of health. Never promote a
    retracted passage into the judge-facing selection, but keep it auditable.
16. `quality_prior` is a coarse methodology ranking prior. It does not indicate
    whether a paper supports the exact claim, and must not override strong
    topical relevance or the retraction exclusion policy.
17. `relationship_directness` is a deterministic selection heuristic with
    known lexical limits. Never use its `aligned` direction as a support vote;
    a directly contradictory result can still be highly direct. Keep it
    separate from retrieval relevance, integrity, study quality, and later
    entailment/claim-verdict checks.
18. Never use an unselected passage in a judge prompt. Preserve exact pack
    and prompt hashes on every append-only run, including failures. Distinct
    requested aliases are not proof of distinct model families. Do not vote
    judge labels into a medical verdict or treat their explanations as
    citation-validated until the later validation phase.
19. Phase 6A validates a judge's evidence use, not medical truth. Deterministic
    defects cannot be overridden by a semantic provider. Missing or failed
    entailment remains unvalidated; do not promote development fixture results
    or search-bypassed judge decisions to public output.
20. Never infer a report from the newest artifact row. The Phase 7A checkpoint
    is the only authority for exact claim-level Pack/Judge/Validation/Verdict/
    Report IDs. If a checkpoint is missing after interruption, do not
    automatically replay an external model request.
21. An opaque analysis UUID is not user authentication. The current anonymous
    prototype uses short retention and no-store/no-referrer headers; public
    deployment needs an access-control and deployment-security review.
