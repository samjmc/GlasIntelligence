-- Add project_id to scenario_sessions so the session can be linked to a project
-- without relying on the projects table row (resilience / recovery path).
-- Migration 008 created an index on this column but never added it — this is the fix.
ALTER TABLE scenario_sessions ADD COLUMN IF NOT EXISTS project_id TEXT;

COMMENT ON COLUMN scenario_sessions.project_id IS 'Project ID linked at graph-build time; denormalised for resilience';
