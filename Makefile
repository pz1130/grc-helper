.PHONY: up down logs test migrate revision migrate-roundtrip fmt create-admin ping-worker purge-staging e2e e2e-down corpus retrieval extraction-eval seed-frameworks mapping-eval relation-eval

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

# 验收清单要求的迁移往返。downgrade 会真的 DROP TABLE，所以必须打一次性库：
# alembic 只认 ALEMBIC_DATABASE_URL 或 .env 的 DATABASE_URL，传 APP_DATABASE_URL
# 是没用的——那样会静默地在开发库上删表。
migrate-roundtrip:
	docker compose exec -T db psql -U grc -d postgres -c "DROP DATABASE IF EXISTS grc_roundtrip"
	docker compose exec -T db psql -U grc -d postgres -c "CREATE DATABASE grc_roundtrip OWNER grc"
	docker compose run --rm --no-deps \
	  -e ALEMBIC_DATABASE_URL=postgresql+asyncpg://grc:grc@db:5432/grc_roundtrip \
	  api sh -c 'alembic upgrade head && alembic downgrade $(to) && alembic upgrade head && alembic check'
	docker compose exec -T db psql -U grc -d postgres -c "DROP DATABASE IF EXISTS grc_roundtrip"

fmt:
	docker compose run --rm api ruff check --fix app tests

create-admin:
	docker compose run --rm api python -m app.cli create-admin "$(email)" "$(name)" "$(password)"

ping-worker:
	docker compose run --rm api python -c "import asyncio; from app.worker import enqueue; print(asyncio.run(enqueue('ping')))"

# 暂存卷的定时清理平时由 worker 的 cron 跑；这个入口用来立刻跑一次。
purge-staging:
	docker compose run --rm worker python -m app.cli purge-staging

# 冒烟用例会建 provider、建用户、往暂存卷写文件，而 provider 和用户都没有删除
# 接口（审计留痕要求如此）。所以 e2e 不跑在开发栈上，而是另起一个 compose 项目：
# 项目名不同 → 容器、网络、数据卷（pgdata/docstore/staging）全部另开一套，
# 跑完 down -v 一次性扔掉，开发库一条痕迹都不留（OQ-3）。端口也要错开，
# 否则和正在跑的开发栈抢 5432/6379/8000/5173。
E2E_COMPOSE = COMPOSE_PROJECT_NAME=grc-e2e DB_PORT=5433 REDIS_PORT=6380 API_PORT=8001 WEB_PORT=5174 docker compose

e2e:
	$(E2E_COMPOSE) up -d --build
	$(E2E_COMPOSE) run --rm api alembic upgrade head
	$(E2E_COMPOSE) run --rm api python -m app.cli create-admin admin@example.com Admin pw123456
	cd frontend && npm install --silent && npx playwright install --with-deps chromium
	(cd frontend && E2E_BASE_URL=http://localhost:5174 E2E_API_BASE=http://localhost:8001 npm run test:e2e); \
	  status=$$?; $(MAKE) e2e-down || status=1; exit $$status

# 单独留一个出口：e2e 中途被 Ctrl-C 打断时，那套栈还在后台占着端口。
e2e-down:
	$(E2E_COMPOSE) down -v

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
