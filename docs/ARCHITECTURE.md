# Architecture

## Implemented boundary

The repository implements intake, normalization, PubMed retrieval with frozen
Evidence Pack 1.3, independent judging, per-judge evidence-use validation,
deterministic verdict aggregation, and evidence-cited report construction.
Phase 7A now sequences them and adds a claim-scoped, server-gated report read
API. Phase 7B consumes that API in a framework-free web client. No live
production-qualified report exists yet.

For screenshot input, the API accepts only decoded PNG/JPEG/WebP images under
server-set byte/pixel limits, rejects animation, and stores a metadata-stripped
PNG under an opaque key. Raw image bytes remain outside PostgreSQL. At most 24
hours later, request-time and lifespan cleanup remove raw upload objects and
the associated short-lived analysis record.

## Target system

```mermaid
flowchart LR
  User[Web / WeChat] --> API[FastAPI API]
  API --> Ingest[Ingestion and sanitation]
  Ingest --> NLP[OCR / atomic claim extraction / PICO]
  NLP --> Retrieval[Evidence retrieval adapters]
  Retrieval --> Pack[Immutable Evidence Pack]
  Pack --> Judges[Independent provider adapters]
  Judges --> Validate[Citation validation and aggregation]
  Validate --> Report[Risk-aware report]
  API --- PG[(PostgreSQL + pgvector)]
  API --- Redis[(Redis)]
```

## Repository layout

```text
backend/                 FastAPI application, schema, tests, migrations
frontend/                Vanilla HTML/CSS/TypeScript + Vite application
wechat-mini-program/     Native Mini Program screen placeholders
evaluation/               Benchmark fixtures and experiment records
infrastructure/           Deployment-oriented configuration and notes
scripts/                  Developer automation
docs/                     API, data, architecture, decisions, and roadmap
```

## Service boundaries

`backend/app/adapters/` is reserved for all outbound systems: PubMed/NCBI,
WHO/CDC curated sources, Crossref, OCR, object storage, Redis-backed rate
limits, and every model provider. Endpoint code must depend on an adapter
interface, never an SDK call scattered through routes or pipeline stages.

Phase 2 adapters are concrete but replaceable: `TesseractOcrAdapter` starts a
bounded local process with no shell interpolation, `LocalFilesystemUploadStorage`
stores only sanitized images for development/container use, and
`OpenAICompatibleClaimExtractor` calls a configured structured-output endpoint.
`MiriClaimExtractor` calls the gateway documented in `../ai api.md` using
`chatgpt-auto` by default. The gateway drives browser UIs and does not promise
strict JSON schema enforcement, so the adapter parses its text response as JSON
and the backend validates every source span locally.
The extractor receives redacted text between untrusted-data delimiters. Its
candidate spans are checked locally against the exact redacted source before
persistence. When no approved extractor is configured, the API fails closed.
Source-offset checking now occurs inside the adapter's one-retry deadline so a
first invalid offset can be repaired without permitting an unbounded third
call. An explicit relation with a missing PICO slot may use that same retry;
it remains partial if still omitted. A second atomic clause may inherit only
the verbatim shared subject of an adjacent, offset-verified `, and` clause;
other PICO values stay grounded in their own raw source span.
Phase 7B.1 makes the downstream invariant explicit: each new atomic
`normalized_text` must stand alone. A deterministic validator accepts a full
clause or reconstructs only a nearby, source-verified English `and`/`but` or
simple pronoun antecedent. Inherited offsets identify the exact source
subject; `raw_text` and clause offsets are never changed. Uncertain fragments
are marked `partial` and fail normal retrieval. The same source-checked
subject may populate PICO exposure and an explicitly named population.
The current model-produced PICO slots may be null and must be treated as query
framing candidates until entity and evidence validation are implemented. The
gateway's ChatGPT model picker is best-effort, so its requested mode is logged
without claiming an exact underlying model version.

