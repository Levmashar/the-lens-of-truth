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

## ADR-018 — Freeze one pack before independent judging

**Decision:** Phase 5A accepts only hash-verified Evidence Pack 1.3 snapshots.
All active judge slots receive the same canonical versioned prompt containing
the same exact claim and ordered selected E passages; no new retrieval or model
tools are available during judging. Slots explicitly state provider, requested
model, and actual model family. Duplicate families are rejected except under a
development/test-only override. Miri and other OpenAI-shaped gateways use one
adapter interface; no model IDs are hardcoded.

**Decision:** individual judges have only `supported`, `contradicted`, and
`not_enough_evidence`. Strict Pydantic validation rejects unsupported labels,
missing fields, and citations outside the selected E IDs. A 45-second attempt
limit, 80-second total per-slot deadline, one retry, bounded concurrent calls,
and process-local circuit breaker isolate failures. An append-only `judge_run`
record links every success or failure to pack ID/hash, prompt version/hash,
provider/model/family, attempt/timing diagnostics, and validated canonical
response when available. Claim/pack retention cascades apply. Descriptive
agreement statistics are not a vote, confidence score, or final verdict.

**Reason:** independent model opinions are only comparable when they assess
identical evidence. Existing `model_evaluation` includes an orchestrator-only
label and lacks failed-run/pack provenance, so a dedicated audit table avoids
misrepresenting technical degradation as a medical decision. Miri browser
aliases do not prove model pinning or that native browsing is disabled; these
controls must be verified before production use.

## ADR-019 — Permit search-enabled Miri modes only for marked development smoke

**Decision:** keep the conservative search-mode name guard on by default and
unconditionally reject matching modes in staging/production. In development
or test only, an explicit `JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT=true` permits
a plumbing smoke. The service independently rechecks the environment and flag.
All runs in a bypassed ensemble, including failures, store
`search_override_active=true` and `search_isolation_verified=false`; matching
slots store `search_guard_bypassed=true`. The CLI warns before calling models.
The canonical prompt version advances to `judge-1.1-2026-09-26` and explicitly
forbids search and outside sources. No search/browsing tool is passed.

**Reason:** the available Miri modes can trigger the name guard, preventing a
live integration smoke. The override tests transport, parsing, persistence,
and failure isolation without misrepresenting a browser-backed model's native
search behavior as controlled. It cannot qualify a model or a medical judgment
for production.

## ADR-020 — Advance to evidence validation without qualifying the live ensemble

**Decision:** the 2026-09-28 development Miri smoke is sufficient to proceed
with Phase 6 citation and evidence validation against frozen Evidence Pack 1.3
and strictly validated judge-response fixtures. It is not a release gate for
live verdicts: two of three configured family labels returned valid responses,
while Gemini returned malformed JSON twice. The smoke used a development-only
search guard bypass, so evidence isolation and underlying model-family identity
remain unverified. Do not interpret descriptive agreement among two successful
slots as a three-judge consensus or aggregate it into a medical verdict.

**Reason:** the smoke exercises the transport, schema, shared-pack, and audit
paths enough to develop the next deterministic validation layer. A public
judgment still requires reliable structured output, verified distinct/pinned
families, provider-side search controls, and the later citation/entailment and
risk-aware verdict gates.

## ADR-021 — Validate judge evidence use separately, with fail-closed semantics

**Decision:** Phase 6A validates each successful `JudgeDecision` against its
exact frozen Evidence Pack 1.3. Recheck selected E IDs, canonical pack and
passage hashes, document provenance, and frozen integrity before bounded
numeric, PICO/scope, and relation-strength checks. Fatal deterministic issues
short-circuit optional per-passage entailment. Association-only evidence
cannot justify a decisive causal judgment but can explain a legitimate
`not_enough_evidence` decision. Cited and opposing roles are validated
independently. Structured entailment stays behind a provider-independent
interface; no live provider is approved in this phase. An absent or failed
provider produces `unable_to_validate`, never manufactured validation.

**Decision:** every validation execution creates a new append-only
`judge_validation_run` with versioned deterministic rules, prompt/provider
provenance when used, result JSON, timing, and failure type. A PostgreSQL
update trigger mirrors the existing judge-run protection; normal claim
retention cascades remain. No public endpoint, final verdict, confidence,
aggregation, or user-facing report is introduced.

**Reason:** model citations can be real but misused through numeric distortion,
population shift, or association-to-causation overclaim. Separate typed audit
records expose those defects without confusing validation of a judge's
reasoning with medical truth or treating development Miri labels as ground
truth. Conservative `uncertain` states prevent lexical heuristics from posing
as clinical entailment.

