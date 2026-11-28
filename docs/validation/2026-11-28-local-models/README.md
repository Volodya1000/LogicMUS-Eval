# Проверка локальных моделей: smoke заблокирован до generation

На 28 ноября 2026 года фактический результат для всех трёх моделей — **blocked / real_smoke=not_verified**. Запланировано 48 задач, выполнено **0 HTTP generation-попыток**, завершено 0. Причины сохранены до первого запроса; выборка, критерии допуска, timeout и бюджеты не менялись.

Наблюдения выполнены Codex автоматически, без подписи человека. `operator_checked` и `user_supplied` в профилях пусты; неподтверждённые факты перечислены в `unknown`. Идентификаторы в инвентаре означают установленную/экспонируемую модель; фактически загруженная instance обнаружена только у Qwen.

## База, admission и ограничения

- Исходная рабочая копия была чистой, HEAD совпадал с проверенной головой PR #9 `40a36468042f3b7af74dbecbb7a3ef9647e568b4`.
- Через GitHub подтверждён merge PR #9; ветка `codex/verify-local-models-and-live-smoke` создана от `origin/master` / `8dc9f27d8acbf19194f7eacc7111de432d8cc819`.
- Сохранённый parent bundle найден. Повторно выполнены существующие `load_admitted_cases`, `validate_selection` и preflight: все обязательные admission-свидетельства полного parent и хеши файлов проверены. Это повторная проверка сохранённого допуска и исходных артефактов, а не новый запуск SMT/leakage-аудита и не новая подготовка parent.
- Parent: controlled-v2, development, 2 048 случаев, четыре ячейки chain/math K=4, N=8/48; frozen seeds `[424242,424244]`, 128 пар/seed. Порог leakage остаётся 0.55.
- `protocol.freeze.json` и его привязки к байтам plan/rule проверены, исторический preparation receipt и все перечисленные в нём артефакты сверены. Parent SHA256 `a1cc6e25e9f17b36c13ba37c8bd856b61b7b9d570a5573126907102148221f04`; selection SHA256 `6f496bff7b3a21ea12a38691d889ec63e0dcc222d1eab8735475ac30a95da53f`.
- Ровно восемь фиксированных случаев, обе стратегии direct/z3, 16 jobs/model. `max_attempts=1`, пустой список transient retries; в каждом точном request transport: `automatic_retries=0`, redirects/proxies отключены. Indeterminate policy не менялась с `halt`.
- Confirmation-v1, исторические receipts, статья, production-код, генератор, метрики и статистические методы не изменены. Новая confirmation-подготовка не выполнялась.

## Фактические файлы и backend

| Модель / exposed ID | Локальные веса | Квантование | Активный контекст | Planned / attempted / finalized |
| --- | --- | --- | --- | --- |
| Qwen / `qwen2.5-coder-14b-instruct` | Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf | Q4_K_M | 12 288, SDK и API | 16 / 0 / 0 |
| Gemma / `google/gemma-4-e4b` | gemma-4-E4B-it-Q4_K_M.gguf | Q4_K_M | unknown: instance не загружена | 16 / 0 / 0 |
| GPT-OSS / `openai/gpt-oss-20b` | gpt-oss-20b-MXFP4.gguf | MXFP4 | unknown: instance не загружена | 16 / 0 / 0 |

Веса находятся в `D:/lmstudiomodels/lmstudio-community/`. Полные пути, размеры и SHA256 сохранены в отдельных `*.profile.json`; metadata непосредственно прочитаны из заголовков этих GGUF, включая tokenizer, словарь/merges и их хеши. Revision весов не устанавливалась по имени: идентичность привязана к файлу и SHA256.

| Веса | SHA256 |
| --- | --- |
| Qwen | `ec8991dc0de5af1c40498adb827192971c4169e9f5ac785f9bde23137e2384e2` |
| Gemma | `3f72a20a06f626c78e6c475ae07a64c88b2663149c0f6197b56bf7cf1f37585c` |
| GPT-OSS | `65d06d31a3977d553cb3af137b5c26b5f1e9297a6aaa29ae7caa98788cde53ab` |

Наблюдаемая версия приложения — LM Studio `0.4.13+1`, CLI commit `0b2a176`. В списке runtime выбран `llama.cpp-win-x86_64-nvidia-cuda12-avx2@2.83.0`; сохранены его manifest и хеши файлов. Это свидетельство выбранного установленного runtime, не независимое подтверждение конкретной запущенной реализации/её upstream commit. Qwen expected profile содержит именно описание выбранного runtime; runner сам трактует expected profile как утверждение, не server echo.

