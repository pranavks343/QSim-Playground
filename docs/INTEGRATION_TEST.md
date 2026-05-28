# Two-User Local Integration Test

A 30-minute manual playbook to verify the full stack end-to-end with two
simultaneous users before each production deploy. This is the human
counterpart to `backend/tests/test_concurrent_users.py` and
`backend/scripts/manual_concurrency_test.py` — those exercise the API
under load, this exercises the *experience* through real browsers.

Run this before every deploy and immediately after, against the deployed
URL, with two real user accounts.

## Prerequisites

- Supabase project provisioned (see `docs/OPERATIONS.md`)
- `backend/.env` filled in with real Supabase + Gemini values
- Frontend `.env.local` with `NEXT_PUBLIC_API_URL`,
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Two browsers (or one regular + one incognito window) so the sessions
  do not share cookies

## Start the stack

```bash
# Terminal 1 — backend
cd backend
uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Confirm both are reachable:

- Backend: `curl http://localhost:8000/api/templates` returns 3 items
- Frontend: <http://localhost:3000> renders the landing page

## Scenario 1 — Simultaneous runs with isolation

Browser A (regular) and Browser B (incognito), side by side:

1. **Sign up** distinct accounts on each browser:
   - A: `qsim-a-<timestamp>@example.com`
   - B: `qsim-b-<timestamp>@example.com`
2. Both navigate to `/new`, pick **Portfolio**, click **Start run**.
3. Both redirect to `/runs/<id>` and watch the agent trace screen.

### What to verify

