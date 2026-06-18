# 01 — MVP Scope

**Project:** Maria One

The MVP delivers a **four-tab app** with an **AI coordinator (Maria)** for a **single user (you)**.
You take the actions; Maria tracks status across modules, suggests next steps, and answers
questions about any client, deal, or ticket.

The CRM is **built in-house** in the backend (replacing Cockpit). The data model is ported from
`BIM.Visitplan`.

## The four tabs

1. **Today** — AI-prioritised to-do list + Maria's daily brief (action-needed items, at-risk deals,
   tickets to triage), with action triggers.
2. **VisitPlan** — plan/log visits; each visit has its own MoM, status, and workflow (RFI, pipeline
   link, follow-ups).
3. **CRM** — clients + sales pipeline; Maria flags healthy vs at-risk opportunities.
4. **Tickets** — Plane projects + Managed-Service tickets; view, update, create + assign.

## In scope (v1)

- **Native iOS app (Swift), four tabs** as above, modern navy/white SaaS UI.
- **AI coordinator (Maria):** inline suggestion cards in each module + a persistent quick-chat over
  all data, with **auto re-indexing** of new visits/deals/tickets into RAG.
- **In-house CRM (full schema).** Postgres-backed: clients, contacts, visits, agenda items, visit
  outcomes, opportunities (with pipeline health), tickets, projects, notes, files, activity
  timeline — modeled on `BIM.Visitplan`. Replaces Cockpit.
- **VisitPlan workflow.** GPS check-in/out, agenda, notes → **AI MoM** (attendees, discussion,
  decisions, action items with owner + due date) → review/confirm.
- **Dispatch fan-out.** A confirmed visit writes — together — a CRM outcome, Plane follow-up
  ticket(s), and a Notion note. Idempotent, with retry.
- **Tickets module.** List/update Plane tickets; create a ticket with an assignee; Maria suggests
  the assignee from history (RAG).
- **CRM module.** Pipeline list with AI health flags (healthy / watch / at-risk).
- **Cloud AI via Ollama Cloud (`gemma4:31b`).** All AI — chat and MoM drafting — runs server-side;
  the backend calls Ollama Cloud (no-logging, no-training). Visits/MoMs carry a sensitivity tier as
  a classification/audit label.
- **Self-hosted Langfuse.** One trace per visit/MoM and per dispatch call.

## Out of scope (deferred)

- **Team / multi-user.** The 14-member shared CRM, team ticket assignment across members, Microsoft
  Entra login, and role-based access come in a later phase. MVP is single-user.
- **Alternative model routing** (deepseek, gpt-oss, etc. behind the same Ollama Cloud key).
- **Pipeline/forecast reporting** (target vs actuals dashboards) beyond the health flag.
- **Offline-everything.** Basic offline capture only; full offline CRM sync later.
- **Other channels** (Telegram, etc.).
- **Encryption at rest** for attachments.

## Success criteria

1. **Today** shows an accurate AI brief: today's visits, at-risk deals, and tickets needing action,
   with working action triggers.
2. A planned visit can be checked into (GPS), run, drafted into a MoM, confirmed, and dispatched —
   producing a CRM outcome, a Plane ticket, and a Notion note, each with its external ID stored.
3. The CRM pipeline list flags healthy vs at-risk deals; a deal with no recent activity is at-risk.
4. You can create a ticket with an assignee, and ask Maria "show me ticket X" / "open MS tickets for
   client Y" and get a correct answer from RAG.
5. New visits/deals/tickets are **auto re-indexed** so chat answers reflect them within minutes.
6. A **Tier 1 (confidential)** visit is labelled as such and its MoM (drafted in the cloud via
   Ollama Cloud's no-logging endpoint) carries the tier through the trace and audit log.
7. Re-running dispatch never creates duplicate entries.

## Milestones

| # | Milestone | Done when |
|---|-----------|-----------|
| M0 | Backend shell + CRM schema | `docker compose up` healthy; CRM tables created and seedable |
| M1 | CRM modules | Clients/visits/opportunities/tickets CRUD via the in-house API |
| M2 | AI coordinator | Inline suggestions + quick-chat over RAG; auto re-index on writes |
| M3 | VisitPlan + MoM | Visit loop → AI MoM → confirm; trace in Langfuse |
| M4 | Dispatch fan-out | Confirmed MoM creates CRM outcome + Plane ticket + Notion note (idempotent) |
| M5 | iOS app (4 tabs) | Swift app: Today / VisitPlan / CRM / Tickets + AI chat (thin cloud client); MoM drafted server-side + tier tag |
