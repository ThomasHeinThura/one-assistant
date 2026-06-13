-- Optional dev seed (M0 success criterion: "CRM tables created and seedable").
-- Safe to run repeatedly: uses fixed UUIDs + ON CONFLICT DO NOTHING.
INSERT INTO people (id, name, email, role) VALUES
  ('00000000-0000-0000-0000-0000000000a1','Hein','thomas.h.thura@bimgoc.com','am'),
  ('00000000-0000-0000-0000-0000000000a2','Aung','aung@bimgoc.com','solution'),
  ('00000000-0000-0000-0000-0000000000a3','Su','su@bimgoc.com','solution'),
  ('00000000-0000-0000-0000-0000000000a4','Linn','linn@bimgoc.com','solution')
ON CONFLICT (id) DO NOTHING;

INSERT INTO clients (id, name, account_type, status) VALUES
  ('00000000-0000-0000-0000-0000000000c1','Thai Bank','banking','active'),
  ('00000000-0000-0000-0000-0000000000c2','Vietnam Finance','finance','active'),
  ('00000000-0000-0000-0000-0000000000c3','Myanmar Banking','banking','active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO opportunities (id, client_id, title, stage, pipeline_value_usd, health, last_activity_at) VALUES
  ('00000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000c1','Thai Bank — SLA renewal','quotation',420000,'at_risk', now() - interval '21 days'),
  ('00000000-0000-0000-0000-0000000000e2','00000000-0000-0000-0000-0000000000c2','Vietnam Finance — Core platform','proposal_commercial',650000,'healthy', now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO tickets (id, client_id, title, type, status, priority, assignee_id, plane_issue_id, sync_source) VALUES
  ('00000000-0000-0000-0000-0000000000f1','00000000-0000-0000-0000-0000000000c1','DB latency on core banking','managed_service','new','high', NULL, NULL, 'local')
ON CONFLICT (id) DO NOTHING;
