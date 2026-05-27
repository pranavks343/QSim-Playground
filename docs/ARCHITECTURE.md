# Architecture

QSim Playground is a typed full-stack application with a pure Python core,
a FastAPI service boundary, and a Next.js frontend that hangs off it.
Authentication and storage live in Supabase; the QUBO pipeline runs
inline inside the FastAPI worker via FastAPI BackgroundTasks.

## Components

- `backend/core`: pure domain logic with no network or database I/O —
  IR, parser, templates, agents, evaluator, orchestrator, circuit
  generation, classical baseline, qubit-cap primitives.
- `backend/api`: FastAPI routes, dependencies, middleware, the background
  executor, and the server-side limits module (`api/limits.py`).
- `backend/infra`: external clients and operational integrations —
  Supabase factories (`anon`, `service`, `user`-bearer), the hardened
  Gemini client + circuit breaker, and pydantic settings.
- `backend/cli`: local Typer commands for foundation and pipeline
  validation that bypass the API.
- `frontend`: Next.js App Router application (Day 4).

## Execution model

`POST /api/runs` returns in under a second by deferring the actual
pipeline work to a FastAPI BackgroundTask:

1. The handler validates the JWT, enforces tier quota and the rolling
   per-user rate limit, fast-fails if the Gemini circuit breaker is
   open, parses the IR, inserts a `queued` row into `runs` via the
   user's JWT (so RLS applies), and schedules
   `execute_pipeline_background` with the run id, user id, IR, and
   tier-derived `max_qubits` cap.
2. `execute_pipeline_background` (in `backend/api/execution.py`)
   acquires a slot from a module-level
   `asyncio.Semaphore(MAX_CONCURRENT_PIPELINES=10)`, switches the run
   to `running`, and invokes `run_pipeline` wrapped in
   `asyncio.wait_for(timeout=180.0)`.
3. Each LangGraph node fires an event into `run_events` through a
   service-role Supabase client (RLS doesn't apply to that role) so the
   frontend can subscribe in realtime. Between major nodes the
   orchestrator polls `runs.cancel_requested`; if it flips to `true`
   the pipeline raises `PipelineCancelled` and the run is finalised
   with `status='cancelled'`.
4. On completion, the executor writes the full result back to `runs`
   (qubos, scorecards, critic verdict, refined QUBO, circuit data,
   simulation + classical results, `total_runtime_ms`, `completed_at`)
   and emits a final `pipeline_done` / `pipeline_failed` /
   `pipeline_cancelled` event.

Cloud Run keeps the container alive while any request handler is still
running, and that includes its registered BackgroundTasks (see
[ADR-002](DECISIONS.md#adr-002-background-execution-without-an-external-queue)
for the full trade-off analysis and scaling envelope).

## Multi-user isolation

Isolation is enforced at three layers, so a bug in one is caught by the
next:

1. **Database — Row-Level Security.** Every table in
   `backend/infra/migrations/001_initial_schema.sql` has RLS enabled
   and an explicit `using (auth.uid() = …)` policy. The
   `runs_select_own_active` / `runs_update_own` / `runs_insert_own`
   policies make it physically impossible for one user's JWT to read or
   mutate another user's rows. `run_events` join through `runs` so
   event leakage is also blocked at the DB. Service-role keys bypass
   RLS and are only used by trusted server code
   (`backend/api/execution.py` and the rate-limit and quota paths) —
   `infra/supabase.py` guards accidental service-role use from a
   request handler.
2. **API — JWT + per-user clients.** `api/deps.py:get_current_user`
   validates the Supabase JWT with the project's JWT secret, stashes
   the bearer JWT on `request.state`, and every route fetches a
   `get_user_client(bearer_jwt)` for its Supabase calls. Cross-user
   `GET /api/runs/{run_id}` deliberately returns **404** rather than
   403 so we never leak the existence of another user's run.
3. **Application — per-tier limits.** `api/limits.py` enforces
   `monthly_runs`, `runs_per_minute`, and `max_qubits` for `free` /
   `pro` / `enterprise` tiers, with all counters maintained server-side
   in `users_profile.monthly_runs_used` (incremented by the
   `runs_increment_monthly_runs_used` trigger) and `rate_limit_log`.
   The qubit cap is threaded into the orchestrator and tripped inside
   `evaluator.evaluate_qubo` and `circuit_gen.build_qaoa_circuit`, so a
   tier violation surfaces as a `pipeline_failed` event with a clear
   message instead of an opaque downstream error.

The `backend/tests/test_concurrent_users.py` smoke test exercises all
three layers together against a real Supabase project; the
`backend/scripts/manual_concurrency_test.py` script is the production
equivalent used during deploy verification (see
[docs/OPERATIONS.md → Concurrency Verification](OPERATIONS.md#concurrency-verification)).

## Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant FastAPI
    participant Supabase
    participant Background as execute_pipeline_background
    participant Gemini
    participant Orchestrator as run_pipeline (LangGraph)

    Client->>FastAPI: POST /api/runs (JWT + body)
    FastAPI->>FastAPI: validate JWT, check quota,<br/>rate limit, Gemini breaker
    FastAPI->>Supabase: insert runs row (user JWT, status=queued)
    FastAPI-->>Client: 201 {run_id, status=queued}

    par BackgroundTask
        FastAPI->>Background: schedule(run_id, user_id, ir, max_qubits)
        Background->>Background: acquire semaphore slot
        Background->>Supabase: update runs.status=running (service role)
        loop each major node
            Background->>Orchestrator: invoke node
            Background->>Supabase: cancel_check via runs.cancel_requested
            Orchestrator->>Gemini: agent / critic / refiner prompt
            Orchestrator->>Supabase: insert run_events row
        end
        Background->>Supabase: update runs row with results +<br/>status=done | failed | timeout | cancelled
    and Client realtime
        Client->>Supabase: subscribe(run_events for run_id)
        Supabase-->>Client: events stream as they appear
    end

    Client->>FastAPI: GET /api/runs/{run_id}
    FastAPI->>Supabase: select * (user JWT)
    FastAPI-->>Client: 200 with full run state
```

Plain-ASCII version (for terminals without mermaid):

```
 Client ──POST /api/runs──> FastAPI (auth, RLS via JWT, quota, rate
                            limit, Gemini breaker)
                              │
                              ├──> Supabase.runs INSERT (queued)
                              │
                              ├──> 201 {run_id}        (returned immediately)
                              │
                              └──> BackgroundTask: execute_pipeline_background
                                       │   ┌──── asyncio.Semaphore(10) ────┐
                                       │   │ run_pipeline / LangGraph      │
                                       │   │  ├─ agent x 5 ──> Gemini       │
                                       │   │  ├─ evaluator (qubit cap)      │
                                       │   │  ├─ critic ──> Gemini          │
                                       │   │  ├─ refiner ──> Gemini         │
                                       │   │  ├─ circuit_gen (qubit cap)    │
                                       │   │  └─ runner (Qiskit + classical)│
                                       │   │ cancel_check between each node │
                                       │   └────────────────────────────────┘
                                       │
                                       ├──> Supabase.run_events INSERT (each event)
                                       │       │
                                       │       └──> Supabase Realtime push to subscribed clients
                                       │
                                       └──> Supabase.runs UPDATE (status, results, completed_at)
```
