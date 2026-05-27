-- QSim Playground initial Supabase schema.
-- Apply this file through the Supabase SQL editor. It is the source of truth for
-- Day 3 database tables, row-level security, triggers, realtime, and cron jobs.

create extension if not exists "uuid-ossp" with schema extensions;
create extension if not exists "pgcrypto" with schema extensions;
create extension if not exists "pg_cron" with schema extensions;

create table if not exists public.users_profile (
    id uuid primary key references auth.users(id) on delete cascade,
    tier text not null default 'free' check (tier in ('free', 'pro', 'enterprise')),
    monthly_runs_used int not null default 0 check (monthly_runs_used >= 0),
    quota_reset_at timestamptz not null default (date_trunc('month', now()) + interval '1 month'),
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.runs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    status text not null default 'queued' check (
        status in ('queued', 'running', 'done', 'failed', 'timeout', 'cancelled')
    ),
    template text,
    input_source text not null check (input_source in ('template', 'code', 'ir')),
    problem_ir jsonb not null,
    qubos jsonb,
    scorecards jsonb,
    winner_agent text,
    critic_verdict jsonb,
    refined_qubo jsonb,
    circuit_data jsonb,
    sim_result jsonb,
    classical_result jsonb,
    error text,
    total_runtime_ms int,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    deleted_at timestamptz
);

create index if not exists runs_user_created_idx
    on public.runs (user_id, created_at desc);

create index if not exists runs_user_active_created_idx
    on public.runs (user_id, created_at)
    where deleted_at is null;

create table if not exists public.run_events (
    id bigserial primary key,
    run_id uuid not null references public.runs(id) on delete cascade,
    event_type text not null,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists run_events_run_created_idx
    on public.run_events (run_id, created_at);

create table if not exists public.exports (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.runs(id) on delete cascade,
    format text not null check (format in ('notebook', 'pdf', 'script')),
    download_count int not null default 0,
    created_at timestamptz not null default now(),
    last_accessed_at timestamptz
);

create table if not exists public.rate_limit_log (
    id bigserial primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    action text not null,
    created_at timestamptz not null default now()
);

create index if not exists rate_limit_log_user_action_created_idx
    on public.rate_limit_log (user_id, action, created_at);

alter table public.users_profile enable row level security;
alter table public.runs enable row level security;
alter table public.run_events enable row level security;
alter table public.exports enable row level security;
alter table public.rate_limit_log enable row level security;

alter table public.run_events replica identity full;

do $$
begin
    if not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
            and schemaname = 'public'
            and tablename = 'run_events'
    ) then
        alter publication supabase_realtime add table public.run_events;
    end if;
end
$$;

revoke all on table public.users_profile from anon, authenticated;
revoke all on table public.runs from anon, authenticated;
revoke all on table public.run_events from anon, authenticated;
revoke all on table public.exports from anon, authenticated;
revoke all on table public.rate_limit_log from anon, authenticated;

grant select on table public.users_profile to authenticated;
grant update (display_name) on table public.users_profile to authenticated;

grant select on table public.runs to authenticated;
grant insert (user_id, template, input_source, problem_ir) on table public.runs to authenticated;
grant update (deleted_at) on table public.runs to authenticated;

grant select on table public.run_events to authenticated;
grant select on table public.exports to authenticated;

drop policy if exists users_profile_select_own on public.users_profile;
create policy users_profile_select_own
    on public.users_profile
    for select
    to authenticated
    using (auth.uid() = id);

drop policy if exists users_profile_update_own on public.users_profile;
create policy users_profile_update_own
    on public.users_profile
    for update
    to authenticated
    using (auth.uid() = id)
    with check (auth.uid() = id);

drop policy if exists runs_select_own_active on public.runs;
create policy runs_select_own_active
    on public.runs
    for select
    to authenticated
    using (auth.uid() = user_id and deleted_at is null);

drop policy if exists runs_insert_own on public.runs;
create policy runs_insert_own
    on public.runs
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists runs_update_own on public.runs;
create policy runs_update_own
    on public.runs
    for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists run_events_select_own_run on public.run_events;
create policy run_events_select_own_run
    on public.run_events
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.runs
            where runs.id = run_events.run_id
                and runs.user_id = auth.uid()
                and runs.deleted_at is null
        )
    );

drop policy if exists exports_select_own_run on public.exports;
create policy exports_select_own_run
    on public.exports
    for select
    to authenticated
    using (
        exists (
            select 1
            from public.runs
            where runs.id = exports.run_id
                and runs.user_id = auth.uid()
                and runs.deleted_at is null
        )
    );

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create or replace function public.create_users_profile()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.users_profile (id)
    values (new.id)
    on conflict (id) do nothing;
    return new;
end;
$$;

create or replace function public.prevent_client_tier_change()
returns trigger
language plpgsql
as $$
begin
    if current_setting('request.jwt.claim.role', true) = 'authenticated'
        and new.tier is distinct from old.tier then
        raise exception 'tier cannot be changed by client role';
    end if;
    return new;
end;
$$;

create or replace function public.increment_monthly_runs_used()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.status in ('done', 'failed')
        and old.status is distinct from new.status
        and old.status not in ('done', 'failed') then
        update public.users_profile
        set monthly_runs_used = monthly_runs_used + 1
        where id = new.user_id;
    end if;
    return new;
end;
$$;

drop trigger if exists users_profile_set_updated_at on public.users_profile;
create trigger users_profile_set_updated_at
    before update on public.users_profile
    for each row
    execute function public.set_updated_at();

drop trigger if exists users_profile_prevent_client_tier_change on public.users_profile;
create trigger users_profile_prevent_client_tier_change
    before update on public.users_profile
    for each row
    execute function public.prevent_client_tier_change();

drop trigger if exists auth_users_create_profile on auth.users;
create trigger auth_users_create_profile
    after insert on auth.users
    for each row
    execute function public.create_users_profile();

drop trigger if exists runs_increment_monthly_runs_used on public.runs;
create trigger runs_increment_monthly_runs_used
    after update of status on public.runs
    for each row
    execute function public.increment_monthly_runs_used();

select cron.unschedule(jobid)
from cron.job
where jobname in (
    'qsim-reset-monthly-quotas',
    'qsim-delete-stale-rate-limit-log',
    'qsim-free-tier-retention'
);

select cron.schedule(
    'qsim-reset-monthly-quotas',
    '0 0 1 * *',
    $$
    update public.users_profile
    set monthly_runs_used = 0,
        quota_reset_at = date_trunc('month', now()) + interval '1 month'
    where quota_reset_at < now();
    $$
);

select cron.schedule(
    'qsim-delete-stale-rate-limit-log',
    '*/15 * * * *',
    $$
    delete from public.rate_limit_log
    where created_at < now() - interval '1 hour';
    $$
);

select cron.schedule(
    'qsim-free-tier-retention',
    '0 3 * * *',
    $$
    update public.runs
    set deleted_at = now()
    from public.users_profile
    where users_profile.id = runs.user_id
        and users_profile.tier = 'free'
        and runs.deleted_at is null
        and runs.created_at < now() - interval '30 days';

    delete from public.runs
    where deleted_at is not null
        and deleted_at < now() - interval '7 days';
    $$
);
