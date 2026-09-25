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
metadata; neither phase judges claim truth.

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
The `verifiability` field is a numeric estimate of testability, not medical
truth. If the browser gateway supplies a qualitative label instead of a number,
the preview returns `null` for that field while retaining locally validated
claim spans.

## `POST /v1/analyses`

Creates a completed Phase 2 extraction. The `Idempotency-Key` header remains
reserved for a later durable orchestrator and is not yet used for deduplication.

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

Successful extraction returns HTTP `201`:

```json
{
  "analysis_id": "c5eb3f8d-5c9e-45d5-b88d-b5152b2de95a",
  "status": "claims_extracted",
  "claim_count": 2
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
When disabled or unavailable, the endpoint returns `503` with
`claim_extractor_unavailable`; malformed replies return `502` with
`claim_extractor_invalid_response`. URL input is reserved for a later phase and
returns `501`.
Two exhausted timeouts return HTTP `504` with `claim_extractor_timeout`;
an overall deadline returns HTTP `504` with
`claim_extractor_deadline_exceeded`. Public errors include a request ID but
never provider response bodies, prompts, credentials, or internal trace IDs.

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

Returns redacted atomic claims and safe OCR metadata. `raw_text` and its
offsets refer to the redacted source representation, preserving positions while
not exposing structured identifiers. There is no verdict field.
Each claim also includes nullable `population`, `intervention_or_exposure`,
`comparator`, `outcome`, and `timeframe` fields for PICO framing. Null means the
source did not supply that detail; these model-produced fields are not evidence.
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

Returns a server-sent snapshot of actual completed Phase 2 stages: `ingested`,
optional `ocr_complete`, `pii_redaction_complete`, and `claims_extracted`. It
does not simulate future evidence-retrieval or judging progress.

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
