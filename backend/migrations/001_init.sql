-- Maria One — initial CRM schema (M0/M1)
-- Postgres is the system of record. Qdrant / Redis / Plane / Notion are derived
-- (see docs/07-datastore.md). This migration is idempotent on a fresh DB.
--
-- Design notes baked in from the pre-build audit:
--   * sensitivity tier lives on visits + meeting_minutes (Tier-1 = on-device only)
--   * agenda_items is a real checklist (audit gap: UI had only free-text agenda)
--   * dispatch is tracked PER DESTINATION (dispatch_targets), not a single id
--   * per-object source-of-truth: tickets carry sync_source + last_synced_at so an
--     inbound Plane change is not clobbered by the verifier
--   * todos carry a source (user|ai) + dedup_key so re-derivation can't wipe user tasks
--   * outbox row is written in the SAME txn as every change (transactional outbox)

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- People (lightweight in MVP; full users/RBAC table lands in the team phase).
-- Needed even for single-user MVP because assignee suggestion references a person.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS people (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  email       text UNIQUE,
  role        text,                      -- admin|management|sales|solution|am (free text in MVP)
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sectors (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  owner_am_id  uuid REFERENCES people(id),
  active       boolean NOT NULL DEFAULT true
);

-- ---------------------------------------------------------------------------
-- Core CRM
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clients (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL,
  sector_id     uuid REFERENCES sectors(id),
  account_type  text,
  status        text NOT NULL DEFAULT 'active',
  am_id         uuid REFERENCES people(id),
  address       text,
  phone         text,
  website       text,
  notes         text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contacts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  name        text NOT NULL,
  email       text,
  phone       text,
  position    text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- sensitivity tier (advisory label): 1=confidential, 2=internal, 3=public
CREATE TABLE IF NOT EXISTS visits (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title         text NOT NULL,
  client_id     uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  contact_id    uuid REFERENCES contacts(id),
  visit_date    date,
  start_time    timestamptz,
  end_time      timestamptz,
  location      text,
  status        text NOT NULL DEFAULT 'scheduled'
                CHECK (status IN ('scheduled','in_progress','completed','missed')),
  sensitivity_tier smallint NOT NULL DEFAULT 2 CHECK (sensitivity_tier IN (1,2,3)),
  checkin_at    timestamptz,
  checkout_at   timestamptz,
  checkin_lat   double precision,
  checkin_lng   double precision,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agenda_items (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id    uuid NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  title       text NOT NULL,
  sort_order  int NOT NULL DEFAULT 0,
  completed   boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS visit_outcomes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id        uuid NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  result          text CHECK (result IN ('positive','neutral','negative','no_show')),
  summary         text,
  next_visit_date date,
  submitted_at    timestamptz
);

-- ---------------------------------------------------------------------------
-- MoM (the AI value-add). drafted_by records the privacy path actually taken.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meeting_minutes (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  visit_id         uuid NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  attendees        jsonb NOT NULL DEFAULT '[]',
  discussion       text,
  decisions        jsonb NOT NULL DEFAULT '[]',
  next_visit_date  date,
  status           text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed')),
  drafted_by       text NOT NULL DEFAULT 'cloud' CHECK (drafted_by IN ('on_device','cloud')),
  sensitivity_tier smallint NOT NULL DEFAULT 2 CHECK (sensitivity_tier IN (1,2,3)),
  content_hash     text,                 -- for RAG drift detection (Check 2)
  confirmed_at     timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS action_items (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mom_id              uuid NOT NULL REFERENCES meeting_minutes(id) ON DELETE CASCADE,
  description         text NOT NULL,
  owner_id            uuid REFERENCES people(id),
  due_date            date,
  dispatched_plane_id text             -- per-item Plane issue id (one MoM -> many tickets)
);

-- ---------------------------------------------------------------------------
-- Sales / pipeline
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunities (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id         uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  title             text NOT NULL,
  stage             text NOT NULL DEFAULT 'lead'
                    CHECK (stage IN ('lead','visit','qualified','proposal_tech',
                                     'proposal_commercial','quotation','contract','won','lost')),
  status            text NOT NULL DEFAULT 'open',
  probability       numeric(5,2),
  pipeline_value_usd numeric(14,2) NOT NULL DEFAULT 0,
  target_close_date date,
  health            text NOT NULL DEFAULT 'healthy' CHECK (health IN ('healthy','watch','at_risk')),
  loss_reason       text,
  renewal_status    text,
  description       text,
  last_activity_at  timestamptz,         -- powers health (at-risk = stale)
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS deal_stage_history (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  opportunity_id  uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
  from_stage      text,
  to_stage        text NOT NULL,
  changed_by      uuid REFERENCES people(id),
  changed_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       uuid REFERENCES clients(id) ON DELETE CASCADE,
  opportunity_id  uuid REFERENCES opportunities(id) ON DELETE CASCADE,
  type            text NOT NULL CHECK (type IN ('rfi','questionnaire','technical_proposal',
                  'commercial_proposal','quotation','invoice','contract','sow','kickoff')),
  title           text NOT NULL,
  status          text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','signed')),
  body            text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS projects (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  opportunity_id  uuid REFERENCES opportunities(id),
  name            text NOT NULL,
  stage           text NOT NULL DEFAULT 'handover'
                  CHECK (stage IN ('handover','kickoff','sow','delivery','closure')),
  status          text NOT NULL DEFAULT 'active',
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Tickets: Plane is the source of truth for STATUS. sync_source records who last
-- wrote the row so the verifier never clobbers an inbound Plane edit.
CREATE TABLE IF NOT EXISTS tickets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id       uuid REFERENCES clients(id) ON DELETE SET NULL,
  project_id      uuid REFERENCES projects(id) ON DELETE SET NULL,
  title           text NOT NULL,
  type            text NOT NULL DEFAULT 'managed_service'
                  CHECK (type IN ('project','managed_service','cr')),
  status          text NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new','triaged','assigned','in_progress','review','done','blocked')),
  priority        text NOT NULL DEFAULT 'normal',
  assignee_id     uuid REFERENCES people(id),
  description     text,
  due_date        date,
  plane_issue_id  text UNIQUE,           -- external mirror id
  sync_source     text NOT NULL DEFAULT 'local' CHECK (sync_source IN ('local','plane')),
  last_synced_at  timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS change_requests (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id           uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title                text NOT NULL,
  status               text NOT NULL DEFAULT 'raised'
                       CHECK (status IN ('raised','assessed','approved','rejected','scheduled','delivered')),
  impact               text,
  commercial_impact_usd numeric(14,2)
);

-- ---------------------------------------------------------------------------
-- Activity / notes / files / timeline
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  title       text,
  body        text,
  created_by  uuid REFERENCES people(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS files (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id   uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  filename    text NOT NULL,
  mime        text,
  size_bytes  bigint,
  storage_key text,                       -- S3-compatible object key
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS timeline_events (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id    uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  item         text NOT NULL,
  content      text,
  parent_type  text,
  parent_id    uuid,
  created_by   uuid REFERENCES people(id),
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- To-dos: source separates AI-derived from user-created; dedup_key keeps
-- re-derivation idempotent (audit gap #7).
CREATE TABLE IF NOT EXISTS todos (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title       text NOT NULL,
  status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','done')),
  due_date    date,
  priority    int NOT NULL DEFAULT 0,           -- AI priority rank
  source      text NOT NULL DEFAULT 'user' CHECK (source IN ('user','ai')),
  dedup_key   text,
  client_id   uuid REFERENCES clients(id) ON DELETE SET NULL,
  opportunity_id uuid REFERENCES opportunities(id) ON DELETE SET NULL,
  ticket_id   uuid REFERENCES tickets(id) ON DELETE SET NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS todos_dedup ON todos (dedup_key) WHERE dedup_key IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Transactional outbox + per-destination dispatch state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox (
  id              bigserial PRIMARY KEY,
  aggregate       text NOT NULL,          -- 'visit' | 'ticket' | 'opportunity' | ...
  aggregate_id    uuid NOT NULL,
  event           text NOT NULL,          -- 'created' | 'updated' | 'mom_confirmed' | ...
  payload         jsonb NOT NULL DEFAULT '{}',
  idempotency_key text UNIQUE,
  status          text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','done','failed','verified')),
  attempts        int NOT NULL DEFAULT 0,
  last_error      text,
  available_at    timestamptz NOT NULL DEFAULT now(),  -- backoff scheduling
  verified_at     timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS outbox_pending ON outbox (status, available_at);

-- One row per (source aggregate, destination). Lets a visit be half-dispatched
-- and surfaces partial failure (audit gap #6).
CREATE TABLE IF NOT EXISTS dispatch_targets (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate     text NOT NULL,            -- usually 'visit' or 'mom'
  aggregate_id  uuid NOT NULL,
  destination   text NOT NULL CHECK (destination IN ('crm','plane','notion')),
  status        text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','done','failed')),
  external_id   text,
  attempts      int NOT NULL DEFAULT 0,
  last_error    text,
  dispatched_at timestamptz,
  UNIQUE (aggregate, aggregate_id, destination)
);

-- updated_at maintenance
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY['clients','visits','meeting_minutes','opportunities','tickets'])
  LOOP
    EXECUTE format(
      'DROP TRIGGER IF EXISTS trg_touch_%1$s ON %1$s;
       CREATE TRIGGER trg_touch_%1$s BEFORE UPDATE ON %1$s
       FOR EACH ROW EXECUTE FUNCTION touch_updated_at();', t);
  END LOOP;
END $$;
