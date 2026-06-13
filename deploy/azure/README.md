# Azure deployment — Maria One backend

Target: **Azure Container Apps** (serverless containers, scale-to-N, managed TLS)
with **Azure Database for PostgreSQL Flexible Server**, **Azure Cache for Redis**,
and **Key Vault** for secrets. Qdrant and Langfuse run as additional container apps
(or VMs with managed disks). This mirrors `docker-compose.yml` so dev/prod parity holds.

```
                 Azure Front Door (WAF + TLS + rate limit)
                                │
                    Container Apps Environment (private VNet)
        ┌───────────────┬───────────────┬───────────────┬──────────────┐
      api (n)        worker (n)        qdrant         langfuse
        │               │
        └──────┬────────┘
        Postgres Flexible Server   Azure Cache for Redis     Key Vault
        (private endpoint)         (private endpoint)        (managed identity)
```

## Why this shape

- **Container Apps** gives KEDA autoscaling (scale `api` on HTTP concurrency,
  `worker` on Redis/outbox queue depth) and zero exposed ports — ingress only.
- **Managed Postgres** = encryption at rest, PITR backups, no DB ops burden.
- **Managed identity → Key Vault** means no connection strings in app config
  (SECURITY.md §2).
- Front Door provides the **WAF + rate limiting** the app layer relies on.

## One-time setup

```bash
az group create -n maria-one -l southeastasia

# Build & push the image to ACR (scan first — see SECURITY.md §6)
az acr create -g maria-one -n mariaoneacr --sku Standard
az acr build -r mariaoneacr -t maria-one-api:$(git rev-parse --short HEAD) ../../backend

# Deploy infra + apps
az deployment group create -g maria-one \
  --template-file main.bicep \
  --parameters imageTag=$(git rev-parse --short HEAD) \
               pgAdminPassword=@Microsoft.KeyVault... \
```

## Secrets (never in the image)

Store in Key Vault, reference from Container Apps:
`API_TOKEN`, `OPENROUTER_API_KEY`, `PLANE_API_KEY`, `NOTION_TOKEN`,
`LANGFUSE_SECRET_KEY`, DB/Redis connection strings.

```bash
az keyvault secret set --vault-name maria-one-kv --name API-TOKEN \
  --value "$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
```

## Migrations

Run `migrations/*.sql` against the Flexible Server once (init job or
`psql "$DATABASE_URL" -f migrations/001_init.sql`). The compose auto-init is
**dev-only**; in Azure run them as a one-shot Container Apps job so they're gated
and logged.

## Scaling rules (KEDA)

- `api`: scale 1→10 on HTTP concurrency (single user today; headroom for the team phase).
- `worker`: scale 0→5 on Redis list length / outbox `pending` count — drains
  reindex/dispatch backlog under load, idles to zero otherwise.

## Hardening (see SECURITY.md)

- Ingress: external on `api` only; `internal` for worker/qdrant/langfuse.
- Private endpoints for Postgres + Redis; no public network access.
- Diagnostic settings → Azure Monitor; alerts on dead-letter growth + Tier-1
  cloud rejections.
