# Delivery Roadmap

## Phase 1: Repository foundation

- [x] Monorepo layout and developer documentation
- [x] FastAPI configuration, logging, errors, health, and typed API contract
- [x] SQLAlchemy models and Alembic base migration
- [x] React/Vite/Tailwind navigation shell and health connectivity
- [x] Docker Compose with PostgreSQL/pgvector and Redis
- [x] Focused backend tests
- [x] Pull-request CI for static checks, tests, and frontend build

## Phase 2: Claim extraction

- [x] Secure text/screenshot ingestion and 24-hour retention enforcement
- [x] OCR adapter with PII redaction and confidence metadata
- [x] Atomic claim extraction with source offsets and ambiguity handling
- [x] Extract nullable PICO framing with atomic claims

## Phase 3A: Medical normalization layer

- [x] Define UMLS and MeSH provider interfaces and fixture-only local providers
- [x] Ground model-produced PICO slots in each atomic source claim
- [x] Store PICO, entity mentions, and explicit normalization status on claims
- [x] Return normalization fields from claim preview and analysis detail APIs
- [x] Cover malformed model JSON, absent/low-confidence terminology, and sunscreen framing

## Phase 3B: Real medical terminology resolution

- [x] Import official MeSH descriptor XML into a local, versioned index
- [x] Resolve preferred names and entry terms; expose bounded ambiguous/fuzzy candidates
- [x] Keep UMLS optional and preserve confident MeSH links without CUIs
- [x] Persist source, release, match type, ambiguity, confidence, and tree numbers in claim JSONB
- [x] Verify the 2026 NLM descriptor release against sunscreen/melanoma locally
- [x] Record source/version/hash and add dry-run re-normalization of untouched `pending` claims
- [ ] Operational follow-up: import the current MeSH release in each deployment
- [ ] Before public release, show NLM attribution and release currency in the
      product UI as required by NLM terms (frontend is out of scope for Phase 3B)
- [ ] Later, integrate a licensed UMLS source if approved and evaluate linking accuracy
- [ ] Later, design a separately reviewed refresh for existing `pico_only` claims;
      the Phase 3B command deliberately processes only untouched `pending` rows
- [ ] Later, assess approved Chinese terminology translations and link quality

## Phase 3C: Claim extraction and normalization hardening

- [x] Canonical claim types with source-wording guard for explicit causal/association language
- [x] Deterministic MeSH source/PICO/entity completeness audit and required-slot rules
- [x] Persist and return normalization quality; keep incomplete legacy rows out of `normalized`
- [x] Bounded extractor retry, classified failures, and non-sensitive diagnostics
- [x] Enforce a configurable 55-second attempt limit and 115-second total deadline
- [x] Cover timeout, empty-response, deadline, and normal-response latency paths offline
- [x] Offline regressions for omission, semantics, terminology, and provider failures
- [ ] Operational follow-up: migrate each deployment and re-audit legacy `partial` rows
- [ ] Evaluate completeness recall on annotated English and Chinese claims before public use

## Phase 4A: PubMed evidence retrieval foundation

- [x] Deterministic, provenance-labeled MeSH/lexical/relation/numeric QueryPlan
- [x] Official NCBI ESearch/EFetch adapter with bounded retries and optional Redis query cache
- [x] Normalize PubMed metadata and exact title/abstract passages; deduplicate PMIDs
- [x] Deterministic relevance ranking and content-hashed, append-only Evidence Packs
- [x] Persist runs, queries, document-query provenance, passages, and frozen snapshots
- [x] Developer evidence preview, CLI smoke command, offline tests, and schema migration
- [x] One live sunscreen/melanoma PubMed smoke (18 documents; partial metadata surfaced)
- [ ] Operational follow-up: set a real `NCBI_EMAIL` for each deployment and run live smoke
- [ ] Evaluate PubMed retrieval recall and publication-date/metadata edge cases

## Phase 4B: Broader evidence retrieval and validation

- [ ] WHO/CDC, Crossref, and ClinicalTrials adapters
- [ ] Retraction/version checks and source validation
- [ ] Hybrid/vector retrieval and reranking, if benchmark results justify them

## Phase 5: Model ensemble

- [ ] Independent, pinned model-provider adapters and circuit breakers
- [ ] Structured judge responses and audit records
- [ ] Calibration and adaptive escalation policy

## Phase 6: Verdict engine

- [ ] Citation existence, numeric alignment, entailment, and scope validation
- [ ] Disagreement analysis and deterministic risk-aware aggregation
- [ ] Evidence-cited human-readable report with safety banners

## Phase 7: Frontend polish

- [ ] Real upload and URL experiences, progressive SSE status, source cards
- [ ] Accessibility review to WCAG 2.2 AA and Chinese localization
- [ ] Native WeChat screens and consent/retention UX

## Phase 8: Evaluation benchmark

- [ ] Annotation guideline and 300+ real zh-CN/English claim benchmark
- [ ] Retrieval, verdict, citation, calibration, and safety metrics
- [ ] Baselines, ablations, red-team set, and CI evaluation gates