## ADR-022 — Aggregate only qualified, validated evidence under a versioned policy

**Decision:** Phase 6B uses immutable, explicit-ID `AggregationInput` and a
pure `verdict-policy-1.0` decision table. The only labels are `supported`,
`contradicted`, `not_enough_evidence`, and `unable_to_verify_reliably`. First
rehash the frozen Pack 1.3 and check normalization, retrieval, selection,
and audit identity. Successful no-results retrieval is evidence insufficiency;
technical retrieval failure is system inability. Only `validated` judge
decisions without fatal issues enter decisive counts. Partial, invalid, failed,
or unavailable judgments are retained as exclusions, never flipped to an
opposite label. Standard risk requires two same-direction validated judges
and zero validated opposition; high risk requires three unanimous validated
judges. Validated conflict or inconclusive evidence abstains as
`not_enough_evidence`; too few qualified judges abstains as
`unable_to_verify_reliably`. No raw-label majority, brand weights, numeric
truth confidence, or LLM final choice is permitted.

**Decision:** production eligibility additionally requires audited underlying
model snapshot/identity, family verification, verified search isolation with
no development bypass, and a policy-approved entailment provider. New judge
audit flags default false; current Miri service cannot self-certify them.
Policy 1.0 approves no live entailment provider. Offline fixture/evaluation
mode can demonstrate logic but is always explicitly non-production. Every
aggregation inserts a new `verdict_run` with input IDs, controlled reasons,
policy/engine versions, semantic hash, and a PostgreSQL update-blocking
trigger. The legacy `final_verdict` table remains unused and no public route
or explanation is introduced.

**Reason:** two matching model labels do not repair a broken pack, an invalid
citation, uncertain entailment, or an unverified browser-backed provider.
Explicit provenance makes policy results reproducible and prevents silent
promotion of the 2/3 development Miri smoke into medical truth. Approval of
live semantic validation or model identity requires reviewed policy and
provider changes, not a casual development switch.

## ADR-023 — Build reports only from frozen, validated audit records

**Decision:** Phase 6C uses a versioned, pure report builder over one named
VerdictRun, its frozen Pack 1.3, and only the judge/validation IDs recorded by
that run. It never changes or redecides the verdict. Four display labels and
every verdict reason code have controlled prose. No LLM-generated medical
explanation, numeric truth confidence, outside-source lookup, or latest-row
selection is permitted. Source cards show exact bounded frozen passages only
when selected and cited by qualified, fully validated assessments; metadata
and citation roles retain their audit provenance. Operational inability does
not show evidence cards. Material numeric, causal-strength, scope, and
integrity issues become explicitly separate limitations.

**Decision:** `production_qualified=false` forces an in-contract visible
development/evaluation notice, so current Miri-like records cannot appear as
ordinary trusted reports. Every report also carries a separate, concise
health-information safety notice. The semantic hash excludes only generation
time; each execution inserts a new append-only `report_run` with an UPDATE
trigger and claim-retention cascade. The CLI remains development/test-only;
there is no public HTTP or frontend report contract in this phase.

**Reason:** source excerpts and deterministic qualification metadata can be
presented reproducibly without granting another model freedom to invent or
overstate medical conclusions. Immutable report snapshots preserve the exact
presentation that was emitted even if controlled wording changes later.

## ADR-024 — Persist orchestration checkpoints and gate frozen report reads

**Decision:** Phase 7A reserves an `analysis_run` before slow work, returns
HTTP 202, and executes the existing services in a single-process FastAPI
background task. Each atomic claim has its own `claim_analysis_run` with
explicit Pack ID/hash and JudgeRun, JudgeValidationRun, VerdictRun, and
ReportRun IDs. These two records hold mutable progress/timestamps and safe
failure categories; the referenced evidence and audit records stay immutable.
The analysis UUID becomes the Submission UUID when ingestion commits. Client
`Idempotency-Key` is hashed and unique with a canonical request digest;
identical retries return the same run, mismatched requests fail 409. Without
a key, a new request creates new immutable work intentionally. An expired
key fails 410 rather than returning an analysis that polling cannot read.

