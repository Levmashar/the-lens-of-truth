# API Specification

## Context-aware document reports (development/test, 2026-10-08)

Existing consent-required `POST /v1/analyses` accepts text and reviewed screenshot
text as before. Paragraph-sized input enters document mode automatically;
`GET /v1/analyses/{analysis_id}` adds `document_mode: true`. The existing status,
stage and progress fields remain. Ordinary short-claim responses are unchanged.

`GET /v1/analyses/{analysis_id}/document` returns `document-report-1.0` with:

- analysis identity/status and production qualification;
- assertion/group progress and expandable group source matches;
- every assertion's exact original spans/text, kind and status;
- separate reporting fidelity and medical interpretation;
- result/explanation, exact citations and backend-derived scientific limitations;
- duplicate links or explicit commentary/unavailable details.

There is no averaged score or forced single verdict for mixed documents. A partially
completed report can be returned while remaining chains are in flight. The endpoint
verifies frozen parents and deterministically replays saved responses; GET makes
no source/model calls. Only artifacts present at the saved report time participate.
Changed/missing provenance returns 503 `document_audit_invalid`; a not-yet-created
report returns `document_not_ready`. Expiration follows existing retention handling.
Production release remains blocked for the current unapproved evaluation contracts.

In development with debug enabled, `debug_group_runs` includes grouped raw judge
and validator responses, attempts, failures, timing/usage and item diagnostics.
Requests/credentials are excluded. `debug_errors` provides bounded sanitized precise
exceptions. Frontend Copy all diagnostics includes grouped raw replies. Public views
do not expose those development fields.

Internal validator 1.2 distinguishes source attribution/reporting checks from
clinical axes and transports exact source/quantity IDs, not generated quotations;
the public report materializes literal quotations from the frozen units. Historical
validator 1.0/1.1 and group-input 1.0 responses are replayed under their original
contracts, without silently mapping invalid old fields.

See [versions, real API runs and limitations](DOCUMENT_MODE_RESULTS_20261008.md).

## V2.4 structured quantity reference diagnostics (development only)

New normal development/test decisions and validations use 2.4. On
`GET /v1/analyses/{analysis_id}/claims`, each V2.4
`debug_judge_runs[].numeric_findings[]` uses version
`numeric-reference-comparability-2.4` and adds `source_quantity_id`, for example
`E2.U1.Q1`. `asserted_values` is retained for API compatibility and now contains
backend-owned frozen values, not parsed generated prose. There is one entry per
statement/reference, regardless of repeated model prose. Raw axes continue to
appear under `evidence_axes`. Older summaries omit the absent quantity ID.

Before a semantic assessment, comparability is pending/uncertain and
`semantic_scope_checked=false`. Afterward the existing measure/scope/numeric
effect fields describe deterministic qualification. Verified references do not
imply comparable magnitude, valid source attribution or medical correctness.
`reference_preflight_failure` identifies corrupt source/catalog/input/provenance
or quantity references; it does not describe a valid different-measure estimate.

The full source-quantity-catalog-1.0 belongs to frozen judge-input-2.4 JSONB;
the debug API still returns only its compact allowlist, without full source text.
No public verdict/report labels or report schema changed. Historical audits,
responses, reports and hashes are not rewritten.

## Numeric fidelity/comparability development diagnostics

With development debug enabled, each `debug_judge_runs` row from
`GET /v1/analyses/{analysis_id}/claims` adds `numeric_findings`, an array of
compact audit summaries (empty for older audits):

```json
{
  "version": "numeric-fidelity-comparability-1.0",
  "target_id": "S3",
  "material": true,
  "source_fidelity": "verified",
  "asserted_values": ["90"],
  "source_measure": "population_attributable_fraction",
  "claim_measure": "percent_change",
  "comparability": "different_measure",
  "numeric_effect": "noncomparable",
  "semantic_scope_checked": true,
  "structure_status": "structured",
  "evidence_ids": ["E2"],
  "differences": ["measure"],
  "conversions": []
}
```

