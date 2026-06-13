# VM deploy — Traefik + Dockge + Maria One (Azure VM)

Single Azure VM (Ubuntu 24.04, 4 vCPU / 8 GiB). **Traefik** is the edge reverse
proxy (replaces the old host nginx) terminating TLS with Let's Encrypt; **Dockge**
gives a web UI to manage compose stacks. The app stack runs behind Traefik on a
shared `web` Docker network.

> Coexists with the existing **Outline VPN** (`shadowbox`, host-network, random
> high ports) and **watchtower** (`--scope outline`) — neither is touched.

## Topology

```
Cloudflare DNS (DNS-only / grey cloud)         *.technexus.info -> 4.194.153.78
        │  :80 / :443
        ▼
   Traefik (edge)  ── Let's Encrypt HTTP-01 (.well-known)
        │  docker labels, network: web
        ├── api.technexus.info     -> maria-one api:8000  (CRM API, /admin, /docs)
        └── dockge.technexus.info  -> dockge:5001         (compose management)
   Traefik dashboard -> 127.0.0.1:8080 (SSH tunnel only)
```

## Prerequisites (you control these)

1. **Cloudflare DNS** — A records (DNS only, grey cloud — required for HTTP-01):

   | Type | Name | Content |
   |---|---|---|
   | A | `*.technexus.info` (or `api`, `dockge`) | `4.194.153.78` |

2. **Azure NSG** — allow inbound TCP **80** and **443** (443 confirmed open; 80 is
   required for the ACME HTTP-01 challenge).

## Deploy

```bash
# on the VM (sudo docker — bimdevops is not in the docker group)
sudo docker network create web                 # once

git clone https://github.com/ThomasHeinThura/one-assistant.git ~/one-assistant
cd ~/one-assistant

# edge: Traefik + Dockge
cp deploy/vm/.env.example deploy/vm/.env        # set DOMAIN + ACME_EMAIL
sudo mkdir -p /opt/stacks
cd deploy/vm && sudo docker compose up -d

# app: behind Traefik
cd ~/one-assistant/backend
cp .env.example .env                            # set ENV=prod + API_TOKEN
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## Verify

```bash
sudo docker ps                                  # traefik, dockge, api, worker, db, redis, qdrant
sudo docker logs maria-edge-traefik-1 | grep -i acme   # cert issuance
curl -s localhost:8000/healthz                  # app liveness (host-bound)
```

- App API: `https://api.technexus.info` (+ `/admin`, `/docs` if ENV≠prod)
- Dockge: `https://dockge.technexus.info` (set an admin password on first load)
- Traefik dashboard: `ssh -L 8080:127.0.0.1:8080 …` then `http://localhost:8080`

## Cutover from nginx

The old host nginx was a dead forwarder (proxied to an unreachable Tailscale IP).
Deploy backs it up then removes it so Traefik can bind 80/443:

```bash
sudo cp /etc/nginx/sites-available/proxy ~/nginx-proxy.bak.conf
sudo systemctl disable --now nginx
sudo apt-get purge -y nginx nginx-common nginx-core && sudo apt-get autoremove -y
```

## Notes

- Certs auto-renew; Traefik retries ACME until 80/443 + DNS are reachable, so order
  doesn't matter — issuance completes on its own once prerequisites are in place.
- Adding a service: attach it to the `web` network and add the four `traefik.*`
  labels (see `backend/docker-compose.prod.yml`).
