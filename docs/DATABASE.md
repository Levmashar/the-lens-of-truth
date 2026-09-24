# Database Foundation

PostgreSQL is the durable record. The initial Alembic migration enables the
`vector` extension and creates the Phase 1 schema.

| Model | Responsibility |
|---|---|
| `Submission` | Privacy-aware analysis request metadata and retention deadline |
| `Claim` | Atomic claim, span, normalization, risk, and PICO fields |
| `EvidenceDocument` | Provenance and publication metadata, not full article storage |
| `EvidencePassage` | Minimal evidence snippet, offsets, hash, and 1024-d vector slot |
| `ModelEvaluation` | A single provider/model judgment linked to a claim |
| `FinalVerdict` | One auditable, aggregated outcome per claim |

The schema uses UUID primary keys, UTC timestamps, a PostgreSQL verdict enum,
and foreign keys appropriate for the target pipeline. Fields that a later
phase will populate are nullable by design; Phase 1 inserts no domain records.

Run migrations locally:

```powershell
docker compose exec backend alembic upgrade head
```

Do not store wholesale paywalled articles. Keep canonical URLs, identifiers,
license information, content hashes, and minimal permitted passages.