Source fidelity is `verified`, `mismatch`, `uncertain` or `not_found`.
Comparability is `aligned`, `compatible_but_narrower`, `different_measure`,
`different_comparator`, `different_population`, `different_exposure`,
`different_endpoint`, `different_timeframe`, `not_comparable` or `uncertain`.
Numeric effect is `supports_magnitude`, `opposes_magnitude`, `noncomparable`
or `unresolved`. Structure is `structured`, `embedded_numeric_assertions`
or `mixed_measures_in_qualitative_finding`. An unchecked semantic scope is
explicitly preliminary; source verification is not judge qualification.

Measures include percent change, percentage points, RR, OR, HR, rate ratio,
absolute risk, risk difference, population/exposed attributable fractions,
prevalence, incidence rate, event count, fold change, duration, dose and unknown.
The full typed fidelity/comparability records remain in append-only validation
JSONB under new `numeric-materiality-1.2`; the API returns this allowlist, not a
raw parser dump. Historical 1.0/1.1 validations omit stored new fields and replay
with their original versions. No migration or historical report backfill.

The UI shows compact material numeric diagnostics. Expanded raw-response
excerpts render as wrapping plain text without a nested scroll container;
the default collapsed disclosure, sanitization and existing excerpt caps remain.
Verdict Explanation 1.0 consumes qualified numeric diagnostics descriptively;
its report schema, voting thresholds and verdict labels are unchanged.

## Verdict Explanation 1.0 — report response addition

New `GET /v1/analyses/{analysis_id}/claims/{claim_id}/report` snapshots use
LensReport `1.3` / builder `report-builder-1.5` and include:

```json
{
  "verdict_explanation": {
    "version": "1.0",
    "summary": "Validated evidence supports the claimed direction of effect. The retrieved evidence does not establish the claimed 85% magnitude at a sufficiently comparable scope, so the specific magnitude could not be verified.",
    "reason_category": "numeric_magnitude_unverified",
    "established": "Validated evidence supports the claimed direction of effect.",
    "unresolved": "The retrieved evidence does not establish the claimed 85% magnitude at a sufficiently comparable scope, so the specific magnitude could not be verified.",
    "evidence_ids": ["E1"]
  }
}
```

`established` and `unresolved` are nullable; `evidence_ids` contains only
qualified frozen evidence responsible for the explanation. New `short_summary`
equals the saved explanation summary. The explanation is included in the
report semantic hash and existing append-only JSONB audit; no schema migration.
Historical reports omit this field and retain their saved summaries and hashes.
GET never generates or backfills an explanation.

Reason categories: `numeric_magnitude_unverified`, `numeric_evidence_not_comparable`,
`scope_too_narrow`, `comparator_mismatch`, `population_mismatch`, `outcome_mismatch`,
`causal_design_insufficient`, `conflicting_material_evidence`, `only_indirect_evidence`,
`only_contextual_evidence`, `insufficient_direct_evidence`, `technical_validation_failure`,
`insufficient_qualified_judges`, `supported_by_validated_evidence`,
`contradicted_by_validated_evidence`, `other_bounded_reason`.

The verdict explanation is descriptive and non-voting. It cannot alter or
override the deterministic Lens verdict. Templates use qualified audited
findings/diagnostics only; no model call, retrieval or new medical reasoning.
Unable describes process failures, separately from scientific NEI. The frontend
shows `summary` beneath the label, keeps existing reasons, and exposes the
structured fields in development technical details when debug mode is enabled.

## Configured versus historical development models

When debug mode is enabled, `GET /v1/analyses/{analysis_id}` returns
`debug_models` from current backend `JUDGE_N_*` environment settings for
uncalled slots. Each row has `origin=current_configuration`. If this analysis
has a live model event or persisted judge audit, its actual provider/model
and status take precedence and `origin=analysis`. This prevents a settings
change from relabeling an old analysis. The frontend displays the origin;
there are no frontend-bundled judge model names. Backend settings are loaded
at startup, so `.env` changes require backend recreation. These fields remain
development-only and never expose API credentials.

## Pre-pilot development diagnostics

Existing URLs and verdict labels are unchanged. `AnalysisClaim.pico` may include
`numeric_effect`: `{raw_text,status,kind,value,unit,direction}`. Kinds include
percent change, percentage points, fold change, risk ratio and unknown; status
is `parsed` or `uncertain`. Historical null fields are omitted from frozen PICO
serialization. The submitted text remains available as `original_claim`.

