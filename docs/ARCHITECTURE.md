# Architecture

## Implemented boundary

The repository implements the foundation plus secure text/screenshot
ingestion, bounded local OCR, PII masking, atomic claim extraction, grounded
PICO framing, normalization completeness auditing, and Phase 4A PubMed-only
retrieval. It does not invoke judges or make a medical judgment.

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
frontend/                React + TypeScript + Vite + Tailwind application
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

No full-text fetching, independent model judging, or medical verdict is
produced here.

PostgreSQL is the system of record. Redis is transient cache/rate-limit state
and must not be the sole copy of evidence or an analysis result. Evidence
passage vectors use pgvector, avoiding a separate vector database in the MVP.

## Safety and trust boundary

Raw user content and retrieved documents are untrusted. Future stages must
separate them from prompts/instructions, validate uploads and URLs, redact PII
before model calls, check retractions and identifiers in retrieval, and force
high-risk cases through stricter abstention thresholds.