Для Qwen SDK также наблюдал GPU ratio 1.0, flash attention=true; API — eval batch 512, parallel=1. Установленные Gemma и GPT-OSS имеют объявленный maximum context 131 072; это не активный контекст. Настройка приложения default context=4 096 также не подменяет активное значение.

У Gemma Hub `model.yaml` содержит собственный prompt-template override. Поэтому сохранённый embedded GGUF template явно не считается её подтверждённым активным шаблоном. Исходные Hub manifest/model.yaml обеих моделей сохранены без потери байтов как UTF-8 строки с SHA256 в `*.hub-definition.json`; embedded templates находятся в `*.gguf-metadata.json`. Сохранён отдельный SHA256 companion vision adapter Gemma; картинок в запросах нет. Hub revision — revision определения Hub, не revision весов.

Запрошенные параметры во всех трёх отдельных operator RunConfig оставлены как в подготовленном smoke: `max_tokens=2048`, `temperature=0.0`, `top_p=1.0`, `seed=null`, `reasoning_effort=null`, request timeout=120 s, Z3 timeout=5 s. Неподтверждённые поля профиля оставлены null. Эти configs ещё не получили generation-допуск.

Объявленные Hub defaults: Gemma temperature=1.0, top_p=0.95, top_k=64, reasoning default=`on`; GPT-OSS temperature=0.8, top_p=0.8, top_k=40, repeat penalty=1.1, min_p=0.05, reasoning default=`low`. Это установленные определения, не подтверждение их эффективного применения к HTTP. Qwen effective omitted defaults, а также эффективные неуказанные sampling/seed/template параметры всех моделей остаются unknown. Запрошенные temperature/top_p не заменены Hub defaults.

## Подсчёт входа и blockers

Сохранены **все точные requests**, включая response schema и transport, для каждого model/strategy: target — полный parent без `infrastructure_smoke` (4 096), smoke — фиксированная выборка (16). На запросах рассчитан существующий `digest(job.request)`; inventory hashes взяты из production preflight. Совпадающие target/smoke requests сверяются по digest.

Для уже загруженной Qwen через штатный LM Studio SDK 1.5.0 выполнены только `list_loaded`, получение metadata/load config, `apply_prompt_template` и `tokenize`; loading/prediction API не вызывались. Подсчитаны все 4 096 chat-template входов, включая 16 smoke-запросов.

| Qwen, только SDK chat-template режим | Target max | Smoke max | Покрытие этого режима |
| --- | --- | --- | --- |
| direct | 2 444 | 2 302 | меньше на 142 |
| z3 | 3 791 | 3 672 | меньше на 119 |

