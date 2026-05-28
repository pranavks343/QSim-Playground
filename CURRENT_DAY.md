# Current Work

Day 4 complete.

Shipped on Day 4:

- Next.js App Router scaffold with Tailwind, Radix, Zod, Supabase auth
  via `@supabase/ssr`, and a typed API client mirroring the backend
  OpenAPI surface.
- Landing page with hero / honesty / how-it-works / agent showcase /
  tech strip.
- Full auth flow: signup, login, password reset, route protection via
  middleware, account menu, sign out.
- Dashboard with recent-runs grid + quota bar.
- Three-mode New Run panel (Template / Code / Math) with Monaco for
  the code path and live IR validation for the math path.
- The agent trace screen — five live agent cards driven by Supabase
  Realtime on `run_events`, with deterministic polling fallback when
  the channel drops, progress stepper, scorecard comparison table,
  critic verdict, refiner, circuit, and benchmark panels with the
  honesty banner enforced in code.
- Four export formats: runnable Jupyter notebook, standalone Python
  script with provenance, executive PDF (client-side jsPDF), and a
  sanitised public share link with the matching read-only page.
- Loading skeletons, helpful empty states, network-aware error
  toasts with Retry-After countdowns, keyboard shortcuts (`n`, `?`)
  with a help dialog, sticky-column scorecards on mobile, focus
  rings, ARIA labels, and dynamic-import code splitting for Monaco
  and Recharts (`/runs/[id]` first-load JS dropped from 771 kB to
  669 kB).
- Two-user local integration playbook at `docs/INTEGRATION_TEST.md`
  covering six scenarios — concurrent runs with isolation, notebook
  identity, share-link sanitisation, PDF contents, failure paths
  (kill backend, lose WiFi, exhaust rate limit), and a11y spot
  checks. Run through this before every deploy.
- Documentation refreshed: README screenshots block + frontend setup
  + integration-test pointer; ARCHITECTURE.md gains a frontend
  data-flow section covering server vs client rendering, Realtime +
  polling fallback, the share path, code splitting, and keyboard
  shortcuts.

Next: Day 5, Block A — deploy the FastAPI backend to Google Cloud Run
(build container image, push to Artifact Registry, deploy with
`--concurrency 20 --min-instances 0 --max-instances 4`, wire Sentry
DSN, point `ALLOWED_ORIGINS` at the Vercel production domain, and
re-enable email confirmation in the production Supabase project per
ADR-004's checklist).
