# Remediation roadmap

Baseline аудита: `a33632bc092ede70f7d6e6c4a819dd65b055bf1d`.

Цель — исправлять проект маленькими проверяемыми PR, не смешивая безопасность, браузерную логику, архитектуру и визуальные изменения.

## Правила выполнения

1. Один PR — одна проверяемая причина изменения.
2. Сначала защита от ложной отправки и утечки данных, потом новые функции.
3. Любая отправка должна иметь три состояния: `confirmed`, `rejected`, `unverified`.
4. `unverified` никогда не считается успехом и останавливает автоматизацию.
5. Нельзя исправлять селектор без fixture/снимка реального состояния.
6. Формулы меняются только вместе с реестром формул и golden tests.
7. UI не должен самостоятельно принимать решение о статусе очереди.
8. Каждая миграция базы начинается с backup и имеет тест старой схемы.
9. До появления CI merge выполняется только после локального полного теста.
10. Реальные `saved_pages`, базы, логи и цели не входят в PR.

## Этап 0. Немедленная защита репозитория

### PR 4 — `SECURITY-LOCAL-ARTIFACTS-GATE`

Состав:

- добавить в `.gitignore`:
  - `saved_pages/`;
  - локальные экспорты;
  - диагностические архивы;
- удалить `saved_pages` из индекса;
- заменить `targets_seed.json` демонстрационными данными;
- изменить `push_to_github.bat`, чтобы он прекращал работу при чувствительных путях;
- добавить явный preview перед commit;
- добавить `docs/security/local-data-policy.md`.

Не включать:

- переписывание истории Git;
- изменения браузерной логики.

Критерии:

- новый снимок не отображается в `git status`;
- `push_to_github.bat` не может случайно добавить снимок;
- приложение продолжает использовать локальную SQLite.

### Отдельная административная операция — очистка истории

После PR 4 принять решение:

- оставить старые снимки в истории, если репозиторий будет приватным и риск принят;
- либо переписать историю `git filter-repo`, force-push и заново клонировать локальную папку.

Это не следует смешивать с обычным кодовым PR.

## Этап 1. Целостность отправки

### PR 5 — `RAID-VERIFICATION-GATE`

Состав:

- обычный рейд обязан найти новую строку полёта;
- при отсутствии строки — `UnverifiedSendError`;
- очередь не переводится в `done`;
- история не увеличивает `raid_count`;
- автоматизация останавливается;
- UI показывает карточку неопределённой отправки.

Тесты:

- server success + новая строка;
- server success без строки;
- строка появляется с задержкой;
- строка другого target/mission;
- одновременная ручная отправка.

### PR 6 — `ALL-FLIGHT-SLOT-ACCOUNTING`

Состав:

- все active missions участвуют в occupied slots;
- атаки отдельно используются для dedupe цели;
- дашборд показывает разбивку миссий;
- wave и auto используют один capacity service.

Тест:

```text
8 атак + 3 астероида + 1 транспортировка при лимите 15 → свободно 3
```

### PR 7 — `SEND-RESPONSE-FAIL-CLOSED`

Состав:

- убрать принудительное снятие `disabled`;
- успех только при явном положительном ответе;
- unknown/malformed response → `unverified`;
- видимые ошибки включают `#dialogMessage`;
- сохранить диагностический event без секретов.

### PR 8 — `SHIP-SELECTION-RETRY-INTEGRATION`

Состав:

- перенести исправление из `ship_retry_fix.py` в `browser.py`;
- удалить monkey patch;
- оставить ровно один повтор;
- проверять точный текст и `#dlg_ok`;
- перед повтором проверять отсутствие принятого рейса;
- удалить второй production entry behavior.

Критерий: `python app.py` и штатный launcher используют одну логику.

## Этап 2. Тестовая инфраструктура

### PR 9 — `WINDOWS-CI-BASELINE`

Состав:

- `.github/workflows/ci.yml`;
- Python 3.10 и 3.11 на Windows;
- `python -m compileall` production-модулей;
- `python -m unittest discover`;
- проверка импорта `app_entry` без запуска mainloop;
- проверка PyInstaller analysis или минимальная smoke-сборка;
- ruff/pyright в щадящем режиме.

Обязательное исправление install script:

- запуск всех тестов, включая page capture и retry;
- компиляция `app_entry.py`, `page_capture.py`, `ship_retry_fix.py` до его удаления.

### PR 10 — `BROWSER-CONTRACT-FIXTURES`

Состав:

- обезличенные fixtures реальных страниц:
  - выбор кораблей;
  - шаг координат;
  - popup «Вы должны выбрать корабли»;
  - отключённая кнопка;
  - таблица полётов;
  - астероидный tooltip;
  - CAPTCHA marker;
- тесты селекторов без подключения к живой игре;
- скрипт redaction перед добавлением fixture.

Fixtures не должны содержать cookies, токены, ники и реальные координаты.

## Этап 3. Время, отчёты и формулы

### PR 11 — `TIMEZONE-CONTRACT`

Состав:

- `GAME_SERVER_TIMEZONE`;
- преобразование серверного UTC+04 времени в UTC;
- запрет naive datetime в persistence;
- поле `time_source` для exact/inferred;
- тесты перехода server → UTC → local.

### PR 12 — `REPORT-PARSER-HARDENING`

Состав:

