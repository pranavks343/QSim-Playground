# Architecture

QSim Playground will be organized as a typed full-stack application with a pure Python core,
a FastAPI service boundary, and a Next.js frontend.

## Components

- `backend/core`: pure domain logic with no network or database I/O.
- `backend/api`: FastAPI routes, dependencies, and middleware.
- `backend/infra`: external clients and operational integrations.
- `backend/cli`: local Typer commands for foundation and pipeline validation.
- `frontend`: Next.js App Router application.

Detailed diagrams and runtime flows will be added as the system is implemented.
