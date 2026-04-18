-- Executive synthesis JSON for multi-scenario bundles (branch weights, marginals, narrative).
ALTER TABLE decision_bundles ADD COLUMN IF NOT EXISTS synthesis JSONB DEFAULT NULL;