Это **не точный InfrastructureInputAccounting HTTP-запросов**. SDK utility не принимает `response_format`; доказательство того, какой вклад JSON Schema вносит в фактический HTTP prompt установленной версии backend, отсутствует. [Документация tokenization](https://lmstudio.ai/docs/python/tokenization) описывает template→tokenize, а [документация structured output](https://lmstudio.ai/docs/developer/openai-compat/structured-output) описывает grammar sampling для GGUF; из этого здесь не сделан вывод о нулевом schema overhead конкретной запущенной реализации.

Qwen заблокирована по отсутствию точного полного accounting и подтверждения defaults/runtime. Дополнительно, измеренный template-only режим не покрывает максимум parent, поэтому его нельзя использовать как свидетельство допуска. Даже если предположить нулевой schema overhead, фиксированная выборка не прошла бы требование покрытия в этом режиме. Значение `3791+2048=5839 < 12288` относится только к нему и не объявляется прохождением полного context gate.

Gemma и GPT-OSS дополнительно заблокированы до проверки реальной загруженной instance, контекста и tokenizer/template. В приложении `unloadPreviousJITModelOnLoad=true`, а Qwen уже занимает backend; автоматически загружать другие модели с возможным вытеснением Qwen не стали. Нужны согласованное оператором окно и безопасная загрузка без прерывания чужой работы. Модели не отсутствуют на диске и не заменены другими.

**InfrastructureInputAccounting не создан:** его значения означали бы неподтверждённые точные измерения. Отдельные `qwen.template-only-*` явно маркированы как диагностика. Выборка, accounting schema и проверяющий код ради допуска не менялись.

## Сохранённые run и проверяющий слой

| Модель | Run UUID |
| --- | --- |
| Qwen | `1e3a90f5-6210-44a2-82a7-bf1c4107a465` |
| Gemma | `61aa55d2-ba63-4661-b2e8-a5835affa454` |
| GPT-OSS | `deb13903-ed63-4dac-ae2a-d4744cc04f28` |

Каждый run создан существующим `experiment-initialize` без HTTP; production `read_snapshot` проверил manifest/report/journal и происхождение. В каждом ровно 16 pending jobs, ноль attempts/outcomes/events; journal head равен исходной manifest identity. Сохранены начальные manifest/report копии, snapshot receipts, UUID и file hashes.

`experiment-resume` не вызывался: run с pending jobs отправил бы generation-запросы при закрытом допуске. Поэтому completed no-op resume, before/after checkpoints, latency, usage, finish_reason, SAT/MUS quality, отказы, JSON/Z3 failures и truncation не измерены. Пустые outcomes не трактуются как отсутствие ошибок модели или успешное покрытие.

В существующий diagnostic AnalysisPlan template подставлены соответствующие UUID; plans провалидированы и сохранены. Анализ пустых runs не выполнялся, завершённого diagnostic analysis/его hashes нет. Primary quality analysis не выполнялся.

`check-development-smoke` вызван отдельно для каждой модели. Все три команды вернули exit=1 и `real_smoke=not_verified`, потому что реального SmokeEvidence нет. Это отрицательная проверка отсутствия evidence, не полная проверка завершённого smoke. Файлы `*.checker.json` сохраняют команды, время и исходные сообщения. SmokeEvidence с обязательным `attested_real_http=true` не изготовлялся для нулевого числа HTTP-попыток; человек не указан как проверявший.

## Где лежат свидетельства

Evidence root: `configs/development-smoke-v2`.

- Версионируемые наблюдения, operator configs, inventory/snapshot receipts, plans и checker outputs: [`local-2026-11-28`](../../../configs/development-smoke-v2/local-2026-11-28/).
- Сохранённый полный parent: `bundle/parent/`; фиксированный selection: `selection.json`.
- Полные target/smoke request JSONL, все Qwen template-only measurements и run directories с SQLite journals: `bundle/local-2026-11-28/` (локально, ignored).
- Точные commands/methods capture сохранены как `capture-observations.py.txt` и `finalize-blocked.py.txt`; environment содержит версии исходной .venv и отдельного SDK target, хеши lockfile/исходников. SDK установлен отдельно в ignored `experiments/live-smoke-tools`; зависимости проекта не менялись.
- `artifact-index.json` хеширует наблюдения и raw артефакты, кроме самого индекса. Вложенные пути относятся к evidence root, без `..`.

Raw parent и полные запросы **не входят в PR**. Его compact receipts не заменяют эти файлы. На этой машине root содержит parent, selection и все initialized run; отсутствие completed checkpoints/accounting/analysis явно сохранено. Никакие архивы, Release или tag не опубликованы. Автоматический повтор capture нельзя использовать для восстановления этих runs: он требует новых output paths и не выполняет generation.

Manifest/identity сохраняют исходные абсолютные Windows paths. Относительные пути в artifact index позволяют найти файлы внутри evidence root, но сами runs привязаны к исходному расположению checkout: перенос raw файлов в другой каталог не делает их автоматически совместимыми с resume. Compact PR не является переносимым исполняемым smoke bundle.

## Проверки и дальнейшие действия

Офлайн-регрессии infrastructure smoke, controlled runner, transport и confirmation evidence: 84 passed. Затем полный pytest через штатный pre-commit hook прошёл; отдельно collection подтверждает 498 тестов. Hooks и финальные проверки/hashes записаны в `verification.json`. Production-код не менялся; отдельного исправления и повторного live цикла нет.

Диапазон времени большого прогона не рассчитан: ни одной измеренной generation latency нет, поэтому development-smoke экстраполяция невозможна. Время hashing/tokenizer utilities не является временем инференса.

Перед разрешённым реальным smoke нужны доказуемый full HTTP tokenizer/schema accounting, подтверждение effective profiles/defaults и безопасное операторское управление загрузкой. Если полный точный accounting подтвердит недостаточное покрытие фиксированной выборки, текущий протокол остаётся blocked; изменение выборки требует отдельного решения и новой фиксации, а не подбора в этом задании. Осталось 48 неиспользованных разрешённых попыток; они здесь не запускаются автоматически.

Этот результат касается только указанного development parent. Он не подтверждает покрытие ещё не созданного confirmation-v2. Следующий этап confirmation-v2 на controlled-v2 возможен отдельно после успешной проверки инфраструктуры, с собственной фиксацией, полной офлайн-подготовкой и допуском.
