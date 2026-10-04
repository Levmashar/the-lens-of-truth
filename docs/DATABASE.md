# Database Foundation

Slice 3 source purpose/currency/lineage/analysis design reside in immutable Pack
JSONB and qualifier inputs in append-only validation JSONB; they require no new
audit tables. `evidence_document.source_kind` distinguishes PubMed from approved
public-health sources, whose PMID/DOI may be null. Canonical URL and content hash
identify approved source versions. New Packs/versions append; historical snapshots
are not rewritten. Migration `20261001_0018` changes `evidence_passage.section`
from VARCHAR(128) to Text because official headings exceeded that bound. Downgrade
refuses existing headings longer than 128 characters rather than truncating them.

PostgreSQL is the durable record. Alembic enables the `vector` extension,
creates the Phase 1 foundation, and adds Phase 2 short-lived upload metadata
and coreference provenance. Existing nullable claim PICO columns are now
populated when the extractor supplies source-grounded fields.
Phase 3A added `pico_json`, `linked_entities`, and `normalization_status` to
`Claim`. Phase 3B stores MeSH source, production year, descriptor ID, match
type, ambiguity, confidence, candidate suggestions, and optional tree numbers
inside the existing `linked_entities` JSONB. No new migration is required.
Phase 4A migration `20260924_0007` adds PubMed metadata fields to
`EvidenceDocument`, permits multiple content-hash versions of one PMID/URL,
and creates `RetrievalRun`, `RetrievalQuery`, `RetrievalDocumentQuery`, and
`EvidencePack` tables. A pack contains a frozen JSONB snapshot and SHA-256;
reruns append records rather than updating an earlier pack.
Pack/run rows cascade when the parent short-lived claim is purged; shared
public PubMed document rows are independent of submission retention.

Reliability Slice 1 requires no migration. Existing append-only `judge_run`
JSONB stores `judge-input-2.1` source units (IDs, offsets, text, document/passage
hashes and section context) and canonical decision 2.1 materialized references.
Failed responses can retain sanitized visible content and safe schema-error
paths in `response_json`; successful response JSON remains canonical decision
JSON. `judge_validation_run.result_json` stores assertion-local numeric
diagnostics and conclusion dependency. Historical 1.0/2.0 rows and Pack hashes
are not updated or retroactively certified. Parent/child revision lineage and
append-only triggers remain unchanged. Developer replay exports are not a
retention extension; see `RELIABILITY_SLICE1_RESULTS.md`.

| Model | Responsibility |
|---|---|
| `Submission` | Privacy-aware analysis request metadata and retention deadline |
| `ScreenshotUpload` | Sanitized raw-image metadata, OCR/redaction metrics, and 24-hour purge deadline; bytes remain in private storage |
| `Claim` | Atomic claim, span, normalization, risk, and PICO fields |
| `EvidenceDocument` | Provenance and publication metadata, not full article storage |
| `EvidencePassage` | Minimal evidence snippet, offsets, hash, and 1024-d vector slot |
| `RetrievalRun` | One claim's PubMed query plan, status, diagnostics, and retrieval time |
| `RetrievalQuery` | Executed query text, family, field provenance, result count, and cache hit |
| `RetrievalDocumentQuery` | Many-to-many paper/query discovery provenance |
| `EvidencePack` | Append-only claim/query/document/ranked-passage snapshot and content hash |
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
license information, content hashes, and minimal permitted passages. Phase 4A
stores PubMed abstracts only, never scraped full text; review NCBI disclaimer
and abstract copyright terms before public display or redistribution.
