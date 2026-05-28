-- Day 4 sharing support for databases that already applied 001_initial_schema.sql.
-- Keep this idempotent so it can be applied safely from the Supabase SQL editor.

alter table public.runs
    add column if not exists shared boolean not null default false;

grant update (shared) on table public.runs to authenticated;
