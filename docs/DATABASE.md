# Database Foundation

PostgreSQL is the durable record. Alembic enables the `vector` extension,
creates the Phase 1 foundation, and adds Phase 2 short-lived upload metadata
and coreference provenance. Existing nullable claim PICO columns are now
populated when the extractor supplies source-grounded fields.

| Model | Responsibility |
|---|---|
| `Submission` | Privacy-aware analysis request metadata and retention deadline |
| `ScreenshotUpload` | Sanitized raw-image metadata, OCR/redaction metrics, and 24-hour purge deadline; bytes remain in private storage |
| `Claim` | Atomic claim, span, normalization, risk, and PICO fields |
| `EvidenceDocument` | Provenance and publication metadata, not full article storage |
| `EvidencePassage` | Minimal evidence snippet, offsets, hash, and 1024-d vector slot |
| `ModelEvaluation` | A single provider/model judgment linked to a claim |
| `FinalVerdict` | One auditable, aggregated outcome per claim |

The schema uses UUID primary keys, UTC timestamps, a PostgreSQL verdict enum,
and foreign keys appropriate for the target pipeline. Fields that a later
phase will populate are nullable by design. Phase 2 writes `Submission`,
`ScreenshotUpload`, and redacted `Claim` rows only; it never stores raw
screenshot bytes or unredacted OCR text in PostgreSQL. The submission records
the non-secret extraction provider, pinned model ID, and prompt version for
every real extraction run.

Run migrations locally:

```powershell
docker compose exec backend alembic upgrade head
```

Do not store wholesale paywalled articles. Keep canonical URLs, identifiers,
license information, content hashes, and minimal permitted passages.