Phase 3A checks every PICO value against its own redacted atomic claim before
storing it. Phase 3B adds a local read-only index generated from official NLM
MeSH descriptor XML. The index contains preferred labels, entry terms, tree
numbers, source hash, and production year; it is installed at runtime rather
than committed. Exact preferred and entry-term matches can resolve a MeSH ID.
Ambiguity and fuzzy/low-confidence suggestions remain unassigned. UMLS is a
separate optional provider, and no CUI is invented without licensed data.
Stored entity JSONB carries the terminology provenance; no schema migration is
needed. A batch command re-normalizes untouched pending claims only, with a
dry-run default. Future retrieval must distinguish coded concepts from
unresolved suggestions and never treat terminology matches as evidence.
Audited, source-complete `partially_linked` claims now follow the lexical PubMed
path without forcing a terminology match. Missing PICO or source concepts,
unsafe scan warnings, and legacy unaudited rows still fail the orchestration
and verdict gates. Verdict qualification still requires independent approved
judges, validated citations, and all other existing safety checks.

Phase 3C restricts new claim types to a controlled taxonomy and locks explicit
English causal/association wording to its source meaning. A deterministic
quality check compares strong source MeSH phrases with grounded PICO/entity
mentions and checks type-specific required slots. Missing concepts become
`partial`, not `normalized`; the JSONB quality record explains why. Legacy
`normalized` rows become `partial` until re-audited. The extractor makes at
most one retry for malformed output or transient provider failures, without
weakening response validation or passing an invalid answer back to the model.

Phase 4A has a separate `app/retrieval/` pipeline: a deterministic QueryPlan
produces bounded MeSH, lexical, relation, and optional numeric queries; an
`app/adapters/pubmed.py` adapter uses official ESearch/EFetch; normalization
retains PubMed metadata and exact title/abstract sections; deduplication merges
  query provenance; a deterministic lexical ranker assigns relevance-only scores
  to every passage. A separate selector chooses an ordered, document-diverse
  subset for future judges (default maximum one passage per PMID), preferring
  directly relevant abstracts over title-only passages. The version 1.1 Evidence
  Pack retains all passages, their E1/E2/... identifiers, selection IDs and
  factors, and a SHA-256 over canonical content excluding retrieval timestamps.
  The database stores an append-only retrieval run, query rows, document-query
  links, versioned document content, ranked passage metadata in the pack
  snapshot, and the complete frozen JSON snapshot. Public PubMed documents may
  be reused across runs, while each
pack remains a separate audit object until the associated short-lived claim
is purged under the existing retention policy. Redis caches ESearch PMID lists for six
hours by source, query, and implementation version; failures bypass cache.
Phase 4B adds a separate integrity/enrichment layer between PubMed fetch and
Evidence Pack construction. Structured PubMed publication types and
`CommentsCorrections` links are checked first. DOI-bearing records optionally
use `app/adapters/crossref.py` for bounded REST enrichment; a versioned DOI
cache in Redis is best-effort and has a short TTL to limit staleness. At most
three DOI lookups run concurrently, with a 30-second default total enrichment
deadline; unfinished checks fail open as `unknown`. PubMed
title, abstract, and date stay primary; Crossref work type, publisher, dates,
and update relations are stored separately with field provenance. Neither
provider overwrites the other. Positive retraction signals win, while a failed
applicable check prevents an otherwise clean document from becoming `valid`.
No DOI makes Crossref not applicable; missing DOI/abstract alone is not an
upstream retrieval failure. EFetch `PubmedBookArticle` records are recognized
as present but outside the article-only normalizer, rather than mislabeled as
missing fetch records.

The deterministic classifier uses PubMed publication types, then MeSH, then
conservative title wording, and otherwise returns `unknown`. A separate
`quality_prior` summarizes coarse methodological design, human-evidence and
integrity/applicability factors; it is not a truth or support score. Topical
`retrieval_score` remains unchanged and drives selection. Retracted papers
remain in the full audit set with `retracted_excluded` but are never selected.
Evidence Pack 1.2 hashes these semantics, references, check statuses, quality
factors, and selection; wall-clock check timestamps are frozen in the snapshot
but excluded from the semantic hash. A later metadata change creates a new
pack, never an in-place edit. The pack JSONB is the authoritative integrity
snapshot; the older `evidence_document.retraction_status` field is not a
current integrity verdict. No database migration is needed for Phase 4B.

