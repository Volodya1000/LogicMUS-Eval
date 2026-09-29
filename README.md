# LogicMUS-Eval

Пайплайн для генерации парных SAT/UNSAT логических бенчмарков с заданной
кардинальностью минимального невыполнимого подмножества требований (MUS),
строгой Z3-верификацией, структурным доказательством уникальности конфликта
и контролем лексической утечки. Включает модуль оценки LLM по двум стратегиям:
прямому текстовому выводу и нейросимвольной трансляции в Z3 (Python).

## Содержание

- [О проекте](#о-проекте)
- [Готовый датасет](#готовый-датасет)
- [Структура](#структура)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
  - [Генерация датасета](#генерация-датасета)
  - [Оценка LLM](#оценка-llm)
- [Эксперименты](#эксперименты)
  - [Smoke-grid](#smoke-grid)
  - [Full-grid](#full-grid)
  - [Проверка жизненного цикла моделей](#проверка-жизненного-цикла-моделей)
  - [Анализ результатов](#анализ-результатов)
- [Метрики](#метрики)
- [Таксономия ошибок](#таксономия-ошибок)
- [Воспроизводимость](#воспроизводимость)
- [Подключение к LLM-серверу для запуска оценки](#подключение-к-llm-серверу-для-запуска-оценки)
- [Ограничения](#ограничения)
- [Разработка](#разработка)

## О проекте

Методология и эталонный датасет для оценки способности LLM выявлять
логические конфликты в спецификациях требований. Основной параметр задачи —
кардинальность MUS, обозначаемая $K$. Генератор создаёт SAT/UNSAT-пары с
контролируемым уровнем независимого шума, скрывая от модели различие между
смысловым ядром и шумом (нейтральные ID $R_1 \dots R_N$).

Ключевые элементы:

- **7 топологических паттернов конфликта**: `direct`, `chain`, `fork`,
  `merge`, `coverage`, `idem`, `math` — реализованы в
  `logicmus_eval/patterns/`.
- **Z3-оракул** для проверки SAT/UNSAT, валидности и минимальности MUS
  (`logicmus_eval/verifier.py`).
- **Структурное доказательство уникальности MUS** за линейное время
  $O(|V| + |E|)$ через анализ компонент связности графа общих переменных
  (`logicmus_eval/verifier.py::verify_mus_uniqueness_by_structure`,
  см. `tests/unit/test_verifier.py`).
- **Контроль лексической утечки** через TF-IDF + LogisticRegression с
  StratifiedGroupKFold (порог F1 = 0.55, `logicmus_eval/run_pipeline.py`).
- **Изолированный sandbox** для исполнения сгенерированного LLM кода на Z3
  (`logicmus_eval/sandbox/executor.py`).
- **Две стратегии оценки**: `direct` (прямой текстовый вывод) и
  `z3` (нейросимвольная трансляция в исполняемый Python + алгоритмическая
  минимизация `unsat_core`).

## Готовый датасет

В репозитории опубликована замороженная версия датасета — её можно
использовать напрямую, без повторной генерации:

- [`datasets/v1.0/dataset_v1_frozen.jsonl`](datasets/v1.0/dataset_v1_frozen.jsonl) —
  200 кейсов (100 SAT / 100 UNSAT).
- [`datasets/v1.0/dataset_v1_frozen.manifest.json`](datasets/v1.0/dataset_v1_frozen.manifest.json) —
  параметры генерации, версии окружения, результаты Z3-верификации,
  leakage-метрики.

Параметры v1.0: MUS = 2..5, `total_rules` = 20, `pairs_per_group` = 25,
`base_seed` = 42. Все кейсы прошли Z3-проверку: SAT-корректность 100/100,
UNSAT-корректность 100/100, MUS-валидность 100/100, MUS-минимальность 100/100,
уникальность MUS подтверждена для всех UNSAT-кейсов.

Пример оценки LLM на опубликованном датасете:

**bash**
```bash
uv run python -m logicmus_eval.cli evaluate \
    --strategy direct \
    --model-name openai/qwen2.5-coder-14b-instruct \
    --dataset-dir datasets/v1.0 \
    --limit 20 \
    --output-file evaluation_direct.json
```

**PowerShell**
```powershell
uv run python -m logicmus_eval.cli evaluate `
    --strategy direct `
    --model-name openai/qwen2.5-coder-14b-instruct `
    --dataset-dir datasets/v1.0 `
    --limit 20 `
    --output-file evaluation_direct.json
```

Воспроизведение датасета с нуля описано в разделе
[Генерация датасета](#генерация-датасета); для точного совпадения с v1.0
используйте те же параметры и `--output-dir datasets/v1.0`.

## Структура

```
logicmus_eval/          # основной пакет
    cli.py              # CLI (Typer): generate, evaluate
    run_pipeline.py     # генерация + верификация + манифест
    evaluate_llm.py     # оценка LLM на датасете
    generator.py        # детерминированный генератор SAT/UNSAT пар
    verifier.py         # Z3-оракул + структурная проверка уникальности MUS
    extractor.py        # обёртка над litellm (structured output)
    hashing.py          # SHA-256 датасета, шаблонов и бандла исходников
    storage.py          # FileStorageManager
    templates.py        # шаблоны правил (5 текстовых пакетов + math_pack)
    patterns/           # 7 паттернов (chain, fork, merge, ...)
    evaluation/         # метрики, диагностика, пайплайн, стратегии
    models/             # pydantic-схемы (rules, test_case, manifests, ...)
    sandbox/executor.py # Z3CodeExecutor
scripts/                # экспериментальные скрипты (см. ниже)
tests/                  # unit + integration
datasets/               # опубликованные замороженные датасеты (в git)
data/                   # локальные артефакты генерации (gitignored)
experiments/            # результаты запусков (gitignored)
```

## Установка

```bash
uv sync
```

Требуется Python 3.13+.

## Быстрый старт

### Генерация датасета

**bash**
```bash
uv run python -m logicmus_eval.cli generate \
    --mus-size-min 2 --mus-size-max 5 \
    --pairs-per-group 25 \
    --total-rules 20 \
    --base-seed 42 \
    --output-dir data/generated_cases
```

**PowerShell**
```powershell
uv run python -m logicmus_eval.cli generate `
    --mus-size-min 2 --mus-size-max 5 `
    --pairs-per-group 25 `
    --total-rules 20 `
    --base-seed 42 `
    --output-dir data/generated_cases
```

После `uv sync` также доступен короткий entry point: `uv run logicmus-eval generate ...`.

Сохраняются:

- `data/generated_cases/dataset_v1_frozen.jsonl`
- `data/generated_cases/dataset_v1_frozen.manifest.json`

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--mus-size-min` | `2` | Минимальная кардинальность MUS. |
| `--mus-size-max` | `5` | Максимальная кардинальность MUS. |
| `--pairs-per-group` | `25` | Пар SAT/UNSAT на каждый размер MUS. |
| `--total-rules` | `20` | Общее число правил (core + noise). |
| `--base-seed` | `42` | Базовый seed генератора. |
| `--output-dir` | `data/generated_cases` | Каталог артефактов. |

### Оценка LLM

**bash**
```bash
# Прямой текстовый вывод
uv run python -m logicmus_eval.cli evaluate \
    --strategy direct \
    --model-name openai/qwen2.5-coder-14b-instruct \
    --dataset-dir data/generated_cases \
    --limit 20 \
    --output-file evaluation_direct.json

# Нейросимвольная трансляция в Z3
uv run python -m logicmus_eval.cli evaluate \
    --strategy z3 \
    --model-name openai/qwen2.5-coder-14b-instruct \
    --dataset-dir data/generated_cases \
    --limit 20 \
    --output-file evaluation_z3.json
```

**PowerShell**
```powershell
# Прямой текстовый вывод
uv run python -m logicmus_eval.cli evaluate `
    --strategy direct `
    --model-name openai/qwen2.5-coder-14b-instruct `
    --dataset-dir data/generated_cases `
    --limit 20 `
    --output-file evaluation_direct.json

# Нейросимвольная трансляция в Z3
uv run python -m logicmus_eval.cli evaluate `
    --strategy z3 `
    --model-name openai/qwen2.5-coder-14b-instruct `
    --dataset-dir data/generated_cases `
    --limit 20 `
    --output-file evaluation_z3.json
```

| Флаг | По умолчанию | Описание |
|---|---|---|
| `--strategy` | `direct` | `direct` или `z3`. |
| `--model-name` | `openai/qwen2.5-coder-14b-instruct` | Идентификатор модели для litellm. |
| `--dataset-dir` | `data/generated_cases` | Каталог с датасетом. |
| `--limit` | `10` | Сколько кейсов обработать. |
| `--output-file` | автогенерируется | Имя отчёта (сохраняется в `--dataset-dir`). |

## Эксперименты

Скрипты повторяют дизайн эксперимента из статьи: три серии на трёх моделях
(`Qwen2.5-Coder-14B`, `Gemma-4-E4B`, `GPT-OSS-20B`) и двух стратегиях.

### Smoke-grid

Быстрый прогон на одной модели, 7 конфигураций.

```bash
uv run python scripts/run_smoke_grid.py
```

### Full-grid

Полный прогон трёх серий эксперимента (EXP1: рост шума при $K=3$;
EXP2: рост $K$ при фиксированном $N$; EXP3: стресс-тест) со сменой
моделей на LM Studio.

```bash
uv run python scripts/run_full_grid.py --pairs 10 --context-length 4096
```

Требуется запущенный OpenAI-совместимый endpoint — см. раздел
[Подключение к LLM-серверу](#подключение-к-llm-серверу-для-запуска-оценки).

Скрипт возобновляем: уже существующие отчёты пропускаются.

### Проверка жизненного цикла моделей

Минимальный smoke-тест: загрузка → 1 инференс → выгрузка для каждой модели.

```bash
uv run python scripts/check_model_lifecycle.py
```

### Анализ результатов

**bash**
```bash
# Построить summary.csv и графики для одного запуска
uv run python scripts/analyze_experiments.py experiments/<timestamp>_full_grid

# Сравнить несколько запусков
uv run python scripts/compare_runs.py \
    experiments/run1 experiments/run2 \
    --output experiments/_combined
```

**PowerShell**
```powershell
# Построить summary.csv и графики для одного запуска
uv run python scripts/analyze_experiments.py experiments/<timestamp>_full_grid

# Сравнить несколько запусков
uv run python scripts/compare_runs.py `
    experiments/run1 experiments/run2 `
    --output experiments/_combined
```

## Метрики

| Метрика | Что показывает |
|---|---|
| `sat_accuracy` | Доля кейсов, где `is_sat` совпал с эталоном (по всем ответам, включая отказы и ошибки). |
| `valid_response_accuracy` | Доля верных ответов среди тех, где модель реально рассуждала (без отказов и инфраструктурных ошибок). |
| `mus_exact_match` | Доля UNSAT-кейсов с точным совпадением множества `conflict_core` с эталонным MUS. |
| `mus_precision` / `mus_recall` / `mus_f1` | Усреднённые по UNSAT-кейсам precision/recall/F1 по элементам MUS. |
| `refusal_rate` | Доля кейсов, где модель отказалась рассуждать. |
| `infrastructure_error_rate` | Доля кейсов с инфраструктурными ошибками (JSON parse, Z3 execution error). |
| `total_tokens_consumed` / `total_thinking_tokens` | Расход токенов. |
| `avg_prompt_tokens` / `avg_completion_tokens` / `avg_thinking_tokens` | Средние значения. |
| `total_execution_seconds` / `avg_latency_seconds` | Время работы. |

## Таксономия ошибок

Каждая запись в `details[*]` содержит `failure_tags`:

| Тег | Значение |
|---|---|
| `correct` | Ответ верен, MUS (для UNSAT) совпал. |
| `refusal_no_facts` | Модель заявила, что не может рассуждать. |
| `wrong_sat` | Ошибка в определении SAT/UNSAT. |
| `wrong_mus_missing` | UNSAT распознан, но часть MUS пропущена. |
| `wrong_mus_extra` | UNSAT распознан, но добавлены лишние правила. |
| `exec_error` | Инфраструктурная ошибка (JSON parse, sandbox exec). |
| `unknown` | Не попало ни в одну категорию (включая случаи без ответа и без ошибки исполнителя). |

## Воспроизводимость

Каждый отчёт `evaluation_*.json` содержит блок `run_info`:

| Поле | Описание |
|---|---|
| `model_name` | Идентификатор модели. |
| `strategy` | `direct` или `z3`. |
| `dataset_filename` | Имя датасета. |
| `dataset_sha256` | SHA-256 датасета на момент прогона. |
| `prompt_template_hash` | SHA-256 шаблонов промптов. |
| `git_commit` | Git HEAD на момент прогона (или `null`). |
| `started_at`, `finished_at` | Метки времени (UTC). |
| `limit` | Лимит кейсов. |
| `total_cases_processed` | Обработано кейсов. |

Манифест датасета `dataset_v1_frozen.manifest.json`:

- `artifacts` — SHA-256 датасета и бандла исходников;
- `environment` — версии Python, z3, numpy, scikit-learn;
- `parameters` — MUS-размеры, пары на группу, всего кейсов, правил на кейс, seed;
- `validation_results` — результаты Z3-верификации (SAT/UNSAT/MUS/MUS-minimality);
- `leakage_metrics_global` — TF-IDF F1 (word и char) по всему датасету;
- `leakage_metrics_by_mus_size` — то же по каждому размеру MUS.

## Подключение к LLM-серверу для запуска оценки

Модели подаются через OpenAI-совместимый endpoint (например, LM Studio).

**bash**
```bash
export OPENAI_API_BASE="http://127.0.0.1:1234/v1"
export OPENAI_API_KEY="lm-studio"
```

**PowerShell**
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:1234/v1"
$env:OPENAI_API_KEY  = "lm-studio"
```

Имя модели берётся из `GET $OPENAI_API_BASE/models` и передаётся в
`--model-name` с префиксом `openai/`.

## Ограничения

- Промпты и шаблоны — русскоязычные; `evaluation/refusal_patterns.py`
  содержит legacy-паттерны на английском только для обратной совместимости
  с историческими отчётами.
- Sandbox в `sandbox/executor.py` защищает от случайных ошибок LLM,
  а не от целенаправленных атак.
- Пул предикатов (`templates.py::PREDICATE_POOL`) ограничен, поэтому
  `--total-rules` имеет верхнюю границу.
- Паттерны `coverage`, `idem` и `merge` определены только для фиксированных
  размеров MUS и в текущей версии не масштабируются на произвольное $K$.

## Разработка

```bash
uv run pytest
uv run pytest tests/unit -v
uv run pytest tests/integration -v

uv run ruff check logicmus_eval tests
uv run ruff format logicmus_eval tests
uv run mypy logicmus_eval
uv run pylint logicmus_eval
```
