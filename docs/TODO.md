# Delivery Roadmap

## Phase 1: Repository foundation

- [x] Monorepo layout and developer documentation
- [x] FastAPI configuration, logging, errors, health, and typed API contract
- [x] SQLAlchemy models and Alembic base migration
- [x] Initial React/Vite/Tailwind navigation shell and health connectivity
      (intentionally replaced by vanilla TypeScript in Phase 7B)
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
- [x] Version judge citation-selection instructions and audit narrow inference
      of an omitted fixed schema version; production still excludes such runs
- [x] Reassess the frozen smoking/lung-cancer pack with prompt 1.6 and
      independently validate every citation: 2 of 3 judges qualified in
      evaluation mode; the original run remains unchanged
- [x] Repeat the smoking claim through the normal API: one completed claim,
      2 qualified assessments, 1 partial exclusion, evaluation-only report
- [ ] Measure over-citation and judge JSON reliability on varied Phase 7 cases
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
- [x] Add a development/test-only live one-passage adapter using another
      configured judge family; record strict E-ID and prompt provenance
- [ ] Approve and evaluate a live one-passage entailment provider before public use
- [ ] Phase 8: measure validator accuracy on medically reviewed, multilingual cases

## Phase 6B: Disagreement and final verdict aggregation

- [x] Versioned deterministic four-label policy over explicit judge/validation IDs
- [x] Standard-risk 2-judge and high-risk 3-judge conservative decision tables
- [x] Distinguish successful no-results retrieval from pipeline/qualification failure
- [x] Exclude failed, partial, invalid, or unavailable judge validations from
      decisive label counts; retain typed exclusion/disagreement diagnostics.
      Evaluation-only inconclusive use may qualify with validated partial scope
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
- [x] Phase 7A: add an explicitly gated, claim-scoped frozen-report endpoint
      and durable orchestration; the web consumer is Phase 7B
- [ ] Release gate: approve live entailment, provider identity and search
      isolation before any report can be production-qualified

## Phase 7A: End-to-end orchestration and gated report API

- [x] Persist analysis and claim-level orchestration checkpoints, timestamps,
      safe failure categories, and exact artifact IDs; preserve immutable runs
- [x] Return an analysis ID before OCR/extraction/retrieval/judging; apply
      extraction, per-claim, retrieval, judge, and analysis-level time budgets
- [x] Process atomic claims independently and preserve partial completion
- [x] Keep Phase 6 production gates: no unqualified report in staging/production;
      show the mandatory evaluation notice for development/test reports
- [x] Add polling progress, claim summaries, claim-scoped frozen LensReport GET,
      and one-shot SSE compatibility snapshot (no streaming worker bus yet)
- [x] Hash client Idempotency-Key and canonical request; never auto-replay
      external providers after restart or repeat POST
- [x] Offline synthetic full-chain and failure fixtures, developer CLI,
      PostgreSQL persistence tests, and schema checks
- [ ] Before public deployment, replace the single-process background runner
      with a durable queue/lease and add an access-control/privacy review
- [ ] Before public deployment, approve live entailment and verify pinned
      independent model identity/families plus native search isolation

## Phase 7B: Vanilla TypeScript/Vite competition-ready web UX

- [x] Remove the Phase 2 React/Tailwind shell; use modular vanilla
      HTML/CSS/TypeScript + Vite with typed API contracts
- [x] Text and sanitized screenshot submission, actual consent version,
      upload preview, accessible controls, and duplicate-submit protection
- [x] Per-attempt idempotency with same-key network retry and same-tab
      digest/key/upload-reference recovery; no raw medical text in storage
- [x] `/analysis/{uuid}` refresh/resume, bounded serial polling, claim-scoped
      progress, partial completion, and one-time frozen-report reads
- [x] Four report labels, exact source excerpts, limitations, safety text,
      and visible development qualification without frontend medical reasoning
- [x] Safe operational errors, no-claim/OCR/expired states, responsive CSS,
      basic keyboard/accessibility semantics, frontend DOM tests and build
