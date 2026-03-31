.PHONY: dev build test lint lint-backend lint-frontend test-backend test-frontend test-integration test-e2e setup setup-hooks deploy-staging deploy-prod monitoring-up monitoring-down clean

# ──── Development ────

dev:
	npm run dev

setup:
	npm run setup:all
	cd e2e && npm install

setup-hooks:
	pip install pre-commit
	pre-commit install

# ──── Linting ────

lint: lint-backend lint-frontend

lint-backend:
	cd backend && uv run ruff check app/
	cd backend && uv run ruff format --check app/
	cd backend && uv run mypy app/ --ignore-missing-imports

lint-frontend:
	cd frontend && npm run lint

# ──── Testing ────

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest tests/ --cov=app --cov-report=term-missing -v

test-frontend:
	cd frontend && npm run test

test-integration:
	cd backend && uv run pytest tests/integration/ -v

test-e2e:
	cd e2e && npx playwright test

test-all: test test-integration test-e2e

# ──── Build ────

build:
	docker build -f Dockerfile.prod \
		--build-arg VITE_SUPABASE_URL=$${VITE_SUPABASE_URL} \
		--build-arg VITE_SUPABASE_ANON_KEY=$${VITE_SUPABASE_ANON_KEY} \
		-t glas-intelligence:local .

# ──── Deployment ────

deploy-staging:
	docker compose -f docker-compose.staging.yml pull
	docker compose -f docker-compose.staging.yml up -d

deploy-prod:
	docker compose -f docker-compose.prod.yml up -d --build

# ──── Monitoring ────

monitoring-up:
	docker compose -f docker-compose.monitoring.yml up -d

monitoring-down:
	docker compose -f docker-compose.monitoring.yml down

# ──── Cleanup ────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	rm -rf frontend/dist e2e/test-results e2e/playwright-report
