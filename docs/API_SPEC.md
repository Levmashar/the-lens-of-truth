# API Specification

Base path: `/v1`. Phase 2 performs secure intake, OCR for screenshots, PII
masking, and atomic-claim extraction only. It does not retrieve evidence or
return a medical verdict. Phase 3A additionally returns claim-grounded PICO
and terminology-linking state; it does not retrieve evidence. Phase 3B can
resolve MeSH descriptors from an installed official NLM release. Phase 3C
adds controlled claim types and a source-grounded completeness audit.
Phase 4A adds developer-only, PubMed-only evidence preview without a verdict.
Phase 4B adds document integrity, Crossref DOI enrichment, and methodology
metadata. Phase 4B.1 adds transparent relationship-directness and selection
metadata. Phase 5A adds a development-only CLI for independent judgments over
an existing frozen pack. Phase 6A adds a developer-only per-judge validation
CLI and audit table. Neither changes public API responses or returns a final
medical verdict. Phase 6B adds an internal deterministic aggregator and
append-only audit; no public endpoint or frontend response changes.
Phase 6C adds an internal deterministic report contract and developer CLI.
Phase 7A adds a background analysis run and a claim-scoped, server-gated read
route for its frozen report. No separate verdict route or new medical report
model is introduced. The Phase 7A route contracts below supersede earlier
Phase 2-only lifecycle descriptions.

## Phase 7A asynchronous analysis lifecycle

The Phase 7B browser app consumes this contract directly. It first uploads a
screenshot when selected, then sends the upload UUID in the ordinary 202 start
request. It sends the versioned consent acknowledgement and a per-attempt
`Idempotency-Key`; uncertain network retries reuse the key. The browser then
navigates to `/analysis/{analysis_id}` and polls the two GET endpoints below.
Refresh of that route reads the existing run; it does not POST again. Each
completed claim with `report_run_id` is read once from the gated report route.
The browser does not use the one-shot SSE snapshot as a stream. Neither the
browser nor the API exposes a production-unqualified report in
staging/production; development/test can inspect one with the mandatory
evaluation notice. The app does not support URL input yet.

`POST /v1/analyses` returns 202 before OCR, extraction, or any external
retrieval/model call. The response contains `analysis_id`, `status: queued`,
`stage: queued`, `claim_count: 0`, and `completed_claims: 0`. Send an opaque
8–128-character `Idempotency-Key` to make a network retry return the same
run; reusing it with different request content returns 409. No key means a
deliberately new run. URL input still returns 501. Text and screenshot
requests keep the existing body/consent/upload contracts below.
Reusing a key whose analysis has expired returns 410; use a new key for an
intentional new analysis.

`GET /v1/analyses/{analysis_id}` polls the durable run. It returns:

```json
{
  "analysis_id": "c5eb3f8d-5c9e-45d5-b88d-b5152b2de95a",
  "status": "running",
  "stage": "retrieving",
  "completed_stages": ["extracting"],
  "stage_timestamps": {
    "extracting": {
      "started_at": "2026-09-28T10:00:00+00:00",
      "completed_at": "2026-09-28T10:00:20+00:00"
    }
  },
  "claim_count": 2,
  "completed_claims": 0,
  "failure_code": null,
  "language": "auto",
  "input_type": "text",
  "claims": [],
  "screenshot_ocr": null,
  "debug_enabled": false,
  "updated_at": "2026-09-28T10:00:21+00:00"
}
```

`claims` contains existing redacted `AnalysisClaim` objects after extraction;
before then it is empty and input/OCR metadata may be null. Stages are
`queued`, `extracting`, `normalizing`, `retrieving`, `judging`, `validating`,
`aggregating`, and `building_report`. Run status is `queued`, `running`,
`completed`, `failed`, or `partially_completed`. `failure_code` is a safe
category, never a raw provider response or prompt. Old Phase 2 submissions
without an AnalysisRun still use their historical detail response.

