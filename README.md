# QSim Playground

[![CI](https://github.com/pranavks343/QSim-Playground/actions/workflows/ci.yml/badge.svg)](https://github.com/pranavks343/QSim-Playground/actions/workflows/ci.yml)

QSim Playground is a multi-agent quantum optimization sandbox for ML engineers.

## Status

Day 3 backend is complete: FastAPI service, Supabase auth and RLS, background
pipeline execution, tiered quotas, rate limiting, qubit caps, Gemini circuit
breaker, and multi-user concurrency verification. Day 4 starts the Next.js
frontend.

## Quickstart

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Local development

```bash
# 1. Clone and enter the repo
git clone https://github.com/pranavks343/QSim-Playground.git
cd QSim-Playground

# 2. Create a Python 3.11 virtualenv and install backend deps
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m pip install -e backend

# 3. Copy the env template and fill in Supabase + Gemini values
cp .env.example backend/.env
$EDITOR backend/.env   # SUPABASE_URL, SUPABASE_ANON_KEY,
                       # SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET,
                       # GEMINI_API_KEYS, ALLOWED_ORIGINS

# 4. Apply the database schema in Supabase
#    Paste backend/infra/migrations/001_initial_schema.sql into the SQL editor.
#    See docs/OPERATIONS.md for the full setup checklist.

# 5. Run the API locally
cd backend
uvicorn api.main:app --reload --port 8000

# 6. Run the test suite
python -m pytest
```

The CLI also runs the full pipeline locally without the API:

```bash
qsim run --template portfolio
```

### Example: create a run via the HTTP API

Obtain a Supabase JWT for a signed-in user (Supabase dashboard or
`supabase.auth.signInWithPassword` from any client) and call:

```bash
curl -X POST http://localhost:8000/api/runs \
     -H "Authorization: Bearer $SUPABASE_JWT" \
     -H "Content-Type: application/json" \
     -d '{"input_source": "template", "template_name": "portfolio"}'
```

Response (HTTP 201):

```json
{"run_id": "7c4f…", "status": "queued"}
```

Then poll for results and stream events:

```bash
curl -H "Authorization: Bearer $SUPABASE_JWT" \
     http://localhost:8000/api/runs/$RUN_ID

curl -H "Authorization: Bearer $SUPABASE_JWT" \
     http://localhost:8000/api/runs/$RUN_ID/events
```

Cancel an in-flight run:

```bash
curl -X POST -H "Authorization: Bearer $SUPABASE_JWT" \
     http://localhost:8000/api/runs/$RUN_ID/cancel
```

### Request flow

```
+----------+   POST /api/runs    +---------------+    insert    +--------+
|  Client  | ------------------> |  FastAPI app  | -----------> | Supabase |
+----------+                     |  (auth, RLS,  |              |   runs   |
     ^                           |   quotas,     |              +----+-----+
     |                           |   rate limit, |                   |
     |   201 + run_id            |   breaker)    |                   |
     +-------------------------- +---+-----------+                   |
                                     |  background_tasks.add_task    |
                                     v                               |
                              +------+------+   evaluator + circuit  |
                              | execute_    | <----+   simulator    |
                              | pipeline_   |      |                |
                              | background  |      | cancel_check + |
                              | (semaphore) |      | max_qubits cap |
                              +------+------+                       |
                                     | LangGraph nodes              |
                                     v                              v
                              +------+------+   events    +---------+--------+
                              |  Gemini     | ----------> |  Supabase        |
                              |  agents x 5 |             |  run_events      |
                              |  + critic   |             |  (realtime sub)  |
                              |  + refiner  |             +------------------+
                              +-------------+
```

`docs/ARCHITECTURE.md` has the same flow as a mermaid diagram plus a
detailed walkthrough of the execution model, multi-user isolation, and
how the per-tier limits compose.

List the built-in templates:

```bash
qsim list-templates
```

Load a template as normalized IR JSON:

```bash
qsim load --template portfolio
```

Parse a supported NumPy snippet:

```bash
qsim parse --file tests/fixtures/portfolio_numpy.py
```

Validate an IR JSON file:

```bash
qsim load --template knapsack > /tmp/knapsack_ir.json
qsim validate --file /tmp/knapsack_ir.json
```

Run the full local pipeline:

```bash
qsim run --template portfolio
```

Example output excerpt:

```text
QSim Pipeline
portfolio
Variables: 6 | Constraints: 1 | Run: cli-...

Agent Formulations
Comparison
Rank  Agent    Score  Qubits  Sparsity  Condition  Sensitivity
1     decomp   7.212  6       0.000     2.78       0.000
2     graph    6.947  6       0.000     2.37       0.000

Critic Verdict
decomp wins with composite_score=7.212...

Refiner Improvements
- none — original was already near-optimal

Simulation Results
Best bitstring: 111110
Objective: -0.4476
Quality vs classical: 100.00%

Execution Comparison
Classical / Simulator / Hardware (Day 6+)
Total wall-clock: 0.62s
```

## Planned Features

- Normalized optimization problem IR.
- Portfolio, Max-Cut, and Knapsack templates.
- AST-only parser for supported NumPy snippets.
- Multi-agent QUBO, circuit, evaluation, critique, and refinement pipeline.
- FastAPI backend with Supabase auth, RLS, quotas, rate limits, and realtime traces.
- Next.js frontend for inputs, agent traces, benchmarks, and exports.

## Built in 5 Days

This project is being built from a focused 5-day implementation plan.

## License

MIT. See [LICENSE](LICENSE).
