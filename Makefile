.PHONY: up down logs ps rebuild clean clean-metrics clean-logs clean-obs psql ai-up ai-down ai-status ai-restart bench

# Поднять весь стек (build + up). Идемпотентно — повторный вызов
# пересобирает образы только если поменялся код или Dockerfile.
up:
	docker compose up -d --build

# Остановить и удалить контейнеры. Volume'ы (postgres_data,
# storage_data, grafana_data) сохраняются — данные на месте.
down:
	docker compose down

# Стрим логов всех сервисов в реальном времени, последние 100 строк.
# Прервать — Ctrl+C.
logs:
	docker compose logs -f --tail=100

# Краткий список контейнеров со статусами.
ps:
	docker compose ps

# Полная пересборка образов без использования кеша слоёв.
# Используется когда меняешь requirements.txt / package.json
# и нужно гарантированно подтянуть новые зависимости.
rebuild:
	docker compose build --no-cache

# Полный сброс: down + удаление ВСЕХ named volumes.
# Потеряешь все документы, БД, Grafana-настройки, Prometheus-историю.
# Нужно когда меняешь init.sql и хочешь применить новую схему БД.
clean:
	docker compose down -v

# Сброс метрик Prometheus.
# Сначала рестартим источники метрик (Counter'ы живут в памяти Python-
# процесса, не сбрасываются при рестарте только Prometheus). Затем
# пересоздаём контейнер Prometheus — TSDB лежит в эфемерном слое контейнера,
# recreate = чистая база.
# Документы в БД, логи Loki, Grafana-дашборды НЕ затрагиваются.
clean-metrics:
	docker compose restart extract transform
	docker compose rm -sf prometheus
	docker compose up -d prometheus

# Сброс логов Loki.
# Останавливаем loki + promtail, удаляем named volume loki_data (BoltDB-
# shipper индекс + chunks), поднимаем заново. Volume promtail_positions
# с /var/lib/promtail/positions.yaml СОХРАНЯЕТСЯ — promtail помнит до какого
# байта он дочитал каждый docker-лог и после wipe Loki шлёт только новые
# строки, а не replay'ит всю историю с начала жизни каждого контейнера.
# Метрики Prometheus, документы в БД, Grafana-дашборды НЕ затрагиваются.
clean-logs:
	docker compose stop loki promtail
	docker compose rm -sf loki promtail
	-docker volume rm graduation-work_loki_data
	docker compose up -d loki promtail

# Полный сброс observability: метрики + логи в одном вызове.
# Совмещает clean-metrics + clean-logs через Make-зависимости (DRY).
clean-obs: clean-metrics clean-logs

# Открыть psql внутри контейнера postgres под пользователем etl
# в БД etl. Выйти — \q.
psql:
	docker compose exec postgres psql -U etl -d etl

# AI-сервера (Phase 3 + 6) запускаются нативно на хосте, не в Docker
# (на macOS Docker не пробрасывает GPU/Metal, инференс был бы в 3-5×
# медленнее). Контейнеры extract/transform дёргают их через
# host.docker.internal:8111 (PaddleOCR) и :8112 (Qwen).
# Скрипт infra/ai/serve.sh держит PID-файлы и логи в .runtime/.
ai-up:
	bash infra/ai/serve.sh up

ai-down:
	bash infra/ai/serve.sh down

ai-status:
	bash infra/ai/serve.sh status

ai-restart:
	bash infra/ai/serve.sh restart

# Phase 8 LLM-bench: сравнение mlx-local vs GigaChat на синтетике + реальных PDF
# из samples/real/. Должен быть поднят mlx_lm.server :8112 (make ai-up) и
# заполнен GIGACHAT_AUTH_KEY в .env. Использует .venv_ai с deps (httpx,
# pdfplumber, python-docx, openpyxl, pandas, pydantic-settings, reportlab).
# Подробнее — tools/llm_bench/README.md, отчёт — docs/llm-comparison.md.
bench:
	QWEN_URL=http://localhost:8112 .venv_ai/bin/python tools/llm_bench/run.py \
		--count 5 --backends mlx,gigachat --real-dir samples/real