`GET /v1/analyses/{analysis_id}/claims` returns one independent
`ClaimAnalysisSummary` per extracted atomic claim. It includes claim ID and
ordinal, stage/status/completed stages/timestamps, safe failure code, exact
`evidence_pack_id`/`evidence_pack_hash`, `judge_run_ids`,
`judge_validation_run_ids`, `verdict_run_id`, `report_run_id`,
`production_qualified`, and `result_label`. A failed technical claim has a
safe `failure_code` and a null `result_label` until a VerdictRun actually
exists; `not_enough_evidence` only comes from successful retrieval/policy.
Staging/production hide the label of any non-production-qualified verdict.
No "latest artifact" fallback is used.

When `DEBUG_MODE=true` and `APP_ENV=development|test`, the polling response
sets `debug_enabled=true` and claim summaries additionally contain
`debug_judge_runs`: slot, provider/model/family, success/failure category,
attempt count, latency, and optional citation-validation status/error code.
The browser uses existing stage timestamps and safe failure codes to show a
development diagnostic panel. The analysis response also includes
`debug_models` (role, provider, model, and last actual call state) and
`debug_events` (attempt, HTTP status, duration, typed failure, and up to 3000
characters of the model's visible response content). `calling` means a request
is still in flight; `not_called` is not a provider health check. These
process-local traces expire after one hour and are not persisted. They may
echo submitted text, so do not use development debug with secrets. Prompts,
provider reasoning fields, credentials, and exception traces are not returned
as diagnostic fields. With the flag off, or in staging/production,
`debug_enabled=false` and debug fields are null. `GET /healthz` also
reports the effective `debug_enabled` state.

`GET /v1/analyses/{analysis_id}/claims/{claim_id}/report` returns the existing
`LensReport` JSON from the exact checkpointed `report_run` only after verifying
its semantic hash, the recomputed frozen Evidence Pack content hash,
claim/Pack/verdict provenance, audit IDs, and qualification.
It does not fetch or discover sources. A missing report is 404, corrupt
provenance is 503, and a non-production-qualified report is 403 in staging or
production. Development/test can inspect such a report, which retains its
mandatory development/evaluation notice and `production_qualified: false`.
Current Miri/entailment gates make live reports non-production. This is not a
trusted public medical verdict API.

`GET /v1/analyses/{analysis_id}/events` emits one SSE-formatted
`analysis.progress` snapshot. Poll `GET /{analysis_id}` for updates; there
is no long-lived event bus in Phase 7A. All analysis responses are
`Cache-Control: no-store` and `Referrer-Policy: no-referrer`. UUID-only
anonymous access is a prototype convention, not reviewed public auth.

## Phase 6C internal report contract (no HTTP route)

### Current schema-2.0 contract overlay

The Phase 5A/6A text below records the historical schema-1.0 CLI contract.
For new runs, `JudgeDecisionV2` requires `schema_version: "2.0"`, a proposed
`label`, 1–8 source-attributed `statements` (`statement_id`, `text`, `kind`,
and exact `evidence_refs` containing E ID plus quote), a `conclusion` naming
the statement IDs it relies on, and controlled `uncertainty_reasons`.
`judge_run` additionally freezes `judge-input-2.0` JSON/hash and optional
revision parent/number. Historical rows remain readable without inferred
statement mappings. Validation 2.0 returns per-statement attribution status,
scope, typed target issues, and a separate conclusion-justification status.
Only a fully validated proposed conclusion is eligible under
`verdict-policy-1.3` for new live runs. Standard-risk development reports may
show an explicitly provisional Supported/Contradicted result from one such
assessment; they remain `production_qualified=false`. Production still
requires two independently qualified judges; high-risk still requires three.
Historical policy 1.2 records are not reinterpreted.

`LensReport` 1.1 can include `neutral_retrieved_sources` for an Unable result
in development when the frozen Pack hash verifies. These exact excerpts are
not attributed support/opposition and are not public-release evidence cards.
The claim debug response includes judge/validation/call IDs, operation kind,
statement/E IDs, and semantic revision number where available. A `calling`
event means an outstanding request, not an empty provider response. The
opt-in `python -m app.validation.semantic_eval --run --slot 2 --limit 14`
checks the configured semantic model against synthetic hand-reviewed cases;
it is not part of CI or a clinical-accuracy claim.

After `alembic upgrade head`, pass the UUID of one persisted `verdict_run`:

```text
python -m app.report.smoke <verdict-run-uuid>
```

The command is limited to `APP_ENV=development|test`. It reads only that
VerdictRun and the explicit Evidence Pack, judge-run, and validation-run IDs
already recorded in it; missing or mismatched provenance fails closed. No
retrieval, model call, latest-row selection, or verdict recomputation occurs.
Each invocation appends a new `report_run` audit row and prints its UUID and
semantic hash. Reruns with the same frozen inputs and builder version have
the same semantic hash despite a new row and generation timestamp.

`LensReport` version `1.0` contains `claim` (exact submitted atomic text and
type), the unchanged four-way `verdict` and display label, `headline`,
`short_summary`, controlled `why_this_result` code/text pairs,
`key_evidence` source cards, `evidence_limitations`, `judge_summary`,
`verification_status`, `sources`, separate `safety_notice`, mandatory
`production_qualified`, provenance, and semantic hash. A source card contains
the frozen E ID, PMID, optional DOI, title, journal/date/design, integrity
status, citation role(s), exact bounded passage excerpt, passage hash/section,
stored source URL, validation indicator, and explicit citing audit IDs.
Source text is never an LLM-generated summary. Only selected passages cited
by fully validated qualified assessments appear; `unable_to_verify_reliably`
has no evidence cards. A non-production report always includes an explicit
development/evaluation notice. The contract has no truth-probability field.

## Phase 5A developer judging command (no HTTP route)

After migrating the database, set one to three verified judge slots in the
local environment (`JUDGE_N_PROVIDER`, `JUDGE_N_MODEL`,
`JUDGE_N_MODEL_FAMILY`, optionally `JUDGE_N_BASE_URL`/`JUDGE_N_API_KEY`).
For Miri, a slot can reuse the existing extraction gateway URL and key. Use
only non-search model modes and independent actual families. Find a persisted
pack ID with `SELECT id, claim_id, snapshot_hash FROM evidence_pack ORDER BY
created_at DESC LIMIT 10;`, then run:

```text
python -m app.judging.smoke <stored-evidence-pack-uuid>
```

The command is restricted to `APP_ENV=development|test`. It reads an existing
Evidence Pack 1.3, verifies its semantic hash, passes only its ordered
`selected_evidence_ids` and exact frozen passages to each judge, persists one
append-only `judge_run` per slot, and prints pack hash, family/model, status,
label, citations, concise reason, latency, and descriptive agreement counts.
It prints `NO FINAL VERDICT`. A missing pack, no configured slot, duplicate
families, or an invalid pack fails before any provider call. Provider failures
are recorded per slot and do not turn into a medical label. The CLI does not
expose raw provider responses or secrets.

Search-enabled Miri modes are rejected by default. For a development/test
plumbing smoke only, `JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT=true` allows the
request but prints `DEVELOPMENT OVERRIDE` before calls. Staging/production
still reject the mode even with that setting. Every run in a bypassed ensemble
records `search_override_active=true` and
`search_isolation_verified=false`; search-mode slots additionally record
`search_guard_bypassed=true`. Do not interpret those model outputs as a
verified same-evidence medical evaluation; Miri-native browsing cannot be
proven disabled by this adapter.

Judge output schema version `1.0` requires: `label` (`supported`,
`contradicted`, `not_enough_evidence`), `cited_evidence_ids`,
`opposing_evidence_ids`, `reasoning_summary`, `claim_strength_assessed`,
`evidence_sufficiency`, and controlled `uncertainty_reasons`.
`unable_to_verify_reliably` is not a judge label. Citation existence is
checked against the selected E IDs only. Phase 6A independently revalidates
citations, numbers, scope, relation strength, and optional entailment; final
verdict aggregation remains unimplemented.

## Phase 6A developer validation command (no HTTP route)

After `alembic upgrade head`, select a successful stored judge run ID from
`SELECT id, model, outcome_status FROM judge_run WHERE decision_json IS NOT NULL
ORDER BY responded_at DESC LIMIT 10;` and run:

```text
python -m app.validation.smoke <stored-judge-run-uuid>
```

The command is development/test-only. It reads the run's frozen Pack 1.3,
performs deterministic checks without retrieval, and persists a new
append-only `judge_validation_run` row. It prints per-citation existence,
numeric/scope/relation/entailment statuses, issue codes, the individual judge
validation status, and `NO FINAL LENS VERDICT`. `validated`,
`partially_validated`, `invalid`, and `unable_to_validate` describe validation
of a judge's evidence use, not medical verdict labels. No live entailment
provider is configured in Phase 6A; absent semantic validation remains
`unable_to_validate` unless a deterministic fatal defect is found.
Search-bypassed Miri runs remain untrusted development plumbing records.

## Phase 6B developer aggregation command (no HTTP route)

After `alembic upgrade head`, explicitly select a stored Pack 1.3 ID, judge
run IDs, and corresponding validation run IDs. No "latest" lookup occurs in
the aggregator:

```text
python -m app.verdict.smoke --pack <pack-uuid> \
  --judge-runs <judge-uuid,judge-uuid> \
  --validation-runs <validation-uuid,validation-uuid> \
  --mode production
```

The CLI is restricted to `APP_ENV=development|test`; `production` above is the
*aggregation policy mode*, not permission to invoke the CLI in production.
An empty `--judge-runs "" --validation-runs ""` is allowed for a genuinely
successful no-results pack. The command prints the claim, pack hash, policy,
qualification/exclusion diagnostics, one of exactly four internal labels,
reason codes, semantic hash, and new audit UUID. It does not call an LLM or
network service or generate a patient-facing explanation.

`fixture_or_evaluation` mode exercises offline policy fixtures and always
records `production_qualified=false`. Production mode requires audited
model identity/snapshot, verified distinct families and search isolation,
and a policy-approved one-passage entailment provider. None is approved in
`verdict-policy-1.1`, so existing Miri runs and synthetic fixtures cannot
produce a production-qualified decisive verdict with the default policy.
`not_enough_evidence` means retrieval succeeded but validated evidence does
not justify a decisive conclusion; `unable_to_verify_reliably` means a
technical, provenance, normalization, qualification, or validation failure.
Partial or invalid judge validations never count as decisive labels. In
development/test evaluation only, a partial-scope inconclusive citation use
may qualify after independent live semantic checking; it remains non-production. No
numeric truth confidence is returned. The internal `verdict_run` table is
append-only; no public `GET` or `POST` verdict route is added in Phase 6B.

## `POST /v1/analyses/uploads/screenshots`

Accepts multipart field `screenshot`. Client MIME and filename are advisory;
the backend decodes and sniffs the image itself. Only single-frame PNG, JPEG,
and WebP images within server-set byte and pixel limits are accepted. The image
is metadata-stripped by re-encoding it to PNG before private storage.

```json
{
  "upload_id": "b3b2cde5-75da-4997-9a8d-34561fc208cc",
  "status": "uploaded",
  "media_type": "image/png",
  "byte_count": 81234,
  "width": 1080,
  "height": 1920,
  "purge_after": "2026-09-25T10:00:00Z"
}
```

The raw screenshot is retained outside PostgreSQL for no more than 24 hours.

## `POST /v1/analyses/uploads/screenshots/{upload_id}/ocr-preview`

Available only when `APP_ENV` is `development` or `test`. Re-runs OCR for a
still-valid upload and returns redacted recognized text, line bounding boxes,
per-line confidence, aggregate confidence, and the number of structured-PII
redactions. The preview output is ephemeral and is never written to PostgreSQL.
It is intentionally unavailable in staging and production.

## `POST /v1/analyses/claim-preview`

Available only when `APP_ENV` is `development` or `test`. Accepts the same
request body as `POST /v1/analyses` and performs OCR when given a screenshot
upload ID. It returns the configured AI extractor's redacted atomic claims,
grounded PICO fields, entity mentions, normalization status, model metadata,
and screenshot OCR metadata without creating a
submission or claim row in PostgreSQL.

This is the quickest way to test a configured gateway:

```powershell
$body = @{
  schema_version = "1.0"
  client = "web"
  lang = "auto"
  input = @{ type = "text"; text = "Vitamin C prevents common colds." }
  consent = @{ privacy_notice_version = "2026-09-01"; accepted = $true }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post `
  -Uri "http://localhost:8000/v1/analyses/claim-preview" `
  -ContentType "application/json" `
  -Body $body | ConvertTo-Json -Depth 8
```

The response is ephemeral. Each claim also includes `normalization_quality`
with lexical `normalization_coverage`, `missing_explicit_concepts`,
`required_slots_missing`, `ambiguous_concepts`, and `normalization_warnings`.
It does not expose the gateway's raw response or
unredacted source text.
`raw_text` and offsets are the exact redacted source span. `normalized_text`
is the independently readable claim; a coordinated clause may repeat a
source-verified subject without changing `raw_text`. `standalone_status` is
`complete`, `reconstructed`, `uncertain`, or `incomplete`. The optional
`resolved_from_span_start/end` offsets trace inherited words in the redacted
source. Uncertain/incomplete fragments are not retrieval-ready.
The `verifiability` field is a numeric estimate of testability, not medical
truth. If the browser gateway supplies a qualitative label instead of a number,
the preview returns `null` for that field while retaining locally validated
claim spans.

## `POST /v1/analyses` request body

Reserves the asynchronous Phase 7A run described above. The existing consent
and Phase 2 intake safeguards are unchanged; extraction happens after 202.

Text request:

```json
{
  "schema_version": "1.0",
  "client": "web",
  "lang": "auto",
  "input": {"type": "text", "text": "A health claim to verify."},
  "consent": {"privacy_notice_version": "2026-09-01", "accepted": true}
}
```

Screenshot request:

```json
{
  "schema_version": "1.0",
  "client": "web",
  "lang": "auto",
  "input": {"type": "screenshot", "upload_id": "b3b2cde5-75da-4997-9a8d-34561fc208cc"},
  "consent": {"privacy_notice_version": "2026-09-01", "accepted": true}
}
```

Successful run reservation returns HTTP `202`:

```json
{
  "analysis_id": "c5eb3f8d-5c9e-45d5-b88d-b5152b2de95a",
  "status": "queued",
  "stage": "queued",
  "claim_count": 0,
  "completed_claims": 0
}
```

Extraction requires a configured adapter. The `miri` adapter calls the
gateway's ChatGPT Auto chat completion and validates its JSON reply and source
offsets locally. It retries at most once for malformed output, timeout,
transport errors, HTTP 429, or HTTP 5xx; ordinary HTTP 4xx fails immediately.
Each attempt is limited to 55 seconds by default, with a 115-second deadline
for the complete extraction. Both limits are configurable within a 60-second
attempt maximum and a 120-second total maximum.
Retrying malformed output never includes the invalid answer in the new prompt.
When disabled or unavailable, background processing records a safe failed
analysis state (the development claim-preview route still returns a typed
HTTP error directly). URL input remains unsupported and returns `501`.
Two exhausted extractor timeouts record `claim_extractor_timeout`; an overall
extraction deadline records `claim_extractor_deadline_exceeded`. The 202 start
call does not wait to return those errors. Safe progress failure codes and
public synchronous errors never expose provider bodies, prompts, or keys.

## `POST /v1/analyses/evidence-preview`

Available only in `development` and `test`. Requires an existing stored claim,
which can be obtained from `POST /v1/analyses` followed by
`GET /v1/analyses/{analysis_id}`. It does **not** rerun extraction or change
claim/PICO semantics. Configure a real developer contact with `NCBI_EMAIL`.

```json
{
  "analysis_id": "c5eb3f8d-5c9e-45d5-b88d-b5152b2de95a",
  "claim_id": "9cf824bf-f871-4f22-b5b3-6dd6f0e8fd99"
}
```

HTTP 200 returns `evidence_pack` and `diagnostics`. The pack contains a
`claim_snapshot` (redacted raw/normalized claim, controlled type, PICO, MeSH
entities), `query_plan` (version, source, query IDs/families/field provenance),
  normalized PubMed `documents`, **all** ranked exact-text `passages` with E1/E2
  IDs, ordered `selected_evidence_ids`, `retrieved_at`, and `snapshot_hash`.
  Version 1.3 distinguishes the diversified judge-facing selection (eight by
  default; at most one passage per document) from the complete audit set.
  Each passage exposes `passage_type`, `selected_for_judging`, `selection_reason`,
  and numeric coverage/background/diversity factors. A query's
  `relation_semantics` preserves causal versus association wording. Passage
  factors and `retrieval_score` measure topical relevance only, never evidence
  quality or medical truth. Each document additionally carries `integrity`
  (`status`, `sources`, `checked_at`, `check_version`, `warnings`, structured
  references, and per-provider checks), optional `crossref` enrichment,
  `metadata_provenance`, canonical `study_design` and its source,
  `quality_prior`, `quality_factors`, and `applicability_warnings`. Crossref
  preserves its own DOI/work type/publisher/published/deposited dates and
  update/relation references; it never overwrites PubMed's bibliographic fields.
  DOI checks are individually timed and collectively limited to a configurable
  30-second enrichment budget; unfinished checks become failed/unknown without
  discarding PubMed evidence.
  A retracted document remains in `documents` and `passages`, but its passages
  have `selection_reason: retracted_excluded` and are absent from
  `selected_evidence_ids`. An integrity-unknown document may still be selected
  with warnings. Historical 1.0/1.1/1.2 packs remain readable, but lack one or
  more current integrity/directness fields and must not be silently treated as
  current judge-ready selections.

In version 1.3, each document and passage additionally exposes
`relationship_directness: {score, direction, factors, reasons, warnings}`.
`direction` is `aligned`, `reverse`, `incidental`, or `unknown`. Factors expose
core-concept occurrence/proximity, section weighting, incidental/exclusion
penalties, and post-outcome or contextual framing. Passages also expose
`selection_priority_score` and `selection_factors` (topical, passage/direct
document, methodology, applicability components). This priority determines
the default selected order, subject to one passage per PMID and retraction
exclusion. A low-directness passage remains in `passages`; it is never deleted.
`relationship_directness.score` means fit to the structured claim question,
not quality, support, contradiction, clinical confidence, or a verdict. An
`aligned` relation can report either a positive or a negative finding.

New Pack 1.4 additionally includes independent `endpoint_directness` on each
document and passage (`score`, numeric `factors`, `reasons`, `warnings`).
It measures whether the asserted outcome is studied or measured, not whether
the study supports the claim. QueryPlan 1.1 may add bounded `endpoint` query
families alongside broad recall queries; explicit population terms are added
only to a separate precision variant. Selection factors now separate topical,
relationship, endpoint, methodology, and applicability contributions, plus
an endpoint-focused title bonus and indirect-endpoint penalty. All
demoted passages remain in the frozen pack. Historic Pack 1.3 hashes use their
original serialization and are never rewritten.
The selection score is normalized by 1.16 to preserve ordering above the
pre-bonus ceiling; reverse/incidental relationship and post-disease endpoint
warnings are auditable separately from support or contradiction.
When at least three direct quantitative-endpoint documents are available,
documents below 0.35 endpoint directness are retained in the pack but not
used to fill the selected-evidence quota.

`integrity.status` is `valid`, `retracted`, `expression_of_concern`,
`corrected`, `updated`, or `unknown`. `valid` means only that the configured,
applicable integrity checks finished without a detected issue. A PubMed or
Crossref failure yields `unknown` unless the other source reports an explicit
issue. `quality_prior` is a design-methodology heuristic, neither medical
truth probability nor support for the submitted claim. It is separate from
`retrieval_score`; selection considers topical relevance alongside separate
relationship directness and applicability factors.

`diagnostics.status` is `ok`, `no_results`, or `partial_metadata` (some PMIDs
were returned but EFetch records were missing, incomplete, or outside the
article-only normalizer). `reason_counts`
distinguishes `missing_efetch_record`, `incomplete_efetch_record`, optional
`optional_doi_absent`/`optional_abstract_absent`, `incomplete_publication_date`,
`unsupported_efetch_record_type` (for example, a PubMed book record),
`crossref_not_applicable`, `crossref_lookup_failed`, `crossref_not_found`, and
`integrity_source_unavailable`. Optional DOI or abstract absence does not by
itself make the status `partial_metadata`. The diagnostics also include
`integrity_status_counts`, `crossref_status_counts`, and `doi_coverage`.
No results produces a
valid empty pack. Technical failures return typed public errors:
`pubmed_timeout` (504), or `pubmed_transport`, `pubmed_upstream_http`,
`pubmed_rate_limited`, `pubmed_malformed_response` (503). They never expose
the API key, response body, raw prompts, or arbitrary external URLs. An
unconfigured contact email returns `pubmed_not_configured` (503).
No verdict or explanation field exists in this response.

The pack is append-only. A repeat preview creates a new retrieval run and
pack; canonical hashing excludes wall-clock retrieval/check timestamps but
includes claim, query, source content, integrity/check results, Crossref
enrichment, methodology/applicability fields, ranking, directness, selection,
priority factors, and passage
text. A changed integrity result therefore produces a new hash.

## `GET /v1/analyses/{analysis_id}`

For Phase 7A runs, returns the polling envelope above plus redacted atomic
claims and safe OCR metadata once extraction has committed. `raw_text` and its
offsets refer to the redacted source representation, preserving positions while
not exposing structured identifiers. There is no verdict field.
Each claim also includes nullable `population`, `intervention_or_exposure`,
`comparator`, `outcome`, and `timeframe` fields for PICO framing. Null means the
source did not supply that detail; these model-produced fields are not evidence.
`standalone_status` and inherited offsets have the same meaning as in claim
preview. For new claims, `normalized_text` is the standalone proposition,
while `raw_text` stays the exact source slice. Existing legacy rows may have
null standalone status. An uncertain/incomplete new claim is `partial` and
cannot enter normal evidence retrieval.
Phase 3A adds `pico` (including `original_claim` and `claim_type`), `entities`,
and `normalization_status` to each claim. Existing flat PICO fields remain for
compatibility. `entities` includes source-grounded mentions; `umls_cui` and
`mesh_id` are null unless an authorized provider resolves them above the
confidence threshold. An installed MeSH index enables descriptor resolution;
without it claims normally report `pico_only` (or `unresolved` when no usable
PICO slots exist). The other statuses are `pending` for pre-migration records,
`partially_linked` when only some identified mentions are linked, `partial`
when a required slot/source concept is missing or the source scan is
incomplete, and `normalized` only when required slots and source-concept
coverage pass and all identified mentions are linked. A `normalized` label
does not imply medical truth. Prior `normalized` rows are migrated to
`partial` with `legacy_not_audited` until separately checked.
None of these statuses is a medical verdict.
The orchestration path accepts source-complete `partially_linked` claims for
lexical retrieval without creating a MeSH ID; `partial`, `pico_only`, and
`unresolved` still do not pass the normalization gate. Such a claim-scoped
failure has the safe `normalization_incomplete` code; it has no report or
medical verdict.

`claim_type` is one of `causal`, `association`, `prevention`, `treatment`,
`diagnostic`, `safety`, `recommendation`, `statistical_or_study_result`,
`methodology`, or `other` (or null on legacy/unclassified claims). Explicit
English causal/association wording controls that distinction if the model
proposes a conflicting type. The original source span remains unchanged.
Unknown new model types fail schema validation; known historic aliases are
converted to canonical types. This is an assertion category, not a verdict.

`normalization_coverage` is the fraction of high-confidence exact/synonym
MeSH source phrases represented by a grounded PICO field or entity mention;
it is null when none are detected and is not a truth/confidence score. Fuzzy
suggestions cannot create missing-concept warnings. For example, if the model
omits `common cold` from the outcome of “Vitamin C prevents the common cold,”
the claim is `partial` and its quality object includes:

```json
{
  "normalization_coverage": 0.5,
  "missing_explicit_concepts": ["common cold"],
  "required_slots_missing": ["outcome"],
  "ambiguous_concepts": [],
  "normalization_warnings": [
    "required_pico_slots_missing",
    "explicit_medical_concepts_not_represented"
  ],
  "terminology_version": "2026",
  "terminology_sha256": "<SHA-256 of the imported official MeSH XML>"
}
```

Each entity also carries `match_type` (`exact`, `synonym`, `fuzzy`, or
`unresolved`), `ambiguous`, `terminology_source`, `terminology_version`, optional
`terminology_sha256`, `tree_numbers`, optional `umls_version`, and up to three
unassigned `candidates`.
A fuzzy or ambiguous
candidate never forces `mesh_id`; `umls_cui` remains null without a licensed
UMLS provider. The original surface text is retained.

For example, without an installed terminology index, a claim may contain:

```json
{
  "pico": {
    "original_claim": "Frequent sunscreen use causes melanoma.",
    "population": null,
    "intervention_or_exposure": "Frequent sunscreen use",
    "comparator": null,
    "outcome": "melanoma",
    "timeframe": null,
    "claim_type": "causal"
  },
  "entities": [
    {
      "surface_text": "Frequent sunscreen use",
      "entity_type": "intervention_or_exposure",
      "umls_cui": null,
      "mesh_id": null,
      "preferred_name": null,
      "confidence": null
    },
    {
      "surface_text": "melanoma",
      "entity_type": "outcome",
      "umls_cui": null,
      "mesh_id": null,
      "preferred_name": null,
      "confidence": null
    }
  ],
  "normalization_status": "pico_only"
}
```

## `GET /v1/analyses/{analysis_id}/events`

For Phase 7A runs, emits one typed `analysis.progress` SSE snapshot. For
historical Phase 2-only submissions it retains the completed-stage snapshot.
Neither is a continuous event stream; polling is the current progress path.

## `GET /healthz`

Liveness endpoint. It reports that the API process is running. The lifecycle
also runs a bounded raw-upload retention cleanup loop; this endpoint does not
expose backing-service details.

## Error format

```json
{
  "error": {
    "code": "request_validation_failed",
    "message": "Request validation failed.",
    "request_id": "uuid"
  }
}
```

Server errors do not expose exception details, OCR output, uploaded image data,
or provider responses.
