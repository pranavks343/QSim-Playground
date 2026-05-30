# QSim Playground — Deployment Log

> Running log of the guided go-live. Each completed step, resulting URLs, and any deviation.
> If the session resets, resume from the last unchecked item.

## Session started: 2026-05-30

Targets: Backend → Google Cloud Run (asia-south1, scale-to-zero). Frontend → Vercel.
DB/Auth/Realtime → Supabase (hardened). Errors → Sentry. Uptime → BetterStack/UptimeRobot.
Constraint: stay on free tier; billing attached to Cloud Run but kept ₹0; budget alert as tripwire.

## Phase: Pre-flight (Section 2)

- [x] **Dockerfile** correct: non-root `qsim`, uses `$PORT`, uvicorn `--factory` launch (`backend.api.main:create_app`).
- [x] **`.dockerignore`** excludes tests/.venv/.git/frontend/.env/docs/node_modules.
- [x] **Env vars from env** (not hardcoded): backend `ALLOWED_ORIGINS`; frontend `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- [x] Local Docker build + run + `GET /api/health` = **200** (image PASS). Subsystem flags `db_reachable:false` / `gemini_reachable:false` diagnosed below — both are data/quota issues, not image issues.
- [x] `npm run build` clean (all 10 routes, types valid). NOTE: required clean `node_modules` reinstall — the bundled `commander` was corrupted (caused `next build`/`next lint` to crash with `Class extends value undefined`; was NOT a Node-version issue). Standardized frontend on **Node 22 LTS** (`.nvmrc` + `engines.node` pin).
- [ ] `git status` clean and pushed to GitHub.

### Pre-flight diagnosis (in-container probes)
- Env vars reach container ✓, `Settings()` constructs ✓, outbound network ✓.
- **DB:** `PGRST205 Could not find table 'public.users_profile' in schema cache` → service key auth works; likely **stale PostgREST schema cache** (app worked locally on this project) OR migration not applied. **RESOLVE IN PHASE A** (verify Table Editor; reload schema cache).
- **Gemini:** `429 ResourceExhausted` → key valid + reachable, just over free-tier rate limit; breaker cooled down. **Add ≥2 keys before launch (Phase H).**

---

## Pending wire-ups (don't forget)
- [ ] Cloud Run `ALLOWED_ORIGINS` ← Vercel URL (set in Phase D)
- [ ] Supabase Site URL + Redirect URLs ← Vercel URL (deferred from Phase A)

## Known blocker
- GCP project `qsim-playground-prod` created earlier, but its **billing account is CLOSED**. Cloud Run (Phase B) cannot proceed until billing is linked. Pre-flight + frontend build are unblocked and done first.

## Captured URLs / resources
- Cloud Run URL: _TBD_
- Vercel URL: _TBD_
- Supabase project ref: _TBD_

## Step log
- Pre-flight [CLAUDE CODE] checks passed: Dockerfile, .dockerignore, env wiring.
