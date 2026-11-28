# LM Studio: development infrastructure-smoke v2

База: master после PR11 (`a327cc5f58973ce3123e806dec6990f4444999822e3795d8e957497adb812d95` — отдельный source hash исполнявшегося кода; Git-база `e139d67`).

Выполнено **10 диагностических + 66 smoke = 76/96 реальных generation-попыток**. Confirmation generation: **0**. Automatic retries: **0**. Новая выборка: **11** development-случаев, обе стратегии, по 22 запроса на модель. `ready_for_scale = blocked`.

| Модель | Загружена / context | Full accounting | Parent / confirmation coverage | Diag / smoke attempted | HTTP completed / finalized | Ошибки smoke | Обрезания | HTTP / runner время | real_smoke |
|---|---|---|---|---:|---:|---|---:|---|---|
| qwen | да / 12288 | verified, scoped | passed / passed | 4 / 22 | 22 / 22 | z3_contract_error: 1 | 0 | 515.0 / 535.1 s | passed |
| gemma | да / 32768 | verified, scoped | passed / passed | 2 / 22 | 22 / 22 | exec_error: 2, generation_truncated: 1 | 1 | 673.1 / 694.3 s | not_verified |
| gpt-oss | да / 32768 | verified, scoped | passed / passed | 4 / 22 | 22 / 22 | z3_contract_error: 6, exec_error: 2 | 0 | 703.1 / 721.7 s | passed |

HTTP completed означает полученный HTTP 200; finalized — сохранённый outcome, включая ошибки и обрезания. Ошибки JSON/Z3 и неверные логические ответы сохранены как outcomes; запросы из-за них не повторялись. Scope результатов — infrastructure-only. Научный primary-анализ этой подвыборки не выполнялся. Диагностика отделена в `diagnostic-results.json` и не служит доказательством smoke. Все отказы, исходные HTTP bodies, usage, finish_reason и время сохранены локально.

**Технические blockers реального допуска:** gemma: Smoke transport/context/budget failure retained in outcomes; обрезаний 1. Для этих запусков real SmokeEvidence не создан. Бюджеты после ошибок не менялись; новые runs и повторы не выполнялись. Полный повтор одной модели требует 22 попытки; осталось 18 smoke и 20 общих, поэтому полный новый smoke-run в текущий лимит не помещается.

Конкретный blocker Gemma: `z3`, case_uid `3546f1d67e3e750565a7c717242de1722a21b48519010b1eb38d0a6177f0efce`, HTTP 200, `finish_reason=length`, 4096/4096 output tokens за 69.6 s. Вход 3316 + output reserve 4096 = 7412 < context 32768; timeout 360 s не достигнут. Это output-budget failure при прошедшем input/context gate. Детали: `gemma.budget-blocker.json`.

## Два независимых покрытия

| Модель | Стратегия | Исторические 8, max | Full parent / новый smoke max | Confirmation max | Context / output cap |
|---|---|---:|---:|---:|---:|
| qwen | direct | 2302 | 2444 / 2444 | 1833 | 12288 / 2048 |
| qwen | z3 | 3672 | 3791 / 3791 | 2824 | 12288 / 2048 |
| gemma | direct | 2008 | 2127 / 2127 | 1584 | 32768 / 4096 |
| gemma | z3 | 3207 | 3322 / 3322 | 2463 | 32768 / 4096 |
| gpt-oss | direct | 1932 | 2059 / 2059 | 1549 | 32768 / 8192 |
| gpt-oss | z3 | 3045 | 3160 / 3160 | 2376 | 32768 / 8192 |

Все 58 368 будущих запросов независимо сверены offline с сохранёнными UID/request digest и длинами при новых предполагаемых development-условиях. Исходные confirmation proposed configs и данные не менялись. Confirmation-покрытие проверено отдельно от parent-покрытия; оно не является допуском release и не проверяет будущую длину reasoning/output.

## Метод и фактические условия

