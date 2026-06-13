-- 007_auth.sql — admin console login (username + password).
-- The MVP API uses a single shared bearer token. This adds a human login layer
-- on top so operators sign in with a username/password and the console fetches
-- the bearer token for them (no hand-pasted tokens). Team phase swaps this for
-- Microsoft Entra ID (PKCE) + RBAC — see docs/03-tech-stack.md.

CREATE TABLE IF NOT EXISTS admin_users (
    username      text PRIMARY KEY,
    password_hash text NOT NULL,           -- pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>
    display_name  text,
    role          text NOT NULL DEFAULT 'admin',
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);

-- Seed operator: thomas. Hash is pbkdf2-sha256 (200k iters) of the chosen
-- password — the plaintext is never stored. Rotate with /auth/password later.
INSERT INTO admin_users (username, password_hash, display_name)
VALUES (
    'thomas',
    'pbkdf2_sha256$200000$38668da9c4527c8ad886cc49f291bd79$5c39f00d5480230b933b2e655c7ad96357d3fb8f1b09791e114aa9e852f73441',
    'Thomas'
)
ON CONFLICT (username) DO NOTHING;