**Decision:** there is no automatic stage replay or startup replay of external
model calls. In the single-worker MVP, startup marks abandoned queued/running
runs failed. A checkpoint gap can leave an orphaned immutable artifact; the
system never guesses a latest row to repair that gap. The run has bounded
retrieval, claim, and total time budgets. Claims fail independently, and
adapter initialization failure becomes a failed run rather than a stuck queue.
Technical failure does not become Not Enough Evidence. Polling is the current
progress contract; the events route is a one-shot SSE snapshot rather than a
live event bus.

**Decision:** the report route reads only the checkpointed ReportRun and
verifies its hash, recomputes the frozen Pack content hash, and checks full
claim/Pack/verdict/audit linkage. A failed claim has no result label until a
VerdictRun exists. Staging/production suppress unqualified result labels and
deny a non-production-qualified report server-side. Development/test return
the unchanged LensReport with its compulsory evaluation notice. URL fetching
and frontend redesign are outside this phase. Analysis responses are
non-cacheable with no-referrer headers. The anonymous UUID convention is not
user authentication; public deployment requires an access-control and
distributed-worker review.

**Reason:** one request can now traverse the implemented evidence pipeline
without duplicating medical logic, combining independent claims, or
accidentally promoting Miri/unapproved entailment outputs. In-process tasks
and explicit no-replay semantics meet the competition MVP's complexity
constraint while honestly recording their crash-recovery limitations.

## ADR-025 — Use framework-free TypeScript for the competition web client

**Decision:** replace the early Phase 2 React/Tailwind shell with vanilla
HTML, CSS, TypeScript, and Vite. Keep small typed API, page, component, and
utility modules instead of a custom reactive framework. Poll the Phase 7A
status and claim checkpoints; the SSE endpoint is a one-shot snapshot, not a
live stream. Use History API routes `/` and `/analysis/{uuid}` and the existing
Vite/Nginx SPA fallback. Submit an opaque idempotency key per deliberate
attempt, retaining it for uncertain retries. A same-tab session record may
store only a content digest, key, and upload UUID, never raw medical text or
image bytes.

**Decision:** render backend LensReports without browser-side medical
reasoning. Preserve four controlled verdict labels, exact frozen excerpts,
the separate safety notice, and a visually prominent backend development
notice whenever `production_qualified=false`. A 403 report gate is displayed
as release ineligibility, not as a medical verdict. Untrusted claim/source
text enters the DOM only as text; source links require backend-provided
HTTP(S) URLs. Avoid demo fixtures in the running product and do not bypass
the backend qualification gate.

**Reason:** the original framework was only a placeholder. A small modular
client keeps the competition MVP understandable while making the complete
claim-scoped pipeline usable and preserving medical and security boundaries.

## ADR-026 — Ground coordinated subjects and retain lexical retrieval for partial terminology

**Decision:** exact extraction span validation happens within the existing
one-retry, 115-second total deadline. If the first structurally valid response
omits an exposure or outcome in an explicit relation, that same single retry
may request repair; a still-missing slot remains `partial`. For subject ellipsis
in an adjacent coordinated `and` clause (with optional comma), normalization
may carry only the exact preceding
subject when the extractor's antecedent offsets, both source slices, and a
small explicit English verb pattern all agree. The later soy regression also
permits the second clause's *explicit* verb object to fill a model-omitted
outcome when the shared-subject syntax is independently verified. It does not
fill an outcome for a standalone claim, change the original span, or assign an
unverified MeSH ID.

**Decision:** `partially_linked` means source PICO is complete but some
terminology mentions lack a safe ID. Only an audited row with complete
source-grounded PICO, explicit completeness fields, and no missing concepts or
unsafe source-scan warnings may use lexical PubMed queries and continue to the
existing verdict policy. The standalone verdict loader rechecks this eligibility;
legacy unaudited rows fail closed. `partial` (missing required slots or source
concepts), `pico_only`, and `unresolved` remain blocked. No judge,
citation, search-isolation, or production-release guard changes. Nondiagnostic
exposure words such as `regular` and `usage` are omitted from lexical query
terms, while the exact qualified exposure stays in frozen PICO and audits.

**Reason:** a colloquial but explicit exposure such as "regular usage of soy"
must not silently become a fabricated vocabulary match or be rejected solely
because MeSH lacks an exact synonym. The original two-clause sentence exposed
both an omitted model outcome and discarded shared subject. The bounded repair
and source-checked coordination preserve that meaning without treating an
unresolved terminology code as missing medical evidence.

## ADR-027 — Treat extractor rate limits as operational failures

