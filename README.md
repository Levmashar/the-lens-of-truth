# The Lens of Truth

Evidence-Based Medical Information Verification System. The product separates
checkable medical claims, retrieves and freezes their evidence, independently
assesses that same evidence, validates citations, and builds a conservative
claim-scoped report. It is neither a generic chatbot nor a binary truth score.

The Phase 7B web app uses **vanilla HTML, CSS, TypeScript, and Vite**. React
was intentionally removed: its early screen only covered claim extraction and
the competition MVP does not require a frontend framework. The backend uses
FastAPI, PostgreSQL/pgvector, Redis, local Tesseract OCR, official MeSH data,
and configured external providers. URL ingestion and native WeChat are not
implemented.

## Run locally with Docker

From `the-lens-of-truth/` in PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Fill in the required provider settings in .env without committing it.
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec --user 10001:10001 backend python -m app.medical.mesh_import --release 2026 --index /app/runtime/mesh/mesh.sqlite3 --download
```

Open `http://localhost:5173/`. API docs are at `http://localhost:8000/docs`.
The web app calls the API at `http://localhost:8000` in the Compose build.
Install the official NLM MeSH release in each runtime as described in
[`backend/README.md`](backend/README.md); without it, claim
normalization can remain incomplete and retrieval will not proceed. A real
NCBI contact email, approved model gateway settings, and any optional
Crossref contact belong in the untracked `.env`.

```powershell
docker compose down
```

To develop the frontend outside Docker:

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run dev
```

The backend must be running separately for live analysis; the landing page
still renders while it is unavailable. `frontend/nginx.conf` falls back to
`index.html` for direct `/analysis/{uuid}` refreshes, and Vite does the same
in development.

## Frontend checks

```powershell
cd frontend
npm run check
npm test
npm run build
```

`src/api/` centralizes network calls and safe error mapping. `src/pages/`
owns the home form and claim-scoped analysis state. `src/components/` renders
progress, upload, reports, and frozen evidence; `src/types/` mirrors the
backend contract. `src/utils/` handles routing, serial polling, and
idempotency; `src/styles/` contains design tokens and responsive CSS.

The home route is `/`. After a 202 start acknowledgement, the browser goes to
`/analysis/{analysis_id}`, polls the Phase 7A status/claims routes, and loads
each completed claim's frozen report once. A refresh resumes the existing run.
A failed network POST can reuse its key; changing input starts a new attempt.
Session storage may hold only an opaque key, SHA-256 content digest, and upload
ID for a same-tab retry—not raw health text, screenshots, or reports.

Development reports visibly show the backend's qualification notice.
Staging/production 403 report gating is never converted into a medical label.
No frontend code generates medical reasoning or hides unqualified status.
The browser renders source excerpts exactly as text, never as trusted HTML.

This remains an anonymous, short-retention prototype with an in-process
background worker. Public deployment still needs approved live entailment,
verified model identity/search isolation, durable work delivery, access
control, and a full accessibility/security review. See
[`docs/TODO.md`](docs/TODO.md) and [`docs/API_SPEC.md`](docs/API_SPEC.md).
