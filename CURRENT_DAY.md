# Current Work

Day 3 complete.

Shipped on Day 3:

- FastAPI app skeleton, auth middleware, request tracing, and health endpoint.
- Supabase schema with RLS, realtime, and pg_cron jobs.
- Profile, templates, and full run-management endpoints
  (create / list / get / events / cancel / soft-delete / export stub).
- Background pipeline executor with cancellation, per-instance semaphore,
  and pipeline timeout.
- Tiered quotas, per-minute rate limiting, qubit caps, and a Gemini
  circuit breaker — all enforced server-side.
- Two-user concurrency test (real Supabase) plus an N-client manual
  stress script for the Day 5 production smoke test.
- Architecture, decisions, and operations documentation refreshed.

Next: Day 4, Block A — Next.js setup (App Router scaffold, Supabase auth
client, shared types from the backend OpenAPI schema).
