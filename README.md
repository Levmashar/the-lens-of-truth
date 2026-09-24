# The Lens of Truth

Evidence-Based Medical Information Verification System.

This monorepo contains the Phase 1 foundation for a pipeline-first product that
verifies atomic health claims against traceable evidence. It is intentionally
not a generic chatbot or a binary truth classifier.

The foundation exposes typed API placeholders, a PostgreSQL/pgvector-ready data
schema, a React web shell, a native WeChat placeholder, and local Docker
services. OCR, claim extraction, retrieval, model judging, and verdict logic
are planned phases and are not implemented here.

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

See [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for boundaries and
[docs/TODO.md](docs/TODO.md) for the implementation roadmap.