Phase 4B.1 runs deterministic relationship analysis after topical ranking and
before selection/pack hashing. `app/retrieval/directness.py` uses exact PICO
phrases and confident MeSH labels (not fuzzy candidate expansion) to locate
exposure and outcome within passages, sentences, adjacent sentences, abstract
sections, and titles. It weights RESULTS/CONCLUSIONS more than BACKGROUND;
unstructured abstracts still use concept proximity and relation cues. A
document and each passage have separate `relationship_directness` objects:
`score` in `[0,1]`, `direction` (`aligned`, `reverse`, `incidental`, `unknown`),
numeric `factors`, `reasons`, and `warnings`. A title/abstract can indicate
post-outcome management, an explicitly excluded exposure or population,
screening/cessation instead of disease risk, or a concept used only as
background/covariate. Such records remain in the full audit set. Unknown
direction stays unknown, and a contrary finding can still be direct.

The default selection priority is the exposed sum `0.30 * retrieval_score +
0.45 * passage_directness + 0.20 * document_directness + 0.05 * quality_prior`,
minus an explicit applicability penalty. Factors are stored per passage;
methodological quality cannot overwhelm relationship fit. The best passage
per document is chosen before global top-k, with relevant abstract preference,
at most one per PMID by default, and a hard exclusion of retracted records.
`retrieval_score`, `quality_prior`, integrity, document directness, and
passage directness remain distinct. Evidence Pack 1.3 hashes directness,
priority, and selection alongside prior metadata; older snapshots are not
rewritten. The existing append-only JSONB pack stores the new fields, so no
database migration is needed. This stage does **not** infer evidence support,
contradiction, causation, or a medical verdict.

Phase 7B.1 adds a separate endpoint role test after relationship directness.
Document and passage `endpoint_directness` records score, factors, reasons,
and warnings. Explicit outcome/measurement wording in title, METHODS, and
RESULTS/CONCLUSIONS outweighs BACKGROUND or mechanistic mentions. Direct
negative findings score highly too. QueryPlan 1.1 adds bounded endpoint
precision variants for measured outcomes and optional explicit population,
while keeping broad lexical/MeSH queries for recall. Selection considers
topical relevance (22%), passage/document relationship fit (28%/12%),
passage/document endpoint fit (22%/11%), and quality prior (5%), with a
bounded endpoint-focused title bonus and explicit applicability/indirect-
endpoint/relationship-reversal penalties. The sum is divided by 1.16 so the
bonus cannot saturate multiple priorities at 1.0 and erase ordering. Generic
post-disease treatment, screening, progression, or mortality endpoints are
demoted for disease-risk claims, not deleted. It is not a truth score. A
sex-only mismatch is penalized through existing applicability metadata, not
discarded. If at least three quantitative-endpoint documents score at least
0.5, selected evidence omits documents below 0.35 endpoint directness; those
documents remain frozen and auditable. Pack 1.4
freezes these factors and selected IDs. Pack 1.3 retains its original hash
serialization and remains auditable; version compatibility changes no
judge, citation, verdict, or report decision rule.

Phase 5A adds `app/judging/` after the frozen pack, without changing retrieval.
It first validates Evidence Pack 1.3's semantic hash, claim identity, unique
selection, selected flags, document presence, and retraction exclusion. One
versioned system instruction plus one canonical JSON data prompt is built from
the claim snapshot and only selected E passages. Evidence text, titles, and
metadata stay in the untrusted data message. No provider tool is supplied.
`JudgeProvider` is a small outbound interface; the HTTPX OpenAI-shaped/Miri
adapter is one implementation. Explicit slots name provider, model, and actual
model family. Duplicate families fail configuration except for a deliberate
development/test override. Miri requested modes are best-effort; production
must verify underlying model identity and native browsing controls.
Search-mode names also fail configuration by default and in every staging or
production run. A separate `JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT` flag can
permit development/test plumbing calls only. The service rechecks this boundary
even for caller-constructed slots, and each affected run persists override,
bypass, and unverified-isolation flags. The versioned prompt explicitly forbids
browsing and search; no browsing tool is passed to the adapter. This is not a
guarantee that a browser-backed provider suppresses its own search behavior.

