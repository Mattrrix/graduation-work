# LLM Benchmark

Сравнение LLM-backend'ов (MLX-local Qwen3.5-9B vs GigaChat) на NER-задаче:
точность извлечения полей и latency.

## Установка

```bash
cd tools/llm_bench
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# плюс tools/generator установить editable, либо просто положить его в PYTHONPATH
pip install -e ../generator
```

## Запуск

```bash
# из корня проекта:
python tools/llm_bench/run.py --count 3                  # синтетика, 3 файла на каждый тип
python tools/llm_bench/run.py --count 0 --real-dir samples/real   # только реальные
python tools/llm_bench/run.py --backends mlx             # только локальный, без GigaChat
python tools/llm_bench/run.py --count 5 --backends mlx,gigachat   # полный прогон
```

Перед запуском должны быть подняты:
- `mlx_lm.server --port 8112 --model mlx-community/Qwen3.5-9B-MLX-4bit` — для backend `mlx`
- `GIGACHAT_AUTH_KEY` в `.env` (Authorization Key из developers.sber.ru) — для `gigachat`

## Ground truth

**Синтетика** — генерируется через `tools/generator`, ground truth берётся напрямую
из dict'а генератора (точные значения, без интерпретации).

**Реальные PDF** — ground truth задаётся sidecar-файлом `<имя_файла>.gt.json`:

```json
{
  "doc_type": "invoice",
  "doc_number": "INV-2026-7006",
  "doc_date": "2026-09-30",
  "amount_total": "936271.07",
  "primary_inn": "8301661312",
  "primary_kpp": "830101001",
  "primary_name": "ООО Меридиан",
  "all_inns": ["8301661312", "6030824623"]
}
```

Без sidecar файл всё равно прогонится (увидим latency и сырой JSON-выход),
но в скоринге не учитывается.

## Что измеряется

- **Latency**: mean / median / p95 / min / max в секундах для успешных вызовов.
- **Reliability**: процент HTTP/JSON-ошибок на стороне backend'а.
- **Field-level accuracy**: doc_type / doc_number / doc_date / amount_total /
  primary_inn / primary_kpp / primary_name / all_inns.
- **Type breakdown**: doc_type accuracy раскрытая по каждому типу.

## Артефакты прогона

- `tools/llm_bench/out/results.json` — сырые результаты по каждому документу
  (включая raw_output LLM, ground truth, prediction, match-вектор).
- `tools/llm_bench/out/summary.json` — агрегаты (для импорта в скрипты).
- `tools/llm_bench/out/synth/*.pdf` — сгенерированные PDF (при `--count > 0`).
