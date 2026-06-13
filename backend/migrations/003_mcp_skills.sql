-- MCP integrations + agent skills registry (managed from the admin panel).
-- Secrets are NOT stored here: auth_ref is a Key Vault SECRET NAME, never the token.

CREATE TABLE IF NOT EXISTS mcp_integrations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL UNIQUE,           -- "Plane", "Notion", or a custom name
  kind        text NOT NULL DEFAULT 'custom' CHECK (kind IN ('plane','notion','custom')),
  transport   text NOT NULL DEFAULT 'http' CHECK (transport IN ('http','sse','stdio')),
  endpoint    text,                           -- URL (http/sse) or launch command (stdio)
  auth_ref    text,                           -- Key Vault secret NAME holding the token
  enabled     boolean NOT NULL DEFAULT false,
  status      text NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown','connected','error','disabled')),
  last_checked_at timestamptz,
  config      jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS skills (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL UNIQUE,           -- kebab-case slug
  description text NOT NULL,
  kind        text NOT NULL DEFAULT 'custom' CHECK (kind IN ('builtin','custom','test')),
  trigger     text,                           -- when Maria should use it
  enabled     boolean NOT NULL DEFAULT true,
  config      jsonb NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_touch_mcp ON mcp_integrations;
CREATE TRIGGER trg_touch_mcp BEFORE UPDATE ON mcp_integrations
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
DROP TRIGGER IF EXISTS trg_touch_skills ON skills;
CREATE TRIGGER trg_touch_skills BEFORE UPDATE ON skills
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Seed the two known integrations (disabled, no secrets — wire endpoints/auth_ref in admin).
INSERT INTO mcp_integrations (name, kind, transport, enabled, config) VALUES
  ('Plane',  'plane',  'http', false, '{"role":"tickets — source of truth for status (inbound sync)"}'),
  ('Notion', 'notion', 'http', false, '{"role":"meeting notes — write-once then human-owned"}')
ON CONFLICT (name) DO NOTHING;

-- Default skill for tests: round-trips through the agent + MCP layer to verify wiring.
INSERT INTO skills (name, description, kind, trigger, enabled, config) VALUES
  ('echo-test',
   'Round-trips a message through the agent + MCP layer to verify the pipeline is wired (no external side effects).',
   'test',
   'Run from the admin panel to smoke-test agent/MCP connectivity before relying on it.',
   true,
   '{"side_effects": false}')
ON CONFLICT (name) DO NOTHING;
