# Glas Intelligence — agent context

Multi-agent AI scenario simulation engine for predictive business intelligence. Models how stakeholders respond to policy changes, market disruptions, and geopolitical events.

## Stack

- **Frontend**: Vue 3 + Vite (`frontend/`)
- **Backend**: Python / Flask (`backend/`)
- **Simulation**: OASIS (camel-ai) multi-agent framework
- **Knowledge graph**: Graphiti on self-hosted Neo4j (default, `GRAPH_BACKEND=graphiti`); Zep Cloud optional (`GRAPH_BACKEND=zep`, metered). All graph access goes through `backend/app/services/graph_store/`: `zep_cloud` and `graphiti_core` are imported only there (and in `utils/zep_paging.py`, which only the Zep store uses). `tests/test_graph_store.py` enforces this. Setup: `docs/graphiti-setup.md`
- **Auth & DB**: Supabase (PostgreSQL + Auth)
- **Billing**: Stripe
- **Task queue**: Celery + Redis
- **Deploy**: static demo on GitHub Pages; the backend is not deployed anywhere at present (Hetzner pipeline retired 2026-08-10)

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

Tests run on the in-memory graph store (`GRAPH_BACKEND=fake`, set in `backend/tests/conftest.py`), and conftest makes any real Zep client raise. So the suite never spends Zep credits or needs Neo4j. The live Graphiti contract tests are opt-in: `RUN_GRAPHITI_IT=1 python -m pytest tests/test_graph_store_contract.py` (needs Neo4j and `LLM_*`; a few cents of tokens).

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
- **Agents must never read, write, or grep `.env`** (only `.env*.example`). Agent harnesses echo the changed lines of any file the agent has touched back into the transcript, which leaked two rotated API tokens on 2026-09-21. Read `.env.example` for the variable names, and ask the human to set secrets themselves — preferably as user-level environment variables, which the app reads ahead of `.env`.

## Demo mode

Static portfolio demo replays a recorded simulation in the browser — no backend, Supabase, or API keys. See `docs/demo-mode-plan.md` and `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md`.

## When making changes

- Run relevant tests after backend or frontend edits.
- Prefer focused diffs; avoid unrelated refactors.
- Only create git commits when explicitly asked.