- [ ] Manually visually review desktop/mobile screenshots at 375/430/768px
      and desktop when a browser-capable environment is available
- [ ] Complete an independent WCAG 2.2 AA audit before public release
- [ ] Consider resumable SSE after a durable event store exists; one-shot
      snapshot remains compatibility-only in Phase 7A
- [ ] Implement safe URL ingestion only after reviewed SSRF/fetch controls

## Phase 7B.1: Claim self-containment and endpoint-direct retrieval hardening

- [x] Validate every new atomic claim as standalone; reconstruct only verified
      adjacent coordinated/pronoun subjects in `normalized_text`, never raw spans
- [x] Persist standalone status and inherited source offsets; block uncertain
      or incomplete fragments before normal retrieval
- [x] Add broad plus endpoint-focused PubMed queries for explicit measured
      outcomes and population, without adding a new source
- [x] Score endpoint directness separately from topical/relationship relevance
      and result direction; demote mechanism/background and wrong-population hits
- [x] Freeze new selection factors in Evidence Pack 1.4, preserving the
      version-specific 1.3 hash path and all auditable passages
- [x] Add offline coordination, soy endpoint, population, negative-result,
      JSONB hash, and existing-claim regression tests
- [x] Complete and inspect the live combined-soy acceptance run: both claims
      completed with a source-grounded standalone second clause; male hormone
      studies led the estrogen selection, while the retrieved osteoporosis and
      mechanism-only papers remained unselected. No meningioma paper appeared
      in this live retrieval. Judge qualification remains a separate issue.

- [x] Retry invalid source offsets within the existing one-retry extraction limit
- [x] Give an explicit but omitted PICO relation one bounded repair attempt;
      preserve `partial` if it remains omitted
- [x] Ground a shared subject from verified adjacent `, and` source syntax,
      without inventing terminology IDs or rewriting the atomic source span
- [x] Permit audited, complete `partially_linked` PICO through lexical retrieval
      and verdict checks; block unaudited rows and incomplete `partial` claims
- [x] Remove non-discriminating exposure words from PubMed lexical terms
- [x] Reject the contextless `consumption` -> `Economics` MeSH alias; keep
      unresolved soy exposure and fall back to source-grounded lexical queries
- [x] Do not label `Male` inside `soy consumption in male body` as an
      intervention; an unresolved exposure remains auditable and retrievable
- [x] Recover the second clause's explicit `muscle growth` outcome and shared
      subject from the exact soy source when model PICO/pointer are incomplete
- [x] Keep explicit nonhuman and low-focus PubMed hits auditable but unselected;
      live soy retrieval now selects human soy/muscle studies instead of animal
      or generic background articles
- [x] Add offline soy, offset, omission, retrieval, and orchestration regressions
- [x] Give an incomplete claim a typed `normalization_incomplete` failure and
      actionable frontend copy, without presenting it as a medical verdict
- [ ] Repeat the exact soy input through the live configured extractor when
      `chatgpt-auto` responds within the bounded attempt timeout; inspect both
      claim reports and top retrieved passages
- [x] Distinguish Miri HTTP 429 from generic extraction failure, log only the
      safe HTTP status, honor bounded `Retry-After`, and show provider-specific
      user-facing failure copy
- [ ] Restore a usable Miri ChatGPT account/quota and repeat the live frontend
      acceptance run; `/models` availability does not prove chat capacity
- [ ] Evaluate coordinated-clause and PICO-repair recall on annotated English
      and Chinese claims before public use
- [x] Add a development-only `DEBUG_MODE` analysis panel for stage checkpoints,
      safe failure codes, judge/validation audit outcomes, and bounded visible
      model-response excerpts with actual call/reachability states
- [x] Harden AIMLAPI extraction against ignored JSON-schema instructions,
      uniquely correct arithmetic source offsets, and retry explicit-relation
      empty outputs once without fabricating claims
- [x] Remove repeated non-debug frontend copy while keeping development and
      safety notices visible
