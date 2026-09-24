# API Specification

Base path: `/v1`. Phase 2 performs secure intake, OCR for screenshots, PII
masking, and atomic-claim extraction only. It does not retrieve evidence or
return a medical verdict.

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
PICO fields, model metadata, and screenshot OCR metadata without creating a
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

The response is ephemeral. It does not expose the gateway's raw response or
unredacted source text.

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
offsets locally. When disabled or unavailable, the endpoint returns `503` with
`claim_extractor_unavailable`; malformed replies return `502` with
`claim_extractor_invalid_response`. URL input is reserved for Phase 3 and
returns `501`.

## `GET /v1/analyses/{analysis_id}`

Returns redacted atomic claims and safe OCR metadata. `raw_text` and its
offsets refer to the redacted source representation, preserving positions while
not exposing structured identifiers. There is no verdict field.
Each claim also includes nullable `population`, `intervention_or_exposure`,
`comparator`, `outcome`, and `timeframe` fields for PICO framing. Null means the
source did not supply that detail; these model-produced fields are not evidence.

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
