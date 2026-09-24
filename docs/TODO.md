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
- [ ] UMLS/MeSH linking and PICO normalization

## Phase 3: Evidence retrieval

- [ ] NCBI/PubMed, WHO/CDC, Crossref, and ClinicalTrials adapters
- [ ] Deterministic query planning, source validation, and retraction checks
- [ ] Hybrid retrieval, ranking, and immutable Evidence Pack generation

## Phase 4: Model ensemble

- [ ] Independent, pinned model-provider adapters and circuit breakers
- [ ] Structured judge responses and audit records
- [ ] Calibration and adaptive escalation policy

## Phase 5: Verdict engine

- [ ] Citation existence, numeric alignment, entailment, and scope validation
- [ ] Disagreement analysis and deterministic risk-aware aggregation
- [ ] Evidence-cited human-readable report with safety banners

## Phase 6: Frontend polish

- [ ] Real upload and URL experiences, progressive SSE status, source cards
- [ ] Accessibility review to WCAG 2.2 AA and Chinese localization
- [ ] Native WeChat screens and consent/retention UX

## Phase 7: Evaluation benchmark

- [ ] Annotation guideline and 300+ real zh-CN/English claim benchmark
- [ ] Retrieval, verdict, citation, calibration, and safety metrics
- [ ] Baselines, ablations, red-team set, and CI evaluation gates
