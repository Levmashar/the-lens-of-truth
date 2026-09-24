# Backend

The FastAPI service provides the Phase 2 intake path: server-side image
sanitation, short-lived raw screenshot storage, local Tesseract OCR,
position-preserving structured-PII masking, and validated atomic claim/PICO
extraction. It does not retrieve evidence, evaluate claims, or issue a
medical verdict.

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

The container entrypoint corrects ownership of the local named upload volume,
then runs the API as the unprivileged `appuser` account.
