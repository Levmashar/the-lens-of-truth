# Infrastructure

Local development uses the repository-root `docker-compose.yml`:

- FastAPI API on port 8000
- React static site on port 5173
- PostgreSQL 16 with pgvector on port 5432
- Redis 7 on port 6379

The competition MVP should use container/serverless deployment before any
Kubernetes adoption. Future production work belongs here: deployment manifests,
secret-manager integration, HTTPS/WAF configuration, telemetry, backup policy,
and deployment runbooks.
