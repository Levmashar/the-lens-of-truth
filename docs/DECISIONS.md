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

## ADR-008 — Use miri-api for ChatGPT Auto claim framing

**Decision:** default to `miri` while requiring a configured gateway address,
send only redacted content to the gateway's OpenAI-shaped chat completion,
request `chatgpt-auto`,
and validate its JSON and source offsets in the backend. Capture nullable PICO
fields from the same extraction response. The gateway address and optional
Bearer token remain in the local environment.

**Reason:** the supplied gateway documentation identifies `chatgpt-auto` as
the ChatGPT Auto picker mode. Its browser-backed responses do not guarantee
schema-constrained JSON or an exact underlying model version. Fail closed on
invalid responses, and do not assign UMLS/MeSH IDs without a verified
vocabulary source.

## ADR-009 — Ground PICO and leave terminology unresolved by default

**Decision:** consume the structured PICO proposal already returned by the
approved claim-extraction adapter, then retain only slot text present in that
same redacted atomic claim. Do not make an additional model call for each
claim. UMLS and MeSH remain separate provider interfaces; local providers
accept only caller-supplied fixture mappings. Runtime providers return no
identifiers until an authorized terminology source is connected. A candidate
below the configured confidence threshold is unresolved.

**Reason:** this prevents cross-claim leakage and invented clinical details,
avoids repeated gateway latency for the competition MVP, and distinguishes
query framing from verified vocabulary concepts or medical evidence.

## ADR-010 — Use a local, versioned official NLM MeSH descriptor index

**Decision:** import NLM's annual MeSH descriptor XML into an atomic SQLite
index outside source control. Use preferred labels and official entry terms for
deterministic exact/synonym matching; keep fuzzy results as suggestions below
the assignment threshold. Record MeSH production year and source-file SHA-256.
When no index is installed, leave IDs unresolved. Keep the UMLS provider
optional and independent. Re-normalize only untouched pending claims using
stored PICO, with dry-run as the default.

**Reason:** a local official source avoids sending sensitive claims to a
terminology API, makes matching reproducible, requires no UMLS license, and
does not fabricate identifiers. The claim's existing JSONB entity field can
carry provenance without another migration. NLM attribution and release
currency remain deployment responsibilities under its data terms.

## ADR-011 — Canonical assertion type and source-grounded completeness

**Decision:** use one controlled claim-type enum rather than a second relation
field. Explicit English causal/association wording deterministically takes
precedence over a conflicting model label; other wording uses the validated
model category. A bounded set of historic labels maps to canonical values,
while unknown new labels are rejected. The exact raw span remains separate.

**Decision:** `normalized` requires source-grounded required-slot and lexical
MeSH completeness checks, plus resolved identified mentions. Preserve
`pending`, `unresolved`, `pico_only`, and `partially_linked`; add `partial` for
missing slots/source concepts or an incomplete source scan. A nullable JSONB
quality audit stores coverage and warnings. On migration, legacy `normalized`
rows become `partial` with `legacy_not_audited`; existing mappings remain
untouched. The pending-only re-normalizer does not rewrite them.

**Reason:** linked extracted mentions are not proof that all explicitly stated
concepts were extracted. The Vitamin C/common-cold omission demonstrated this
failure mode. MeSH exact/entry-term checks are reproducible but lexical, not
medical evidence; generic terms and fuzzy suggestions cannot force a finding.

## ADR-012 — One bounded extraction retry, then fail closed

**Decision:** both existing OpenAI-shaped adapters make at most two requests.
Malformed JSON/schema/empty/unsupported responses receive one strict-JSON
repair prompt with the same redacted source, never the invalid answer.
Timeouts, transport failures, HTTP 429, and HTTP 5xx retry once; other HTTP
errors fail immediately. Exhaustion keeps the existing public 502/503 error
codes. Diagnostics log only non-sensitive provider/model, failure class,
attempt count, latency, and a validated upstream request ID.

**Reason:** browser-backed responses can violate JSON structure despite an
HTTP 200. A small retry improves resilience without weakening validation,
adding an unapproved provider, or fabricating claims.

## ADR-013 — Bound claim-extraction wall time

**Decision:** each extractor attempt has a configurable 55-second default
timeout (maximum 60 seconds), and the entire operation has a configurable
115-second default deadline (maximum 120 seconds). An asynchronous deadline
wraps the actual HTTP request, even if an HTTP client ignores its own timeout.
At most one retry remains available. Empty responses still qualify for that
retry. Exhausted attempt timeouts return `claim_extractor_timeout`; an overall
deadline returns `claim_extractor_deadline_exceeded`, both with HTTP 504.

**Reason:** a browser gateway can return slowly or produce an empty first
reply. Two former 180-second attempts allowed the API to outlast common client
timeouts. Distinct failure codes and logs make timeout behavior observable
without disclosing prompts, credentials, or provider responses to users.

## ADR-014 — PubMed-only, content-addressed Evidence Pack foundation

**Decision:** Phase 4A plans small deterministic PubMed query variants from
source-grounded PICO and confident MeSH concepts. It uses NCBI ESearch/EFetch,
never HTML scraping. Search PMID lists may be cached briefly in Redis; Redis
is never the evidence system of record. Documents are keyed by PMID and
content hash so metadata revisions do not overwrite earlier source versions.
Each retrieval run stores query provenance and creates a new, append-only JSONB
Evidence Pack with backend E IDs and canonical SHA-256. Retrieval timestamps
do not affect the content hash. Ranking is lexical topical relevance only.

