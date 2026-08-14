# Glas Intelligence — agent context

Multi-agent AI scenario simulation engine for predictive business intelligence. Models how stakeholders respond to policy changes, market disruptions, and geopolitical events.

## Stack

- **Frontend**: Vue 3 + Vite (`frontend/`)
- **Backend**: Python / Flask (`backend/`)
- **Simulation**: OASIS (camel-ai) multi-agent framework
- **Knowledge graph**: Zep Cloud
- **Auth & DB**: Supabase (PostgreSQL + Auth)
- **Billing**: Stripe
- **Task queue**: Celery + Redis
- **Deploy**: Vite frontend on Cloudflare Pages; Docker for production API

## Local development

```bash
cp .env.example .env   # fill in API keys
make setup             # install frontend + backend deps
make dev               # backend + frontend concurrently
```

Manual alternative: `cd frontend && npm run dev` and `cd backend && uv sync && uv run python run.py`.

## Testing & lint

```bash
make test              # backend pytest + frontend vitest
make test-backend
make test-frontend
make test-integration
make test-e2e          # Playwright; app must be running
make lint              # ruff + mypy + eslint
```

Pre-commit: `make setup-hooks` (ruff, mypy, eslint, gitleaks).

## Project layout

```
backend/app/     Flask API, services, Celery tasks, models
frontend/src/    Vue views, components, router, demo adapter
e2e/             Playwright tests
docs/            Specs, reports, conventions
scripts/         Utilities (PDF, demo recording, etc.)
```

## Conventions

- Keep source files around **750 lines** or fewer when practical; extract composables, child components, or Python submodules instead of growing monoliths.
- Match existing patterns in the surrounding module before introducing new abstractions.
- Backend deps: `uv` + `backend/pyproject.toml`. Frontend: npm in `frontend/`.
- Do not commit secrets (`.env`, credentials). Demo builds use `VITE_DEMO_MODE=1` and are intentionally keyless.

## Demo mode

Static portfolio demo replays a recorded simulation in the browser — no backend, Supabase, or API keys. See `docs/demo-mode-plan.md` and `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md`.

## When making changes

- Run relevant tests after backend or frontend edits.
- Prefer focused diffs; avoid unrelated refactors.
- Only create git commits when explicitly asked.