- [ ] **Agent cards animate independently** in each browser.
- [ ] The **connection badge** says `Live` (or `Polling` if Supabase
      Realtime isn't reachable from your network).
- [ ] **Stepper advances** through Agents → Evaluate → Critic → Refine →
      Circuit → Simulate → Done in both.
- [ ] **Each browser sees only its own run id** in the URL.
- [ ] After both finish (≤3 minutes), open `/dashboard` in each — each
      list shows **exactly one** run (the user's own).
- [ ] In **Browser A**, paste **Browser B's run id** into the URL
      (`/runs/<b_run_id>`). It must show a **404 page**, not the run.

## Scenario 2 — Notebook exports match the right run

1. In **both** browsers, after the run reaches `done`, click
   **Qiskit Notebook (.ipynb)** in the Export bar.
2. Open each downloaded `.ipynb`:
   - File A's first markdown cell mentions the winning agent for
     run A.
   - File B's first markdown cell mentions the winning agent for
     run B.
3. Spot-check the `metadata.qsim_provenance.run_id` field — it must
   match the run id from that browser's URL.
4. **Optional but recommended**: open one notebook in real Jupyter
   (`pip install jupyter qiskit qiskit-aer && jupyter notebook`) and
   run all cells. Top-5 bitstrings should print without errors.

### Verify

- [ ] **Notebooks are different** (diff the two `.ipynb` files — the
      `run_id` and Q matrix entries must differ).
- [ ] Running A's notebook **does not surface B's data** anywhere.

## Scenario 3 — Shareable link is sanitised

1. In **Browser A**, click **Enable shareable link** in the Export bar.
   A toast confirms the link was copied to your clipboard.
2. In **Browser B**, **sign out** (or open a third incognito window),
   then paste the share URL.

### Verify

- [ ] The shared page renders A's scorecards, critic verdict, refiner,
      circuit, and benchmark.
- [ ] The page is marked **Read-only** and there are **no export
      controls**.
- [ ] **A's email is nowhere** on the page (Cmd-F / Ctrl-F "@").
- [ ] **B's runs are not reachable** from anywhere on the shared page.
- [ ] The page source / network tab response for `GET /api/share/<id>`
      contains **no `user_id`** and **no `error`** field.
- [ ] In Browser A, click **Disable link**. Reload the share URL —
      it now returns 404.

## Scenario 4 — PDF report is presentation-ready

1. In Browser A, click **PDF Report** in the Export bar.
2. Open the downloaded PDF.

### Verify

- [ ] Title, generated-at timestamp, and run id are at the top.
- [ ] Problem summary (variables / constraints / objective sense).
- [ ] Scorecard table with all five agents.
- [ ] Critic verdict pull-quote with winner + runner-up + rejected
      chips.
- [ ] Benchmark table includes the **honesty banner**:
   - amber if quality < 80% of classical, with "Classical wins on this
     instance" copy
   - green if ≥ 80%, with "Quantum matches the classical baseline"
- [ ] Methodology footnote cites QAOA + the five agents + Qiskit Aer.

## Scenario 5 — Failure / edge paths

These verify graceful degradation. Each path should result in a clear
UI signal, **never** a white screen or stack trace.

### 5a. Kill the backend mid-run

1. Start a fresh run in Browser A; watch the agents start.
2. While the run is in progress, **stop uvicorn** in Terminal 1
   (Ctrl-C).
3. In Browser A, observe the screen.

Verify:

- [ ] The page **does not white-screen**.
- [ ] An error toast appears ("Network error — check your connection").
- [ ] The streaming indicator changes from `Live` to `Polling` and the
      polling retries continue silently (no toast spam).

### 5b. Restart backend, refresh the page

1. Restart `uvicorn` in Terminal 1.
2. Refresh `/runs/<id>` in Browser A.

Verify:

- [ ] The page loads with whatever state the executor managed to
      persist before the kill — usually status `running` plus any
      events that were already written.
- [ ] Streaming resumes (`Live` badge returns).
- [ ] If the executor was killed mid-pipeline, the run will stay in
      `running` until the next deploy / restart cleans it up. This is
      the trade-off documented in `docs/DECISIONS.md` ADR-002 and the
      reason a queued-job system is the next scaling step.

### 5c. Disconnect WiFi during streaming

1. Start a run in Browser A.
2. While agents are still firing, **turn off WiFi**.
3. Wait 5–10 seconds, then turn WiFi back on.

Verify:

- [ ] The connection badge flips to **Polling** when WiFi is off.
- [ ] When WiFi returns, the Supabase channel reconnects and the
      badge flips back to **Live**.
- [ ] No events are lost — the page state matches what
      `GET /api/runs/<id>/events` returns.

### 5d. Exhaust the per-minute rate limit

Free tier is 5 runs / 60 s (see `backend/api/limits.py`).

1. In Browser A, hit **Start run** six times in rapid succession
   (within one minute).
2. The 6th request should return **429**.

Verify:

- [ ] The first 5 succeed (each navigates to a new `/runs/<id>` page).
- [ ] The 6th surfaces a **rate-limit toast** with a Retry-After
      countdown like "Try again in 60s".
- [ ] The user's quota counter on the dashboard is **not** incremented
      for the rejected request (rate limit fires before the runs row
      is inserted).

## Scenario 6 — Keyboard + a11y spot check

1. With Browser A on the dashboard, press `n`.
   - [ ] Navigates to `/new`.
2. From any authenticated page, press `?`.
   - [ ] Opens the shortcuts dialog with `n` and `?` listed.
3. Open the run detail page. Tab through the agent cards.
   - [ ] **Focus rings are visible** around every interactive control.
4. Resize the browser to **375px wide** (DevTools device mode).
   - [ ] Agent cards stack vertically.
   - [ ] The scorecard table horizontally scrolls with the first
         column (Agent) **sticky**.
   - [ ] Nav collapses to a hamburger.
5. Toggle the theme.
   - [ ] All screens stay legible in both light and dark mode.

## Cleanup

1. In Supabase Auth → Users, delete the two test users
   (`qsim-a-*@example.com`, `qsim-b-*@example.com`).
2. Stop `uvicorn` and `npm run dev`.

## Sign-off checklist

Before declaring Day 4 done, every box above must be ticked. If any
fails, file the failure as an issue and resolve before deploy.

- [ ] Scenarios 1–6 all green
- [ ] Two notebooks produced, distinct, runnable in real Jupyter
- [ ] Shared link visible logged-out, exposes nothing private
- [ ] All failure paths degrade gracefully — no white screens
- [ ] Screenshots captured (see `docs/screenshots/README.md`)