**Decision:** keep the configured ChatGPT extraction model and the existing
one-retry/total-deadline boundary. A provider HTTP 429 is logged with only its
status code, optionally waits for a numeric or date `Retry-After` within the
remaining deadline, and becomes `claim_extractor_rate_limited` if retry is
exhausted or cannot fit the deadline. The web client presents extraction
outages and rate limits as operational failures, never medical verdicts. No
silent fallback to another model or fabrication of claims is permitted.

**Reason:** the live Miri catalog listed `chatgpt-auto`, but a chat probe
returned 429 and the user's analysis stopped before extracting any claim.
Immediate retries and a generic verification-failure screen obscured the
actual operational condition.

## ADR-028 — Keep generic aliases and unrelated studies out of selected evidence

**Decision:** an isolated generic MeSH entry term such as `consumption` must
not resolve a multiword exposure to `Economics`. Query planning falls back to
the source-grounded PICO slot when an entity is only a generic alias or a
population modifier. The linker likewise leaves an exposure unresolved rather
than recording `Male` as its intervention when it occurs only in an explicit
demographic suffix. Query planning retains an outcome qualifier in a bounded
lexical variant. Explicit nonhuman study subjects in a title take precedence
over ambiguous mixed species metadata. Nonhuman studies for claims without an
explicit animal subject, and documents without a sufficiently direct two-core-
concept focus, remain in the immutable, auditable Evidence Pack but are not
selected for judge prompts. If no paper qualifies, selection may be empty;
retrieval never manufactures a substitute. These are relevance and
applicability heuristics, not medical support or contradiction judgments.

**Reason:** the live soy run linked `consumption` to `Economics`, queried only
that MeSH concept for the estrogen claim, and omitted soy from the muscle
query. A later retrieval included papers explicitly about ducks, crabs, pigs,
and broilers despite the human-health context; one pig paper even had both
`Humans` and `Animals` MeSH tags. The source-grounded queries and conservative
selection keep such hits auditable without presenting them as direct medical
evidence. Judge qualification and verdict gates are unchanged.

## ADR-029 — Bound development model diagnostics and distrust provider JSON mode

**Decision:** In development/test only, a single-process, expiring trace records
actual extraction/judge call states, typed failures, and at most 3000 characters
of visible completion content per event. It never records requests, provider
reasoning fields, or credentials; production/staging ignore `DEBUG_MODE`.
This diagnostic trace is not a durable audit or a provider-wide heartbeat.
OpenAI-compatible extraction repeats a JSON-only instruction in the system
message because a live provider ignored `response_format`. Exact unique
source spans may have arithmetic offsets corrected locally; non-unique or
invented spans still fail validation. An empty claim array for source text
containing an explicit health-relation cue gets the existing single retry and
then a typed failure, not a fabricated claim.

**Reason:** live Ling output was sometimes YAML-like or contained correct
source text with incorrect offsets, producing no claims. Other long requests
still timed out at the configured deadline. Developers need to distinguish
calling, responding, invalid content, and provider unavailability without
loosening medical evidence or public-release gates.

## ADR-030 — Cross-check inconclusive evidence use in development only

**Decision:** development/test orchestration uses `fixture_or_evaluation`
aggregation and may send each cited frozen passage to a different configured,
non-search judge-family model through a no-tools entailment adapter. Strict
E-ID JSON results, provider/model, and prompt hashes remain in append-only
validation audits. The adapter is not approved for production. A partially
scoped source may qualify an *inconclusive* evaluation assessment only when
every cited use is semantically validated and no other material warning is
present; decisive and production gates remain unchanged. Such citations may
appear as `relevant_but_insufficient` cards with the evaluation notice. Old
reports are never rewritten.

**Reason:** the hypertension/cancer run had relevant observational passages
and two inconclusive judges but no live citation validator. A first live
validator confused "supports the explanation of insufficiency" with "proves
the causal claim"; the versioned prompt now distinguishes them. Ling HTTP 500
outages remain separate operational failures with no silent model fallback.
The changed abstention qualification is versioned as `verdict-policy-1.1`
and `verdict-engine-1.1`; report rendering is `report-builder-1.1`.

## ADR-031 — Bound judge citation selection and audit protocol-only repair

**Decision:** judge prompt `judge-1.6-2026-09-29` requires the smallest set
of passages that directly supports each cited use. It warns against adding
generic background, indirect estimates, or title-only topical matches to a
decisive judgment. The independent citation validator and verdict thresholds
are unchanged. If a provider omits only the constant `schema_version`, local
parsing can insert `1.0` and revalidate the entire decision. The append-only
judge row marks `schema_version_inferred`; production qualification rejects
that row. No medical content, citation, or label is silently repaired, and an
old judge or verdict run is never rewritten.

