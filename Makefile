.PHONY: dev stop test test-unit test-integration test-contract lint migrate seed logs gen-ca deploy help frontend-dev test-frontend build-frontend compact-delta

COMPOSE = docker-compose
PYTHON = python
ALEMBIC = alembic

help:
	@echo "Health Intelligence Platform - Available targets:"
	@echo "  dev              Start all services (build + detach)"
	@echo "  stop             Stop all services"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-contract    Run contract tests only"
	@echo "  lint             Run ruff + mypy"
	@echo "  migrate          Run Alembic migrations"
	@echo "  seed             Seed database with test devices"
	@echo "  logs             Tail app container logs"
	@echo "  gen-ca           Generate local CA certificate for MQTT mTLS"
	@echo "  deploy           Deploy to AWS via CloudFormation bootstrap"
	@echo "  frontend-dev     Start Vite dev server (hot-reload on port 5173)"
	@echo "  test-frontend    Run frontend tests (Vitest)"
	@echo "  build-frontend   Build frontend static assets"
	@echo "  compact-delta    Compact + vacuum + checkpoint Delta Lake tables"

dev:
	mkdir -p ./data/delta ./data/parquet ./data/models ./data/packages
	$(COMPOSE) up --build -d

stop:
	$(COMPOSE) down

test:
	$(PYTHON) -m pytest tests/ -v

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v

test-contract:
	$(PYTHON) -m pytest tests/contract/ -v

lint:
	$(PYTHON) -m ruff check src/ tests/
	$(PYTHON) -m ruff format --check src/ tests/
	$(PYTHON) -m mypy src/ --ignore-missing-imports

migrate:
	$(COMPOSE) exec app alembic upgrade head

migrate-down:
	$(ALEMBIC) downgrade -1

seed:
	API_ENDPOINT=http://localhost:8100 API_KEY=$${API_KEY:-poc-dev-key} $(PYTHON) scripts/seed_devices.py

logs:
	$(COMPOSE) logs -f app

gen-ca:
	@echo "Generating local CA for MQTT mTLS..."
	@mkdir -p infra/certs
	openssl genrsa -out infra/certs/ca.key 4096
	openssl req -new -x509 -days 3650 -key infra/certs/ca.key \
	  -out infra/certs/ca.crt \
	  -subj "/C=US/ST=Local/O=Platform/CN=LocalCA"
	@echo "CA certificate: infra/certs/ca.crt"

deploy:
	@echo "Deploying to AWS..."
	./infra/bootstrap.sh

frontend-dev:
	cd frontend && npm run dev

test-frontend:
	cd frontend && npm run test

build-frontend:
	cd frontend && npm run build

ps:
	$(COMPOSE) ps

shell:
	$(COMPOSE) exec app bash

compact-delta:
	$(PYTHON) scripts/compact_delta.py --base-dir ./data/delta --recommendations-dir ./data/recommendations --log-retention-hours 1
