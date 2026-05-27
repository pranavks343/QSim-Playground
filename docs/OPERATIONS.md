# Operations

Operational runbooks will be expanded as deployment, monitoring, quota handling, and incident
response paths are implemented.

## Supabase Local Setup

1. Create the Supabase organization `qsim-playground-org`.
2. Create the free-tier project `qsim-playground-prod` in Mumbai (`ap-south-1`).
3. Save the generated database password in a password manager. Do not commit it.
4. Copy Project Settings -> API values into `backend/.env`:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_JWT_SECRET`
5. Authentication -> Providers:
   - Enable Email.
   - Disable Confirm email for local development signups.
   - Disable other providers until Google OAuth is explicitly planned.
6. Authentication -> URL Configuration:
   - Site URL: `http://localhost:3000`
   - Redirect URLs: `http://localhost:3000/**`
7. Database -> Extensions:
   - Enable `pg_cron`.
   - Enable `uuid-ossp`.
   - Confirm `pgcrypto` is enabled.
8. Verify locally:

```bash
cd backend
python -m pytest tests/test_supabase_connection.py
```

## Apply Database Schema

1. Open Supabase -> SQL Editor.
2. Paste and run `backend/infra/migrations/001_initial_schema.sql`.
3. Confirm Table Editor shows:
   - `users_profile`
   - `runs`
   - `run_events`
   - `exports`
   - `rate_limit_log`
4. Confirm RLS is enabled on all five tables.
5. Confirm Database -> Replication/Realtime includes `run_events`.
6. Confirm pg_cron jobs exist:
   - `qsim-reset-monthly-quotas`
   - `qsim-delete-stale-rate-limit-log`
   - `qsim-free-tier-retention`
7. Verify isolation locally:

```bash
cd backend
python -m pytest tests/test_rls.py
```

TODO Day 5: re-enable email confirmation before production launch and update the Site URL and
Redirect URLs to the Vercel production domain.

## Concurrency Verification

We have two layers of verification that the system isolates concurrent users
correctly. Run the automated test against any environment that has Supabase
credentials configured; run the manual stress script as part of the Day 5
production smoke test.

### Automated two-user concurrency test

```bash
cd backend
python -m pytest tests/test_concurrent_users.py -v
```

The test provisions two ephemeral Supabase users, fires their
`POST /api/runs` requests via `asyncio.gather`, polls both to completion,
and asserts:

- both runs finish with `status="done"`
- User A cannot read User B's run (returns `404`, not `403`, to avoid
  leaking existence)
- `GET /api/runs` lists only the caller's own runs
- run events do not leak across users
- the `users_profile.monthly_runs_used` trigger increments once per user

The test is automatically skipped when Supabase credentials are missing,
so CI without secrets stays green. The QUBO pipeline is stubbed with
deterministic agents so no Gemini quota is consumed.

### Manual N-client stress script

Use this before each deploy and as the Day 5 production smoke test. Run
it against the deployed Cloud Run URL with N=4 (default):

```bash
cd backend
python scripts/manual_concurrency_test.py \
    --clients 4 \
    --runs-per-client 3 \
    --base-url https://api.qsim-playground.com
```

What to look for in the output:

- All N × runs-per-client runs print `status=done`
- Each `client-N` line shows a unique `user_id`
- Total `Wall-clock elapsed` is well under `90s` for `N=4, runs=3`
- The exit code is `0` (any non-`done` or `--base-url` error sets it to `1`)

Inspect Cloud Run logs for the same request window and confirm:

- Each request carries a distinct `request_id`
- Per-pipeline log lines (`execution_pipeline_done`, `gemini_call`,
  `orchestrator_node_slow`) reference the expected `run_id` and `user_id`
- No request handler logs a `run_id` belonging to a different user

The script provisions throwaway accounts via the service-role admin API
and deletes them on completion. If a cleanup line prints
`cleanup_failed`, manually delete the listed `user_id` from Supabase
Auth.