**Reason:** a live smoking/lung-cancer run had direct frozen passages, but two
decisive judgments also cited weaker passages and failed citation validation.
The third provider returned otherwise structured JSON without the mandatory
protocol version. Topical over-citation should be reduced at generation;
protocol-only omission should be visible in the audit rather than disguised
as a fully native schema-valid answer.
Invalid citation IDs or unlisted E mentions may use the existing single
retry, but the first response remains rejected and citations are never
silently removed from a model decision.

## ADR-032 — Require standalone atomic claims and measure endpoint fit separately

**Decision:** the exact redacted `raw_text`/offsets remain immutable source
provenance. For new claims, a deterministic validator constructs independently
readable `normalized_text` only from the clause itself or an adjacent,
unambiguous English shared subject. The persisted `standalone_status` and
verified antecedent offsets distinguish reconstructed text from a literal
source span. Uncertain/incomplete fragments are `partial` and stop before
normal retrieval. A source-grounded population can be carried to PICO; no
unstated qualifier or causal strength is inferred.

**Decision:** preserve broad PubMed recall and add bounded endpoint-focused
precision queries for explicit measured outcomes. Score title/abstract
outcome-as-endpoint signals separately from topical `retrieval_score`,
relationship directness, study quality, integrity, and applicability. Favor
measured outcomes in selection; mechanistic/background/unrelated endpoint
hits remain auditable. Contrary findings can be highly endpoint-direct.
Normalize selection priority by the maximum title-bonus weight so ties at
1.0 do not erase ordering; demote reverse/incidental relationships and
post-disease endpoints for disease-risk claims without treating those
signals as a medical verdict. If an extractor inflects only the leading
relation verb in a proposed outcome, retain the exact remainder only when
it occurs verbatim in the atomic source span.
When three strong quantitative-endpoint documents are present, do not fill
selection with documents scoring below 0.35 on endpoint directness; preserve
all such documents in the auditable pack. Keep broader directly measured
studies eligible even when their titles use less specific hormone wording.
Evidence Pack 1.4 freezes endpoint factors and the changed selection order;
historic Pack 1.3 retains its exact canonical hash path. A nullable claim
status column requires migration `20260929_0016`; old rows remain nullable
rather than being falsely certified as reconstructed.

**Reason:** coordinated soy claims lost the shared subject even though PICO
could recover it, while estrogen-related meningioma/bone-health papers could
rank as topical matches without measuring the asserted hormone endpoint.
These are extraction and retrieval-selection defects, not grounds to change
judge labels, citation validation, verdict thresholds, or report templates.

## ADR-033 — Validate attributed findings before proposed conclusions

**Decision:** new judge requests use strict decision schema 2.0: one
source-attributed statement per finding/method/limitation, exact quote and E
ID for each reference, and a separate proposed-label justification naming
its statement IDs. A statement may cite multiple frozen passages jointly.
Judge input `judge-input-2.0` groups exact frozen sections by selected
document, records omitted E IDs and a content hash, and is identical for all
judges. Passage IDs remain from the immutable Pack; historical Pack 1.3/1.4
hashes and old judge rows are not rewritten. The old **whole free-text
explanation against each individual citation** approach in ADR-021 is
superseded for new runs. Historical v1 decisions remain readable, but no
statement mappings are inferred for them under policy 1.2.
Snapshot equivalence is checked by canonical JSON content hash after JSONB
round-trip, not Python tuple/list object equality; the latter caused a live
false provenance failure and is covered by a regression test.

**Decision:** `judge-validation-2.0` first checks pack/input/quote/number
provenance per statement, then asks a no-tools semantic validator whether the
*statement* is attributed, and separately whether validated findings justify
the proposed label for the *original claim*. Typed target-specific issues
identify judge statement versus user claim versus source metadata. A correctly
quoted estimate from one study is not compared with every other citation or
with a user claim number. OR/RR/HR and other typed measures are not silently
substituted. Missing context stays uncertain. The source can contradict the
user claim while supporting an accurate judge statement; a null result alone
does not establish absence of effect. Valid findings remain recorded even
when a conclusion fails. Mock semantic providers test orchestration only;
the bounded, opt-in real-model semantic command is not clinical validation.

