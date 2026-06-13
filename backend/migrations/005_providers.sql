-- Correct the Plane base URL and register OpenRouter as a manageable integration.
-- Secret keys are added via the admin API (/mcp/{id}/env), never seeded here.

-- Plane is hosted at plane.bimats.com (not technexus).
UPDATE mcp_integrations
SET env = jsonb_set(COALESCE(env, '{}'), '{PLANE_BASE_URL}', '"https://plane.bimats.com"')
WHERE name = 'Plane';

-- OpenRouter (cloud LLM, Tier 2/3) — shown alongside Plane/Notion so its key +
-- connectivity are visible in the admin. data_collection:deny is enforced in the client.
INSERT INTO mcp_integrations (name, kind, transport, endpoint, enabled, config)
VALUES ('OpenRouter', 'custom', 'http', 'https://openrouter.ai/api/v1', false,
        '{"role":"cloud LLM (Tier 2/3) — provider.data_collection: deny"}')
ON CONFLICT (name) DO NOTHING;
