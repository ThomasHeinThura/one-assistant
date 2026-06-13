# 04 — Architecture

**Project:** Maria One

## Components

```mermaid
flowchart TD
  subgraph Phone["iOS app (Swift / SwiftUI)"]
    VIS["Visit UI<br/>plan · check-in · notes"]
    GEMMA["Gemma 2B (Apple MLX)<br/>MoM draft + sensitivity tag"]
    VIS --> GEMMA
  end

  subgraph Backend["Backend (Docker)"]
    API["FastAPI<br/>CRM + visit + MoM API"]
    CRM[("In-house CRM<br/>PostgreSQL")]
    ORCH["AgentScope<br/>planner → worker → critic (MoM)"]
    DISP["Dispatch worker<br/>(outbox)"]
    QD[("Qdrant RAG<br/>past MoMs / docs")]
    LF["Langfuse (self-hosted)"]
  end

  subgraph Cloud["Cloud LLM (Tier 2/3 only)"]
    OR["OpenRouter<br/>Gemma 4 free · data_collection=deny"]
  end

  subgraph Ext["External destinations"]
    PMCP["Plane MCP<br/>follow-up tickets"]
    NMCP["Notion MCP<br/>meeting notes"]
  end

  GEMMA -->|"visit + draft MoM (+tier)"| API
  API --> CRM
  API --> ORCH
  ORCH --> QD
  ORCH -->|Tier 2/3 heavier draft| OR
  ORCH --> API
  API -->|on confirm| DISP
  DISP --> CRM
  DISP --> PMCP
  DISP --> NMCP
  ORCH --> LF
  DISP --> LF
  CRM --> DASH["Dashboard"]
```

## AI coordinator (Maria)

Maria is an ambient layer over the three data modules, not a separate app. She has three jobs:

1. **Suggest** — inline, context-aware cards in each module (new visit → RFI/pipeline/follow-ups;
   new ticket → process + suggest assignee; pipeline → health flags).
2. **Answer** — a persistent quick-chat grounded in **Qdrant RAG** over all CRM data (visits, MoMs,
   clients, opportunities, tickets).
3. **Coordinate** — she reads status across modules to build the **Today** brief and to-do list.

```mermaid
flowchart LR
  subgraph Modules
    V["VisitPlan"]; C["CRM / pipeline"]; T["Tickets"]
  end
  V & C & T -->|writes| DB[("In-house CRM<br/>PostgreSQL")]
  DB -->|change events| RX["Auto re-index worker"]
  RX --> QD[("Qdrant RAG")]
  QD --> AI["Maria (AgentScope)"]
  AI -->|inline suggestions| V & C & T
  AI -->|quick-chat answers| CHAT["Assistant chat"]
  AI -->|brief + to-do| TODAY["Today tab"]
```

**Auto re-indexing.** Every write to the CRM (new visit, MoM, opportunity change, ticket) emits a
change event; a re-index worker embeds the new/changed record into Qdrant so Maria's chat and
suggestions reflect it within minutes. No manual reindex step.

> Full data-store design — PostgreSQL system of record, Qdrant RAG, Redis worker pools, the
> transactional outbox, and the AI **double/triple-check + reindex** flow — is in
> [07-datastore.md](07-datastore.md).

## Orchestration (Maria + sub-agents)

Maria is the **coordinator**. For simple things she answers directly; for long or parallel work she
spawns **sub-agents** (proposal draft, quotation assembly, ticket triage, follow-up chase) and
reconciles their results before any system is updated. This maps onto AgentScope: Maria is the
planner/coordinator, sub-agents are workers, and a critic gates writes.

```mermaid
flowchart LR
  U["You take actions"] --> M["Maria (coordinator)"]
  M -->|long / parallel| SUB["Sub-agents"]
  SUB --> TOOLS["CRM · Plane MCP · Notion MCP · docs"]
  M --> TOOLS
  M --> FU["Follow-ups / reminders"]
  M --> Q["'What happened to deal X?'"]
  TOOLS --> DB[("CRM + RAG")]
  DB -->|realtime re-index| BRIEF["Today brief + suggestions"]
```

See [06-workflows.md](06-workflows.md) for the full deal lifecycle and per-module state machines.



```mermaid
sequenceDiagram
  participant U as User
  participant P as iOS app (Gemma 2B)
  participant A as Backend CRM API
  participant O as AgentScope (MoM)
  participant D as Dispatch worker
  participant X as CRM + Plane + Notion
  participant L as Langfuse

  U->>P: Plan visit, check in (GPS), take notes
  P->>P: Tag sensitivity tier
  alt Tier 1 (confidential)
    P->>P: Draft MoM on-device
  else Tier 2/3
    P->>A: Send agenda + notes
    A->>O: Draft MoM (RAG context)
    O->>L: Trace (tokens, cost)
    O-->>A: Structured MoM
    A-->>P: Draft MoM
  end
  U->>P: Review + confirm MoM
  P->>A: Confirm (visit_id, MoM)
  A->>D: Enqueue dispatch (status = pending)
  D->>X: Create CRM outcome + Plane ticket(s) + Notion note
  X-->>D: External ids
  D->>A: Store ids, mark dispatched
  D->>L: Close trace
```

