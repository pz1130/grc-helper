.PHONY: up down logs test migrate revision fmt create-admin ping-worker e2e corpus retrieval extraction-eval seed-frameworks mapping-eval relation-eval

up:
	docker compose up -d --build db redis api

down:
	docker compose down

logs:
	docker compose logs -f api worker

test:
	docker compose run --rm -e TEST_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc_test api pytest -v

migrate:
	docker compose run --rm api alembic upgrade head

revision:
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

fmt:
	docker compose run --rm api ruff check --fix app tests

create-admin:
	docker compose run --rm api python -m app.cli create-admin "$(email)" "$(name)" "$(password)"

ping-worker:
	docker compose run --rm api python -c "import asyncio; from app.worker import enqueue; print(asyncio.run(enqueue('ping')))"

e2e:
	docker compose up -d --build
	docker compose run --rm api alembic upgrade head
	docker compose run --rm api python -m app.cli create-admin admin@example.com Admin pw123456
	cd frontend && npm install --silent && npx playwright install --with-deps chromium && npm run test:e2e

corpus:
	docker compose run --rm --no-deps \
	  -e TEST_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc_test \
	  -v "$(PWD)/sample docs:/samples:ro" \
	  api pytest tests/test_corpus_report.py -v -s

retrieval:
	docker compose run --rm --no-deps \
	  -e TEST_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc_test \
	  -e RUN_RETRIEVAL_EVAL=1 \
	  -e APP_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc \
	  -v "$(PWD)/sample docs:/samples:ro" \
	  api pytest tests/test_retrieval_quality.py -v -s

extraction-eval:
	docker compose run --rm --no-deps \
	  -e RUN_EXTRACTION_EVAL=1 \
	  -e APP_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc \
	  api pytest tests/test_extraction_quality.py -v -s

seed-frameworks:
	docker compose run --rm api python -m app.cli import-framework \
	  seeds/nist-csf-2.0.csv nist-csf-2.0 "NIST 网络安全框架 2.0" "NIST CSF 2.0" 2.0 nist.gov
	docker compose run --rm api python -m app.cli import-framework \
	  seeds/nist-800-53-r5.csv nist-800-53-r5 "NIST SP 800-53 Rev.5" "NIST SP 800-53 Rev.5" 5.1.1 nist.gov

mapping-eval:
	docker compose run --rm --no-deps \
	  -e RUN_MAPPING_EVAL=1 \
	  -e APP_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc \
	  api pytest tests/test_mapping_quality.py -v -s

relation-eval:
	docker compose run --rm --no-deps \
	  -e RUN_RELATION_EVAL=1 \
	  -e APP_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc \
	  api pytest tests/test_relation_quality.py -v -s
