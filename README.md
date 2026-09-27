# LogicMUS-Eval

Пайплайн для генерации парных SAT/UNSAT логических бенчмарков со строгой
Z3-верификацией, проверкой минимальных невыполнимых ядер (MUS) и диагностикой
лексической утечки. Включает модуль оценки LLM на сгенерированном датасете
(direct reasoning и Z3-translation стратегии).

## Структура проекта

```
data/
    generated_cases/        # dataset_v1_frozen.jsonl, манифест, отчёты
src/
    config.py               # настройки (pydantic-settings)
    enums.py                # StrEnum-типы (включая FailureTag)
    cli.py                  # CLI-слой на Typer
    run_pipeline.py         # генерация + верификация + манифест
    evaluate_llm.py         # оценка LLM на датасете
    generator.py            # детерминированный генератор кейсов
    verifier.py             # Z3-оракул и MUS-валидатор
    extractor.py            # обёртка над litellm со structured output
    hashing.py              # SHA-256 файлов и бандла исходников
    storage.py              # FileStorageManager
    templates.py            # шаблоны правил и пул предикатов
    evaluation/
        diagnostics.py      # classify_failure + is_refusal
        metrics.py          # Sat, Mus, Token, Time, Refusal, Infra, ValidResponse
        pipeline.py         # EvaluationPipeline
        strategies.py       # DirectEvaluationStrategy, Z3TranslationEvaluationStrategy
    models/
        evaluation.py       # DTO метрик, RunInfo, failure_tags
        llm.py              # схемы ответов LLM
        manifests.py        # BenchmarkManifest
        pipeline.py         # DatasetValidationMetrics, LeakageReport
        rules.py            # типы правил и Z3-представление
        test_case.py        # LogicTestCase
    patterns/
        base.py, chain.py, coverage.py, direct.py,
        fork.py, idem.py, math.py, merge.py
    sandbox/
        executor.py         # Z3CodeExecutor
tests/
    integration/
    unit/
```

## Установка

```bash
uv sync
```

## Команды
### 1. Генерация датасета

**bash**
```bash
uv run -m src.cli generate \
    --mus-size-min 2 --mus-size-max 5 \
    --pairs-per-group 25 \
    --total-rules 20 \
    --base-seed 42 \
    --output-dir data/generated_cases
```

**PowerShell**
```powershell
uv run -m src.cli generate `
    --mus-size-min 2 --mus-size-max 5 `
    --pairs-per-group 25 `
    --total-rules 20 `
    --base-seed 42 `
    --output-dir data/generated_cases
```

Флаги:

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--mus-size-min` | `2` | Минимальный размер MUS (включительно). |
| `--mus-size-max` | `5` | Максимальный размер MUS (включительно). |
| `--pairs-per-group` | `25` | Пар SAT/UNSAT на каждый размер MUS. |
| `--total-rules` | `20` | Общее число правил в кейсе (core + noise). |
| `--base-seed` | `42` | Базовый seed. |
| `--output-dir` | `data/generated_cases` | Каталог для артефактов. |

Сохраняются:

- `data/generated_cases/dataset_v1_frozen.jsonl`
- `data/generated_cases/dataset_v1_frozen.manifest.json`

### 2. Оценка LLM — стратегия `direct`

**PowerShell**
```powershell
uv run -m src.cli evaluate `
    --strategy direct `
    --model-name openai/qwen2.5-coder-14b-instruct `
    --dataset-dir data/generated_cases `
    --limit 10 `
    --output-file evaluation_direct.json
```

### 3. Оценка LLM — стратегия `z3`

**PowerShell**
```powershell
uv run -m src.cli evaluate `
    --strategy z3 `
    --model-name openai/qwen2.5-coder-14b-instruct `
    --dataset-dir data/generated_cases `
    --limit 10 `
    --output-file evaluation_z3.json
```

Флаги команды `evaluate`:

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--strategy` | `direct` | `direct` или `z3`. |
| `--model-name` | `openai/qwen2.5-coder-14b-instruct` | Идентификатор модели для litellm. |
| `--dataset-dir` | `data/generated_cases` | Каталог с `dataset_v1_frozen.jsonl`. |
| `--limit` | `10` | Сколько кейсов обработать. |
| `--output-file` | `evaluation_results.json` | Имя файла отчёта (сохраняется в `--dataset-dir`). |

### 4. Локальный LLM-сервер

**PowerShell**
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:1234/v1"
$env:OPENAI_API_KEY  = "lm-studio"
```

