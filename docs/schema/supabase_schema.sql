-- Glas Intelligence - Supabase Schema
-- Consolidated: base schema + migrations 002-009 (retention engine, atomic credits,
-- scenario sessions, research credits, bundle synthesis). Run this in the Supabase
-- SQL Editor to provision a fresh project. Source of truth: backend/migrations/.
--
-- Manual step (not SQL): create the Storage bucket "session-files"
--   Public: false | MIME: application/pdf, text/plain, text/markdown | Max: 10 MB

-- Industries (no FK deps, must come first)
create table if not exists industries (
  id text primary key,
  name text not null,
  country text not null,
  description text default ''
);

-- Seed industries
insert into industries (id, name, country, description) values
  ('energy_uk', 'Energy & Utilities', 'UK', 'UK energy sector: Ofgem regulation, price caps, net zero transition, grid infrastructure'),
  ('energy_us', 'Energy & Utilities', 'US', 'US energy sector: FERC regulation, state-level markets, renewable transition'),
  ('finance', 'Finance & Banking', 'Global', 'Banking regulation, capital markets, fintech, Basel framework'),
  ('geopolitics', 'Geopolitics', 'Global', 'International relations, conflict scenarios, sanctions, diplomatic dynamics')
on conflict (id) do nothing;

-- Profiles (extends Supabase auth.users)
create table if not exists profiles (
  id uuid references auth.users on delete cascade primary key,
  email text,
  display_name text,
  plan text default 'free' check (plan in ('free', 'payg', 'pro', 'business', 'enterprise')),
  credits integer default 0,
  research_credits integer not null default 0,
  selected_industry_id text references industries(id),
  stripe_customer_id text,
  created_at timestamptz default now()
);

alter table profiles enable row level security;
create policy "Users can read own profile" on profiles for select using (auth.uid() = id);
create policy "Users can update own profile" on profiles for update using (auth.uid() = id);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)));
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Projects
create table if not exists projects (
  id text primary key,
  user_id uuid references profiles(id) on delete cascade,
  name text,
  status text default 'created',
  simulation_requirement text,
  graph_id text,
  entities_count integer default 0,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table projects enable row level security;
create policy "Users can manage own projects" on projects for all using (auth.uid() = user_id);

-- Simulations
create table if not exists simulations (
  id text primary key,
  project_id text references projects(id) on delete cascade,
  user_id uuid references profiles(id) on delete cascade,
  status text default 'created',
  current_round integer default 0,
  total_actions integer default 0,
  created_at timestamptz default now()
);

alter table simulations enable row level security;
create policy "Users can manage own simulations" on simulations for all using (auth.uid() = user_id);

-- Reports
create table if not exists reports (
  id text primary key,
  simulation_id text references simulations(id) on delete cascade,
  user_id uuid references profiles(id) on delete cascade,
  status text default 'generating',
  markdown_content text,
  created_at timestamptz default now()
);

alter table reports enable row level security;
create policy "Users can manage own reports" on reports for all using (auth.uid() = user_id);

-- Credit transactions (type check includes research_usage/research_refund per migration 006)
create table if not exists credit_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id) on delete cascade,
  amount integer not null,
  type text not null check (type in ('purchase', 'usage', 'subscription_grant', 'refund', 'research_usage', 'research_refund')),
  description text default '',
  created_at timestamptz default now()
);

alter table credit_transactions enable row level security;
create policy "Users can read own transactions" on credit_transactions for select using (auth.uid() = user_id);

-- Decision bundles (migration 002 + synthesis column from 007)
create table if not exists decision_bundles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  title text not null,
  decision_context text,
  suggested_scenarios jsonb default '[]',
  completed_scenarios jsonb default '[]',
  status text default 'in_progress' check (status in ('in_progress', 'completed')),
  synthesis jsonb default null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

alter table decision_bundles enable row level security;
create policy "Users can manage own bundles" on decision_bundles for all using (auth.uid() = user_id);

-- Simulation reminders (migration 002)
create table if not exists simulation_reminders (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  simulation_id text not null,
  scenario text not null default '',
  remind_at timestamptz not null,
  sent boolean default false,
  created_at timestamptz default now()
);

alter table simulation_reminders enable row level security;
create policy "Users can manage own reminders" on simulation_reminders for all using (auth.uid() = user_id);

-- Scenario sessions (migrations 004 + 008 + 009: graph_id and project_id denormalized for resilience)
create table if not exists scenario_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  status text not null default 'active'
    check (status in ('active', 'researching', 'research_complete', 'simulating', 'completed', 'abandoned')),
  prompt text not null,
  decision_context jsonb default '{}',

  -- Research fields
  research_status text,
  research_dossier jsonb,
  research_angles jsonb,
  research_started_at timestamptz,
  research_completed_at timestamptz,
  research_task_id text,

  -- Simulation fields
  simulation_id text,
  simulation_count int not null default 0,

  -- Files (metadata array; actual bytes in Storage bucket "session-files")
  uploaded_files jsonb not null default '[]',

  -- Bundle / Full Analysis
  bundle_config jsonb,

  -- Resilience links (migrations 008/009)
  graph_id text,
  project_id text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_sessions_user_active
  on scenario_sessions(user_id, created_at desc)
  where status not in ('completed', 'abandoned');

