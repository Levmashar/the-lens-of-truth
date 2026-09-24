# Backend

The FastAPI service provides the Phase 2 intake path: server-side image
sanitation, short-lived raw screenshot storage, local Tesseract OCR,
position-preserving structured-PII masking, and validated atomic claim/PICO
extraction. It does not retrieve evidence, evaluate claims, or issue a
medical verdict. Phase 3B can resolve terminology against a locally imported
official NLM MeSH descriptor release; this is not evidence retrieval.

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
