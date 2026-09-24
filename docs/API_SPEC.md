# API Specification

Base path: `/v1`. The Phase 1 endpoints establish a stable contract; no
medical pipeline is executed yet.

## `POST /v1/analyses`

Accepts a requested analysis and returns a generated ID with `processing`
status. An `Idempotency-Key` header is accepted for the future durable
orchestrator, but Phase 1 does not persist or deduplicate submissions.

```json
{
  "schema_version": "1.0",
  "client": "web",
  "lang": "auto",
  "input": {"type": "text", "text": "A health claim to verify."},
  "consent": {"privacy_notice_version": "2026-09-01", "accepted": true}
}
```

`input.type` supports `text`, `screenshot`, and `url` in the contract. Only
the payload shape is validated in Phase 1; screenshot storage/OCR and URL
fetching are intentionally deferred.

## `GET /v1/analyses/{analysis_id}`

Returns the current mock lifecycle object. The `claims` array is empty until
Phase 2 implements atomic claim extraction.

## `GET /v1/analyses/{analysis_id}/events`

Returns an SSE stream with mock `stage` and `completed` events. This lets the
frontend establish the progressive-analysis integration without implying that
verification has occurred.

## `GET /healthz`

Liveness endpoint. It reports that the API process is running and does not
check third-party services; readiness checks will be introduced with workers
and required backing services.

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

Server errors do not expose exception details to clients.
