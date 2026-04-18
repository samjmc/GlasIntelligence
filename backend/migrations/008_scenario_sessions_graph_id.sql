-- Denormalized Zep graph id on sessions so graph_id survives missing Supabase projects rows or disk issues.
ALTER TABLE scenario_sessions ADD COLUMN IF NOT EXISTS graph_id TEXT;

COMMENT ON COLUMN scenario_sessions.graph_id IS 'Zep graph id copied from project at build/link time for recovery';

CREATE INDEX IF NOT EXISTS idx_scenario_sessions_project_graph
  ON scenario_sessions (project_id)
  WHERE project_id IS NOT NULL AND project_id <> '' AND graph_id IS NOT NULL AND graph_id <> '';