With development debug enabled, `GET /v1/analyses/{id}/claims` adds
`debug_diagnostics` per claim: extraction/PICO, retrieval counts and source-role
counts, a deterministic stage waterfall, qualified positions, aggregation
reasons, available call total and elapsed time. `debug_judge_runs` adds proposal,
finding count, source IDs, raw axes bases, null/gradient diagnostics, reason and
failure codes, token counts when supplied, identity flags and audited ID
normalizations. These fields are absent when debug is disabled. A PASS stage
means execution completed, not medical correctness. Raw model responses remain
inside a separate collapsed development-only section; prompts and credentials
are not returned.

For current development 2.13 judging only, `debug_judge_runs` also returns
`judge_unit_id_normalizations`: bounded `{statement_id, from, to, rule}`
records when an exact frozen parent evidence ID was expanded to its unique
`.U1` source unit. This is distinct from the semantic validator's existing
`id_normalizations` field. Unknown or ambiguous IDs are rejected, and neither
field appears outside development debug. Repeated targeted issue codes are
counted in the UI without changing the underlying audit rows. A structured
model response still does not imply that its citations or final assessment
qualified.

New joint prompt `joint-evidence-axes-2.3-2026-10-02` and qualifier
`conclusion-qualifier-1.4` preserve the 2.3 decision schema. The original
`joint_response` and `id_normalizations` are stored in append-only validation
JSONB. A foreign or fabricated ID fails validation.

## Reliability Slice 4.1: versioned development audit additions

Existing submission, progress, report routes and Lens labels are unchanged.
New development/test judge audits use `schema_version=2.3`, with maximum five
statements. Each keeps `text`, `qualitative_finding`, `numeric_details` (string
array), `numeric_dependency`, `kind` and backend-materialized source-unit refs.
Conclusions keep original `justification`, `qualitative_justification`, dependency
flag and exact `based_on_statement_ids`. Raw model content is also retained under
existing sanitization/retention rules; ordinary users are not given raw prompts.

New validation `relation_validation` has `version=evidence-claim-axes-1.0`, exact
`input_json/input_hash`, prompt/provider/model provenance and `joint_response`:

```json
{
  "attributions": [{
    "statement_id": "S1", "evidence_ids": ["E1"],
    "status": "supported_by_sources", "scope_match": "exact",
    "reason": "Illustrative source-grounded description", "numeric_independent": true
  }],
  "assessments": [{
    "statement_id": "S1", "direction": "opposes_claim",
    "scope": "compatible_but_narrower", "strength": "strong", "role": "direct",
    "scope_basis": "exposure_gradient", "finding_basis": "direct_result",
    "reason": "Illustrative tested greater-versus-lesser exposure result"
  }],
  "missing_material_evidence": false
}
```

Enums: direction supports_claim/opposes_claim/neutral/mixed/unclear;
scope aligned/compatible_but_narrower/broader_or_indirect/incompatible/uncertain;
strength decisive/strong/supporting/weak/insufficient/uncertain;
role direct/synthesis/contextual/mechanistic/background/uncertain.
These are raw model assessments, not final medical votes. Python qualification
is recorded separately in `conclusion_qualification`. Optional numeric warning
codes are `OPTIONAL_NUMERIC_DETAIL_INVALID` and `OPTIONAL_NUMERIC_DETAIL_UNCERTAIN`;
material failures retain the existing fatal mismatch/unresolved quantity behavior.

Latest prompt: `judge-2.12.1-compact-development-2026-10-02`;
joint: `joint-evidence-axes-2.2-2026-10-02`;
qualifier: `conclusion-qualifier-1.3`. Earlier 4.1 versions (judge 2.12, joint
2.0/2.1, qualifier 1.2) remain reconstructible; historical 2.2 is unchanged.
`attempt_count=1` is one joint request, not one independent judge or production
approval. New debug claim summaries may include `evidence_axes` keyed by S ID,
containing only direction/scope/strength/role. Hidden when development debug is off.

Slice 4.1 semantic acceptance is partial; see `RELIABILITY_SLICE4_1_RESULTS.md`.

## Slice 4 boundary: no public contract change

