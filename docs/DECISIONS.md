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
