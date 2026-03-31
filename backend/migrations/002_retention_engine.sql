-- Retention and Monetization Engine: new tables
-- Run this migration against your Supabase project

CREATE TABLE IF NOT EXISTS decision_bundles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  decision_context TEXT,
  suggested_scenarios JSONB DEFAULT '[]',
  completed_scenarios JSONB DEFAULT '[]',
  status TEXT DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bundles_user ON decision_bundles(user_id);
CREATE INDEX IF NOT EXISTS idx_bundles_status ON decision_bundles(status);

ALTER TABLE decision_bundles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own bundles" ON decision_bundles
  FOR ALL USING (auth.uid() = user_id);


CREATE TABLE IF NOT EXISTS simulation_reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  simulation_id TEXT NOT NULL,
  scenario TEXT NOT NULL DEFAULT '',
  remind_at TIMESTAMPTZ NOT NULL,
  sent BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reminders_user ON simulation_reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON simulation_reminders(remind_at) WHERE sent = false;

ALTER TABLE simulation_reminders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own reminders" ON simulation_reminders
  FOR ALL USING (auth.uid() = user_id);