Judges run concurrently with a configurable semaphore, 45-second per-attempt
and 80-second per-slot total defaults, one retry, independent failure records,
and a process-local per-slot circuit breaker. The strict `JudgeDecision` has
only three evidence labels; it rejects unsupported labels, unknown or duplicate
E citations, and absent fields. The `judge_run` table stores one append-only
success or failure per invocation, keyed to the stored pack ID/hash and exact
prompt hash. The canonical validated decision is retained; failed raw model
text, secrets, and prompts are not logged. A PostgreSQL trigger forbids updates
to judge rows. Rows follow claim/pack retention
through foreign-key cascades. Agreement statistics are descriptive only. The
legacy `model_evaluation` and `final_verdict` tables remain unused by Phase 5A.

Phase 6A adds `app/validation/` after each successful judge run. It rehashes
the exact Pack 1.3 and each cited passage, checks selected E IDs and frozen
document provenance/integrity, then compares explicit numbers, PICO scope,
and relationship strength. Deterministic fatal defects cannot be overridden
by semantic entailment. Cited and opposing passages have separate records.
The optional `EvidenceEntailmentValidator` receives only one exact passage,
the atomic claim, judge label/short reasoning, and frozen metadata. Its
versioned system prompt treats source text as untrusted, forbids browsing and
outside knowledge, and requires a strict single-E-ID response. No live
provider is configured; offline fakes are acceptance fixtures.

Numeric alignment compares only typed comparable quantities: percent changes
and percentage points, RR/OR/HR, CI/p values, sample counts, safe mass/volume
doses, and same-unit durations. Unsupported or ambiguous conversions remain
`uncertain`; absent quantitative assertions are `not_applicable`. A material
mismatch is fatal for `supported` use or a judge-reasoning numeric assertion.
A contradiction may correctly cite a differing claim number. Scope checks
use stated PICO slots and frozen study metadata; explicit adult/child,
human/animal, prevention/treatment, comparator, outcome, and post-outcome
mismatches can be fatal to a decisive judge use. Missing scope is not invented.
For causal claims, association-only observational evidence is
`weaker_than_claim` and cannot validate a decisive causal label; the same
limitation can support a properly framed inconclusive judgment. These lexical
rules are conservative, not medical entailment.

Controlled fatal issue codes cover pack/citation identity, missing provenance,
retraction, material numeric/scope/relation mismatch, and evidence that
contradicts its claimed judge use. Unknown integrity, partial scope, uncertain
numeric/relation/entailment, low quality prior, and provider unavailability are
warnings. `validated` requires eligible citations and successful one-passage
entailment; material uncertainty in numbers, scope, or integrity yields
`partially_validated` even if the semantic provider says the use is entailed.
The provider's concise evidence claim, scope assessment, and reason are kept
in the citation audit record. Without an approved provider, the CLI reports
`unable_to_validate` unless a deterministic fatal issue makes it `invalid`.
`judge_validation_run` inserts a new row on every execution with versions,
prompt hash when applicable, timing, result JSON, and failure category. A
PostgreSQL update trigger protects this append-only audit; normal retention
cascades follow the underlying judge/pack. Phase 6A has no public endpoint,
final aggregation, medical verdict, or report. The legacy `final_verdict`
table remains unused.

Phase 6B adds a pure `app/verdict/` policy engine. `AggregationInput` names the
claim, Pack ID/hash, every judge and validation run ID, mode, and policy
version; no latest-row selection is permitted. The engine rehashes Pack 1.3,
checks claim normalization, retrieval status, selected evidence, and audit
identity before assessing any labels. Successful `no_results` produces
`not_enough_evidence`; retrieval/pack/normalization failure produces
`unable_to_verify_reliably`. One failed/invalid/partial/unavailable validation
never becomes a decisive vote or a vote for the opposite label.
In `fixture_or_evaluation` mode only, an inconclusive assessment with a
partial-scope warning may qualify when every cited use is semantically
validated, the only material limitation is that partial scope, and all frozen
provenance/integrity checks pass. It still cannot make a decisive claim.

