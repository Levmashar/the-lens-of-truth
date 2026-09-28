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

## Phase 4A.1: Evidence-selection hardening

- [x] Keep every extracted title/abstract passage in version 1.1 Evidence Packs
- [x] Store a separate, ordered top-evidence selection with one passage per PMID by default
- [x] Prefer relevant abstracts, expose concept coverage and background/diversity factors
- [x] Regression-test auditability, ordering, selection diversity, and stable pack hashes
- [x] Repeat live sunscreen/melanoma smoke (18 documents; 42 passages; no repeated selected PMID)
- [ ] Benchmark generic-background penalties and top-k recall on varied claims

## Phase 4B: Evidence integrity and study-quality metadata

- [x] Parse structured PubMed integrity types and linked correction/retraction records
- [x] Add optional, bounded, cached Crossref DOI enrichment and conservative merge
- [x] Freeze check statuses, references, provenance, study design, quality prior,
      and applicability flags in version 1.2 Evidence Packs
- [x] Exclude retracted documents from selected evidence while preserving all passages
- [x] Distinguish optional metadata omissions from incomplete/missing EFetch records
- [x] Offline regressions and live sunscreen smoke (18 articles; 16 successful
      Crossref DOI checks; one unsupported PubMed book record; no verdict)
- [ ] Evaluate integrity coverage and classifier accuracy against annotated papers
- [ ] Decide whether an additional integrity source is needed before public use

## Phase 4B.1: Evidence directness and relationship-aware selection

- [x] Add separate document/passage directness scores, factors, and conservative
      aligned/reverse/incidental/unknown direction with reasons
- [x] Weight exact concept proximity and structured abstract sections; demote
      post-outcome, background-only, covariate-only, exposure-excluded, and
      screening/cessation-only contexts without deleting audit records
- [x] Select by exposed topical/directness/quality/applicability components,
      preserving one PMID by default and retraction exclusion in Pack 1.3
- [x] Offline regressions, full static/test suite, and live four-claim smoke
- [ ] Later evaluate directness precision/recall on an annotated Phase 7 set,
      especially multilingual text, complex comparators, and atypical abstracts

## Later evidence-retrieval work (outside Phase 4B.1)

- [ ] WHO/CDC and ClinicalTrials adapters
- [ ] Hybrid/vector retrieval and reranking, if benchmark results justify them

## Phase 5A: Independent Evidence Judges

- [x] Require the same validated Evidence Pack 1.3 selection and exact E passages for every judge
- [x] Configure up to three explicit provider/model/model-family slots; reject duplicate
      families unless a development-only override is deliberately enabled
- [x] Add canonical versioned prompt, strict three-label JudgeDecision, selected-E-ID
      citation validation, and prompt-injection trust boundary
- [x] Run bounded concurrent calls with one retry, isolated failures, and per-slot breaker
- [x] Append success/failure audit rows tied to pack ID/hash and prompt hash
- [x] Expose descriptive agreement counts and developer CLI, without a final verdict
- [x] Offline judge/adapter tests and migrated-PostgreSQL persistence test
- [x] Add opt-in development/test-only search-mode guard bypass for Miri plumbing
      smoke, with explicit warning and per-run unverified-isolation audit flags
- [x] Run a development Miri smoke with three distinct configured family labels
      against the frozen sunscreen Evidence Pack 1.3: ChatGPT and Qwen returned
      valid judge responses; Gemini failed `malformed_json` twice; no verdict
- [ ] Verify underlying model-family identity and pinning in each runtime;
      configured labels and the 2/3 development smoke do not prove independence
- [ ] Validate provider-native browsing/search controls for each approved
      production provider before a public medical judgment
- [ ] Resolve Gemini structured-output reliability and repeat a 3/3 live smoke
      without development search or same-family overrides before release

## Later model-ensemble work (outside Phase 5A)

- [ ] Calibration and adaptive escalation policy

## Phase 6A: Judge citation and evidence validation

- [x] Recheck every cited/opposing E ID against frozen Pack 1.3 selection,
      passage hash, document provenance, and recorded judge-pack hash
- [x] Recheck frozen integrity; exclude retracted citations and warn on unknown
      integrity or expressions of concern
- [x] Run conservative numeric, PICO/scope, and relation-strength checks before
      optional one-passage semantic entailment
- [x] Add strict provider-independent entailment contract, untrusted-data prompt,
      offline synthetic fixtures, and development-only CLI
- [x] Persist repeated validation as new append-only judge_validation_run rows;
      verify the PostgreSQL trigger and Alembic schema
- [x] Keep development Miri labels out of acceptance; expose no final verdict
- [ ] Approve and evaluate a live one-passage entailment provider before public use
- [ ] Phase 8: measure validator accuracy on medically reviewed, multilingual cases

## Phase 6B: Disagreement and final verdict aggregation

- [x] Versioned deterministic four-label policy over explicit judge/validation IDs
- [x] Standard-risk 2-judge and high-risk 3-judge conservative decision tables
- [x] Distinguish successful no-results retrieval from pipeline/qualification failure
- [x] Exclude failed, partial, invalid, or unavailable judge validations from
      decisive label counts; retain typed exclusion/disagreement diagnostics
- [x] Require verified identity, family, search isolation, and approved entailment
      source for production; keep development Miri smoke ineligible
- [x] Persist append-only, semantically hashed verdict runs with PostgreSQL
      update-blocking trigger and an internal explicit-ID CLI
- [x] Offline policy fixtures and current-Miri regression; no public result API
- [ ] Release gate: approve a live entailment provider in a reviewed policy
      revision, verify pinned independent model families and native search isolation
- [ ] Phase 8: medically review and benchmark verdict safety and abstention rates

## Phase 6C: Evidence-cited report and safety UX

- [x] Internal typed `LensReport` from one explicit, persisted VerdictRun and
      its frozen Evidence Pack, JudgeRun, and JudgeValidationRun IDs
- [x] Controlled four-label display, reason-code prose, qualification and
      disagreement summaries; no LLM writing or numeric truth confidence
- [x] Exact bounded source excerpts from selected, validated citations only;
      distinguish source text from Lens-generated explanation
- [x] Surface material numeric, causal-strength, scope, and integrity limits;
      show standard health-information safety and non-production notices
- [x] Append-only, semantically hashed `report_run`, internal CLI, offline
      four-label/Miri regressions, PostgreSQL trigger and schema checks
- [ ] Phase 7: add a separately reviewed, explicitly gated report endpoint
      and accessible frontend presentation; no public verdict route in Phase 6C
- [ ] Release gate: approve live entailment, provider identity and search
      isolation before any report can be production-qualified

## Phase 7: Frontend polish

- [ ] Real upload and URL experiences, progressive SSE status, source cards
- [ ] Accessibility review to WCAG 2.2 AA and Chinese localization
- [ ] Native WeChat screens and consent/retention UX

## Phase 8: Evaluation benchmark

- [ ] Annotation guideline and 300+ real zh-CN/English claim benchmark
- [ ] Retrieval, verdict, citation, calibration, and safety metrics
- [ ] Baselines, ablations, red-team set, and CI evaluation gates
