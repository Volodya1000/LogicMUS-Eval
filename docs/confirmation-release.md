# Версионированный confirmation-выпуск

Актуальный короткий infrastructure-smoke использует отдельный допущенный
development-parent и фиксированную выборку:
[инструкция controlled-v2](development-infrastructure-smoke.md).
Описанный ниже двухсемейный smoke и primary-анализ относятся к историческому
контракту; их не следует применять к `infrastructure-smoke-v1`.
Исторические receipts сохраняются; новая проверка реального HTTP требует
явного происхождения каждой попытки, которого у старых журналов может не быть.

Научный протокол: [`releases/confirmation-v1/protocol.md`](../releases/confirmation-v1/protocol.md).
Выпуск v1 намеренно не разрешает модельный запуск, пока нет допуска наборов,
полных профилей, операторской проверки backend и реального development smoke.
Точный текущий результат сохранен в `releases/confirmation-v1/readiness.json`.
Техническое прохождение набора не означает готовности статьи.

## Состав и проверка после копирования

В Git хранятся планы, три существующих RunConfig, проспективный AnalysisPlan,
протокол, inventory до подготовки, манифест фиксации и компактные результаты.
Большой `bundle/` и все архивы исключены из Git. Полные JSONL, SMT-контроль и все
диагностики, включая неудачные, сохраняются локально. `package.json` перечисляет
локальные архивы, размеры и SHA256; автоматической выгрузки нет.

Скопировать нужно checkout с теми же байтами исходников и зависимостями,
каталог выпуска и отдельно его архивы. Сначала проверить SHA256 архивов по
`package.json`, восстановить source-and-contracts архив в checkout, затем
распаковать архив артефактов в каталог выпуска, сохраняя
`bundle/confirmation/...`, и выполнить:

```powershell
uv sync --frozen --group analysis --group dev
uv run logicmus-eval release-check --release-dir releases/confirmation-v1
```

Код 1 для blocked — ожидаемый содержательный результат, а не разрешение
продолжать. Проверка офлайн: сверяет байты всех файлов, исходники, lock-файл,
версии окружения и повторяет gates PR #5–#7. Отсутствующий bundle блокирует
допуск. `package.json` не хранит архив внутри Git; его отсутствие после клонирования
не заменяется вымышленным свидетельством. При переносе на другое окружение
сначала установить зафиксированные версии. Сохраненные runner identity содержат
абсолютные пути: уже начатый run нужно возобновлять по прежнему пути; перенос
не начатого выпуска возможен до UUID-инициализации. Смена окружения/исходников
после фиксации требует новой версии, не редактирования старого manifest.
Хеш исходников относится к фактическим байтам рабочей копии: в исходном Windows
checkout часть исторических файлов имеет CRLF. Git может нормализовать их в LF.
Поэтому source-and-contracts архив сохраняет точные байты Python-файлов, lock,
pyproject и зафиксированных контрактов; для побайтового воспроизведения нужно
восстановить этот архив, а не принимать несовпадающий хеш после `git clone`.

Архивы остаются локальными: их передачу выполняет оператор. Если доступен только
Git checkout implementation_commit из `source-snapshot.json`, восстановить
точные LF/CRLF по сохраненным SHA256 можно без архива. Для каждого перечисленного
файла допускается только та форма конца строки, которая дает **точное** совпадение
хеша; любое другое расхождение останавливает восстановление:

```powershell
@'
import hashlib, json
from pathlib import Path
receipt = json.loads(Path("releases/confirmation-v1/source-snapshot.json").read_text(encoding="utf-8"))
for name, expected in receipt["files"].items():
    path = Path(name)
    raw = path.read_bytes()
    lf = raw.replace(b"\r\n", b"\n")
    matches = [value for value in (raw, lf, lf.replace(b"\n", b"\r\n")) if hashlib.sha256(value).hexdigest() == expected]
    if not matches:
        raise SystemExit("Source/contract differs beyond line endings: " + name)
    if raw != matches[0]:
        path.write_bytes(matches[0])
print("Exact frozen source and contract bytes restored")
'@ | uv run --no-sync python -
```

Воспроизведение подготовки — только в отдельной копии и новом пустом каталоге,
с точными версиями/байтами исходников из архива и зафиксированным планом:

```powershell
uv run logicmus-eval prepare-experiment --plan releases/confirmation-v1/confirmation.plan.json --output-dir data/reproduction-confirmation-v1
```

Это воспроизведение исходной попытки, не подбор нового допустимого набора.
Сравнить хеши каждого JSONL и reference с `preparation.json`; исходный провал
сохраняет свой статус. Не перезаписывать исходный `bundle/confirmation`.

## Проверка backend и новая версия

