.PHONY: test validate validate-platform config render-config bootstrap verify lab-status lab-bootstrap-plan lab-destroy-plan loadgen-plan smoke-local local-up local-down

PYTHON ?= python3

test:
	$(PYTHON) -m pytest

validate:
	$(MAKE) validate-platform

validate-platform:
	PYTHON=$(PYTHON) ./scripts/validate.sh

config:
	@test -f platform_setup_scripts/config.env || cp platform_setup_scripts/config.env.example platform_setup_scripts/config.env

render-config:
	./platform_setup_scripts/render_config.py --write

bootstrap:
	./platform_setup_scripts/bootstrap.sh

verify:
	./platform_setup_scripts/07-verify.sh

lab-status:
	./scripts/lab-ops.sh status

lab-bootstrap-plan:
	./scripts/lab-ops.sh bootstrap-plan

lab-destroy-plan:
	./scripts/lab-ops.sh destroy-plan

loadgen-plan:
	./scripts/run-loadgen.sh --plan

smoke-local:
	./scripts/smoke-local.sh

local-up:
	docker compose up --build

local-down:
	docker compose down --volumes --remove-orphans