`verdict-policy-1.1` requires two distinct, fully validated judges and no
validated opposite label for standard-risk supported/contradicted. High risk
requires three unanimous fully validated judges. Mixed validated decisive
labels, all inconclusive labels, or insufficiently decisive validated evidence
yield `not_enough_evidence`. Fewer qualified judges than the risk-specific
minimum is operational inability, not evidence insufficiency. This is a
decision table after qualification and evidence-use validation, not raw
majority voting. No numeric truth probability is calculated.

Production additionally requires audited underlying model identity/snapshot,
actual family verification, search isolation without any bypass, and a
policy-approved entailment provider. New identity/family audit booleans on
`judge_run` default false; current judge service never asserts them. No live
entailment provider is approved in policy 1.0. Thus the development Miri
smoke fails production qualification, while offline evaluation results carry
`production_qualified=false`. Each execution inserts a distinct, update-
protected `verdict_run` with explicit input IDs, policy/engine versions,
controlled reason codes, deterministic result JSON and semantic hash. The
legacy one-row `final_verdict` remains unused. Phase 6B does not itself
generate human-readable report text.

Phase 6C adds a pure `app/report/` builder downstream of the immutable
`verdict_run`. It loads one explicit VerdictRun ID and only the Pack, JudgeRun,
and JudgeValidationRun IDs recorded in that run. The persisted verdict label
and semantic hash are rechecked, not recomputed. The frozen Pack 1.3 hash is
rechecked before any excerpt is shown. Controlled versioned templates map all
reason codes to concise prose and preserve the four existing labels; no LLM,
outside source, truth-confidence score, or new medical interpretation is used.

Evidence cards are sourced only from selected Pack passages actually cited by
qualified, validated assessments; evaluation-only partial-scope inconclusive
uses can produce cards marked `relevant_but_insufficient`. Cards retain exact E ID, source
identifiers, document metadata, citation roles, validation-run IDs, and a
deterministic 600-character prefix of the frozen passage; full passages stay
in the Pack audit. Source excerpts are structurally distinct from Lens prose.
Retracted or unverified positive citations are never cards. An operational
`unable_to_verify_reliably` report shows reasons and no evidence cards; a
successful no-results `not_enough_evidence` report says only that the
configured search returned none, not that no research exists. Material
numeric, causal-strength, scope, and integrity validation flags become
controlled limitations. Excluded assessments and descriptive validated-label
counts remain visible without model-brand ranking or confidence percentages.

Every report has a separate health-information safety notice and a mandatory
development/evaluation notice when `production_qualified=false`. Report
provenance contains the explicit audit IDs, verdict and Pack hashes, versions,
and generation time. The report semantic hash covers all stable content and
excludes only generation time; each execution inserts a new append-only
`report_run` row with an UPDATE-blocking PostgreSQL trigger. Reports follow
the VerdictRun's claim-retention cascade. The Phase 6C CLI creates a report
from one explicit VerdictRun; Phase 7A can also create one during an analysis.

## Phase 7A orchestration boundary

`analysis_run` is a mutable orchestration record, not a medical artifact. It
stores an opaque ID, hashed Idempotency-Key and canonical request digest,
queued/running/completed/failed/partially_completed state, current stage,
completed stages, per-stage timestamps, short retention deadline, counts,
and a safe failure code. `claim_analysis_run` stores claim-scoped state and
the explicit Pack ID/hash, JudgeRun IDs, JudgeValidationRun IDs, VerdictRun
ID, and ReportRun ID. Only these checkpoints are mutable; frozen Evidence
Packs and later audit rows remain insert-only. The analysis UUID is also the
eventual Submission UUID, preserving the existing API link.

The HTTP start request reserves the run and returns 202. A FastAPI background
task uses a fresh database session and the existing Phase 2 ingestion service,
then iterates atomic claims independently:

```text
extracting (existing OCR / redaction / claim extraction / normalization)
  -> for each claim: normalization eligibility -> PubMed retrieval
  -> frozen Pack -> configured judges -> per-success validation
  -> verdict-policy-1.1 -> deterministic LensReport
```