**bash**
```bash
export OPENAI_API_BASE="http://127.0.0.1:1234/v1"
export OPENAI_API_KEY="lm-studio"
```

Имя модели берётся из `GET $OPENAI_API_BASE/models` и передаётся в
`--model-name` с префиксом `openai/`.

### 5. Справка

```bash
uv run -m src.cli --help
uv run -m src.cli generate --help
uv run -m src.cli evaluate --help
```

## Метрики оценки

| Метрика | Что показывает |
|---|---|
| `sat_accuracy` | Доля кейсов, где `is_sat` совпал с эталоном (по всем ответам, включая отказы и ошибки). |
| `valid_response_accuracy` | Доля верных ответов **среди ответов, где модель реально рассуждала** (без отказов и инфраструктурных ошибок). Главная новая метрика. |
| `mus_exact_match` | Доля UNSAT-кейсов с точным совпадением множеств `conflict_core`. |
| `mus_precision` / `mus_recall` / `mus_f1` | Усреднённые по UNSAT-кейсам precision/recall/F1 по MUS. |
| `refusal_rate` | Доля кейсов, где модель отказалась рассуждать («нет начальных состояний» и т.п.). |
| `infrastructure_error_rate` | Доля кейсов с инфраструктурными ошибками (JSON parse, Z3 execution error). |
| `total_tokens_consumed`, `total_thinking_tokens` | Расход токенов. |
| `avg_prompt_tokens`, `avg_completion_tokens`, `avg_thinking_tokens` | Средние значения. |
| `total_execution_seconds`, `avg_latency_seconds` | Время работы. |

## Таксономия ошибок

Каждая запись в `details[*]` содержит поле `failure_tags` — список
классификаторов из `FailureTag`:

| Тег | Значение |
|---|---|
| `correct` | Ответ верен и MUS (для UNSAT) совпал. |
| `refusal_no_facts` | Модель заявила, что не может рассуждать (нет начальных фактов и т.п.). |
| `wrong_sat` | Модель ошиблась в SAT/UNSAT. |
| `wrong_mus_missing` | Модель верно распознала UNSAT, но пропустила часть правил из MUS. |
| `wrong_mus_extra` | Модель верно распознала UNSAT, но добавила лишние правила. |
| `exec_error` | Инфраструктурная ошибка (JSON parse, sandbox exec). |
| `unknown` | Не попало ни в одну категорию. |

## Run metadata

Каждый отчёт `evaluation_*.json` содержит блок `run_info`:

| Поле | Описание |
|---|---|
| `model_name` | Идентификатор модели. |
| `strategy` | `direct` или `z3`. |
| `dataset_filename` | Имя датасета. |
| `dataset_sha256` | SHA-256 датасета на момент прогона. |
| `prompt_template_hash` | SHA-256 шаблонов промптов. |
| `git_commit` | Git HEAD на момент прогона (или `null`). |
| `started_at`, `finished_at` | Временные метки в UTC. |
| `limit` | Лимит кейсов. |
| `total_cases_processed` | Сколько кейсов реально обработано. |

## Тесты

```bash
uv run pytest
uv run pytest tests/unit -v
uv run pytest tests/integration -v
```

## Линтеры и форматирование

```bash
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run pylint src
```

## Что сохраняется в манифест

`dataset_v1_frozen.manifest.json`:

- `artifacts` — имя файла датасета, его SHA-256 и SHA-256 бандла исходников;
- `environment` — версии Python, z3, numpy, scikit-learn;
- `parameters` — размеры MUS, пары на группу, всего кейсов, правил на кейс, seed;
- `validation_results` — результаты Z3-верификации (SAT/UNSAT/MUS/MUS-minimality);
- `leakage_metrics_global` — TF-IDF F1 (word и char) по всему датасету;
- `leakage_metrics_by_mus_size` — то же в разрезе каждого размера MUS.
