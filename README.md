# LogicMUS-Eval

Пайплайн для генерации парных SAT/UNSAT логических бенчмарков со строгой
Z3-верификацией, проверкой минимальных невыполнимых ядер (MUS) и диагностикой
лексической утечки. Также включает модуль оценки LLM на сгенерированном датасете
(direct reasoning и Z3-translation стратегии).

## Структура проекта

```
data/
    generated_cases/        # артефакты: dataset_v1_frozen.jsonl, манифест, отчёты
src/
    config.py               # настройки (pydantic-settings)
    enums.py                # StrEnum-типы
    cli.py                  # CLI-слой на Typer (единственная точка входа)
    run_pipeline.py         # генерация + верификация + сохранение манифеста
    evaluate_llm.py         # оценка LLM на датасете
    generator.py            # детерминированный генератор кейсов
    verifier.py             # Z3-оракул и MUS-валидатор
    extractor.py            # обёртка над litellm со structured output
    hashing.py              # SHA-256 файлов и бандла исходников
    storage.py              # FileStorageManager: save/load датасета и манифеста
    templates.py            # шаблоны правил и пул предикатов
    evaluation/
        metrics.py          # SatAccuracy, MusValid, TokenUsage, ExecutionTime
        pipeline.py         # EvaluationPipeline
        strategies.py       # DirectEvaluationStrategy, Z3TranslationEvaluationStrategy
    models/
        evaluation.py       # DTO метрик, предсказаний, отчётов
        llm.py              # схемы ответов LLM
        manifests.py        # BenchmarkManifest и вложенные модели
        pipeline.py         # DatasetValidationMetrics, LeakageReport
        rules.py            # типы правил и их Z3-представление
        test_case.py        # LogicTestCase
    patterns/               # стратегии генерации паттернов
        base.py             # BasePatternStrategy (ClassVar метаданные)
        chain.py, coverage.py, direct.py, fork.py,
        idem.py, math.py, merge.py
    sandbox/
        executor.py         # Z3CodeExecutor (безопасный exec с таймаутом)
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

Собирает SAT/UNSAT-пары, прогоняет Z3-верификацию и MUS-проверку, считает
лексическую утечку и сохраняет:

- `data/generated_cases/dataset_v1_frozen.jsonl`
- `data/generated_cases/dataset_v1_frozen.manifest.json`

**bash**
```bash
uv run -m src.cli generate \
    --mus-sizes 2 --mus-sizes 3 --mus-sizes 4 --mus-sizes 5 \
    --pairs-per-group 25 \
    --total-rules 20 \
    --base-seed 42 \
    --output-dir data/generated_cases
```

**PowerShell (многострочно, backtick)**
```powershell
uv run -m src.cli generate `
    --mus-sizes 2 --mus-sizes 3 --mus-sizes 4 --mus-sizes 5 `
    --pairs-per-group 25 `
    --total-rules 20 `
    --base-seed 42 `
    --output-dir data/generated_cases
```

Флаги:

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--mus-sizes` | `2 3 4 5` | Размеры MUS. Флаг можно повторять: `--mus-sizes 2 --mus-sizes 3`. |
| `--pairs-per-group` | `25` | Сколько пар SAT/UNSAT на каждый размер MUS. |
| `--total-rules` | `20` | Общее число правил в кейсе (core + noise). |
| `--base-seed` | `42` | Базовый seed для воспроизводимости. |
| `--output-dir` | `data/generated_cases` | Куда сохранять артефакты. |

При генерации циклически перебираются все 7 стратегий
(`chain`, `coverage`, `direct`, `fork`, `idem`, `merge`, `math`), отфильтрованные
по минимально допустимому `mus_size`.

В конце в лог печатается отчёт:

### 2. Оценка LLM — стратегия `direct`

Модель сама выводит SAT/UNSAT и указывает MUS в текстовом рассуждении.

**bash**
```bash
uv run -m src.cli evaluate \
    --strategy direct \
    --model-name openai/qwen2.5-coder-14b-instruct \
    --dataset-dir data/generated_cases \
    --limit 10 \
    --output-file evaluation_direct.json
```

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

Модель пишет Python-код с `z3-solver`; код исполняется в песочнице
`Z3CodeExecutor` (белый список импортов, таймаут 5 секунд).

**bash**
```bash
uv run -m src.cli evaluate \
    --strategy z3 \
    --model-name openai/qwen2.5-coder-14b-instruct \
    --dataset-dir data/generated_cases \
    --limit 10 \
    --output-file evaluation_z3.json
```

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

### 4. Локальный LLM-сервер (LM Studio, Ollama, vLLM)

Перед запуском `evaluate` выставите переменные окружения:

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
`--model-name` с префиксом `openai/`, например `openai/qwen2.5-coder-14b-instruct`.

### 5. Справка

```bash
uv run -m src.cli --help
uv run -m src.cli generate --help
uv run -m src.cli evaluate --help
```

## Метрики оценки

| Метрика | Что показывает |
|---|---|
| `sat_accuracy` | Доля кейсов, где `is_sat` совпал с эталоном. |
| `mus_exact_match` | Доля UNSAT-кейсов с точным совпадением множеств `conflict_core`. |
| `mus_precision` / `mus_recall` / `mus_f1` | Усреднённые по UNSAT-кейсам precision/recall/F1 по MUS. |
| `total_tokens_consumed`, `total_thinking_tokens` | Расход токенов. |
| `avg_prompt_tokens`, `avg_completion_tokens`, `avg_thinking_tokens` | Средние значения. |
| `total_execution_seconds`, `avg_latency_seconds` | Время работы. |

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

`dataset_v1_frozen.manifest.json` содержит:

- `artifacts` — имя файла датасета, его SHA-256 и SHA-256 бандла исходников;
- `environment` — версии Python, z3, numpy, scikit-learn;
- `parameters` — размеры MUS, пары на группу, всего кейсов, правил на кейс, seed;
- `validation_results` — результаты Z3-верификации (SAT/UNSAT/MUS/MUS-minimality);
- `leakage_metrics_global` — TF-IDF F1 (word и char) по всему датасету;
- `leakage_metrics_by_mus_size` — то же в разрезе каждого размера MUS.
=Символ переноса должен быть **последним символом в строке**, без пробелов и табов после него. Иначе PowerShell/bash попытаются выполнить пустую команду и упадут.
