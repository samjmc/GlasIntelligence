-- Allow the 'sim_failed' session status.
-- The run-status route, bundle runs and the startup sweep of stale 'simulating'
-- sessions (backend/app/__init__.py) all write 'sim_failed', but 004's CHECK never
-- allowed it, so every one of those updates was rejected.
-- 004 declared the CHECK inline, so Postgres named it scenario_sessions_status_check.

ALTER TABLE scenario_sessions DROP CONSTRAINT IF EXISTS scenario_sessions_status_check;
ALTER TABLE scenario_sessions ADD CONSTRAINT scenario_sessions_status_check
  CHECK (status IN ('active', 'researching', 'research_complete', 'simulating', 'completed', 'abandoned', 'sim_failed'));
