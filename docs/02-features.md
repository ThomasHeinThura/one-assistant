# 02 — Features

**Project:** Maria One

Legend: ✅ MVP · 🔜 fast follow · 🧭 later

The app is **four tabs** (Today · VisitPlan · CRM · Tickets) with an **AI coordinator (Maria)**
present across all of them.

## Today (home) — AI coordinator brief

- ✅ **Daily brief** — Maria summarises the day: visits, at-risk deals, tickets needing action.
- ✅ **AI-prioritised to-do** — your tasks ranked by what matters (at-risk deal, unassigned ticket).
- ✅ **Action triggers** — act directly from a to-do (assign ticket, log call, draft email).
- ✅ **Health glance** — counts of visits, tickets-to-action, healthy deals.

## AI coordinator (Maria) — cross-cutting

- ✅ **Inline suggestions** — context-aware cards inside each module:
  - new visit → suggest workflow (RFI, pipeline link, follow-ups),
  - new/odd ticket → process, store, and suggest an assignee from history,
  - pipeline → flag healthy vs at-risk.
- ✅ **Persistent quick-chat** — a floating icon to ask about any client, deal, or ticket
  ("open MS tickets for Thai Bank", "which deals are at-risk?").
- ✅ **Auto re-indexing** — new visits/deals/tickets are embedded into RAG automatically, so chat
  and suggestions stay current.
- ✅ **Coordinates, doesn't take over** — you act; Maria tracks status and advises.

## Orchestration & realtime (agentic)

- ✅ **Coordinator + sub-agents** — Maria answers simple things herself, or spawns sub-agents for
  longer/parallel work (draft a proposal, assemble a quotation, triage a ticket, chase an approval).
- ✅ **Follow-up loop** — she proactively asks "what happened to deal X?" and records the answer
  across the right systems.
- ✅ **Realtime suggestions** — every CRM write is re-indexed, so her next suggestion reflects the
  latest state.
- ✅ **Deal lifecycle tracking** — cold call → visit → pipeline → proposals → quotation → contract →
  won/lost → project/MS → delivery, with stage history. See [06-workflows.md](06-workflows.md).
- ✅ **Per-module workflows** — Sales, Tickets, CR, Projects, Managed Service each run as a tracked
  state machine.
- ✅ **Lifecycle documents** — RFI, questionnaire, technical/commercial proposal, quotation, invoice,
  contract, kick-off, SOW: Maria knows which each stage needs and drafts them.

## Visit planning & logging (VisitPlan tab)

- ✅ **Today / visit list** — your day's 5–10 visits, scheduled vs completed.
- ✅ **Plan a visit** — pick client + contact, date/time, agenda; creates a CRM visit.
- ✅ **Agenda checklist** — per-visit agenda items you tick off during the meeting.
- ✅ **GPS check-in / check-out** — stamps location + time; sets visit status.
- ✅ **Notes capture** — jot raw notes during/after the meeting (text; voice later).
- 🔜 **Voice capture** — dictation → text feeding the MoM draft.
- 🧭 **Route / day planning** — order visits by location.

## AI Minutes of Meeting (the hero feature)

- ✅ **MoM drafting** — the backend (via Ollama Cloud, `gemma4:31b`) turns agenda + raw notes into structured minutes:
  attendees, discussion summary, **decisions**, and **action items (owner + due date)**.
- ✅ **Review & edit** — you correct/approve the draft before anything is created.
- ✅ **Action-item extraction** — each action becomes a candidate Plane ticket.
- 🔜 **Next-visit suggestion** — propose a follow-up date from the outcome.

## In-house CRM (full schema, replaces Cockpit)

- ✅ **Core objects** — clients, contacts, visits, agenda items, visit outcomes.
- ✅ **Sales objects** — opportunities (with a **real numeric pipeline value**, not the old
  `next_action` text hack), tickets, projects.
- ✅ **Activity** — notes, files, and an activity timeline per client.
- ✅ **Visit outcome** — result, summary, action items, next-visit date, attachments.
- 🔜 **Reports** — visits by sector/owner; target vs actuals.
- 🧭 **Team & RBAC** — Microsoft Entra login, 5 roles, group scoping for 14 members.

## Dispatch fan-out (one visit → three systems)

- ✅ **One-confirm fan-out** — a confirmed MoM writes, together:
  - **CRM** — visit outcome + opportunity update (in-house).
  - **Plane** (MCP) — follow-up ticket(s) from the action items.
  - **Notion** (MCP) — a meeting note.
- ✅ **Idempotent dispatch** — retries on failure; never double-creates.
- 🔜 **Selective dispatch** — choose which destinations to send per visit.

## Tickets module (Plane projects + Managed Service)

- ✅ **Ticket overview** — list projects + Managed-Service tickets with status.
- ✅ **Create + assign** — raise a ticket and assign it; Maria suggests an assignee from history.
- ✅ **Process + store** — new tickets are recorded in the CRM DB and indexed into RAG.
- ✅ **Ask about a ticket** — query Maria for a specific ticket or a client's open tickets.
- 🧭 **Team board (14 members)** — view/manage the whole team's tickets, scoped by role.

## Cloud AI (Ollama Cloud, `gemma4:31b`)

- ✅ **Cloud-only inference** — all AI (chat + MoM drafting) runs server-side; the backend calls
  Ollama Cloud's OpenAI-compatible endpoint. Ollama Cloud does not log or train on prompts.
- ✅ **Sensitivity tagging** — classify each visit/MoM into a tier as a metadata/audit label:
  - 🔴 **Tier 1 — confidential** (client/banking data).
  - 🟡 **Tier 2 — internal**.
  - 🟢 **Tier 3 — public/testing**.
  The tier is retained for classification and audit; it no longer keeps data on-device, because all
  AI now runs in the cloud (there is no on-device path).
- 🔜 **Additional models** — the paid Ollama Cloud plan unlocks other models (deepseek, gpt-oss, etc.)
  behind the same key for heavier drafting.

## Knowledge & retrieval

- ✅ **Qdrant RAG** — pull a client's past MoMs/docs as context when planning or drafting.
- 🔜 **Document indexing** — ingest uploaded client documents into per-client collections.

## Observability

- ✅ **Self-hosted Langfuse** — one trace per visit across MoM drafting and each dispatch call
  (tokens, cost, latency), tagged with sensitivity tier and destination.
- ✅ **Dashboard** — visits + MoM status + per-destination dispatch status.
- 🔜 **Langfuse dashboards** — cost/latency per model, escalation rate, tier distribution, errors.

## Security & privacy

- ✅ **No-logging cloud provider** — all AI runs via Ollama Cloud, which does not log or train on
  prompts. Sensitivity tiers are retained as classification/audit labels, not as an on-device
  routing guarantee (there is no on-device path anymore).
- 🧭 **Encryption at rest** — encrypt stored attachments.
