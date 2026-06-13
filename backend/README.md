# Maria One — Backend

In-house CRM + AI coordination gateway. FastAPI + PostgreSQL + Qdrant + Redis +
Langfuse, run with Docker Compose locally and deployed to **Azure Container Apps**
(see [../deploy/azure](../deploy/azure)).

> **Why Python/FastAPI and not Go/gRPC?** The heavy model (Gemma 2B) runs
> **on-device** (Apple MLX), never on the server — the backend only makes HTTP
> calls to OpenRouter for Tier 2/3. The workload is therefore **I/O-bound**
> (Postgres, external APIs, Qdrant), where async FastAPI is more than enough and
> language choice is noise next to network latency. Python also gives us the
> AgentScope + RAG ecosystem directly. If one worker ever becomes a hot path, the
> Redis-queue boundary lets us rewrite just that worker in Go later.

## Quickstart

```bash
cd backend
cp .env.example .env          # set API_TOKEN for staging/prod; blank ok in dev
docker compose up --build
```

Then:

- API & OpenAPI docs: http://localhost:8000/docs (disabled in prod)
- Liveness / readiness: http://localhost:8000/healthz · /readyz
- Ops console (OpenRouter, workload, **MCP integrations**, **skills**): http://localhost:8000/admin
  - Manage MCP servers (Plane/Notion/custom) and agent skills; run the default
    `echo-test` skill to smoke-test the agent/MCP pipeline. API under `/admin/api/*`.
- Tracing (Langfuse): **not run locally** — self-hosted v3 needs ~16 GiB (ClickHouse +
  worker + MinIO). Use [Langfuse Cloud](https://cloud.langfuse.com) by setting
  `LANGFUSE_*` keys in `.env` (the tracer no-ops until then), or a dedicated VM.

Migrations in `migrations/` run automatically on first DB init (`001_init.sql`
creates the schema; `002_seed.sql` adds optional dev data — M0 "seedable").

## Layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app, CORS, security headers, routers, /admin
│   ├── config.py          # typed settings from env / Key Vault
│   ├── db.py              # asyncpg pool + transactional-outbox helper
│   ├── redis_client.py    # shared Redis: idempotency keys + per-entity locks
│   ├── bus.py             # message bus/store: Redis Streams (default) | Kafka (scale)
│   ├── security.py        # bearer auth + Tier-1 cloud guard (fail-closed)
│   ├── workers.py         # relay (outbox→bus) + consumer (reindex/dispatch), traced
│   ├── routers/           # today, clients, visits(+MoM+dispatch), opportunities, tickets, chat, health, admin_api
│   ├── integrations/      # openrouter (deny-logging), plane, notion, qdrant, langfuse_client
│   └── admin/index.html   # ops console (OpenRouter, workload, MCP integrations, skills)
├── migrations/            # 001_init.sql, 002_seed.sql, 003_mcp_skills.sql
├── Dockerfile             # multi-stage, non-root (uid 10001), healthcheck
└── docker-compose.yml     # db, redis, qdrant, api, worker, langfuse
```

## What this skeleton covers (M0–M2) and what's stubbed

**Working now:** `docker compose up` healthy; full CRM schema; CRUD for clients/
contacts/visits/opportunities/tickets/todos; GPS check-in/out; agenda checklist;
structured MoM draft → confirm → per-destination dispatch rows; Today brief;
quick-chat contract (DB-grounded stub); transactional outbox + worker drainer;
auth + Tier-1 guard + security headers.

**Stubbed with a clear seam (TODO tags):** real Qdrant embedding/upsert (M2),
AgentScope coordinator (M2), Plane/Notion create + inbound sync (M4), the
verifier's triple-check (M4). On-device Gemma drafting happens in the iOS app.

## Messaging & observability backbone

The change pipeline (docs/07-datastore.md) is wired end to end:

```
API write ──(same txn)──▶ Postgres + outbox row
                              │  relay loop
                              ▼
                      Message bus / store ── Redis Streams (default)
                              │               consumer groups · replay · at-least-once
                              ▼               (Kafka drop-in: BUS_BACKEND=kafka)
        consumer ─▶ reindex → Qdrant (RAG, tier-aware)
                 ─▶ dispatch → Plane / Notion (per-destination, idempotent)
                 ─▶ (M2) derive → todos / health · (M4) verifier triple-check
                              │
                       Langfuse trace (one span per event: tokens, cost, tier, destination)
```

- **Redis** also provides idempotency keys (`SET NX`) and per-entity locks so
  at-least-once delivery is safe and two workers never touch the same aggregate.
- **Langfuse** degrades to a no-op when keys are unset, so dev/tests run without it.
- **Why Redis Streams over Kafka:** at single-user scale a Kafka broker is
  unjustified ops; Streams give the same durability/consumer-groups/replay. The
  `MessageBus` interface is identical for both — switching is config-only later.

Run `docker compose up` (Redis Streams). For Kafka:
`BUS_BACKEND=kafka docker compose --profile kafka up` (after uncommenting
`aiokafka` and wiring `KafkaBus`).

## Audit fixes baked into the schema

- `sensitivity_tier` on visits + MoM; Tier-1 cloud path rejected server-side.
- `agenda_items` real checklist; structured `meeting_minutes` + `action_items`.
- `dispatch_targets` = one row per destination → partial-failure is visible.
- Tickets carry `sync_source` + `last_synced_at` → Plane stays authoritative for
  status; the verifier won't clobber a teammate's Plane edit.
- `todos.source` (`user`|`ai`) + `dedup_key` → re-derivation never wipes your tasks.

## Tests

```bash
pip install -r requirements.txt pytest
pytest -q
```
