# ==============================================================================
# AAO — Development, QA & Operations Automation
# ==============================================================================

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Load local environment variables if .env.local exists
ifneq (,$(wildcard .env.local))
  include .env.local
  export
  # Strip quotes preserved by make inclusion
  AAO_POSTGRES_URL := $(patsubst '%',%,$(patsubst "%",%,$(AAO_POSTGRES_URL)))
  AAO_TEST_POSTGRES_URL := $(patsubst '%',%,$(patsubst "%",%,$(AAO_TEST_POSTGRES_URL)))
  AAO_DEV_POSTGRES_PASSWORD := $(patsubst '%',%,$(patsubst "%",%,$(AAO_DEV_POSTGRES_PASSWORD)))
endif

# Virtual environment and tool detection
VENV ?= .venv
PYTHON ?= $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
PYTEST ?= $(if $(wildcard $(VENV)/bin/pytest),$(VENV)/bin/pytest,pytest)
RUFF ?= $(if $(wildcard $(VENV)/bin/ruff),$(VENV)/bin/ruff,ruff)
NPM ?= npm

# Ports
API_PORT ?= 8001
FRONTEND_PORT ?= 5173

# Compose file for PostgreSQL datastore
COMPOSE_DEV ?= compose.dev.yaml

# Colors for terminal output
CYAN   := \033[36m
GREEN  := \033[32m
YELLOW := \033[33m
RED    := \033[31m
RESET  := \033[0m

.PHONY: all help dev run qa test lint free-ports \
        db-up db-down db-status db-logs db-reset db-wait \
        migrate migrate-status migrate-verify \
        backend-run backend-test backend-lint backend-format backend-format-check backend-qa \
        frontend-install frontend-run frontend-build frontend-typecheck frontend-test frontend-qa

all: help

## Mostrar este menú de ayuda
help:
	@echo -e "$(CYAN)AAO (Autonomous AI Organization) — Comandos de Automatización$(RESET)"
	@echo -e "Uso: $(GREEN)make [comando]$(RESET)\n"
	@awk '/^## / { desc = substr($$0, 4); next } /^[a-zA-Z0-9_-]+:/ { if (desc != "") { sub(":", "", $$1); printf "  $(GREEN)%-22s$(RESET) %s\n", $$1, desc; desc = "" } }' $(MAKEFILE_LIST)

# ------------------------------------------------------------------------------
# 1. Base de Datos (PostgreSQL en Docker)
# ------------------------------------------------------------------------------

## Levantar PostgreSQL local en Docker (compose.dev.yaml) y esperar a que esté listo
db-up:
	@echo -e "$(CYAN)Levantando PostgreSQL en contenedor Docker...$(RESET)"
	@docker compose -f $(COMPOSE_DEV) --env-file .env.local up -d postgres
	@$(MAKE) db-wait
	@echo -e "$(GREEN)PostgreSQL está listo para aceptar conexiones.$(RESET)"

## Esperar activamente a que PostgreSQL pase su healthcheck
db-wait:
	@echo -e "$(YELLOW)Esperando a que PostgreSQL esté 'healthy'...$(RESET)"
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' aao-postgres-1 2>/dev/null)" = "healthy" ]; do \
		sleep 1; \
	done

## Detener PostgreSQL en Docker
db-down:
	@echo -e "$(YELLOW)Deteniendo contenedor PostgreSQL...$(RESET)"
	@docker compose -f $(COMPOSE_DEV) --env-file .env.local stop postgres

## Ver estado de contenedores de base de datos
db-status:
	@docker compose -f $(COMPOSE_DEV) --env-file .env.local ps

## Ver logs de PostgreSQL en tiempo real
db-logs:
	@docker compose -f $(COMPOSE_DEV) --env-file .env.local logs -f postgres

## Reiniciar PostgreSQL descartando volúmenes (¡ATENCIÓN: BORRA DATOS!)
db-reset:
	@echo -e "$(RED)Eliminando contenedor y volumen de datos...$(RESET)"
	@docker compose -f $(COMPOSE_DEV) --env-file .env.local down -v
	@$(MAKE) db-up
	@$(MAKE) migrate

# ------------------------------------------------------------------------------
# 2. Migraciones PostgreSQL
# ------------------------------------------------------------------------------

## Aplicar migraciones pendientes a PostgreSQL
migrate:
	@echo -e "$(CYAN)Aplicando migraciones unificadas...$(RESET)"
	@$(PYTHON) scripts/migrate.py --apply

## Comprobar estado de las migraciones
migrate-status:
	@$(PYTHON) scripts/migrate.py --status

## Verificar integridad de migraciones aplicadas
migrate-verify:
	@$(PYTHON) scripts/migrate.py --verify

# ------------------------------------------------------------------------------
# 3. Backend (FastAPI / Uvicorn / Pytest / Ruff)
# ------------------------------------------------------------------------------

## Ejecutar servidor de API Backend con reload en puerto 8001
backend-run:
	@echo -e "$(CYAN)Iniciando Backend API en http://127.0.0.1:$(API_PORT)...$(RESET)"
	@PYTHONPATH=src $(PYTHON) -m uvicorn aao.work_management_api:app --host 127.0.0.1 --port $(API_PORT) --reload

## Ejecutar pruebas del Backend con Pytest
backend-test:
	@echo -e "$(CYAN)Ejecutando pruebas de Backend (pytest)...$(RESET)"
	@$(PYTEST) -q -rs --tb=short

## Ejecutar análisis de linting con Ruff
backend-lint:
	@echo -e "$(CYAN)Comprobando reglas con Ruff...$(RESET)"
	@$(RUFF) check src tests

## Aplicar formateo automático con Ruff
backend-format:
	@echo -e "$(CYAN)Formateando código con Ruff...$(RESET)"
	@$(RUFF) format src tests

## Verificar formateo sin modificar archivos
backend-format-check:
	@$(RUFF) format --check src tests

## Ejecutar suite completa de QA de Backend (compilación, lint y pruebas)
backend-qa: backend-lint backend-test
	@echo -e "$(CYAN)Verificando compilación de bytecode Python...$(RESET)"
	@$(PYTHON) -m compileall -q src tests
	@echo -e "$(GREEN)Backend QA completado con éxito.$(RESET)"

# ------------------------------------------------------------------------------
# 4. Frontend (React / Vite / Vitest / TypeScript)
# ------------------------------------------------------------------------------

## Instalar dependencias del frontend
frontend-install:
	@echo -e "$(CYAN)Instalando dependencias de frontend...$(RESET)"
	@cd frontend/app && $(NPM) install

## Ejecutar servidor de desarrollo Frontend en http://localhost:5173
frontend-run:
	@echo -e "$(CYAN)Iniciando Frontend Vite en http://127.0.0.1:$(FRONTEND_PORT)...$(RESET)"
	@cd frontend/app && $(NPM) run dev

## Compilar bundle de producción del Frontend
frontend-build:
	@echo -e "$(CYAN)Compilando Frontend (build)...$(RESET)"
	@cd frontend/app && $(NPM) run build

## Comprobar tipos TypeScript en Frontend
frontend-typecheck:
	@echo -e "$(CYAN)Comprobando tipos TypeScript en Frontend...$(RESET)"
	@cd frontend/app && npx tsc --noEmit

## Ejecutar pruebas unitarias de Frontend con Vitest
frontend-test:
	@echo -e "$(CYAN)Ejecutando pruebas de Frontend (vitest)...$(RESET)"
	@cd frontend/app && $(NPM) run test

## Ejecutar suite completa de QA de Frontend (tipos, compilación y pruebas)
frontend-qa: frontend-typecheck frontend-test frontend-build
	@echo -e "$(GREEN)Frontend QA completado con éxito.$(RESET)"

# ------------------------------------------------------------------------------
# 5. Comandos Compuestos de Alto Nivel
# ------------------------------------------------------------------------------

## Liberar puertos 5173 y 8001 si están retenidos
free-ports:
	@echo -e "$(YELLOW)Liberando puertos $(FRONTEND_PORT) y $(API_PORT)...$(RESET)"
	@-systemctl stop aao-api-dev.service 2>/dev/null || true
	@-fuser -k -9 $(FRONTEND_PORT)/tcp $(API_PORT)/tcp 2>/dev/null || true
	@echo -e "$(GREEN)Puertos liberados.$(RESET)"

## Ejecutar QA integral (Backend + Frontend)
qa: backend-qa frontend-qa
	@echo -e "$(GREEN)========================================$(RESET)"
	@echo -e "$(GREEN)   QA GENERAL COMPLETADO CON ÉXITO      $(RESET)"
	@echo -e "$(GREEN)========================================$(RESET)"

## Ejecutar todas las pruebas (Backend + Frontend)
test: backend-test frontend-test

## Ejecutar todos los linters (Backend + Frontend typecheck)
lint: backend-lint backend-format-check frontend-typecheck

## Iniciar entorno completo de desarrollo: Levantar DB, migrar y verificar estado
dev: db-up migrate
	@echo -e "$(GREEN)Entorno preparado.$(RESET)"
	@echo -e "Para iniciar los servicios en terminales independientes:"
	@echo -e "  - Backend:  $(CYAN)make backend-run$(RESET)"
	@echo -e "  - Frontend: $(CYAN)make frontend-run$(RESET)"
