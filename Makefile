.PHONY: up down logs test migrate revision fmt create-admin ping-worker e2e corpus

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
