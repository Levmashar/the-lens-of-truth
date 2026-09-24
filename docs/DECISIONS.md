# Architecture Decisions

## ADR-001 — Keep the MVP pipeline-first

**Decision:** analysis is a staged evidence-verification pipeline, not a chat
completion or popularity-based fact checker.

**Reason:** claim decomposition, shared evidence, provenance, and abstention
are essential to medical safety and the competition differentiator.

## ADR-002 — PostgreSQL + pgvector for the initial corpus

**Decision:** use PostgreSQL with pgvector before introducing a separate search
or vector cluster.

**Reason:** the expected MVP workload is small enough that operational
simplicity is more valuable than premature distributed search infrastructure.

## ADR-003 — Preserve a four-label outcome

**Decision:** distinguish `NOT_ENOUGH_EVIDENCE` from `UNABLE_TO_VERIFY`.

**Reason:** a claim with inconclusive evidence is materially different from a
claim that cannot be reliably formulated or retrieved. Conflating them would
hide technical degradation as medical uncertainty.

## ADR-004 — Adapter boundary for external services

**Decision:** all OCR, evidence, model, storage, and other outbound services
are accessed through an adapter owned by the backend.

**Reason:** it prevents provider details from leaking into pipeline logic and
supports testing, fallbacks, auditing, and vendor changes.

## ADR-005 — No fake AI

**Decision:** routes must never generate simulated claims, evidence, or verdict
data that resembles a real analysis.

**Reason:** fabricated medical reasoning would undermine safety and make
integration behavior indistinguishable from a real verification result.

## ADR-006 — Phase 2 extraction fails closed

**Decision:** use a configured, OpenAI-compatible structured-output adapter
for semantic atomic-claim extraction and return an availability error when it
is not configured or returns invalid offsets.

**Reason:** sentence splitting or a simulated response cannot reliably produce
atomic medical propositions. A provider response is treated as untrusted too:
the backend verifies every returned span against the redacted source before it
can become a stored claim.

## ADR-007 — Re-encode then retain raw screenshots for at most 24 hours

**Decision:** accept only decoded static PNG/JPEG/WebP images, re-encode them
to metadata-free PNG, keep their bytes outside PostgreSQL, and purge uploads
and their short-lived analyses after 24 hours.

**Reason:** client-declared MIME types and image metadata are not trustworthy.
Short retention and position-preserving PII masking minimize exposure while
preserving source offsets required for claim auditing.
