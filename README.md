# Glas Intelligence

Multi-agent AI scenario simulation engine for predictive business intelligence.

## Overview

Glas Intelligence uses large language models and multi-agent social simulation (OASIS) to model how stakeholders — governments, regulators, businesses, consumers — respond to policy changes, market disruptions, and geopolitical events.

## Architecture

- **Frontend**: Vue 3 + Vite
- **Backend**: Python / Flask
- **Simulation**: OASIS (camel-ai) multi-agent framework
- **Knowledge Graph**: Graphiti on a self-hosted Neo4j (default; see [docs/graphiti-setup.md](docs/graphiti-setup.md)); Zep Cloud optional (`GRAPH_BACKEND=zep`)
- **Auth & DB**: Supabase (PostgreSQL + Auth)
- **Billing**: Stripe
- **Task Queue**: Celery + Redis
- **Deployment**: the static demo deploys to GitHub Pages; the backend is not deployed anywhere at present (see [Deployment](#deployment))

## Local Development

The knowledge graph needs a running **Neo4j 5.26** (with Java 21) and `NEO4J_PASSWORD` set as a user environment variable. Follow [docs/graphiti-setup.md](docs/graphiti-setup.md) once; it covers Windows without admin rights, and Docker.

```bash
# Copy environment variables
cp .env.example .env
# Edit .env with your API keys (keep NEO4J_PASSWORD in a user-level env var instead)

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

### Other workflows

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| `deploy-pages.yml` | push to `main` | Builds the static demo and deploys it to GitHub Pages |
| `demo-e2e.yml` | PRs, push to `main` | End-to-end tests of the static demo |
| `docker-image.yml` | tags, manual | Builds and pushes the Docker image |

## Deployment

The backend is **not deployed anywhere** at present. The Hetzner server pipeline (staging and production, `deploy.yml`, `deploy.sh`, `docker-compose.prod.yml` / `.staging.yml`) was retired on 2026-08-10. Only the static demo is live, on GitHub Pages.

Hosting the backend again is an open decision. It now also needs a home for Neo4j (see the end of [docs/graphiti-setup.md](docs/graphiti-setup.md)).

## Monitoring & Observability

The monitoring configs are kept for a self-hosted server. None is running at present (see [Deployment](#deployment)). They run as separate Docker services:

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

See `.env.example` for all configuration. Notable ones:

| Variable | Purpose |
|----------|---------|
| `GRAPH_BACKEND` | `graphiti` (default) or `zep`; see [docs/graphiti-setup.md](docs/graphiti-setup.md) |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | The Neo4j database for the Graphiti backend (password as a user-level env var) |
| `SENTRY_DSN` | Sentry error tracking |
| `ENABLE_PROMETHEUS` | Enable `/api/metrics` endpoint |
| `SENTRY_ENVIRONMENT` | Sentry environment tag |

## Project Structure

```
├── .github/workflows/     # CI and the static-demo deploy
│   ├── ci.yml             # PR checks (lint, test, security, E2E)
│   ├── demo-e2e.yml       # Static demo end-to-end tests
│   ├── deploy-pages.yml   # Static demo to GitHub Pages
│   └── docker-image.yml   # Docker image build (tags / manual)
├── backend/               # Flask API
│   ├── app/               # Application code
│   ├── tests/             # Unit + integration tests
│   └── pyproject.toml     # Python dependencies
├── frontend/              # Vue 3 SPA
│   └── src/               # Components, views, router
├── e2e/                   # Playwright E2E tests
├── monitoring/            # Observability configs
│   ├── prometheus.yml
│   ├── alert-rules.yml
│   ├── loki-config.yml
│   ├── promtail-config.yml
│   └── grafana/           # Dashboards + datasources
├── docker-compose.yml         # Local dev
├── docker-compose.monitoring.yml  # Observability stack
├── docker-compose.ci.yml     # CI E2E testing
├── Makefile               # Developer commands
└── .pre-commit-config.yaml
```

## License

Proprietary — All rights reserved.
