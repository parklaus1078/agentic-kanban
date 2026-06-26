# Agent System v2 — developer entrypoints. Run all targets from the repo ROOT.
#
#   make install          install backend (pip) + web (npm) deps
#   make up               build + start the full stack (detached)
#   make down             stop + remove the stack
#   make logs             follow logs for all services
#   make ps               show service status
#   make seed             POST /admin/seed (board + personas + skills)
#   make demo             run the end-to-end demo lifecycle script
#   make test             run backend pytest suite
#   make web-build        build the React frontend (dist/)
#   make compose-validate validate the compose file (needs Docker)

COMPOSE  := docker compose -f infra/docker-compose.yml --project-directory .
API_BASE ?= http://localhost:8000

.DEFAULT_GOAL := help
.PHONY: help install up down logs ps seed demo test web-build compose-validate host-daemon

help:
	@echo "Agent System v2 — make targets:"
	@echo "  install          backend (pip) + web (npm) deps"
	@echo "  up               build + start full stack (detached)"
	@echo "  down             stop + remove stack"
	@echo "  logs             follow all service logs"
	@echo "  ps               service status"
	@echo "  seed             POST /admin/seed  (API_BASE=$(API_BASE))"
	@echo "  demo             run scripts/demo.py end-to-end lifecycle"
	@echo "  test             pytest in apps/api"
	@echo "  web-build        build React frontend (apps/web -> dist/)"
	@echo "  compose-validate docker compose config (requires Docker)"

install:
	pip install -r apps/api/requirements.txt
	@if [ -d apps/web ]; then cd apps/web && npm ci || npm install; \
	 else echo "apps/web not present yet — skipping web deps"; fi

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

seed:
	curl -fsS -X POST $(API_BASE)/admin/seed

demo:
	python scripts/demo.py

test:
	cd apps/api && python -m pytest -q

web-build:
	cd apps/web && (npm ci || npm install) && npm run build

compose-validate:
	$(COMPOSE) config

# Phase 5C — real interactive executor. Runs on the HOST (not Docker) so it can use
# host tmux + the logged-in claude/codex CLI. Postgres is reached on localhost:5432.
host-daemon:
	cd apps/api && DATABASE_URL=postgresql+psycopg://asv2:asv2@localhost:5432/asv2 \
	  ASV2_AGENT_MODE=real python -m app.host_daemon
