UV = uv
RUN = $(UV) run --no-sync
COMPOSE = docker compose -f infrastructure/compose/compose.yaml
.PHONY: bootstrap infra infra-core seed-core seed-demo dev api worker dashboard migrate test integration lint typecheck e2e e2e-ui recovery screenshots format build schema doctor down mcp mcp-config mcp-smoke
bootstrap:
	python3 scripts/bootstrap.py
	$(UV) sync --frozen
	npm ci
infra-core:
	$(COMPOSE) up -d --wait postgres temporal redis keycloak
infra:
	$(COMPOSE) up -d --wait postgres temporal redis minio keycloak
seed-core:
	$(RUN) python scripts/seed.py
seed-demo: seed-core
	$(RUN) python scripts/artifacts.py
migrate:
	$(RUN) alembic upgrade head
dev:
	$(COMPOSE) up -d --build
api:
	$(RUN) uvicorn apps.api.main:create_app --factory --host 127.0.0.1 --port 8080
worker:
	$(RUN) python -m workers.main
dashboard:
	npm run dev --workspace apps/dashboard
test:
	$(RUN) pytest tests/unit tests/security
integration:
	AG_TEST_POSTGRES=1 $(RUN) pytest tests/integration
lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	npm run format:check
typecheck:
	$(RUN) mypy
	npm run typecheck --workspace apps/dashboard
	npm run typecheck --workspace sdk/typescript
e2e:
	$(RUN) python scripts/demo.py
e2e-ui:
	$(RUN) python scripts/browser.py
recovery:
	$(RUN) python scripts/recovery_check.py
screenshots:
	AG_UPDATE_SCREENSHOTS=1 $(RUN) python scripts/browser.py
format:
	$(RUN) ruff check --fix .
	$(RUN) ruff format .
	npm run format
build:
	$(UV) build
	npm run build --workspace apps/dashboard
	npm run build --workspace sdk/typescript
schema:
	$(RUN) python scripts/export_openapi.py
	npm run generate --workspace sdk/typescript
doctor:
	$(RUN) agentgenome doctor
down:
	$(COMPOSE) down
mcp:
	$(RUN) agentgenome-mcp
mcp-config:
	$(RUN) python scripts/mcp_config.py
mcp-smoke:
	$(RUN) python scripts/mcp_smoke.py
