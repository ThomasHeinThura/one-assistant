# Security Baseline — Maria One

Scope: the Docker/Azure backend, the iOS app, and the three external integrations
(Plane, Notion, OpenRouter). This is the regulated baseline the build follows —
mapped to OWASP ASVS, the CIS Docker Benchmark, and Azure's security baseline, with
an explicit eye on data-breach and CVE exposure.

## 1. Data classification & the privacy tiers (the core control)

The product handles **banking-client data**, so the sensitivity tier is a hard
security boundary, not a UX nicety:

| Tier | Data | Rule (enforced in two places) |
|---|---|---|
| 🔴 1 Confidential | Banking/PII/credentials | MoM drafted **on-device only**. The app never makes a cloud LLM call; the backend **rejects** any Tier-1 cloud request (`security.assert_cloud_allowed`, fail-closed). Tier-1 embeddings must use an on-device/self-hosted model. |
| 🟡 2 Internal | Internal/partner | Cloud allowed **only** with `data_collection: "deny"` (OpenRouter, fail-closed). |
| 🟢 3 Public | Generic/test | Any free model. |

**Defense in depth:** the phone decides the tier first; the server re-checks. If a
no-logging cloud endpoint is unavailable, the request **errors** rather than
silently downgrading (fail-closed). A scheduled job re-reads each pinned model's
`data_policy` and alerts on change.

> **Open decision to confirm before go-live (from the pre-build audit):** does a
> Tier-1 MoM dispatch to **Notion** (an external SaaS) at all, and is it persisted
> server-side in Postgres/Qdrant? Recommended default: **Tier-1 stays on-device +
> CRM-only**, no Notion fan-out, embeddings on a self-hosted model.

## 2. Secrets

- **Never** in images, source, or `.env` committed to git. `.dockerignore` excludes
  `.env*`; only `.env.example` (placeholders) is tracked.
- Azure: **Key Vault** + Container Apps secret references; managed identity to read
  the vault — no connection strings in app settings.
- API token, Plane key, Notion token, OpenRouter key, Langfuse keys: rotate on a
  schedule; revoke on staff change.
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
  destination) — kept in-stack, so confidential prompts are never sent to a 3rd-party
  observability SaaS. Use it to prove Tier-1 visits never touched the cloud.
- Centralize app logs (Azure Monitor); **no secrets/PII in logs**.
- Alert on: Tier-1-cloud rejections, failed dispatch backlog, outbox dead-letter
  growth, `data_policy` drift on pinned models, auth failures spike.

## 10. Pre-go-live checklist

- [ ] `API_TOKEN` set (prod refuses to boot without it) and rotated.
- [ ] All secrets in Key Vault; none in image/env/git.
- [ ] CORS origins locked to the real app/admin origins.
- [ ] Trivy + pip-audit clean (no HIGH/CRITICAL) in CI gate.
- [ ] Base images pinned by digest; SBOM archived.
- [ ] DB/Redis/Qdrant on private network; no public ports.
- [ ] Tier-1 → on-device + (decision) no Notion/cloud; verified in a Langfuse trace.
- [ ] Backup + restore tested.
- [ ] WAF + rate limiting enabled at ingress.
