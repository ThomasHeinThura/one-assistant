-- AI model registry — what Maria can draft/embed/chat with, and whether each is
-- ready. One provider: Ollama Cloud (the only AI engine; the on-device/SLM path was
-- removed). The admin shows readiness + test.

CREATE TABLE IF NOT EXISTS ai_models (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  provider    text NOT NULL CHECK (provider IN ('ollama')),
  model_id    text NOT NULL,
  role        text NOT NULL DEFAULT 'draft',     -- draft | embed | chat
  tier_use    text,                              -- which sensitivity tiers
  ready       boolean NOT NULL DEFAULT false,
  status      text NOT NULL DEFAULT 'unknown',   -- unknown | ready | error
  detail      text,
  last_checked_at timestamptz,
  sort        int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO ai_models (name, provider, model_id, role, tier_use, ready, status, detail, sort) VALUES
  ('Gemma 4 31B', 'ollama', 'gemma4:31b', 'draft', 'all tiers', false, 'unknown',
   'Primary cloud drafter on Ollama Cloud (Pro plan, no prompt logging).', 0)
ON CONFLICT DO NOTHING;
