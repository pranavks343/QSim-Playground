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
