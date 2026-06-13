-- Extend MCP integrations to support stdio (command-launched) servers + env vars,
-- so e.g. Plane (uvx plane-mcp-server) can be configured from the admin portal.
--
-- env may hold secrets (PLANE_API_KEY). It is stored here for a single-user,
-- self-hosted deployment; the admin API REDACTS env values on read. For stricter
-- setups, move secrets to Key Vault and keep only their names here.

ALTER TABLE mcp_integrations
  ADD COLUMN IF NOT EXISTS command text,
  ADD COLUMN IF NOT EXISTS args jsonb NOT NULL DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS env  jsonb NOT NULL DEFAULT '{}';

-- Pre-fill Plane with the uvx stdio launch (from the provided mcp.json).
-- The secret PLANE_API_KEY is intentionally NOT seeded — add it in the admin UI.
UPDATE mcp_integrations
SET transport = 'stdio',
    command   = 'uvx',
    args      = '["plane-mcp-server","stdio"]'::jsonb,
    env       = '{"PLANE_WORKSPACE_SLUG":"bimdevops","PLANE_BASE_URL":"https://plane.technexus.info"}'::jsonb
WHERE name = 'Plane';