`model-facts.json` отличает исторические сведения репозитория, ввод оператора,
наблюдения и неизвестное. LM Studio и контекст 4096 — исторические настройки,
не проверенное состояние текущего сервера. Оператор должен записать для каждой
из трех моделей фактический HTTP model ID, ревизию или точный файл/его хеш,
квантование, активный контекст, backend/version, шаблон чата и tokenizer.
Для HTTP-профиля нельзя механически переносить служебный префикс LiteLLM.

Поскольку v1 фиксирует null в обязательных характеристиках, заполнение профилей
создает **новую версию выпуска**. Сохранить v1, скопировать планы и неизменные
наборы в новый release root, обновить release_id/профили и обоснование, создать
новый manifest через `release-freeze` и новый receipt через
`release-seal-preparation`. Повторная генерация неизменных семейств не нужна.
При изменении исходников использовать их новую зафиксированную версию и явно
описать происхождение ранее подготовленного набора; проверка не пропустит
несовпадающий source hash. Не обходить это ручным исправлением checksum.

До confirmation HTTP зафиксировать калибровку бюджета/timeout по правилу из
протокола. Если 2048/120 не подходят на development, сначала оформить новую
версию; по неудачным confirmation-ответам повышать их нельзя.

`backend.evidence.json` — объект с ключами `qwen`, `gemma`, `gpt-oss`.
Каждое значение соответствует `BackendEvidence` из
`logicmus_eval/confirmation/models.py`: SHA256 конкретного RunConfig,
checked_by/checked_at/method, относительные пути к проверенным файлам и их
SHA256, `requests_sha256` из существующего offline preflight, максимальное число
входных токенов с учетом чата/schema, обе явные операторские проверки и путь
к полному development-калибровочному run. Сохранять вывод backend/model/version,
конфигурацию загрузки без секретов и результаты tokenizer-проверки. Серверу
не требуется echo всех параметров: сохраненный запрос, операторская проверка
backend и наблюдаемые поля ответа остаются разными видами свидетельств.
Проверка этих файлов офлайн не доказывает истинность операторской аттестации.

## Короткий реальный development smoke — в этом PR не выполнялся

Команды ниже разрешены **только оператору после подготовки и проверки backend**.
Они используют новый controlled-runner и его HTTP-адаптер, а не исторические
`run_smoke_grid.py`/`run_full_grid.py`. Не использовать smoke для отбора моделей
по точности. Все неверные рассуждения, отказы, неправильные MUS и ошибки
сохраняются в журнале и анализе.

Фиксированный development plan: even seeds 424242/424244, по одной паре,
chain/math K=4 N=8/48. Это четыре ячейки, 16 случаев, 96 плановых запросов
на три модели/обе стратегии (до retries). N48 — стресс по длине, а не новая
confirmation-ячейка. Оператор actual-tokenizer должен подтвердить, что он
покрывает максимальный confirmation-вход каждого model/strategy, включая
schema/chat overhead; длины в символах недостаточно.

```powershell
# $r должен указывать на новую версию с полными профилями.
$r = 'releases/confirmation-v2'
uv run logicmus-eval prepare-experiment --plan "$r/development.smoke.plan.json" --output-dir "$r/bundle/development-smoke"
```

При недопуске development-набора остановиться, сохранить диагностику, не
ослаблять порог и не перебирать seeds. Минимальное число семей в smoke служит
проверке инфраструктуры, не оцениванию качества или научному обоснованию выборки.

Создать smoke-конфигурации копированием каждого уже зафиксированного RunConfig;
единственное изменение — `series_manifest` на development-smoke, затем сохранить
производные файлы, их хеши и условия. Не менять generation/timeout/profile/model.
Пути `series_manifest` разрешаются относительно файла RunConfig.

```powershell
@'
import json, sys
from pathlib import Path
r = Path(sys.argv[1])
for name in ("qwen", "gemma", "gpt-oss"):
    config = json.loads((r / (name + ".run.json")).read_text(encoding="utf-8"))
    config["series_manifest"] = "development-smoke/series.manifest.json"
    path = r / "bundle" / (name + ".smoke.run.json")
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
'@ | uv run --no-sync python - $r
```

Для каждого `qwen`, `gemma`, `gpt-oss` (нужная модель должна быть загружена оператором):

```powershell
uv run logicmus-eval experiment-preflight --config "$r/bundle/qwen.smoke.run.json"
# Единственная следующая команда начинает реальные HTTP-запросы smoke:
uv run logicmus-eval experiment-start --config "$r/bundle/qwen.smoke.run.json" --run-dir "$r/bundle/smoke/qwen"
Copy-Item -LiteralPath "$r/bundle/smoke/qwen/report.json" -Destination "$r/bundle/smoke/qwen/report.before-resume.json"
uv run logicmus-eval experiment-resume --run-dir "$r/bundle/smoke/qwen"
Copy-Item -LiteralPath "$r/bundle/smoke/qwen/report.json" -Destination "$r/bundle/smoke/qwen/report.after-resume.json"
uv run logicmus-eval experiment-preflight --run-dir "$r/bundle/smoke/qwen"
```

