-- Glas Intelligence - Supabase Schema
-- Run this in the Supabase SQL Editor

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

-- Credit transactions
create table if not exists credit_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references profiles(id) on delete cascade,
  amount integer not null,
  type text not null check (type in ('purchase', 'usage', 'subscription_grant', 'refund')),
  description text default '',
  created_at timestamptz default now()
);

alter table credit_transactions enable row level security;
create policy "Users can read own transactions" on credit_transactions for select using (auth.uid() = user_id);

-- Indexes
create index if not exists idx_projects_user_id on projects(user_id);
create index if not exists idx_simulations_user_id on simulations(user_id);
create index if not exists idx_simulations_project_id on simulations(project_id);
create index if not exists idx_reports_user_id on reports(user_id);
create index if not exists idx_reports_simulation_id on reports(simulation_id);
create index if not exists idx_credit_transactions_user_id on credit_transactions(user_id);

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

