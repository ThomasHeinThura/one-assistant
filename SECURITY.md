# Security Baseline — Maria One

Scope: the Docker/Azure backend, the iOS app, and the three external integrations
(Plane, Notion, Ollama Cloud). This is the regulated baseline the build follows —
mapped to OWASP ASVS, the CIS Docker Benchmark, and Azure's security baseline, with
an explicit eye on data-breach and CVE exposure.

## 1. Data classification & the privacy tiers (the core control)

The product handles **banking-client data**, so the sensitivity tier matters — but be
honest about what it does now:

**All AI runs in the cloud.** Every AI call (chat and MoM drafting) goes server-side to
**Ollama Cloud**, which does not log or train on prompts. There is **no on-device model**
and no on-device inference path. The previous guarantee — *"Tier-1 confidential never
leaves the device / never goes to cloud"* — **no longer holds and has been removed.**
Confidential data is processed in the cloud like everything else; the privacy basis is the
provider's no-logging / no-training policy, not on-device isolation.

The sensitivity tier is therefore an **advisory classification/audit label**, not a routing
or residency guarantee:

| Tier | Data | What the label does now |
|---|---|---|
| 🔴 1 Confidential | Banking/PII/credentials | Flagged for review/audit and traced; MoM is still drafted in the cloud via Ollama Cloud (no logging, no training). It does **not** keep data on-device — there is no on-device path. |
| 🟡 2 Internal | Internal/partner | Internal classification for reporting/audit. |
| 🟢 3 Public | Generic/test | Lowest-sensitivity marker. |

The tier is set on the phone and carried through to the Langfuse trace for audit. Because
no inference happens on the device, there is no longer a server-side "Tier-1 cloud block"
to enforce — the residency guarantee it backed no longer exists.

> **Open decision to confirm before go-live:** for Tier-1 (banking/PII) content, decide
> whether it is dispatched to **Notion** (an external SaaS) and how long it is persisted
> server-side in Postgres/Qdrant. Since on-device isolation is no longer available, controls
> for confidential data rest on: the no-logging Ollama Cloud provider, in-stack Langfuse,
> retention limits, and (optionally) suppressing Notion fan-out for Tier-1.

## 2. Secrets

- **Never** in images, source, or `.env` committed to git. `.dockerignore` excludes
  `.env*`; only `.env.example` (placeholders) is tracked.
- Azure: **Key Vault** + Container Apps secret references; managed identity to read
  the vault — no connection strings in app settings.
- API token, Plane key, Notion token, Ollama Cloud key (`OLLAMA_API_KEY`), Langfuse keys:
  rotate on a schedule; revoke on staff change.
- iOS: bearer token in the **Keychain** (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`),
  never `UserDefaults`/`Info.plist`.

## 3. Authentication & authorization

- MVP: single rotating **bearer token** over TLS (`security.require_auth`,
  constant-time compare). Prod refuses to start without `API_TOKEN`.
- Team phase: **Microsoft Entra ID** (PKCE) + 5-role RBAC; scope every query by role.
- Admin/ops console (`/admin`) is served **only behind the ingress auth** — never
  expose it publicly without Entra in front.

## 4. Transport & network

- TLS 1.2+ everywhere; **HSTS** in prod (set in `main.middleware`).
- No inbound ports open on the host: Cloudflare Tunnel (dev/parity) or Azure
  Front Door/Container Apps ingress (prod). Compose binds DB/Redis/Qdrant to
  `127.0.0.1` only.
- Postgres/Redis/Qdrant are **not internet-reachable** — private VNet only in Azure.
- **CORS** is an allow-list of exact origins; never `*` in prod.
- Security headers on every response: `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, HSTS.

## 5. Container hardening (CIS Docker Benchmark)

- Multi-stage build; **non-root** user (uid 10001); `cap_drop: ALL`;
  `no-new-privileges:true`.
- Pinned base + dependency versions for reproducible, scannable builds.
- Read-only root filesystem where feasible (add `read_only: true` + tmpfs in prod).
- Healthchecks on every service; orchestrator gates traffic on `/readyz`.

## 6. CVE / supply-chain management

- **Pin** all images and Python deps (done). Track exact versions so a scan maps
  to a fix.
- **Scan in CI** before deploy — fail the build on HIGH/CRITICAL:
  ```bash
  trivy image maria-one-api:$(git rev-parse --short HEAD)   # image CVEs
  pip-audit -r backend/requirements.txt                      # Python advisories
  trivy fs --scanners vuln,secret,misconfig backend          # deps + leaked secrets + IaC
  ```
- **Dependabot/Renovate** for automated dependency PRs; rebuild base images
  weekly to pick up distro patches.
- **SBOM** generated at build (`syft`) and stored with the release.
- Pin base images by **digest** (`python:3.12-slim@sha256:…`) in prod to defeat
  tag mutation.

## 7. Application-layer (OWASP)

- **SQL injection:** all queries are parameterized via asyncpg (`$1,$2…`); no
  string-built SQL.
- **Input validation:** Pydantic v2 models on every endpoint; tier is `1..3`,
  enums checked.
- **Idempotency:** outbox `idempotency_key` + per-destination `dispatch_targets`
  prevent duplicate external writes on retry (also a correctness control).
- **Rate limiting / abuse:** enforce at the ingress (Front Door WAF / Cloudflare)
  and per-token in Redis.
- **No stack traces to clients** in prod; OpenAPI docs disabled in prod.

## 8. Data at rest, backups, retention

- Azure managed Postgres: encryption at rest (platform), TLS in transit,
  point-in-time restore.
- **Daily encrypted backups**, 30-day retention (docs/03). Test restore quarterly.
- Object storage (attachments): private, encrypted; pre-signed URLs only.
  *(Attachment encryption-at-rest is a tracked fast-follow.)*
- Right-to-erasure: Postgres is the single source of truth, so deletion + a Qdrant
  re-index purges derived copies; Plane/Notion deletions handled per integration.

## 9. Observability & incident response

- **Self-hosted Langfuse** traces every model call + dispatch (tokens, cost, tier,
  destination) — kept in-stack, so trace metadata stays out of a 3rd-party observability
  SaaS. Use it to audit which model handled each visit and at what tier. (Note: the AI
  prompts themselves are sent to Ollama Cloud, which does not log or train on them.)
- Centralize app logs (Azure Monitor); **no secrets/PII in logs**.
- Alert on: failed dispatch backlog, outbox dead-letter growth, Ollama Cloud errors/quota,
  auth failures spike.

## 10. Pre-go-live checklist

- [ ] `API_TOKEN` set (prod refuses to boot without it) and rotated.
- [ ] All secrets in Key Vault; none in image/env/git.
- [ ] CORS origins locked to the real app/admin origins.
- [ ] Trivy + pip-audit clean (no HIGH/CRITICAL) in CI gate.
- [ ] Base images pinned by digest; SBOM archived.
- [ ] DB/Redis/Qdrant on private network; no public ports.
- [ ] Tier-1 handling decision recorded (Notion fan-out? retention?); tier label verified in a Langfuse trace. (No on-device path — all AI is cloud-side via Ollama Cloud.)
- [ ] Backup + restore tested.
- [ ] WAF + rate limiting enabled at ingress.