- безопасное чтение ZIP;
- лимит размера/файлов;
- точный парсинг чисел;
- корректная completeness-модель;
- parsing player/attack_at;
- отказ от `errors="ignore"` как стандартного поведения;
- расширенные fixtures.

### PR 13 — `RANKING-CONTRACT`

До реализации зафиксировать продуктовый выбор:

#### Вариант A — простой металл

```text
priority = reported_metal
```

Плюсы: прозрачно.  
Минусы: не учитывает время и газ.

#### Вариант B — металл в час

```text
priority = min(reported_metal, capacity) / round_trip_hours
```

Плюсы: ближе к эффективности.  
Минусы: нужна достоверная capacity.

#### Вариант C — несколько режимов

- максимум металла;
- металл в час;
- ручной порядок.

В любом варианте:

- добавить максимальный возраст разведки;
- показывать компоненты приоритета;
- удалить мёртвый `Target.score` или сделать его активным режимом;
- синхронизировать README.

### PR 14 — `ASTEROID-FORMULA-CONTRACT`

Состав:

- property tests движения;
- convergence trace;
- тесты точной временной границы;
- метрики кандидатов/пропусков;
- решение по reserve=5 и max=200;
- явное описание поведения safety window.

Логику скорости флота не копировать: продолжать получать её от Nemexia.

## Этап 4. Хранение данных

### PR 15 — `DATABASE-MIGRATION-FRAMEWORK`

Состав:

- `PRAGMA user_version`;
- последовательные migration functions;
- backup + integrity check;
- тесты обновления старых схем;
- документированный restore.

### PR 16 — `STRUCTURED-OPERATION-EVENTS`

Состав:

- таблица событий операций;
- тип операции, target, attempt, outcome, reason, screenshot path;
- связь с history/queue;
- отдельное состояние unverified;
- UI инцидентов.

Не хранить полный HTML автоматически.

## Этап 5. Архитектурное разделение

### PR 17 — `DOMAIN-SEND-RESULTS`

Ввести типы:

```text
SendResult
SendVerification
CapacitySnapshot
OperationFailure
```

Убрать критичные строковые словари из границы automation/application.

### PR 18 — `RAID-SERVICE-EXTRACTION`

Вынести из `app.py`:

- queue policy;
- send orchestration;
- status transitions;
- auto-stop rules.

Tkinter только вызывает service и отображает state.

### PR 19 — `BROWSER-MODULE-SPLIT`

Разделить:

- connection/page binding;
- fleet form;
- raid sender;
- flight reader;
- asteroid scanner/sender;
- messages importer.

### PR 20 — `PERSISTENCE-MODULE-SPLIT`

Разделить schema/migrations/repositories/backups.

## Этап 6. UI/UX

### PR 21 — `UI-SAFETY-STATE`

- общий счётчик слотов;
- persistent auto banner;
- глобальная Stop-кнопка;
- unverified incident card;
- привязанная вкладка и планета.

### PR 22 — `UI-QUEUE-DETAILS`

- двухпанельный план;
- причина приоритета;
- возраст разведки;
- подготовка отдельно от отправки.

### PR 23 — `UI-RESPONSIVE-TABLES`

- горизонтальный scrollbar;
- конфигурация колонок;
- DPI matrix;
- scrollable settings;
- выборочный render текущей страницы.

### PR 24 — `UI-DIAGNOSTICS-CENTER`

- переименовать кнопку в «Сохранить диагностику»;
- предупреждение о приватных данных;
- список локальных снимков;
- копирование пути;
- комментарий пользователя к снимку.

## Этап 7. Релиз и документация

### PR 25 — `DOCUMENTATION-REALIGNMENT`

- переписать README по фактическому алгоритму;
- добавить quick start и safe mode;
- описать ограничения расы/вселенной;
- добавить privacy/security guide;
- перенести `REPORT_*.md` в `docs/archive/`;
- добавить `AGENTS.md`;
- добавить LICENSE/SECURITY/CONTRIBUTING по выбранной модели.

### PR 26 — `RELEASE-PIPELINE`

- версионирование;
- changelog по PR;
- Windows artifact;
- SHA256 checksum;
- smoke test готового EXE;
- понятная инструкция обновления без потери базы.

## Порядок, который нельзя нарушать

```text
Security artifacts
→ Raid verification
→ Slot accounting
→ Fail-closed response
→ Unified tests/CI
→ Time/parser/formulas
→ Architecture
→ UI polish
→ Release automation
```

Нельзя начинать крупный визуальный редизайн или новые автоматические сценарии до PR 4–10: это увеличит поверхность риска и усложнит проверку критичной логики.

## Контрольная точка после каждого PR

1. Какое опасное состояние устранено?
2. Как тест воспроизводит прежнюю ошибку?
3. Может ли изменение создать двойную отправку?
4. Изменился ли контракт формул?
5. Требуется ли миграция базы?
6. Совпадает ли README с поведением?
7. Не попали ли локальные данные в diff?
8. Проверен ли готовый Windows-сценарий?

## Определение завершённости аудита

Аудит считается отработанным не после merge документации, а после того, как:

- все P0 закрыты;
- все P1 либо закрыты, либо приняты как документированный риск;
- CI обязателен для merge;
- реестр формул соответствует production-коду;
- пользователь видит confirmed/rejected/unverified;
- приватные данные больше не попадают в Git.