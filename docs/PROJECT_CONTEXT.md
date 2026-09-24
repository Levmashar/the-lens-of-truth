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
- Verdicts are limited to `SUPPORTED`, `CONTRADICTED`,
  `NOT_ENOUGH_EVIDENCE`, and `UNABLE_TO_VERIFY`.
- `UNABLE_TO_VERIFY` means the claim or verification process is unreliable;
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
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Testing | Pytest |
| Local runtime | Docker Compose |

## Current implementation status

Phase 1 foundation and the scoped Phase 2 intake path are implemented:

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
- An OpenAI-compatible, schema-constrained claim-extraction adapter. It is
  disabled by default and fails closed until an approved endpoint, pinned model
  ID, and secret are configured; no heuristic or mock claims are substituted.
- A web flow to submit text or screenshots and review extracted claims.
- Docker Compose services for API, web, PostgreSQL/pgvector, and Redis.
- GitHub Actions checks for API tests/static analysis and frontend type/build validation.

UMLS/MeSH linking, PICO normalization, retrieval, evidence packs, independent
judging, citation validation, and verdicts are not implemented. Phase 2 claim
extraction is not medical analysis and must not be presented as a verdict.

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
