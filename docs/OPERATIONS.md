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

## Cloud Run Backend Deployment

The production backend runs on Google Cloud Run in Mumbai
(`asia-south1`) and scales to zero when idle.

### One-Time GCP Setup

```bash
gcloud auth login
gcloud projects create qsim-playground-prod --name="QSim Playground"
gcloud config set project qsim-playground-prod
```

Attach a billing account before deploying. Cloud Run has a free tier,
but Google still requires billing to be enabled. Create a budget alert
at Rs 100 before the first deploy.

Enable required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

Create Secret Manager entries for:

- `GEMINI_API_KEYS`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `SENTRY_DSN`

Grant the Cloud Run runtime service account
`roles/secretmanager.secretAccessor`.

### Local Container Smoke Test

```bash
docker build -t qsim-backend ./backend
docker run --rm -p 8080:8080 --env-file backend/.env qsim-backend
curl http://localhost:8080/api/health
```

Expected result: HTTP 200 with `status`, `db_reachable`,
`gemini_reachable`, and `version` fields.

### Deploy

From the repository root:

```bash
PROJECT_ID=qsim-playground-prod \
FRONTEND_ORIGIN=https://qsim-playground.vercel.app \
bash backend/scripts/deploy_cloud_run.sh
```

The script deploys `qsim-backend` with:

- `--region asia-south1`
- `--min-instances 0`
- `--max-instances 10`
- `--concurrency 20`
- `--timeout 300`
- secrets loaded from Secret Manager

After deploy, note the Cloud Run URL and verify:

```bash
curl https://<cloud-run-url>/api/health
```

### Monitoring Alerts

Configure Cloud Monitoring alerts to email the maintainer when:

- 5xx rate is greater than 5% over 5 minutes
- memory utilization is greater than 90% or any instance OOMs
- request latency p95 is greater than 30 seconds

### Cold Starts

With `--min-instances 0`, the first request after an idle period may
take roughly 3-5 seconds. This is expected and is the cost trade-off
for Rs 0 idle infrastructure. The frontend should surface this as a
warming state, not as an outage.

## Vercel Frontend Deployment

The frontend deploys from the same GitHub repository with Vercel's
Next.js preset.

### Import Project

1. Open Vercel -> Add New Project -> Import Git Repository.
2. Select `pranavks343/QSim-Playground`.
3. Set Root Directory to `frontend/`.
4. Keep the detected Next.js framework preset and default build/output
   settings.

### Environment Variables

Set these for both Production and Preview environments:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `NEXT_PUBLIC_API_URL` set to the Cloud Run HTTPS URL from Block A

Deploy to production and note the assigned URL, for example
`https://qsim-playground.vercel.app`.

### Close the CORS Loop

After Vercel assigns the production URL, update Cloud Run so the backend
accepts browser requests from that exact origin:

```bash
gcloud run services update qsim-backend \
  --region asia-south1 \
  --set-env-vars ALLOWED_ORIGINS=https://qsim-playground.vercel.app
```

If a custom domain is added later, include it in `ALLOWED_ORIGINS` as a
comma-separated value and redeploy/update the service again.

### Supabase Auth URLs

In Supabase -> Authentication -> URL Configuration:

- Site URL: `https://qsim-playground.vercel.app`
- Redirect URLs: add `https://qsim-playground.vercel.app/**`

For production launch, re-enable email confirmation in Supabase
Authentication -> Providers -> Email.

### Vercel Analytics

Vercel Analytics is mounted in the Next.js root layout through
`@vercel/analytics/next`. Enable Analytics in the Vercel project
dashboard to start collecting page-level traffic.

### Production Smoke Test

Verify:

- Landing page loads over HTTPS.
- Signup creates both an `auth.users` row and a `users_profile` row.
- A template run created from the live frontend calls the Cloud Run
  backend and reaches `status="done"`.
- The first slow request after an idle backend shows the non-blocking
  "Warming up the backend..." toast and clears when the response arrives.

## Production Supabase Hardening

Run this checklist against the production Supabase project before public
launch.

### Auth Provider Settings

In Supabase -> Authentication -> Providers -> Email:

- Turn **Confirm email** on.
- Keep every non-email provider disabled until OAuth is explicitly
  planned and reviewed.
- Confirm built-in signup/login throttles are active in Authentication
  -> Rate Limits. Keep defaults unless production abuse requires lower
  limits.

In Authentication -> URL Configuration:

- Site URL: `https://qsim-playground.vercel.app`
- Redirect URLs: `https://qsim-playground.vercel.app/**`

In Authentication -> Email Templates -> Confirm signup:

