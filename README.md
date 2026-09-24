# The Lens of Truth

Evidence-Based Medical Information Verification System.

This monorepo contains the Phase 1 foundation and scoped Phase 2 intake path for a pipeline-first product that
verifies atomic health claims against traceable evidence. It is intentionally
not a generic chatbot or a binary truth classifier.

The implementation securely ingests text and screenshots, re-encodes accepted
images before short-lived private storage, runs local OCR, masks structured
PII, and calls an approved configured adapter for atomic claim extraction.
Retrieval, entity linking/PICO, model judging, and verdict logic are not
implemented here.

## Quick start

```powershell
Copy-Item .env.example .env
docker compose up --build
```

- Web UI: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health endpoint: `http://localhost:8000/healthz`

Apply the initial schema after the containers are running:

```powershell
docker compose exec backend alembic upgrade head
```

Screenshot OCR is included in the backend image. Semantic claim extraction is
disabled by default so the system cannot fabricate claims. To enable it, set
the following values in your untracked `.env` for an approved OpenAI-compatible
provider or self-hosted vLLM endpoint, then rebuild the backend:

```dotenv
CLAIM_EXTRACTOR_PROVIDER=openai_compatible
CLAIM_EXTRACTOR_BASE_URL=https://approved-provider.example/v1
CLAIM_EXTRACTOR_MODEL=pinned-model-id
CLAIM_EXTRACTOR_API_KEY=replace-with-secret
```

Raw screenshots and associated Phase 2 records are purged within 24 hours.
Local filesystem upload storage is suitable only for Docker/local development;
implement an approved isolated object-storage adapter before public deployment.

See [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for boundaries and
[docs/TODO.md](docs/TODO.md) for the implementation roadmap.
