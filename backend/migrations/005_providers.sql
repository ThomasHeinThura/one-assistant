-- Correct the Plane base URL and register Ollama Cloud as a manageable integration.
-- Secret keys are added via the admin API (/mcp/{id}/env), never seeded here.

-- Plane is hosted at plane.bimats.com (not technexus).
UPDATE mcp_integrations
SET env = jsonb_set(COALESCE(env, '{}'), '{PLANE_BASE_URL}', '"https://plane.bimats.com"')
WHERE name = 'Plane';

-- Ollama Cloud (cloud LLM, Tier 2/3) — shown alongside Plane/Notion so its key +
-- connectivity are visible in the admin. Ollama's cloud does not log/train on prompts.
INSERT INTO mcp_integrations (name, kind, transport, endpoint, enabled, config)
VALUES ('Ollama', 'custom', 'http', 'https://ollama.com/v1', false,
        '{"role":"cloud LLM (Tier 2/3) — no prompt logging/training"}')
ON CONFLICT (name) DO NOTHING;
