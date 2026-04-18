# Glas Intelligence

Multi-agent AI scenario simulation engine for predictive business intelligence.

## Overview

Glas Intelligence uses large language models and multi-agent social simulation (OASIS) to model how stakeholders — governments, regulators, businesses, consumers — respond to policy changes, market disruptions, and geopolitical events.

## Architecture

- **Frontend**: Vue 3 + Vite
- **Backend**: Python / Flask
- **Simulation**: OASIS (camel-ai) multi-agent framework
- **Knowledge Graph**: Zep Cloud (GraphRAG)
- **Auth & DB**: Supabase (PostgreSQL + Auth)
- **Billing**: Stripe
- **Task Queue**: Celery + Redis
- **Deployment**: Docker Compose + Nginx + GitHub Actions CI/CD

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

### Continuous Deployment (on merge to main)

```
merge to main
  → build Docker image + push to GHCR
  → run database migrations (Supabase CLI)
  → deploy to staging (staging.glasinsight.com)
  → smoke test staging
  → deploy to production (glasinsight.com)
  → health check with auto-rollback
```

If the production health check fails within 60 seconds, the system automatically rolls back to the previous working image.

### Environments

| Environment | URL | Trigger |
|-------------|-----|---------|
| **Production** | https://glasinsight.com | Merge to `main` (after staging passes) |
| **Staging** | https://staging.glasinsight.com | Merge to `main` (before production) |

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

## Production Deployment

Automated via GitHub Actions on merge to `main`. Manual fallback:

```bash
# Build and deploy
make deploy-prod

# Or using the deploy script on the server
./deploy.sh start
```

## Environment Variables

See `.env.example` for all required configuration. Key additions for CI/CD:

| Variable | Purpose |
|----------|---------|
| `SENTRY_DSN` | Sentry error tracking |
| `ENABLE_PROMETHEUS` | Enable `/api/metrics` endpoint |
| `SENTRY_ENVIRONMENT` | Sentry environment tag |

## GitHub Secrets Required

| Secret | Purpose |
|--------|---------|
| `DEPLOY_SSH_KEY` | SSH private key for deploying to the server |
| `VITE_SUPABASE_URL` | Supabase URL for frontend build |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key for frontend build |
| `SUPABASE_ACCESS_TOKEN` | Supabase CLI access token for migrations |
| `SUPABASE_PROJECT_REF` | Supabase project reference for migrations |

## Project Structure

```
├── .github/workflows/     # CI/CD pipeline
│   ├── ci.yml             # PR checks (lint, test, security, E2E)
│   └── deploy.yml         # Automated deployment
├── backend/               # Flask API
│   ├── app/               # Application code
│   ├── tests/             # Unit + integration tests
│   └── pyproject.toml     # Python dependencies
├── frontend/              # Vue 3 SPA
│   └── src/               # Components, views, router
├── e2e/                   # Playwright E2E tests
├── docs/                  # Reference artifacts (reports for PDF tools, SQL schema snapshot)
│   ├── reports/           # Markdown sources for client/PDF reports
│   └── schema/            # Reference SQL (Supabase schema snapshot)
├── tasks/                 # Local task tracking (todo.md)
├── scripts/               # PDF/visual/DB utilities (simulation CLIs live under backend/scripts/)
├── nginx/                 # Nginx configs for prod/staging/monitoring
├── monitoring/            # Observability configs
│   ├── prometheus.yml
│   ├── alert-rules.yml
│   ├── loki-config.yml
│   ├── promtail-config.yml
│   └── grafana/           # Dashboards + datasources
├── docker-compose.yml         # Local dev
├── docker-compose.prod.yml    # Production
├── docker-compose.staging.yml # Staging
├── docker-compose.monitoring.yml  # Observability stack
├── docker-compose.ci.yml     # CI E2E testing
├── Makefile               # Developer commands
└── .pre-commit-config.yaml
```

## Status

![CI](https://github.com/samjmc/GlasIntelligence/actions/workflows/ci.yml/badge.svg)

## License

Proprietary — All rights reserved.
