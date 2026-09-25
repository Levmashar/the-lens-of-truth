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
- A web flow to submit text or screenshots and review extracted claims.
- Docker Compose services for API, web, PostgreSQL/pgvector, and Redis.
- GitHub Actions checks for API tests/static analysis and frontend type/build validation.
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

Licensed UMLS source integration, non-PubMed evidence retrieval, hybrid/vector
search, independent judging, citation validation, and verdicts are not
implemented. Integrity checks are not exhaustive: PubMed/Crossref metadata can
lag or omit events, and `valid` is not medical correctness or evidence quality.
MeSH linking and PICO framing are terminology operations, not medical truth
assessment. The 2026 MeSH index must be imported separately in each runtime;
the generated vocabulary is not committed to the repository.
Phase 4A is PubMed-only evidence retrieval; it does not judge claims.

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
