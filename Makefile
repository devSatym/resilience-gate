.PHONY: test validate validate-platform smoke-local local-up local-down

PYTHON ?= python3

test:
	$(PYTHON) -m pytest

validate:
	$(MAKE) validate-platform

validate-platform:
	PYTHON=$(PYTHON) ./scripts/validate.sh

smoke-local:
	./scripts/smoke-local.sh

local-up:
	docker compose up --build

local-down:
	docker compose down --volumes --remove-orphans