- Use product name: `QSim Playground`.
- Subject: `Confirm your QSim Playground account`.
- Make the primary CTA point at `{{ .ConfirmationURL }}`.
- Keep the copy short and explicit: the account is not active until the
  user confirms.

The frontend signup form handles both modes: if Supabase returns a
session it redirects to `/dashboard`; if email confirmation is required
it shows a "Check your email to confirm" state.

### RLS Production Verification

In Supabase SQL Editor, confirm RLS is enabled on all user-data tables:

```sql
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'users_profile',
    'runs',
    'run_events',
    'exports',
    'rate_limit_log'
  )
order by tablename;
```

Every `rowsecurity` value must be `true`.

Then run the two-user isolation test locally against production
credentials:

```bash
cd backend
SUPABASE_URL=... \
SUPABASE_ANON_KEY=... \
SUPABASE_SERVICE_ROLE_KEY=... \
SUPABASE_JWT_SECRET=... \
GEMINI_API_KEYS=test-key \
ALLOWED_ORIGINS=https://qsim-playground.vercel.app \
python -m pytest tests/test_rls.py -v
```

The fixture deletes test users after completion. If cleanup fails,
delete the printed test users from Supabase Auth manually.

### Cron Jobs

Confirm scheduled jobs exist:

```sql
select jobname, schedule, active
from cron.job
where jobname in (
  'qsim-reset-monthly-quotas',
  'qsim-delete-stale-rate-limit-log',
  'qsim-free-tier-retention'
)
order by jobname;
```

All three jobs must exist and `active` must be `true`.

### Signup Notifications

Use Supabase Database Webhooks:

1. Database -> Webhooks -> Create webhook.
2. Table: `auth.users`.
3. Events: `INSERT`.
4. Destination: an email/logging endpoint you control.
5. Payload fields: user id, email, created_at. Never send tokens or
   service-role keys.

For the zero-cost launch path, route the webhook to a free logging
endpoint or automation that emails `kondapisripranav@gmail.com`.

### Backups And Manual Export

Supabase free tier includes limited backup retention. Treat it as
best-effort recovery, not long-term archival.

Manual fallback export before major launch changes:

```bash
pg_dump "$SUPABASE_DB_URL" \
  --schema public \
  --format custom \
  --file qsim-public-$(date +%Y%m%d-%H%M).dump
```

Store the dump outside the repository. Never commit database exports.

### Rotate Gemini Keys

1. Create a replacement Gemini API key.
2. Update Google Secret Manager:

```bash
printf '%s' 'new-key-1,new-key-2' | \
  gcloud secrets versions add GEMINI_API_KEYS --data-file=-
```

3. Redeploy or restart Cloud Run so the service reads the latest secret
   version.
4. Hit `/api/health` and confirm `gemini_reachable=true`.
5. Disable the old Gemini key after the new key is verified.

### Bump A User Tier

Tier changes require service-role or direct SQL access; clients cannot
change their own tier.

```sql
update public.users_profile
set tier = 'pro',
    updated_at = now()
where id = '<user_uuid>';
```

Allowed values are `free`, `pro`, and `enterprise`.

### Quota Exception Request

For a one-off free-tier exception, either bump the tier temporarily or
reset the monthly counter:

```sql
update public.users_profile
set monthly_runs_used = 0,
    quota_reset_at = date_trunc('month', now()) + interval '1 month',
    updated_at = now()
where id = '<user_uuid>';
```

Record the exception reason and expiry in the launch notes or issue
tracker so manual exceptions do not become hidden product state.

### Wipe A User

Use this when a user requests GDPR-style deletion.

1. Export the user's `id` and confirm the request came from that email.
2. Delete the Supabase Auth user from Authentication -> Users, or use
   the admin API.
3. Confirm cascade deletion removed:
   - `users_profile`
   - `runs`
   - `run_events`
   - `exports`
   - `rate_limit_log`

Verification query:

```sql
select
  (select count(*) from public.users_profile where id = '<user_uuid>') as profiles,
  (select count(*) from public.runs where user_id = '<user_uuid>') as runs,
  (select count(*) from public.rate_limit_log where user_id = '<user_uuid>') as rate_limits;
```

All counts must be `0`.

### Roll Back A Bad Deploy

Backend:

```bash
gcloud run revisions list --service qsim-backend --region asia-south1
gcloud run services update-traffic qsim-backend \
  --region asia-south1 \
  --to-revisions <known-good-revision>=100
```

Frontend:

1. Vercel -> Project -> Deployments.
2. Open the last known-good deployment.
3. Click Promote to Production.

Database:

- Prefer forward fixes for schema changes.
- If a destructive migration shipped, stop writes first by pausing the
  frontend run-creation path or taking the backend private, then restore
  from Supabase backup/manual export.
