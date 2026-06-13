# Maria One

A **sales & solution work assistant** with an AI coordinator (**Maria**) who tracks status across
your day, suggests the next step, and answers questions about any client, deal, or ticket. You do
the work; Maria keeps everything coordinated.

The app has **four tabs** plus an always-available AI:

1. **Today** — your AI-prioritised to-do list + Maria's daily brief (what needs action, what's
   at-risk), with action triggers.
2. **VisitPlan** — plan/log visits; each visit has its own **MoM**, status updates, and workflow.
3. **CRM** — clients + sales pipeline; Maria flags **healthy vs at-risk** deals.
4. **Tickets** — Plane projects + Managed-Service tickets; overview, updates, create + assign.

The CRM is **built in-house** as part of the backend (replacing Cockpit, which is slow). Plane and
Notion stay as external integrations.

## The AI coordinator (Maria)

- **Inline suggestions** in every module (e.g. a new visit → suggest RFI / pipeline link /
  follow-ups; a new ticket → process, store, and suggest an assignee).
- **Persistent chat icon** to quick-chat across all your data ("show me open MS tickets for Thai
  Bank", "which deals are at-risk?").
- **Auto re-indexing** keeps Maria's knowledge (RAG) current as you add visits, deals, and tickets.
- Each module has its **own SOP + workflow** that Maria walks you through.

## A visit, end to end (inside VisitPlan)

> **Plan visit → GPS check-in + agenda → AI drafts MoM → you confirm → dispatch to
> CRM + Plane + Notion.**

## Built from three existing projects

- **`BIM.Visitplan/`** — shipped Expo/RN visit app; we reuse its **CRM data model** (clients,
  contacts, visits, agenda, outcomes, opportunities) but replace its Cockpit backend.
- **`personal_ai/`** — backend shell: FastAPI gateway, PostgreSQL, Cloudflare tunnel, dashboard.
- **`AI_assistant/`** — AgentScope planner/worker/critic engine + Qdrant RAG, used to draft the MoM
  and extract action items.

> The new mobile app is a **fresh native Swift (iOS)** app, not an extension of the RN app.

## Core ideas

- **AI coordinates, you act.** Maria watches state across all three modules and surfaces what needs
  attention — she doesn't take over your actions.
- **Module SOPs + workflows.** Each module (VisitPlan / CRM / Tickets) has its own guided workflow.
- **AI writes the MoM.** Attendees, discussion, decisions, action items (owner + due date) — drafted
  by **Gemma 2B on-device (Apple MLX)**, reviewed by you before anything is created.
- **One confirm, three destinations.** Confirm a visit's MoM once, fan out to CRM + Plane + Notion.
- **Always current.** Auto re-indexing keeps the RAG knowledge base fresh for chat + suggestions.
- **Privacy by tier.** Confidential client data is tagged on-device and never sent to logged/free
  cloud endpoints. See [docs/04-architecture.md](docs/04-architecture.md).
- **Traced everywhere.** Self-hosted Langfuse records every model call and workflow step.

## Scope

- **MVP is single-user (you).** Team features for your 14 members — shared CRM, team ticket
  view/manage, Microsoft Entra login + role-based access — come in a later phase.
- **CRM is full-schema from day one** (clients, contacts, opportunities, tickets, projects, notes,
  files, activity timeline), modeled on `BIM.Visitplan`.

## Folder map

```
one-assistant/
├── README.md            # this file
├── docs/
│   ├── 01-mvp.md        # MVP scope, success criteria, milestones
│   ├── 02-features.md   # full feature list
│   ├── 03-tech-stack.md # backend, mobile, infra choices
│   ├── 04-architecture.md # components, CRM data model, MoM + dispatch, diagrams
│   ├── 05-workflow.md   # end-to-end narrative of one visit
│   ├── 06-workflows.md  # deal lifecycle + per-module state machines + orchestration
│   ├── 07-datastore.md  # DB/RAG/Redis stores, workload distribution, verify + reindex
│   └── 08-mobile-ux.md  # mobile gestures & QoL (mostly final native app)
├── ui/
│   └── index.html       # single-file UI/UX sample (no build step)
├── backend/             # FastAPI CRM + AI gateway, workers, Docker Compose
├── mobile/              # native iOS app (Swift / SwiftUI) scaffold
├── deploy/
│   ├── vm/              # Traefik + Dockhand edge stack for the Azure VM (prod)
│   └── azure/           # Azure Container Apps (Bicep) alternative
└── SECURITY.md          # security baseline (tiers, CVE/CIS, secrets)
```

> **Deployed:** Azure VM behind **Traefik** (TLS via Let's Encrypt) with **Dockhand**
> for management; services at `<svc>.technexus.info` via Cloudflare DNS. See
> [deploy/vm/README.md](deploy/vm/README.md).

## Quickstart (planned)

1. Read [docs/01-mvp.md](docs/01-mvp.md) for what the first version does.
2. Open `ui/index.html` in a browser to preview the visit → MoM → dispatch UX.
3. Backend + mobile implementation follows the phases in the project plan.

> Status: scaffolding and design docs. Implementation phases are tracked in the plan.
