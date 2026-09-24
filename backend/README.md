# Backend

The FastAPI service provides the Phase 2 intake path: server-side image
sanitation, short-lived raw screenshot storage, local Tesseract OCR,
position-preserving structured-PII masking, and validated atomic claim/PICO
extraction. Phase 3B resolves terminology against a locally imported official
NLM MeSH release. Phase 4A retrieves PubMed title/abstract evidence and stores
frozen Evidence Packs; it does not evaluate claims or issue a medical verdict.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
uvicorn app.main:app --reload --port 8000
pytest
```

Use PostgreSQL with pgvector before running migrations. Environment variables
are documented in the repository-level `.env.example`. `requirements.lock`
pins the API and development tools used by local validation and CI.

The Docker image installs Tesseract language data for English, Simplified
Chinese, and Traditional Chinese. Set `CLAIM_EXTRACTOR_PROVIDER=miri`,
`CLAIM_EXTRACTOR_BASE_URL`, and optionally `CLAIM_EXTRACTOR_API_KEY` in `.env`.
The default model is `chatgpt-auto`. The browser gateway may wrap JSON in a
code fence; the adapter parses and validates it locally, including source
offsets, and never substitutes heuristic claims on failure.
Extraction defaults to 55 seconds per attempt, a 115-second total deadline,
and at most one retry. Set `CLAIM_EXTRACTOR_TIMEOUT_SECONDS` (maximum 60) and
`CLAIM_EXTRACTOR_TOTAL_TIMEOUT_SECONDS` (maximum 120) in `.env` if needed.
Timeouts return a typed HTTP 504 error without creating claims.

The container entrypoint corrects ownership of the local named upload volume,
and MeSH-index volume, then runs the API as the unprivileged `appuser` account.

## MeSH terminology setup

From `backend/`, import NLM's production-year descriptor XML into the local
ignored runtime directory:

```powershell
python -m app.medical.mesh_import --release 2026 --index runtime/mesh/mesh.sqlite3 --download
python -m app.medical.renormalize --dry-run --batch-size 100
python -m app.medical.renormalize --apply --batch-size 100
```

For Docker Compose, import inside the backend container to populate its named
volume, then restart the backend so new requests load the index:

```powershell
docker compose exec --user 10001:10001 backend python -m app.medical.mesh_import --release 2026 --index /app/runtime/mesh/mesh.sqlite3 --download
docker compose restart backend
docker compose exec backend python -m app.medical.renormalize --dry-run --batch-size 100
docker compose exec backend python -m app.medical.renormalize --apply --batch-size 100
```

The index is not committed. Use `--replace` only for an intentional release
refresh. `--source` accepts a separately downloaded official descriptor XML/gz.
The importer records its source URL (when downloaded), release, SHA-256, and
descriptor count. Missing MeSH data leaves entity IDs unresolved. UMLS is not
required. A re-normalization run never overwrites a claim with existing
entity mappings or PICO JSON. The command defaults to dry-run even without a
flag. Courtesy of the U.S. National Library of Medicine. NLM does not endorse
this application; check its data terms before public distribution.

## PubMed retrieval smoke test

Set `NCBI_EMAIL` in the repository `.env` to a real developer/organization
contact. `NCBI_TOOL` defaults to `the_lens_of_truth`; `NCBI_API_KEY` is
optional. PubMed ESearch result lists are cached in Redis for six hours by
default. Configure timeout, retry count, per-query PMID limit, and cache TTL
with the `PUBMED_*` settings in `.env.example`. Without the contact email,
retrieval returns a typed 503 rather than making an unidentified request.

Apply the Phase 4A migration and create a text analysis. Get its `claim_id`
from `GET /v1/analyses/{analysis_id}`. Then run:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.retrieval.smoke "<claim_id>"
```

Or call the development-only API with `analysis_id` and `claim_id`:

```powershell
$body = @{ analysis_id = "<analysis_id>"; claim_id = "<claim_id>" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/analyses/evidence-preview" `
  -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 20
```

The output shows QueryPlan variants, PubMed metadata, exact passages, E IDs,
relevance factors, and a snapshot hash. A retrieval score is not a truth or
study-quality probability. `no_results` is valid; timeout, transport, rate
limit, upstream HTTP, and malformed responses are separate typed failures.
Each rerun creates a new, append-only pack rather than modifying an old one.

If extraction is unavailable but you want to test PubMed alone, provide
explicit, source-grounded fields. This mode does **not** create a claim or
persist a pack, and it does not guess PICO fields:

```powershell
docker compose exec backend python -m app.retrieval.smoke `
  "Frequent sunscreen use causes invasive melanoma." `
  --exposure "Frequent sunscreen use" --outcome "invasive melanoma" `
  --claim-type causal
```