**Decision:** after a target-specific invalid validation, at most one
same-provider, same-model semantic revision may be requested. It sees only
the original claim, the *same* frozen input, its own response, and its own
issues. The new append-only judge row links to its parent and gets one model
attempt, without another schema retry. An explicit claim checkpoint names
only the active run per slot for aggregation; parent and failed revision rows
remain audit records, never second votes. Database uniqueness prevents a
second child revision. `verdict-policy-1.2` retains existing 2/3 minimum
judge counts and production identity/family/search/validator gates; it accepts
only v2 validation. Policy 1.1 remains for historical fixtures and audit
reading, not reinterpretation of old free text.

**Decision:** report contract 1.1 and builder 1.2 attribute numeric issues to
the actual target. An Unable result in development may show a separate
neutral set of exact frozen, hash-verified retrieved excerpts, explicitly not
validated support or opposition. Staging/production still deny unqualified
reports. Debug events bind analysis/claim/judge/validation/call, operation,
statement/E IDs, and revision; `calling` means awaiting a response. Stage
execution is displayed separately from accepted assessment counts.

**Reason:** retained sunscreen analysis
`9338114b-f9fe-4642-b1e3-29830073400f` proved the old contract could
cross-compare two studies' numbers, label E8 as contradicting judge use while
its explanation said it opposed the *user claim*, and blame a nonexistent
numeric magnitude in the claim. It also showed PMID 21135266's METHODS and
RESULTS frozen but hidden behind its selected CONCLUSION. None of these
observations establishes a particular sunscreen verdict; the old 1-of-3
qualified Unable result remains an immutable historical outcome.

## ADR-034 — Permit a clearly provisional single-assessment result in development

**Decision:** new live V2 runs use `verdict-policy-1.3`. Only in
`fixture_or_evaluation` mode, for a standard-risk claim, one fully validated
decisive judge assessment may yield a provisional `supported` or
`contradicted` result. The report labels this “Provisional … (Development
Only),” keeps `production_qualified=false`, displays its exact validated
citations, and records `EVALUATION_SINGLE_VALIDATED_ASSESSMENT` alongside all
excluded-assessment reasons. Zero qualified judges, an inconclusive qualified
judge, partial/invalid validation, no selected evidence, and high-risk claims
cannot use this branch. Production still requires two independently qualified
judges for standard risk and three for high risk, plus all existing identity,
search-isolation, provenance, and approved-validator gates. Policies 1.1 and
1.2 and historical append-only records are unchanged. This is a prototype
demonstration output, not a public medical report or a substitute for the
Phase 8 clinical evaluation benchmark.

For causal/prevention/treatment wording under policy 1.3, a decisive label
also needs at least one *conclusion-cited* trial or evidence synthesis in the
frozen Pack. An observational/unknown-design citation alone yields
`not_enough_evidence` with `CAUSAL_EVIDENCE_TOO_INDIRECT`, even when a semantic
model mistakenly calls a reverse-direction association decisive. Study-design
metadata is a conservative sufficiency gate, not a truth vote; a trial or
synthesis still needs normal attribution and conclusion validation.

**Reason:** live runs on a direct smoking/lung-cancer association found and
validated strong cited evidence but frequently lost the second vote to
provider response-shape or semantic-validator availability. Reporting only
`Unable to Verify Reliably` hid that one assessment had actually passed every
available evidence-use check. A versioned, visibly provisional evaluation
result preserves useful prototype behavior without silently releasing a
single-model medical verdict.

## ADR-035 — Increase retrieval recall and repair validation contract edges

**Decision:** the PubMed query planner retains MeSH/source-grounded queries
and adds bounded automatic-term/lay-word fallbacks when a literal phrase is
overly restrictive. Selection ranks direct exposure-outcome endpoint studies
above generic topical articles and keeps exclusions in the auditable Pack.
The judge accepts at most eight attributed statements and 1,200 conclusion
characters, while its prompt still requests one or two concise decisive
findings. Exact source IDs and quotes, numeric alignment, semantic validation,
and the frozen input hash remain mandatory. The numeric parser recognizes
`confidence interval (CI)` as well as `CI`, avoiding comparison against the
wrong interval in a multi-estimate passage. The semantic validator receives
and must echo exact required statement/evidence identifiers. Statement
attribution deliberately omits the original claim so the model cannot
confuse a source-to-statement check with the final claim check. No retrieval
rank is treated as a medical support vote.

**Reason:** the carrot/eyesight smoke had no selected papers because the
literal query missed ordinary vision wording; smoking/lung-cancer runs had
direct studies yet lost judges to bounded JSON-shape issues and one false
numeric mismatch. These repairs improve reachability and audit fidelity, not
the medical truth threshold for a production verdict.