Проверены точные файлы Q4_K_M (Qwen/Gemma) и MXFP4 (GPT-OSS), свежие SHA256, загруженные instance, контекст, runtime DLL, raw effective base/session config и реально применённый template. Запрошены temperature=0.0, top_p=1.0, seed не фиксирован. Qwen: output=2048, timeout=180s; Gemma: reasoning_effort=none, output=4096, timeout=360s; GPT-OSS: reasoning_effort=low, output=8192, timeout=600s. Эти условия зафиксированы до confirmation tokenization и smoke. GPU: Qwen/Gemma full offload; GPT-OSS ratio=0.75, CPU threads=10; parallel=1. Наблюдения, явные настройки, реализация и неизвестные поля разделены в profiles/base configs/method receipt. Человек не указан как проверявший.

Полный input accounting установлен для exact installed LM Studio 0.4.13+1 / llama.cpp CUDA12 2.83.0: inspected HTTP schema → sampler grammar path; native formatPrompt с raw base/session и HTTP/reasoning overrides; точный tokenizer из того же llama.dll, add_special=true, parse_special=true. Native vocabulary-only ABI и передача флагов подтверждены disassembly. SDK template-only не использован как полный подсчёт. У Gemma диагностика показала 673 SDK-токена против 670 HTTP; полный путь учитывает thinking/template/BOS, а не поправку по нескольким примерам. Метод ограничен сохранёнными single-user text-only запросами, двумя schemas, backend/model/template/config и датой 2026-11-28. GPT-OSS включает динамическую дату в system prompt. Покрытие confirmation здесь условно той же датой и сохранёнными conditions; для многосуточного release clock/template ещё не зафиксированы. Перенос этих exact counts на другую дату требует отдельной проверки или проспективной фиксации даты в шаблоне. Это дополнительный blocker готовности многодневного запуска.