## Sensitivity-tier policy

The phone decides the tier **before any data leaves the device**. The backend re-checks as defense
in depth.

| Tier | Example | MoM drafting path | Cloud allowed? |
|---|---|---|---|
| 🔴 1 Confidential | Banking client meeting | On-device Gemma 2B only | **No** |
| 🟡 2 Internal | Internal/partner meeting | OpenRouter Gemma 4 free + `data_collection: "deny"` | Yes, no-logging only |
| 🟢 3 Public/testing | Generic / test content | Any free model | Yes |

**Enforcement:** every cloud request sends `provider: { data_collection: "deny" }` (fail closed).
The backend rejects any Tier-1 MoM flagged for cloud. A periodic check of each pinned model's
`data_policy` (via the OpenRouter models API) alerts if a previously no-logging endpoint changes.

## In-house CRM data model

Built in PostgreSQL, ported from `BIM.Visitplan` (replacing Cockpit). Single-user in the MVP;
`users` / roles activate in the team phase.

### Core (visit loop)

- **clients** — `id, name, sector, account_type, status, am_id, address, phone, website, notes`
- **contacts** — `id, client_id, name, email, phone, position`
- **sectors** — `id, name, owner_am_id, active`
- **visits** — `id, title, client_id, contact_id, date, start_time, end_time, location,
  agenda, status(scheduled|in_progress|completed|missed), checkin_at, checkout_at,
  checkin_lat, checkin_lng, financial_year_id, financial_quarter_id`
- **agenda_items** — `id, visit_id, title, order, completed`
- **visit_outcomes** — `id, visit_id, result(positive|neutral|negative|no_show), summary,
  next_visit_date, attachments[], submitted_at`

### MoM (greenfield — the AI value-add)

- **meeting_minutes** — `id, visit_id, attendees[], discussion, decisions[],
  next_visit_date, status(draft|confirmed), drafted_by(on_device|cloud), confirmed_at`
- **action_items** — `id, mom_id, description, owner, due_date,
  dispatched_plane_id` (replaces the old `next_action` text/regex hack)

### Sales / CRM extensions (full schema upfront)

- **opportunities** — `id, client_id, title, stage(lead|visit|qualified|proposal_tech|
  proposal_commercial|quotation|contract|won|lost), status, probability,
  pipeline_value_usd` *(real numeric field)*, `target_close_date, health(healthy|watch|at_risk),
  loss_reason, renewal_status, financial_year_id, financial_quarter_id, description`
- **deal_stage_history** — `id, opportunity_id, from_stage, to_stage, changed_by, changed_at` (audit
  of every transition; powers realtime + the lifecycle strip)
- **documents** — `id, client_id, opportunity_id, type(rfi|questionnaire|technical_proposal|
  commercial_proposal|quotation|invoice|contract|sow|kickoff), title, template_id, status(draft|
  sent|signed), body, created_at` (one row per document the lifecycle produces)
- **tickets** — `id, client_id, project_id, title, type(project|managed_service|cr), status(new|
  triaged|assigned|in_progress|review|done|blocked), assignee_id, due_date, plane_issue_id`
- **projects** — `id, client_id, opportunity_id, name, stage(handover|kickoff|sow|delivery|closure),
  status`
- **change_requests** — `id, project_id, title, status(raised|assessed|approved|rejected|scheduled|
  delivered), impact, commercial_impact_usd`
- **notes** — `id, client_id, title, body, created_by, created_at`
- **files** — `id, client_id, filename, mime, size, created_at`
- **timeline_events** — `id, client_id, item, content, parent_type, created_by, created_at`
- **financial_years**, **financial_quarters** — calendar reference tables

### Dispatch state (per visit)

Mirrors the outbox pattern: `crm_done`, `plane_done`/`plane_issue_id`,
`notion_done`/`notion_page_id`, `dispatch_error`, `attempts`, `dispatched_at`.

## MCP vs in-house placement

- **CRM → in-house.** The backend *is* the CRM (Postgres); no external CRM API.
- **Plane & Notion → MCP clients** run inside the backend, exposed to the agent/dispatch worker as
  tools.
- **The phone never speaks MCP.** It talks only to the backend CRM API. This keeps Plane/Notion
  secrets server-side and lets the dispatch worker own idempotency and retries.

## Team / multi-user (later phase)

- **users** — `id, name, email, ms_email, ms_id, role, approval_status, meeting_group,
  owned_sectors[], target_usd, team, active`
- Roles: `admin | management | sales | solution | am`; meeting groups: `infra | es | app | ms |
  account | all`. Visits gain `participants[]` for cross-department visibility.
- Microsoft Entra ID login (PKCE), reused from `BIM.Visitplan`.
