# Glas Intelligence

Multi-agent AI scenario simulation engine for predictive business intelligence.

## Overview

Glas Intelligence uses large language models and multi-agent social simulation (OASIS) to model how stakeholders — governments, regulators, businesses, consumers — respond to policy changes, market disruptions, and geopolitical events.

## Architecture

- **Frontend**: Vue 3 + Vite
- **Backend**: Python / Flask
- **Simulation**: OASIS (camel-ai) multi-agent framework
- **Knowledge Graph**: Zep Cloud (temporal knowledge graph with entity and relationship extraction)
- **Auth & DB**: Supabase (PostgreSQL + Auth)
- **Billing**: Stripe
- **Task Queue**: Celery + Redis
- **Deployment**: Vite frontend builds on Cloudflare Pages

## Local Development

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Install everything
make setup

# Start dev servers (frontend + backend concurrently)
make dev
```

Or manually:

```bash
# Frontend
cd frontend && npm install && npm run dev

# Backend
cd backend && uv sync && uv run python run.py
```

## Testing

```bash
# Run all tests
make test

# Backend unit tests with coverage
make test-backend

# Frontend component tests
make test-frontend

# API integration tests
make test-integration

# E2E browser tests (requires app running)
make test-e2e

# All tests
make test-all
```

## Linting

```bash
# Run all linters
make lint

# Backend only (ruff + mypy)
make lint-backend

# Frontend only (eslint)
make lint-frontend
```

## Pre-commit Hooks

```bash
make setup-hooks
```

This installs git hooks that automatically run ruff, mypy, eslint, and gitleaks before each commit.

## CI/CD Pipeline

### Continuous Integration (on every PR)

All checks must pass before a PR can be merged to `main`:

| Job | What it does |
|-----|--------------|
| **lint-backend** | Ruff lint + format check, Mypy type check |
| **lint-frontend** | ESLint |
| **test-backend** | Pytest with coverage |
| **test-frontend** | Vitest component tests |
| **integration-tests** | API endpoint tests with Flask test client |
| **security-scan** | pip-audit, npm audit, Gitleaks (secrets), Semgrep (SAST) |
| **build-and-e2e** | Docker build + Playwright E2E tests |
| **docker-scan** | Trivy vulnerability scan on production Docker image |

### Static Demo Hosting

The portfolio demo is a fully static site hosted on Cloudflare Pages. See `docs/demo-mode-plan.md` and `docs/superpowers/specs/2026-08-08-static-demo-hosting-design.md` for architecture and implementation details.

| Environment | URL | Trigger |
|-------------|-----|---------|
| **Demo** | https://demo.glasinsight.com | Merge to `main` (Cloudflare Pages auto-build) |

## Monitoring & Observability

The monitoring stack runs on the same server as separate Docker services:

```bash
# Start the monitoring stack
make monitoring-up

# Stop it
make monitoring-down
```

| Service | URL | Purpose |
|---------|-----|---------|
| **Grafana** | https://monitor.glasinsight.com | Dashboards + alerting |
| **Uptime Kuma** | https://uptime.glasinsight.com | Uptime monitoring |
| **Prometheus** | :9090 (internal) | Metrics collection |
| **Loki** | :3100 (internal) | Log aggregation |

### Pre-configured Dashboards

- **Application**: request rate, latency (p50/p95), error rate
- **Infrastructure**: CPU, memory, disk, network (host + containers)
- **Redis**: memory usage, connected clients, hit rate

### Alerts

- **Critical**: API down > 1 min, disk > 90%, OOM kills
- **Warning**: CPU > 80%, Redis memory > 80%, error rate > 5%, latency p95 > 5s
- **Info**: SSL cert expiring < 14 days

## Environment Variables

See `.env.example` for all required configuration. The static demo build uses:

| Variable | Purpose |
|----------|---------|
| `VITE_DEMO_MODE` | Enable fixture-based replay (set to `1` for demo builds) |
| `VITE_SUPABASE_URL` | Supabase URL for frontend build (optional, can be empty for demo) |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key for frontend build (optional, can be empty for demo) |

## Project Structure

```
├── .github/workflows/     # CI/CD pipeline
│   └── ci.yml             # PR checks (lint, test, security, E2E)
├── backend/               # Flask API
│   ├── app/               # Application code
│   ├── tests/             # Unit + integration tests
│   └── pyproject.toml     # Python dependencies
├── frontend/              # Vue 3 SPA + Vite build
│   ├── src/               # Components, views, router
│   └── dist/              # Built static site (Cloudflare Pages)
├── e2e/                   # Playwright E2E tests
├── docs/                  # Reference artifacts and design specs
│   ├── reports/           # Markdown sources for client/PDF reports
│   ├── schema/            # Reference SQL (Supabase schema snapshot)
│   ├── demo-mode-plan.md  # Portfolio demo replay architecture
│   └── superpowers/       # Implementation plans and design specs
├── tasks/                 # Local task tracking (todo.md)
├── scripts/               # PDF/visual/DB utilities
├── docker-compose.yml         # Local dev
├── docker-compose.monitoring.yml  # Observability stack
├── docker-compose.ci.yml     # CI E2E testing
├── Makefile               # Developer commands
└── .pre-commit-config.yaml
```

## Status

![CI](https://github.com/samjmc/GlasIntelligence/actions/workflows/ci.yml/badge.svg)

## License

Proprietary — All rights reserved.
