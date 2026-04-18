-- Scenario sessions: persistent session for scenario workflows (research + simulation).
-- One session = one credit. Covers deep research + first simulation run.
-- Additional simulation runs on the same session cost one credit each.

CREATE TABLE IF NOT EXISTS scenario_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'researching', 'research_complete', 'simulating', 'completed', 'abandoned')),
  prompt TEXT NOT NULL,
  decision_context JSONB DEFAULT '{}',

  -- Research fields
  research_status TEXT,
  research_dossier JSONB,
  research_angles JSONB,
  research_started_at TIMESTAMPTZ,
  research_completed_at TIMESTAMPTZ,
  research_task_id TEXT,

  -- Simulation fields
  simulation_id TEXT,
  simulation_count INT NOT NULL DEFAULT 0,

  -- Files (metadata array; actual bytes in Supabase Storage bucket "session-files")
  uploaded_files JSONB NOT NULL DEFAULT '[]',

  -- Bundle / Full Analysis
  bundle_config JSONB,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_active
  ON scenario_sessions(user_id, created_at DESC)
  WHERE status NOT IN ('completed', 'abandoned');

-- Storage bucket "session-files" must be created via Supabase dashboard:
--   Public: false
--   Allowed MIME types: application/pdf, text/plain, text/markdown
--   Max file size: 10 MB