Штатные [model IO logs](https://lmstudio.ai/docs/cli/serve/log-stream) использованы для дополнительной проверки. Совпадения побайтного SHA256 emitted prompt с offline native-formatting inventory: 66/66; совпадения HTTP usage.prompt_tokens с полным accounting: 66/66. Данные проверены для каждой модели, включая blocked runs; детали в final-validation.json. Это проверка выполненных запросов; основание общего метода — сохранённая реализация и native path.

V2 независимо воспроизводит выбор из full admitted parent: исторический v1 receipt закреплён отдельным base_selection pin, затем максимум каждой из шести model/strategy групп, lexical case_uid tie-break и dedup. Ответы не участвуют в выборе. Три дополнительных UID дают 11 случаев. V1 receipt/hash, восемь случаев и отрицательные PR10 результаты сохранены.

## Журнал, resume и проверки

Для каждого из трёх новых UUID выполнены production HTTP-adapter и журнал, completed no-op resume с нулём новых HTTP-попыток и неизменными report/journal/outcomes, production diagnostic analysis и отдельный check-development-smoke. Real SmokeEvidence записаны только после успешной проверки. Audit hook резервирует попытку в общем fsync-журнале до оригинального urllib POST; retries отключены, indeterminate policy=halt. Guard-тесты проверили 13-ю diagnostic, 85-ю smoke, 97-ю общую попытку и обход через новый run без сети.

Полные проектные hooks прошли: ruff/format, strict mypy, pylint и pytest; 549 тестов. Регрессии сохраняют old v1, full-parent admission и отказы для tokenizer/length/request/selection/base tampering, alternate seed/pair, недостаточного покрытия, mocks и пустого журнала. Начальная uv sync попытка упёрлась в неработающий proxy до hooks; штатные проверки выполнены в существующем окружении с UV_NO_SYNC и UV_OFFLINE. Код/зависимости ради обхода не менялись.

При позднем commit-hook прогоне один существующий Windows-тест `test_large_request_cannot_block_deadline_when_worker_never_reads` завершился `subprocess.TimeoutExpired` во время повторного cleanup communicate(timeout=1.0): 548 passed, 1 failed. Изолированный повтор прошёл (1/1), весь sandbox-файл также прошёл (41/41, 38.03s). Код sandbox, тест и timeout не менялись; исправленным этот intermittent teardown-сбой не объявляется. Он сохранён в `post-smoke-test-anomaly.json`; завершающая полная проверка выполняется обычным commit hook без skip.

## Время большого прогона и retries

Для 9 728 случаев × 3 модели × 2 стратегии = **58 368 запросов** линейная оценка по средним **реальным HTTP latency smoke**: **19.36 суток** без retries. Масштабирование полного runner wall time: **19.97 суток**. Сценарий медианных latency: 21.59 суток; сценарий самого медленного наблюдения каждой группы: 33.80 суток. Это сценарии, не доверительные интервалы и не гарантированные границы.

Допущения: та же RTX 3060/128GB машина, последовательное исполнение, те же модели/offload/reasoning/budgets и распределение длины ответов; модели загружаются группами, отдельная инфраструктурная выборка преднамеренно включает длинные входы. Будущие топологии, output/reasoning, фоновые нагрузки, длительные отказы и thermal effects могут изменить время. Offline tokenizer elapsed time в оценку генерации не входит.

Ни одного retry в пилоте не было. Ниже — только расчёт при гипотетическом max_attempts=3 и backoff 2/4s из proposed candidate. p — неизвестная вероятность retryable ошибки на попытке; независимость и одинаковая стоимость попыток — отдельные допущения. Если ошибки расходуют полный timeout, простой множитель попыток существенно недооценивает время.

| p | E[attempts], 1+p+p² | Равная стоимость попыток, суток | Из них backoff, часов | Ошибки занимают полный model timeout, суток |
|---:|---:|---:|---:|---:|
| 0% | 1.0000 | 19.36 | 0.00 | 19.36 |
| 5% | 1.0525 | 20.45 | 1.78 | 32.94 |
| 10% | 1.1100 | 21.65 | 3.89 | 48.00 |
| 25% | 1.3125 | 25.91 | 12.16 | 103.80 |

**Ограничение оценки времени:** обрезанные ответы измеряют ограниченные попытки при текущих caps. Время полностью завершённых ответов при ещё не откалиброванных достаточных бюджетах для заблокированных моделей неизвестно. Эти цифры не являются оценкой длительности успешно допущенного большого прогона. Runner-wall сценарий также линейно масштабирует разовый preflight пилота; в крупных batches эта часть амортизируется иначе.

## Provenance и оставшиеся ограничения

До production-правок сохранён exact source bundle кандидата `9434b557…`; дополнительно восстановлены и проверены все 130 repository_inputs исходного candidate receipt. Новый исполнявшийся source `a327cc5f…` сохранён отдельным архивом. Ни один исторический receipt/source hash не переписан. Saved-data admission/artifact revalidation новым кодом явно отделена от равенства preparation sources.

Отдельно сохранены точные байты всех 87 исторических компактных artifacts/receipts. У 6 файлов их исторические рабочие CRLF-байты отличаются от Git LF-представления только переводами строк; hashes не переписаны. `historical-byte-identity.json` фиксирует оба SHA256, локальный архив сохраняет оригиналы. Для новых `verified-local/**` атрибут `-text` сохраняет зафиксированные bytes в Git; это не нормализация старых receipts.

**Точные байты исторического development-parent source `595ec63f…` не восстановлены.** Receipt описывает intermediate working tree. Проверены локальные snapshots/archives, Git reflogs/unreachable objects и 2 889 ограниченных реконструкций; совпадения нет. Сохранены исходный hash и точный пробел provenance. Candidate archive не выдан за parent archive. Этот пункт первоначального запроса остаётся технически невыполненным.

Все подготовленные candidate/raw files и исторические компактные evidence сверены по исходным hash. Статья, данные, seeds и научные методы не изменены; parent и основной confirmation-набор заново не готовились. Новые generation были только development. Большие requests, ответы, SQLite journals, analyses, tokenizer inventories, native proofs и source archives остаются в ignored bundle/verified-local. Git содержит компактные configs, методику, receipts, summaries и hashes; Release/tag/archive upload отсутствуют.

**ready_for_scale = blocked.** Финальный executable release, проверяемый candidate handoff и отдельный admission ещё не выполнены. Старые candidate gates остаются историческими записями; новый standalone infrastructure smoke их не переписывает. Компактный PR требует локальных raw artifacts и сохранённых абсолютных путей; он не является переносимым исполняемым release.

Ключевые файлы: `smoke.execution.freeze.json`, `selection.v2.json`, `measurements.manifest.json`, `coverage.json`, `confirmation-coverage.verification.json`, `full-http-input-method-verification.json`, `native-tokenizer-verification.json`, `final-validation.json`, `scale-estimate.json`, `*.evidence.json`, `*.checker.json`, `artifact-index.json`.
