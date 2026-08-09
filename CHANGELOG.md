# Changelog

## 2.0.0 — 2026-08-09

### Production cutover

- PySide6 V2 is now the default Windows runtime: `run_app.bat -> app_qt.py`.
- Default PyInstaller package `NemexiaRaidManager.spec` now builds the Qt entrypoint as `NemexiaRaidManager.exe`.
- Independent tested Tkinter rollback remains available: `run_legacy.bat -> app_entry.py`.
- Independent legacy package remains available through `NemexiaRaidManagerLegacy.spec` / `build_legacy_exe.bat`.
- Qt and legacy build paths clean only their own artifacts so sequential builds preserve both packages.

### Qt V2

- Complete 11-route PySide6 UI: Overview, Plan, Active, AutoFarm, Asteroids, Debris, Recon, Targets, History, Settings and Diagnostics.
- Frozen reusable Qt design system and two-size full-page gate at 1180×720 and 1440×900.
- Typed/persistent raid, spy, recon, asteroid and debris workflows with fail-closed recovery.
- AutoFarm remains explicitly armed per session with exact processable Spy fleet identity.

### Storage / recovery

- V2 SQLite schema is **9**.
- V2 runtime state is isolated under `%LOCALAPPDATA%\NemexiaRaidManagerV2\`.
- Legacy SQLite is read-only from V2 (`mode=ro`, `PRAGMA query_only=ON`).
- Production startup/shutdown backup boundaries and restart persistence are release-gated.
- Clean-install and existing-user upgrade black-box tests verify storage isolation, V2 restart, legacy DB integrity where required and DB unlock after shutdown.

### Release safety

- `NO NAVIGATION BOUNDARY` remains authoritative.
- V2 does not add automatic 3×40 traversal, background navigation, Rest Mode navigation loops, automatic `refreshGalaxy`, `change_planet.php`, arbitrary `page.goto`, CAPTCHA solve/click/bypass, automatic message deletion or automatic retry after ambiguous remote side effects.
- Spy mutation requires an exact existing processable fleet row; V2 does not create a new espionage route when none exists.
- No unattended asteroid/debris scheduler is enabled.

### Rollback retention

- REL-08 legacy reachability audit classified **no production legacy file as PROVEN DEAD**.
- REL-09 therefore performed **zero production deletions** and hardened the tested rollback surface instead.
- Rollback refs remain `stable/tkinter-v1` and `archive/pre-pyside6-4e01bfda`, both at `4e01bfda752c6383e48c0f6eb8be64d68676da67`.

> The retained Tkinter fallback continues to carry its historical legacy application version identity in its own runtime code. Version 2.0.0 identifies the Qt/V2 production release and does not rewrite the fallback runtime.

## 1.1.0

- Добавлен отдельный экран «Астероиды».
- Автоматическое переключение на Питер `[3:39:8]` и сканирование систем `39 → 1`.
- Чтение времени и периода перемещения астероидов через штатные данные Nemexia.
- Прогноз координаты на момент прилёта, включая переход `38:24 → 39:1`.
- Выбор 5 переработчиков и миссии «Добыча газа» с точным игровым расчётом времени.
- Отправка волны с повторной проверкой координаты перед каждым рейсом.
- Автопродление: следующий цикл после возврата последнего рейса плюс настраиваемый запас.
- Остановка на CAPTCHA, неподтверждённой отправке и серьёзной ошибке; CAPTCHA не обходится.
- Сохранение сканов, циклов и астероидных рейсов в SQLite.

## 1.0.0

- Новый тёмный интерфейс с семью разделами.
- SQLite вместо одного `state.json`.
- Автоматический импорт всех страниц шпионских отчётов.
- Импорт ZIP и HTML.
- Очередь до 200 целей и волновая отправка.
- Автоотправка с аварийным отключением.
- Фактические времена, история, CSV, чёрный список и заметки.
- Автовосстановление соединения, логирование, скриншоты ошибок и резервные копии.
- Системный трей и уведомления о возврате.
- Сценарий сборки Windows EXE.