Normal API judging stays input/decision `2.2`, combined Pack `1.5` and report `1.2`.
The unit-only V3/minimal-V2/lean/oracle implementations are opt-in developer CLI
experiments, not API versions or approved report artifacts. No extraction,
normalization, progress, claim-result or debug schema was changed by Slice 4.
Normal frontend HTTP acceptance remains the existing consent/submission/polling/
claims/report flow; no visual browser acceptance is claimed.

Private developer artifacts record provider/model aliases, bounded source-unit
classifications, input/prompt/Pack hashes, failures, timing and usage. They must
not be exposed to regular clients as clinically qualified results. Provider
reasoning/credentials are not retained; no browsing tool is supplied. Captures
expire and cannot be reclassified as originals after fresh retrieval. See
[Slice 4 reproduction/results](RELIABILITY_SLICE4_RESULTS.md).

## Slice 3 additions (existing endpoints, no new public browsing API)

Normal analysis and evidence-preview retrieval now freeze combined Pack `1.5`
when `AUTHORITATIVE_ENABLED=true` (default). A false setting retains PubMed-only
`1.4`. Source URLs are server-manifest entries; API clients cannot supply a source
URL to this adapter. Query diagnostics additionally record `actual_query`, `sort`,
`retmax`, `total_count`, `returned_count`, cache state and authoritative availability/
currency. Legacy caches may have unknown total counts; these are never invented.
ESearch explicitly uses relevance sorting.

Frozen document additions: `source_kind`, `authoritative`, `relationship_analysis`,
`evidence_role_hint`. Authoritative metadata includes source ID, organization,
controlled purpose, last review/update date, content version/hash, currency,
reference URLs, underlying PMIDs, summary/lineage indicators and attribution.
`study_design` remains the parent design; actual `analysis_design` and
`exposure_assignment` are separate. Roles are direct/contextual/incompatible, not
supports/contradicts votes. The common internal document uses empty PMID for a
non-PubMed source; persistence and public report PMID are nullable, never fabricated.

LensReport `1.2` source cards add `document_id`, `source_kind`, organization,
document purpose, analysis design, exposure assignment, currency, attribution and
`excerpts[]`. Each excerpt retains E ID, unit ID, exact text, section, truncation
indicator and full passage hash. New grouped excerpts retain complete frozen
passage text; legacy preview fields keep their explicitly marked short prefixes.
Multiple excerpts from one document form one
card; old report fields remain supported. Frontend uses analysis design ahead of
parent design and does not render "PMID null". Judge wire input remains `2.2`;
new purpose/role/design metadata is included identically for all judges.

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

### Slice 2 internal validation overlay

New invocations use canonical decision `2.2`, `judge-input-2.2` and
`judge-validation-2.2`. Model content keeps the same Slice 1 wire shape below;
the backend attaches versions and exact frozen references. No public route,
medical-label enum, request body, frontend type or production release gate changes.
Historical 2.0/2.1 rows remain readable under their original contracts.

After source attribution, an independent semantic adapter receives one batch
without the proposed judge label. Its strict output is:

```json
{"assessments":[{"statement_id":"S1","relation":"insufficient",
"scope":"aligned","materiality":"supporting",
"reason":"The validated finding reports association, not the asserted causation."}]}
```

Relation: `supports_claim|contradicts_claim|insufficient|context_only|uncertain`.
Scope: `aligned|compatible_but_narrower|broader_or_indirect|mismatch|uncertain`.
Materiality: `decisive|supporting|contextual|uncertain`. Exact ordered IDs,
1–8 assessments, no extra fields, reason max 1200 characters, JSON max 16384.
The request uses only validated statements and frozen metadata, no tools.

Internal validation JSONB adds `relation_validation` (contract, provider/model,
prompt version/hash, input hash/exact input, assessments/error category) and
`conclusion_qualification` (qualifier version, full typed inputs, output status,
decisive/conflicting/insufficient/contextual IDs and reason codes). Pure output
statuses are `justified|not_justified|uncertain`. Existing
`conclusion_justification` remains a compatibility view, not another model call.
Relation operational failure maps to `unable_to_assess`/excluded validation,
never a fabricated NEI vote. Normal users do not receive raw requests/provider
internals. Developer tracing retains its existing restricted/redacted boundary.
Null new fields are omitted when serializing historical results.

