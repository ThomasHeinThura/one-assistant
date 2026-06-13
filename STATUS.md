# Maria One — Project Status

_Last updated: 2026-06-13_

Sales & solution work assistant with AI coordinator **Maria** — a native iOS app
(Today / VisitPlan / CRM / Tickets) + FastAPI backend that coordinates an in-house
CRM (Postgres), Plane (tickets), Notion (notes), and RAG (Qdrant).

**Live URLs**
- API + admin console: `https://api.technexus.info` → `/admin`
- Docker management: `https://dockhand.technexus.info`
- Host: Azure VM `4.194.153.78` (Ubuntu 24.04, 4 vCPU / 8 GiB). Coexists with Outline VPN (untouched).

---

## ✅ Done

### Backend / API
- [x] FastAPI app — CRM, visits, MoM, tickets, chat, health, admin API.
- [x] Postgres schema (migrations 001–007): clients, contacts, visits (sensitivity tier + GPS),
      agenda, meeting minutes, action items, opportunities, tickets, outbox, todos.
- [x] Transactional outbox → Redis Streams bus → worker dispatch (idempotent, per-entity locks).
- [x] Tier-1 cloud guard (fail-closed 422) — confidential content never leaves the device.
- [x] Bearer-token auth; security headers; strict CORS.
- [x] **Username/password login** (`/auth/login`) — operator `thomas`; console fetches the
      bearer token after sign-in (no hand-pasted tokens). pbkdf2-sha256, stdlib only.

### Integrations (all connected & verified live 2026-06-13)
- [x] **Plane** — `https://plane.bimats.com`, workspace `bimdevops` → **24 projects**. Key stored in DB.
- [x] **Notion** — internal integration → **52 databases** accessible. Token stored in DB.
- [x] **OpenRouter** — key valid (free tier, 10/mo). `data_collection: deny` enforced.
- [x] Admin "Test" buttons do **real** REST checks and report counts (projects / databases).

### AI / Models
- [x] Model registry (migration 006): on-device Gemma 2B + 2 OpenRouter Gemma 4 models.
- [x] Per-model "Test" → on-device noted; OpenRouter pinged live (3/3 ready).
- [x] **Maria chat is real** — `/chat` builds a live CRM snapshot and answers via OpenRouter
      (pinned no-logging chain), with a deterministic DB fallback if the cloud is down.

### Admin console (`/admin`)
- [x] Enterprise UI: sidebar nav, KPI cards, MCP / Skills / AI & Models / Workflow pages.
- [x] **Sign-in overlay** (username + password) replaces the fragile token prompt.
- [x] Live KPIs: outbox depth, integrations connected, models ready.
- [x] MCP CRUD + per-row env-secret management (redacted on read).
- [x] Default `echo-test` skill (smoke-tests the agent pipeline).

### Mobile (iOS / SwiftUI)
- [x] App scaffold: 4 tabs, Today brief, Settings (API URL + token via Keychain), Face ID lock.
- [x] Networking client → live API; graceful loading/empty/error/needs-token states.
- [x] **Maria chat calls the real `/chat`** endpoint (was a hardcoded reply).

### Deployment / Infra
- [x] Docker Compose stack: Postgres, Redis, Qdrant, api, worker.
- [x] Traefik v3.5 reverse proxy + Let's Encrypt (DNS-01 via Cloudflare). Full (Strict) SSL.
- [x] Dockhand management UI. nginx docker-socket-proxy (API version rewrite).
- [x] git-clone deploy on the VM; schema applied via psql; secrets in `.env` (never committed).

---

## 🔧 In progress / next

- [ ] **Mobile UI restyle** to match `ui/index.html` (navy gradient header, Maria AI-brief card,
      stat cards, to-do chips, purple FAB chat). _Scaffold styled but not yet pixel-matched._
- [ ] **In-app model test** surface (on-device Gemma 2B + OpenRouter) in Settings.

## 🗓️ Later (team phase)
- [ ] Microsoft Entra ID (PKCE) login + RBAC — replaces the single shared token.
- [ ] AgentScope planner/worker/critic for MoM drafting; Qdrant RAG retrieval in chat.
- [ ] Inbound Plane status sync (webhook/poll); Notion write-once dispatch.
- [ ] Langfuse tracing (keys blank → no-op today).
- [ ] Kafka bus backend (drop-in for Redis Streams at scale).

---

## ⚠️ Notes / risks
- OpenRouter free tier is **10 requests/month** — chat will throttle quickly; add credits or a
  paid key for real usage. Tier-1 (confidential) drafting must stay on-device regardless.
- MVP is single-user (one shared API token behind the login). Do not expose `/admin` publicly
  without the sign-in layer.
- Secrets live in the VM `.env` and the DB (redacted on read) — never commit real keys.
