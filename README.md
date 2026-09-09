# Configurable Knowledge Assistant Platform

**Arabic name:** منصة المساعد المعرفي القابل للتخصيص

**Status:** Stage 6I — Organization Control Plane core

- Architecture: Modular Monolith + Ports and Adapters
- Runtime: Python 3.13 and FastAPI
- Platform persistence/vector backend: Supabase PostgreSQL + pgvector
- Document RAG, safe structured retrieval, deterministic evaluation
- Arabic-first organization control plane at `/app`
- Internal operational acceptance surface at `/app/acceptance`

The core is a framework-independent modular monolith. Structured retrieval accepts
only validated typed plans and emits parameterized SELECT statements; raw LLM SQL is
prohibited. Model and embedding inference use provider-neutral, remote-only HTTP ports.
The Yemen content is a clearly labeled reference fixture.

Configure the environment from `.env.example`, then start the production composition root:

```text
uvicorn knowledge_platform.bootstrap.asgi:app --host 0.0.0.0 --port 8000
```

Open `/app`. Health and readiness are available at `/health` and `/ready`. Build with:

```text
docker build -t knowledge-platform:stage6 .
```

Run the available quality checks with `python3.13 -m pytest -q`,
`python3.13 -m ruff check .`, and `python3.13 -m mypy src`.

Live Supabase/PostgreSQL, RLS, pgvector, and provider execution require separately
authorized acceptance; local source checks do not imply live verification.
