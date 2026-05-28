# Decisions

## ADR-001: Free-Tier Stack

Status: accepted

QSim Playground uses FastAPI, Next.js, Supabase, Gemini 2.0 Flash, LangGraph, Qiskit,
Google Cloud Run, Vercel, and Sentry because each component has a viable free-tier path for
the 5-day build and demo constraints.

This keeps the project deployable without paid infrastructure while still matching the target
architecture: typed API boundaries, managed auth and Postgres, realtime updates, hosted frontend,
hosted backend, and production error tracking.

The tradeoff is that quotas and cold starts must be treated as product constraints from the start.
Server-side limits and clear operational documentation will be required before production launch.

<a id="adr-002-background-execution-without-an-external-queue"></a>

## ADR-002: Background Execution Without an External Queue

Status: accepted

`POST /api/runs` schedules `execute_pipeline_background` through FastAPI's
`BackgroundTasks.add_task` instead of pushing onto an external queue (Redis,
Celery, GCP Tasks, etc.). The handler inserts the `queued` row, schedules
the task, and returns the `run_id` in under a second. The pipeline runs
inside the same Cloud Run worker process and writes its progress to
`run_events` via the service-role Supabase client.

Cloud Run keeps a container alive while *any* request handler is still
running, and that includes its registered BackgroundTasks. Our 3-minute
pipeline timeout (`PIPELINE_TIMEOUT_SECONDS = 180.0`) sits well under the
60-minute Cloud Run request timeout, so a pipeline cannot outlive its
container. A module-level `asyncio.Semaphore(MAX_CONCURRENT_PIPELINES=10)`
caps in-flight pipelines per instance, leaving headroom under the
`--concurrency 20` deploy flag for non-pipeline traffic. When the
semaphore is full, the run row stays in `queued` status and an event row
records that it is waiting; the next free slot picks it up.

Trade-offs we are accepting:

- **No durable queue.** If a Cloud Run instance is killed mid-pipeline
  (deploy, OOM, eviction), the run is stranded in `running` status with no
  worker to finish it. For a 5-day free-tier build this is acceptable;
  users can re-submit. A future migration to Cloud Tasks or Pub/Sub would
  fix this by making the work durable.
- **Per-instance concurrency only.** The semaphore is in-process; two
  Cloud Run instances each accept up to 10 pipelines. Global concurrency
  caps would need Redis or DB-backed coordination.
- **Scaling envelope.** This pattern is healthy for roughly ~100
  concurrent runs per instance. Beyond that, we would move to a real
  queue (GCP Tasks → Cloud Run worker, or a dedicated worker service).

Cancellation is cooperative: `POST /api/runs/{id}/cancel` flips
`cancel_requested=true` on the row, and the orchestrator polls that flag
between major LangGraph nodes via a `cancel_check` closure passed into
`run_pipeline`.

## ADR-003: Row-Level Security as the Authorization Boundary

Status: accepted

Cross-user authorization is enforced in the database via Supabase
Row-Level Security, not in application code. Every per-user table
(`runs`, `run_events`, `exports`, `users_profile`,
`rate_limit_log`) has RLS enabled, and policies tie reads and writes
to `auth.uid()` so the database itself rejects any cross-user access
attempt.

The API layer still validates JWTs, scopes Supabase clients to the
caller's bearer token, and returns `404` (never `403`) for cross-user
lookups so existence of other users' rows does not leak. But the
*authority* on whether a row is visible is the database. If a handler
forgets a filter, RLS still rejects the query. If we add new tables in
the future, we add RLS first and add the application checks second.

Trade-offs we are accepting:

- **Schema discipline required.** Every new table needs RLS enabled
  and explicit policies; forgetting one is a security hole. Migration
  reviews must check for `alter table … enable row level security`
  and the matching `create policy` statements.
- **Service-role usage must stay narrow.** Service-role keys bypass
  RLS entirely. We keep their use limited to trusted server code in
  `backend/api/execution.py`, `backend/api/limits.py`, and the cron
  jobs in the schema. `infra/supabase.py` logs a warning if a
  service-role client is requested from inside a request handler.
- **Tests must cover RLS, not just routes.** `backend/tests/test_rls.py`
  and `backend/tests/test_concurrent_users.py` exercise the RLS
  policies directly against a real Supabase project so a route that
  forgets to filter still cannot leak data.

This is defense in depth: an application-layer bug, a missing filter,
or a forgotten `WHERE` clause should not become a confidentiality
incident. The database is the final authority.

## ADR-004: Email Confirmation Disabled During Development

Status: accepted — must be reversed before Day 5 launch

Supabase Authentication → Providers → Email has "Confirm email"
**disabled** in the development project. This lets fixtures, tests, and
local sign-ups proceed without a working inbox; the existing
`backend/tests/test_rls.py` and `backend/tests/test_concurrent_users.py`
fixtures depend on it via `email_confirm=True` on the admin
`create_user` call.

Before the Day 5 production launch we will:

1. Re-enable email confirmation in the production Supabase project.
2. Configure the production transactional email sender.
3. Update `Site URL` and `Redirect URLs` to the Vercel production
   domain (already tracked in `docs/OPERATIONS.md`).
4. Re-run `tests/test_concurrent_users.py` against the production
   project to confirm the existing fixtures still work (they create
   users with `email_confirm=True` via the service-role admin API,
   which bypasses the confirmation flow on purpose).

The trade-off we are accepting during development is that anyone with
the dev URL and a guessed-but-valid email format can create an
account. That is acceptable because the dev project is unpublished and
behind unguessable Supabase project URLs; production has none of that
slack and must require confirmation.

## ADR-005: Cloud Run Scale-to-Zero Backend

Status: accepted

The production FastAPI backend deploys to Google Cloud Run in Mumbai
(`asia-south1`) with `--min-instances 0`. This keeps idle cost at Rs 0
inside the Cloud Run free-tier envelope while still giving the API a
public HTTPS URL, autoscaling, request timeouts, and managed container
startup.

The trade-off is cold start latency. The first request after an idle
period can take several seconds while Cloud Run starts a container,
imports Qiskit/LangGraph dependencies, and initializes the FastAPI app.
The frontend should treat this as an expected state and show a
"Warming up..." message on the first API request of a session instead
of reporting it as a failure.

Operational guardrails:

- Runtime is capped to `--memory 1Gi`, `--cpu 1`, `--max-instances 10`,
  `--concurrency 20`, and `--timeout 300`.
- Secrets are mounted from Google Secret Manager, not passed in deploy
  commands or committed files.
- A billing account is required by Cloud Run even when usage stays
  inside the free tier; a Rs 100 budget alert is required before launch.
- Monitoring alerts cover 5xx rate, p95 latency, and memory/OOM risk.