### Slice 1 internal judging contract overlay

No public route, request body, medical-label enum, or release gate changes.
New append-only judge rows use decision `2.1` and `judge-input-2.1`, preserving
the existing 2.0 statement-attribution/conclusion structure. The model wire
contains `label`, `statements`, `conclusion`, and `uncertainty_reasons` only:

```json
{
  "label": "not_enough_evidence",
  "statements": [
    {
      "statement_id": "S1",
      "text": "The trial reported an association at its studied scope.",
      "kind": "study_finding",
      "source_unit_ids": ["E1.U1"]
    }
  ],
  "conclusion": {
    "based_on_statement_ids": ["S1"],
    "justification": "S1 does not establish the original causal claim."
  },
  "uncertainty_reasons": ["association_not_causation"]
}
```

`source_units` in the frozen input bind `unit_id`, `evidence_id`, `document_id`,
`document_sha256`, `passage_sha256`, `content_version`, exact `start`/`end`
offsets, `text`, and `section`. Offsets are Python character indexes in the
stored passage. Units are whole included sections; document context remains
in the existing bundles. The backend materializes canonical `evidence_refs`
and sets `schema_version: "2.1"`. A model must not supply trusted quotes,
offsets, hashes, or protocol metadata. Unknown IDs and modified snapshots fail;
valid references still require semantic attribution and conclusion validation.

New targeted numeric issues can include `numeric_diagnostic` (asserted tokens
and offsets, measure, candidates, reason, source-unit IDs) and
`conclusion_dependency`. Definite false statistics remain fatal. Unresolved
required quantities prevent eligibility; optional unresolved detail does not
become a certified explanation. It can only be removed through the existing
single append-only semantic revision and a new validation. Parent and child
never count as two judges. Historical free-text 2.0 quotes retain their exact
checks and are not retroactively certified.

On final schema failure, existing internal `response_json` can contain
`rejected_responses`: attempt, category, safe schema locations/types, bounded
sanitized visible content and truncation flag. No normal-user response gains
raw provider output or schema internals. Successful `response_json` remains
the canonical decision; all existing identity/isolation/release checks apply.

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
  quality or medical truth. New Pack 1.4 selections may mark an unasserted
  active-treatment comparison
  as `unstated_active_comparator_excluded`, or a paper without the specific
  claimed muscle-gain/growth endpoint as
  `specific_outcome_endpoint_absent_excluded`. An explicitly women-only or
  men-only numbered exposure arm that conflicts with the claim population is
  marked `exposure_arm_population_mismatch_excluded`. These records remain in
  the returned audit pack but are absent from `selected_evidence_ids`; none
  of these reasons is a medical verdict. Each document additionally carries `integrity`
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

### Slice 4 development validation audit

Public analysis/report contracts and four Lens labels are unchanged. New normal
development/test judge decisions still use 2.2 source-unit references. The compact
development prompt is versioned separately; quantitative claims still receive
numeric alignment checks. `optional_numeric_content` is a bounded judge-format
failure, not permission to delete numbers or manufacture a clinical finding.

Append-only validation `result_json.relation_validation` may now contain
`joint_response` with strict `attributions`, `assessments` and
`missing_material_evidence`. Its `prompt_version` is
`joint-source-relation-1.1-2026-10-02` (historical 1.0 also reconstructible).
`input_json/input_hash/prompt_hash` describe the ACTUAL dual-target request;
`attempt_count=1` denotes one semantic HTTP request, not a skipped target.
The conclusion remains backend-qualified separately. Missing material evidence
sets validation unavailable and cannot qualify a verdict. These diagnostics are
development-only; normal users receive safe error/report text, not raw prompts.
No new production validator approval or model identity certification is implied.


### Incomplete normalization public result (2026-10-05)

A failed claim with `failure_code=normalization_incomplete` exposes
`result_label=unable_to_verify_reliably` in its analysis claim summary. Its
technical status remains `failed`, and report/verdict/evidence IDs are absent
unless independently created. This operational label does not fabricate a
medical report or bypass production qualification of successful assessments.
