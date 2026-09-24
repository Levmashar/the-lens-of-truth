# The Lens of Truth

Evidence-Based Medical Information Verification System.

This monorepo contains the Phase 1 foundation and scoped Phase 2 intake path for a pipeline-first product that
verifies atomic health claims against traceable evidence. It is intentionally
not a generic chatbot or a binary truth classifier.

The implementation securely ingests text and screenshots, re-encodes accepted
images before short-lived private storage, runs local OCR, masks structured
PII, and calls a configured adapter for atomic claim and PICO extraction.
Terminology linking, evidence retrieval, model judging, and verdict logic are
not implemented here.

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

Screenshot OCR is included in the backend image. To use the `miri-api` gateway
described in `../ai api.md`, set its address in your untracked `.env`, then
recreate the backend. The URL must include `/v1`; put the gateway token in the
path or set `CLAIM_EXTRACTOR_API_KEY` for Bearer authentication:

```dotenv
CLAIM_EXTRACTOR_BASE_URL=http://host.docker.internal:8001/<gateway-token>/v1
```

The backend defaults to the `miri` adapter and `chatgpt-auto`, with a 180-second
timeout. It remains unavailable until you supply the address. You may instead
set `CLAIM_EXTRACTOR_API_KEY` and use a `/v1` address without a token in its
path.

In development, `POST /v1/analyses/claim-preview` returns transient redacted
claim and PICO extraction output without storing an analysis. A ready-to-run
PowerShell example is in [docs/API_SPEC.md](docs/API_SPEC.md).

`host.docker.internal` is for a gateway running on the Windows host. If it
runs on another machine, use that machine's reachable address. Miri's model
picker is best-effort, so the recorded model is the requested `chatgpt-auto`
mode, not proof of the exact ChatGPT model that answered. Without a reachable
gateway, extraction returns an availability error.

Raw screenshots and associated Phase 2 records are purged within 24 hours.
Local filesystem upload storage is suitable only for Docker/local development;
implement an approved isolated object-storage adapter before public deployment.

See [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for boundaries and
[docs/TODO.md](docs/TODO.md) for the implementation roadmap.
