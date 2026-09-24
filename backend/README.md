# Backend

The FastAPI service currently provides the Phase 1 health check and analysis
contract. Analysis responses are explicitly mock lifecycle objects; this
package does not perform OCR, retrieval, AI evaluation, or medical verdicts.

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