The orchestrator contains sequencing and timeouts, not medical logic. A
non-`normalized` claim stops before retrieval; no Pack or report is invented.
Successful empty retrieval produces a frozen empty Pack and follows Not
Enough Evidence policy. Judge/provider/validation qualification failures can
produce an audited Unable to Verify Reliably report. Unrecoverable retrieval,
pack, or persistence failure leaves that claim failed with no fabricated
downstream artifact; peers may complete and the parent becomes
`partially_completed`.

A repeated identical Idempotency-Key returns the same run and never schedules
another worker; no-key requests intentionally create new runs. No automatic
stage retry or startup replay exists. On startup in the current **single API
worker** deployment, queued/running rows are marked `worker_interrupted`;
their checkpointed artifact IDs remain available. A crash in the narrow gap
between an immutable artifact insert and its checkpoint may leave an orphaned
immutable run. It is not guessed via latest-row lookup or automatically
replayed; explicit operator recovery/transactional checkpointing belongs to
a later queue-backed design. Raw text remains only in task memory during
processing, not persisted for crash replay.

`GET /v1/analyses/{id}` is the polling source of truth. The existing events
route emits one SSE-format progress snapshot, not a long-lived event bus.
`GET .../claims` exposes per-claim artifact IDs; the report route loads only
its checkpointed ReportRun, verifies semantic hash, Pack/claim/verdict IDs,
qualification, and explicit audit IDs, and never retrieves new sources.
Staging/production return 403 for an unqualified report; development/test
inspection returns the frozen LensReport with its mandatory evaluation marker.
URL input still returns 501; screenshot input uses the sanitized upload/OCR/
PII path. Analysis responses carry no-store and no-referrer headers, but
anonymous UUID access is not authentication and needs review before release.

Configurable ceilings are 180 seconds per retrieval, 300 seconds per claim,
and 900 seconds per analysis, alongside existing extractor/judge limits. This
in-process runner is deliberately small for the competition MVP. It does not
offer multi-worker coordination, durable queue delivery, automatic model-call
replay, or a public resume endpoint.

PostgreSQL is the system of record. Redis is transient cache/rate-limit state
and must not be the sole copy of evidence or an analysis result. Evidence
passage vectors use pgvector, avoiding a separate vector database in the MVP.

## Phase 7B web boundary

The web app uses vanilla HTML/CSS/TypeScript with Vite. React and Tailwind
were intentionally removed: the old frontend was only an extraction shell,
and a small page-level state model is sufficient for the competition MVP.
`src/api/` is the sole fetch boundary; `src/types/` mirrors the Phase 7A
status, claim, and LensReport contracts; `src/pages/` owns home/analysis page
state; `src/components/` builds safe DOM fragments; `src/utils/` owns routing,
polling, and idempotency; `src/styles/` holds design tokens and responsive CSS.

`/` holds the text/screenshot submission. `/analysis/{uuid}` can be loaded
directly or refreshed; the server's SPA fallback serves `index.html` for the
deep link. The analysis page polls `GET /v1/analyses/{id}` and `/claims` about
every 1.5 seconds, serially, with bounded network backoff and abort on page
cleanup. Terminal states stop polling. Reports are fetched only for completed
claim checkpoints and never recomputed in the browser. The one-shot SSE route
is not used as a live stream. A retry of an uncertain POST reuses its
Idempotency-Key; a deliberate input change creates a new key. A same-tab
session record can retain only a SHA-256 digest, opaque key, and upload ID,
not medical text or image bytes.

Each report displays backend-provided reasons, exact frozen source excerpts,
limitations, safety text, and a prominent backend development notice when
`production_qualified=false`. The frontend does not infer source roles or a
medical verdict. It maps four controlled verdict labels and safe operational
error categories to UI copy. A 403 report gate is not a fifth medical result.
Text nodes are created with `textContent`, and external source URLs are used
only when the backend-provided URL is HTTP(S). No credentials enter the web
bundle. URL submission, WeChat, localization, and public access controls
remain later work.

## Safety and trust boundary

Raw user content and retrieved documents are untrusted. Future stages must
separate them from prompts/instructions, validate uploads and URLs, redact PII
before model calls, check retractions and identifiers in retrieval, and force
high-risk cases through stricter abstention thresholds.