create index if not exists idx_scenario_sessions_project_graph
  on scenario_sessions (project_id)
  where project_id is not null and project_id <> '' and graph_id is not null and graph_id <> '';

-- RLS on scenario_sessions (the app's central user table: prompts, research
-- dossiers, uploaded-file metadata). Safe to enable: the backend accesses this
-- table exclusively via the service-role key, which bypasses RLS — this policy
-- only blocks direct anon-key reads of other users' sessions. The backend's
-- service-role writes are unaffected.
alter table scenario_sessions enable row level security;
create policy "Users can read own sessions" on scenario_sessions
  for select using (auth.uid() = user_id);
create policy "Users can update own sessions" on scenario_sessions
  for update using (auth.uid() = user_id);
create policy "Users can insert own sessions" on scenario_sessions
  for insert with check (auth.uid() = user_id);
create policy "Users can delete own sessions" on scenario_sessions
  for delete using (auth.uid() = user_id);

-- Indexes
create index if not exists idx_projects_user_id on projects(user_id);
create index if not exists idx_simulations_user_id on simulations(user_id);
create index if not exists idx_simulations_project_id on simulations(project_id);
create index if not exists idx_reports_user_id on reports(user_id);
create index if not exists idx_reports_simulation_id on reports(simulation_id);
create index if not exists idx_credit_transactions_user_id on credit_transactions(user_id);
create index if not exists idx_bundles_user on decision_bundles(user_id);
create index if not exists idx_bundles_status on decision_bundles(status);
create index if not exists idx_reminders_user on simulation_reminders(user_id);
create index if not exists idx_reminders_due on simulation_reminders(remind_at) where sent = false;

-- Feed simulations (public scenario intelligence content)
create table if not exists feed_simulations (
  id uuid primary key default gen_random_uuid(),
  industry_id text references industries(id),
  title text not null,
  summary text default '',
  scenario_description text,
  simulation_id text references simulations(id),
  report_id text references reports(id),
  published_at timestamptz,
  is_published boolean default false,
  is_industry_specific boolean default false,
  created_at timestamptz default now()
);

alter table feed_simulations enable row level security;
create policy "Anyone can read published feed simulations" on feed_simulations
  for select using (is_published = true);
create policy "Admins can manage feed simulations" on feed_simulations
  for all using (auth.uid() in (select unnest(string_to_array(current_setting('app.admin_ids', true), ','))::uuid));

create index if not exists idx_feed_simulations_industry on feed_simulations(industry_id);
create index if not exists idx_feed_simulations_published on feed_simulations(is_published, published_at);

-- Feed view tracking (for free-tier monthly limits)
create table if not exists feed_views (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id) on delete cascade,
  feed_simulation_id uuid references feed_simulations(id) on delete cascade,
  viewed_at timestamptz default now(),
  unique(user_id, feed_simulation_id)
);

alter table feed_views enable row level security;
create policy "Users can read own views" on feed_views for select using (auth.uid() = user_id);
create policy "Users can insert own views" on feed_views for insert with check (auth.uid() = user_id);

create index if not exists idx_feed_views_user_month on feed_views(user_id, viewed_at);

-- ============================================================================
-- RPC functions (migrations 003 + 005)
-- ============================================================================

-- One-time backfill from migration 005 (comment out for fresh installs — only
-- run when migrating an existing user base so paid plans get research credits):
-- UPDATE profiles SET research_credits = 3 WHERE plan = 'pro';
-- UPDATE profiles SET research_credits = 13 WHERE plan = 'business';
-- UPDATE profiles SET research_credits = 33 WHERE plan = 'enterprise';

-- Atomic credit deduction — prevents race conditions.
-- Returns the new credit balance, or -1 if insufficient credits.
create or replace function deduct_credit_atomic(
    p_user_id uuid,
    p_description text default 'simulation'
)
returns integer
language plpgsql
security definer
as $$
declare
    v_new_credits integer;
begin
    update profiles
    set credits = credits - 1
    where id = p_user_id and credits >= 1
    returning credits into v_new_credits;

    if v_new_credits is null then
        return -1;
    end if;

    insert into credit_transactions (user_id, amount, type, description)
    values (p_user_id, -1, 'usage', p_description);

    return v_new_credits;
end;
$$;

-- Atomic research-credit deduction (one per deep research run).
create or replace function deduct_research_credit_atomic(
    p_user_id uuid,
    p_description text default 'deep_research'
)
returns integer
language plpgsql
security definer
as $$
declare
    v_new_credits integer;
begin
    update profiles
    set research_credits = research_credits - 1
    where id = p_user_id and research_credits >= 1
    returning research_credits into v_new_credits;

    if v_new_credits is null then
        return -1;
    end if;

    insert into credit_transactions (user_id, amount, type, description)
    values (p_user_id, -1, 'research_usage', p_description);

    return v_new_credits;
end;
$$;

-- Refund helper (for failed research).
create or replace function refund_research_credit(
    p_user_id uuid,
    p_description text default 'research_refund'
)
returns integer
language plpgsql
security definer
as $$
declare
    v_new_credits integer;
begin
    update profiles
    set research_credits = research_credits + 1
    where id = p_user_id
    returning research_credits into v_new_credits;

    insert into credit_transactions (user_id, amount, type, description)
    values (p_user_id, 1, 'research_refund', p_description);

    return coalesce(v_new_credits, 0);
end;
$$;