**Reason:** later judges must see identical, auditable source bytes and cannot
invent identifiers. A bounded official adapter and simple relevance ranking
meet the MVP latency/complexity target without implying medical truth or study
quality. Subsequent source and retraction checks remain separate work.

## ADR-015 — Separate auditable passages from judge-facing evidence selection

**Decision:** Phase 4A.1 Evidence Packs use version 1.1. All extracted PubMed
title and abstract passages remain ranked and frozen with E IDs. An ordered
`selected_evidence_ids` subset identifies future judge input, with a default
maximum of one passage per document. Selection favors directly relevant
abstracts, while title-only evidence is retained and may be selected when its
core-concept coverage is unique or no usable abstract exists. Lexical/MeSH
concept coverage and conservative outcome-only background penalties are
recorded as relevance factors. The selected IDs and flags enter the pack hash;
older version 1.0 packs remain readable but are not automatically judge-ready.

**Reason:** multiple passages from one PMID can otherwise dominate a small
top-k, and a broad outcome review can rank like a paper directly discussing
both claim concepts. Selection must improve topical diversity without hiding
source text or implying a truth, causal, or study-quality judgment.

## ADR-016 — Treat publication integrity as checked, versioned metadata

**Decision:** Phase 4B parses PubMed publication types and linked
`CommentsCorrections` records, then optionally checks DOI-bearing records
through Crossref's REST API using `CROSSREF_MAILTO`. Crossref is enrichment,
not a medical search source. Its per-DOI timeout, one retry, bounded 429
backoff, three-way concurrency cap, 30-second overall enrichment budget, and
versioned one-hour Redis cache are fail-open for PubMed retrieval. DOI-less
records mark Crossref `not_applicable`; configured failures/not-found and
unconfigured DOI checks never imply `valid`. Positive signals from either
provider win, with severity order retracted, expression of concern, corrected,
updated. A retraction notice's `update-to` target is recorded but must not
label the notice itself retracted; `updated-by` can label the original.

**Decision:** Evidence Pack 1.2 freezes per-provider check status/version,
integrity status/sources/references/warnings, Crossref fields, field provenance,
study design, methodology `quality_prior` and factors, applicability warnings,
and selection. PubMed bibliographic values are not overwritten by Crossref.
Semantic changes alter the hash, while check/retrieval wall-clock timestamps
do not. The append-only pack JSONB is authoritative; the pre-existing
`evidence_document.retraction_status` column is legacy bibliographic storage,
not a current integrity decision, so no schema migration is required.

**Decision:** Study design is classified without an LLM from PubMed publication
types, then structured MeSH, then conservative title wording; uncertainty is
`unknown`. `quality_prior` is a transparent methodology heuristic, not truth,
claim support, or verdict confidence. It is not added to the topical
`retrieval_score`. Retractions remain auditable but are excluded from selected
evidence; unknown integrity stays eligible with warnings. `partial_metadata`
denotes incomplete/missing EFetch records or unsupported PubMed book records,
while reason counts expose optional field absences and enrichment failures
separately.

**Reason:** medical claims can be harmed by treating a retracted source, a
metadata outage, or a prestigious but irrelevant review as decisive evidence.
Separate typed signals and immutable provenance let later judges evaluate the
same snapshot without hiding uncertainty or conflating retrieval relevance
with study quality.

## ADR-017 — Separate relationship directness from relevance and evidence truth

**Decision:** Phase 4B.1 adds deterministic, claim-specific document and
passage `relationship_directness` with an exposed `[0,1]` score, direction
(`aligned`, `reverse`, `incidental`, `unknown`), factors, reasons, and warnings.
Only PICO wording and confident exact/synonym MeSH labels expand concepts.
Same/adjacent sentence and section occurrence, RESULTS/CONCLUSIONS weighting,
relation cues, post-outcome framing, background/covariate-only mentions, and
explicit exposure/population exclusions affect directness. Ambiguous direction
remains unknown. The signal is a heuristic for addressing the same question,
not entailment or support/contradiction; a paper finding no effect can be
highly direct.

**Decision:** Keep `retrieval_score`, `quality_prior`, integrity, and directness
separate. Version 1.3 records an explained selection priority (30% topical,
45% passage directness, 20% document directness, 5% study-quality prior, minus
an applicability penalty). It chooses the strongest direct representative per
document, preserves the one-PMID default and hard retraction exclusion, and
retains every nonselected record in the append-only pack. Version 1.3 hashes
the new metadata and selection. Existing pack JSONB needs no schema migration;
older packs are not rewritten.

**Reason:** topical overlap selected a zinc review for a Vitamin C prevention
claim, post-stroke BP management for a hypertension-to-stroke-risk claim, and
screening/cessation or never-smoker contexts for a smoking-to-lung-cancer-risk
claim. The bounded lexical rules address these reproducibly without a new
model, fabricated medical inference, or PMID-specific hardcoding. Their
precision/recall and multilingual coverage still require Phase 7 evaluation.
