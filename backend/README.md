# Backend

The FastAPI service provides the Phase 2 intake path: server-side image
sanitation, short-lived raw screenshot storage, local Tesseract OCR,
position-preserving structured-PII masking, and schema-constrained atomic
claim extraction. It does not retrieve evidence, evaluate claims, or issue a
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
Chinese, and Traditional Chinese. Claim extraction fails closed unless the
approved OpenAI-compatible adapter settings are configured in `.env`; this is
intentional and never falls back to heuristic claim generation.

The container entrypoint corrects ownership of the local named upload volume,
then runs the API as the unprivileged `appuser` account.
