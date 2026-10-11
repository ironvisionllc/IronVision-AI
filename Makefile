.PHONY: up up-prod migrate test acceptance scan perf backup restore-verify portability openapi

up:            ## dev stack
	docker compose up -d --build
up-prod:       ## production overlay (OIDC, no demo seed, TLS edge)
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
migrate:
	cd backend && alembic upgrade head
test:
	cd backend && python -m pytest -c pytest.aegis.ini tests -q
acceptance:    ## AT-1..AT-12 + full suite, writes docs/TEST_RESULTS.md
	bash scripts/run_acceptance.sh
scan:          ## writes docs/security/*
	bash scripts/security_scan.sh
perf:          ## writes docs/PERFORMANCE.md
	python3 scripts/perf_smoke.py
backup:
	bash scripts/backup.sh
restore-verify: ## make restore-verify BACKUP_DIR=backups/<ts>  (restore into the DATABASE_URL/storage you point it at, then verify)
	bash scripts/restore.sh $(BACKUP_DIR)
portability:
	bash scripts/verify_portability.sh
openapi:
	cd backend && python -c "import json;from app.main import app;json.dump(app.openapi(),open('../docs/openapi.json','w'),indent=1)"