- [x] Include focus/nonhuman exclusion reasons in frozen Evidence Pack schema;
      verify pack JSON round trips and a live single-claim report completes
- [ ] Retest the existing long sunscreen screenshot when Ling responds within
      the configured 55-second attempt deadline; OCR works, but the 2026-09-29
      live extraction smoke timed out twice and returned typed HTTP 504
- [x] Complete one live text-claim report with the current AIMLAPI models;
      source span validation passed, but the report remains development-only
- [x] Diagnose hypertension/cancer Unable: relevant sources existed, but the
      dev run lacked live entailment, one Ling judge failed schema, and
      aggregation incorrectly applied production mode
- [x] Add cross-family development validation, clarify inconclusive citation
      use, and retain safe limited-scope source cards in evaluation reports
- [x] Re-evaluate the same frozen Pack: two cited inconclusive judges and
      live citation checks yielded append-only Not Enough Evidence, evaluation only
- [ ] Resolve Ling HTTP 500 availability; two later full-run extraction attempts
      and the frozen-Pack judge 1 failed. Do not silently substitute a model
- [ ] Benchmark live entailment accuracy before public medical use
- [ ] Repeat live screenshot and multi-claim acceptance with the current
      provider; the long screenshot timed out during Ling extraction

## Phase 7C: Chinese localization and native WeChat follow-up, if justified

- [ ] Chinese UI/medical terminology review and native WeChat screens

## Evidence-to-judgment validation contract repair

- [x] Replay retained sunscreen Pack/three judge audits without altering them;
      record a sanitized local note under ignored `runtime/debug/`
- [x] Version judge decisions and frozen, coherent document input; expose
      omitted sections and input hashes
- [x] Split statement attribution from conclusion justification, target
      numeric/quote/scope issues, and retain valid findings on bad conclusions
- [x] Bound semantic revision to one append-only child per judge and prevent
      parent/child double voting; preserve existing policy thresholds
- [x] Correct report/debug target wording and allow neutral, provenance-
      verified source excerpts only in development Unable reports
- [x] Add deterministic regressions and an opt-in real-model semantic command
- [x] Run the 14-case opt-in semantic check on configured slot 2: 13 expected
      checks matched and 8 mismatched; no provider/format failures. This is
      an evaluation result, not model qualification.
- [x] Replay the retained sunscreen Pack without new retrieval; the new
      input included 35 passages, and one live judge plus one revision were
      audited. The revision remained invalid; no historical verdict changed.
- [x] Run one new sunscreen development analysis: extraction/retrieval/report
      completed, but all three judges failed provider or schema response;
      policy 1.2 returned Unable with 0 qualified, not production qualified.
- [x] Add bounded PubMed lexical fallback and rank direct endpoint studies
      ahead of generic topical papers; keep every exclusion auditable
- [x] Repair false multi-interval numeric mismatch and explicit semantic-ID
      echo; accept bounded longer judge JSON without dropping citation checks
- [x] Add versioned policy 1.3 for a clearly provisional, development-only
      standard-risk result from one fully validated decisive assessment;
      production and high-risk multi-judge gates remain unchanged
- [x] Complete a fresh smoking/lung-cancer association analysis with a
      provisional Supported report and validated frozen source excerpts
- [x] Complete a fresh inverse smoking association as Contradicted with two
      qualified judges; add a causal study-design gate after the carrot
      reverse-causation counterexample
- [x] Confirm carrot/eyesight finishes as Not Enough Evidence with the
      causal-design reason; verify the final inverse claim still contradicts
      and production/high-risk one-judge paths stay blocked
- [ ] Improve/qualify semantic validation on an annotated set and investigate
      remaining provider/schema failures; retain deterministic and production
      judge-count gates
- [ ] Evaluate statistical/scope behavior and release qualification on an
      annotated benchmark before public medical use

## Phase 8: Evaluation benchmark

- [ ] Annotation guideline and 300+ real zh-CN/English claim benchmark
- [ ] Retrieval, verdict, citation, calibration, and safety metrics
- [ ] Baselines, ablations, red-team set, and CI evaluation gates
