# 03 — Tech Stack

**Project:** Maria One

## Backend (in-house CRM + AI)

| Concern | Choice | Notes |
|---|---|---|
| API / gateway | **FastAPI** + Uvicorn | From `personal_ai`; hosts CRM + visit + MoM endpoints |
| **CRM** | **In-house** (FastAPI + Postgres) | Replaces Cockpit; full schema (see architecture) |
| Agent engine | **AgentScope** | Planner → worker → critic, from `AI_assistant`; drafts the MoM |
| Relational store | **PostgreSQL** (asyncpg) | CRM objects, visits, MoM, dispatch state |
| Vector store | **Qdrant** | Per-client RAG over past MoMs/docs |
| Cache / pub-sub | **Redis** | Sessions, rate limits, dispatch worker coordination |
| Tracing | **Langfuse (self-hosted)** | Full prompt/output kept private in-stack |
| Cloud LLM | **OpenRouter** (OpenAI-compatible) | Gemma 4 free models, no-logging enforced (Tier 2/3) |
| HTTP client | **httpx** | Plane/Notion calls and outbound requests |
| Validation | **Pydantic v2** | CRM schema, structured MoM output |

### Model configuration (OpenRouter — Tier 2/3 only)

- Base URL: `https://openrouter.ai/api/v1`
- Pinned chain: `google/gemma-4-31b-it:free` → `google/gemma-4-26b-a4b-it:free`
- **Every request sends** `provider: { data_collection: "deny" }` (fail closed — if no
  no-logging endpoint exists, the request errors and the MoM is drafted on-device instead).
- Account setting: training/logging on free models **disabled**.
- Optional headers: `HTTP-Referer`, `X-Title` (leaderboard attribution only).

> Why not `openrouter/free` router or other free models: most free endpoints log prompts/outputs
> for training. The Nvidia free-endpoint warning is the general rule, not an exception. We pin
> Gemma 4 and enforce `data_collection: "deny"`. Confidential (Tier 1) client data never goes to
> cloud at all — its MoM is drafted on-device.

## Mobile — new native iOS app (Swift)

| Concern | Choice | Notes |
|---|---|---|
| Language / UI | **Swift / SwiftUI** | Fresh native app (not the Expo RN `BIM.Visitplan`) |
| On-device model | **Gemma 2B** via **Apple MLX** | ~1.5 GB quantized; drafts MoM + tags sensitivity |
| Local storage | **Core Data / SQLite** | Visits, agenda, notes; basic offline capture |
| Location | **CoreLocation** | GPS check-in / check-out |
| Networking | **URLSession** → backend CRM API | Sends visit + MoM + tier flags |

> The shipped `BIM.Visitplan` (Expo/React Native) is the **design + data-model reference**, not the
> codebase we extend. The new app is built natively in Swift, which also makes Apple MLX the natural
> on-device runtime for Gemma 2B.

## Infrastructure

| Concern | Choice | Notes |
|---|---|---|
| Containers | **Docker Compose** | Postgres, Qdrant, Redis, api, worker (message bus = Redis Streams) |
| Edge / ingress | **Traefik v3** | Reverse proxy + TLS; replaces host nginx. Routes `<svc>.technexus.info` by Docker labels on a shared `web` network |
| TLS certs | **Let's Encrypt** (DNS-01 via Cloudflare) | Works behind the CF proxy; auto-renew; no port-80 dependency |
| DNS | **Cloudflare** (proxied) | A records (orange cloud) → Azure VM `4.194.153.78`; SSL/TLS = Full (Strict) |
| Management UI | **Dockhand** | Web UI to manage Docker/compose (`dockhand.technexus.info`) |
| Host | **Azure VM** (Ubuntu 24.04, 4 vCPU/8 GiB) | Coexists with Outline VPN (`shadowbox`) — untouched |
| Tracing | **Langfuse Cloud** | Self-hosted v3 too heavy (~16 GiB); tracer no-ops until keys set |
| Backups | encrypted cron | Daily, retained 30 days |

> Deploy guide: [`deploy/vm/README.md`](../deploy/vm/README.md). Azure Container Apps
> path (alt): [`deploy/azure/README.md`](../deploy/azure/README.md).

## Integrations

| System | Role | Mechanism | Status |
|---|---|---|---|
| **CRM** | Visits, clients, opportunities, MoM | **In-house** (Postgres) | ✅ built, MVP |
| **Plane** | Follow-up tickets, team board | MCP client (agent tool) | ✅ MVP |
| **Notion** | Meeting notes | MCP client (agent tool) | ✅ MVP |

## Auth & multi-user (later)

| Concern | Choice | Notes |
|---|---|---|
| Login | **Microsoft Entra ID** | Reuse the `BIM.Visitplan` PKCE flow |
| Roles | admin / management / sales / solution / am | Group scoping for 14 members |

> MVP is single-user; Entra login + RBAC land in the team phase.

## Reused from existing projects

- `BIM.Visitplan/src/types.ts` — Cockpit + legacy CRM types = the **CRM data-model blueprint**.
- `BIM.Visitplan/visitplan-v2.html` — 13-screen UI design system (styling/IA reference).
- `BIM.Visitplan/src/hooks/useVisits.ts` — visit lifecycle (create / check-in / check-out).
- `personal_ai/gateway/main.py` — FastAPI ingress, Cloudflare tunnel.
- `personal_ai/dashboard/main.py` — monitoring UI + WebSocket.
- `AI_assistant/assistant_app/workflow.py` — planner/worker/critic (MoM drafting).
- `AI_assistant/assistant_app/tools.py` — sandboxed tool pattern for Plane/Notion adapters.
- `AI_assistant/assistant_app/rag.py`, `config.py` — Qdrant RAG + config conventions.
