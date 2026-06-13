-- AI model registry — what Maria can draft/embed/chat with, and whether each is
-- ready. Two providers: on-device (Gemma 2B via Apple MLX, runs on the iPhone)
-- and OpenRouter (Tier 2/3 cloud, no-logging). The admin shows readiness + test.

CREATE TABLE IF NOT EXISTS ai_models (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  provider    text NOT NULL CHECK (provider IN ('on_device','openrouter')),
  model_id    text NOT NULL,
  role        text NOT NULL DEFAULT 'draft',     -- draft | embed | chat
  tier_use    text,                              -- which sensitivity tiers
  ready       boolean NOT NULL DEFAULT false,
  status      text NOT NULL DEFAULT 'unknown',   -- unknown | ready | error | on_device
  detail      text,
  last_checked_at timestamptz,
  sort        int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO ai_models (name, provider, model_id, role, tier_use, ready, status, detail, sort) VALUES
  ('Gemma 2B (on-device)', 'on_device', 'gemma-2b-mlx', 'draft', 'Tier 1/2/3', true, 'on_device',
   'Runs on the iPhone via Apple MLX — confidential (Tier-1) drafting never leaves the device. Test in the app.', 0),
  ('Gemma 4 31B (free)', 'openrouter', 'google/gemma-4-31b-it:free', 'draft', 'Tier 2/3', false, 'unknown',
   'Primary cloud drafter; data_collection: deny enforced.', 1),
  ('Gemma 4 26B A4B (free)', 'openrouter', 'google/gemma-4-26b-a4b-it:free', 'draft', 'Tier 2/3', false, 'unknown',
   'Fallback cloud drafter in the pinned chain.', 2)
ON CONFLICT DO NOTHING;