Повторить тот же блок для двух остальных имен. Успешный no-op resume должен
сохранить полный отчет и не добавить HTTP-попыток. Сравнить journal head/event
count и оба checkpoint-отчета. Если произошел обрыв незавершенной HTTP-попытки,
сохранить историю/неизвестную стоимость; явно разрешенный retry через существующий
`--indeterminate-policy retry` создает новую попытку. Обычный resume остается halt.

Для каждого smoke UUID сохранить обычный development `AnalysisPlan`: одна группа
с этим UUID, все ячейки/обе стратегии, primary MUS Exact Match, дополнительные
MUS F1/SAT accuracy/coverage, seed=20261128, pointwise Wilson/family bootstrap.
После этого выполнить существующий анализ:

UUID можно прочитать из `bundle/smoke/<name>/run.manifest.json` поля payload.run_id.
Полный минимальный план для одного smoke (выполнить после создания его run):

```powershell
@'
import json, sys
from pathlib import Path
r = Path(sys.argv[1])
for name in ("qwen", "gemma", "gpt-oss"):
    saved = json.loads((r / "bundle" / "smoke" / name / "run.manifest.json").read_text(encoding="utf-8"))
    plan = {
        "analysis_version": "controlled-analysis-v1", "purpose": "development", "mode": "primary",
        "groups": [{"name": "smoke", "run_ids": [saved["payload"]["run_id"]]}],
        "primary_metric": "mus_exact_match", "additional_metrics": ["mus_f1", "sat_accuracy", "coverage"],
        "contrasts": [], "intervals": {"seed": 20261128, "repeats": 10000, "level": 0.95, "min_families": 2},
    }
    (r / "bundle" / (name + ".smoke.analysis.json")).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8", newline="\n")
'@ | uv run --no-sync python - $r
```

```powershell
uv run logicmus-eval analyze-controlled --run "$r/bundle/smoke/qwen" --plan "$r/bundle/qwen.smoke.analysis.json" --output "$r/bundle/smoke-analysis/qwen"
```

Сохранить `smoke.evidence.json`, ключи — все три logical run. Каждая запись
соответствует `SmokeEvidence`: run_dir, явная `attested_real_http: true` оператора,
checked_by/checked_at, пути к обоим checkpoint-отчетам внутри run, analysis_dir,
longest_input_accounting и artifacts с SHA256. У longest-input JSON обязательны
`confirmation_requests_sha256`, `smoke_requests_sha256`,
`confirmation_max_input_tokens`, `smoke_max_input_tokens`. Последнее число должно
быть не меньше первого; tokenizer и способ подсчета документируются оператором
в файлах evidence. Хешировать checkpoint-отчеты, accounting, сам analysis manifest
и backend-условия. Проверка требует реальных HTTP envelopes, полный run,
controlled primary analysis с хешами входного журнала и все его артефакты.
Mock-тесты этого PR не являются свидетельством реального smoke.

## Допуск → инициализация → основной запуск → resume → анализ

```powershell
uv run logicmus-eval release-check --release-dir $r
# При всех входных допусках до UUID-привязки общий статус еще blocked.
# Проверить ready_for_initialization=passed, затем:
uv run logicmus-eval release-initialize --release-dir $r
uv run logicmus-eval release-check --release-dir $r
```

Инициализация офлайн: сохраняет три UUID и пустые журналы, держит блокировки
всех запусков при привязке, пишет bound AnalysisPlan и фиксирует admission.
Повторная инициализация запрещена; частичный неудачный результат сохраняется
для диагностики. Научные поля менять при привязке нельзя.

После ready_for_scale=passed оператор по очереди загружает каждую выбранную
модель с проверенными условиями и выполняет:

```powershell
uv run logicmus-eval release-resume --release-dir $r --logical-run qwen
uv run logicmus-eval release-resume --release-dir $r --logical-run gemma
uv run logicmus-eval release-resume --release-dir $r --logical-run gpt-oss
```

Та же команда возобновляет run, пропуская finalized jobs. При неопределенной
попытке сначала проверить журнал, затем, если оператор действительно разрешает
повтор с возможной повторной стоимостью:

```powershell
uv run logicmus-eval release-resume --release-dir $r --logical-run qwen --indeterminate-policy retry
```

После завершения всех трех запусков:

```powershell
uv run logicmus-eval analyze-controlled --run "$r/bundle/runs" --plan "$r/bundle/binding/analysis.bound.json" --output "$r/bundle/confirmation-analysis"
```

Для confirmation пользоваться release-командами: общий `experiment-start`
сохраняет прежний контракт PR #6 и сам по себе не означает допуска выпуска.
Ни одна команда этого документа не публикует GitHub Release/tag или архив.
