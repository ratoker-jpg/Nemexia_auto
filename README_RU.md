# Nemexia Raid Manager V2 2.0.0

Текущий production runtime — **PySide6 / Qt V2**.

```text
DEFAULT:
run_app.bat -> app_qt.py

ROLLBACK:
run_legacy.bat -> app_entry.py
```

Legacy Tkinter stack намеренно сохранён как протестированный rollback. Он не является default UI после cutover.

## Установка в Windows

Поддерживаются **Python 3.10 x64** и **Python 3.11 x64**.

1. Распакуй репозиторий/релиз в отдельную папку.
2. Запусти `install.bat`.
3. Скрипт создаст локальную `.venv`, установит общий набор зависимостей для Qt default и Tk rollback, выполнит compile checks и legacy self-test.
4. Запусти `run_app.bat`.

Обычный production запуск:

```text
run_app.bat
```

`launcher.bat` остаётся convenience-wrapper для default запуска и установки `.venv`, если она отсутствует.

## Existing-user upgrade

Обновление с legacy/Tkinter не требует удаления старой SQLite-базы.

1. Закрой обе версии приложения.
2. Обнови файлы программы.
3. Запусти `install.bat`.
4. Запусти `run_app.bat`.
5. V2 создаст собственное хранилище в `%LOCALAPPDATA%\NemexiaRaidManagerV2\` и импортирует только разрешённые legacy facts/settings.
6. Legacy SQLite остаётся неизменяемой со стороны V2: открытие выполняется read-only через `mode=ro` + `PRAGMA query_only=ON`.
7. Повторный запуск V2 должен использовать уже созданную schema 9 и сохранённое V2 state.

Release CI отдельно воспроизводит clean install и existing-user upgrade, проверяет byte-integrity legacy DB там, где импортный контракт требует неизменности, V2 restart и освобождение SQLite-файла после shutdown.

## Rollback

Если необходимо временно вернуться к прежнему Tkinter runtime:

```text
run_legacy.bat
```

Этот launcher независимо запускает:

```text
app_entry.py
```

Он не является alias на `run_app.bat`, поэтому переключение default на Qt не меняет rollback path.

Для отдельной legacy EXE-сборки сохранены:

```text
NemexiaRaidManagerLegacy.spec
build_legacy_exe.bat
```

Rollback stack прошёл отдельный black-box smoke после реальной установки и остаётся защищён retention-contract тестами.

Rollback refs репозитория:

```text
stable/tkinter-v1
archive/pre-pyside6-4e01bfda
```

Обе refs зафиксированы на original Tkinter SHA:

```text
4e01bfda752c6383e48c0f6eb8be64d68676da67
```

## Где хранятся данные

### V2 / Qt

```text
%LOCALAPPDATA%\NemexiaRaidManagerV2\
```

V2 SQLite schema: **9**.

V2-owned состояние включает typed settings, raid action journal/queue, spy action journal, recon targets/reports, asteroid actions/observations и debris observations.

Production lifecycle создаёт резервные копии V2 state на startup/shutdown boundaries и закрывает БД детерминированно.

### Legacy / Tkinter

Legacy хранение остаётся отдельно:

```text
%LOCALAPPDATA%\NemexiaRaidManager\
```

V2 не использует эту SQLite как writable storage.

## PySide6 интерфейс

Qt shell содержит 11 маршрутов:

- Overview / Обзор;
- Plan / План;
- Active / Активные;
- AutoFarm / Автофарм;
- Asteroids / Астероиды;
- Debris / Обломки;
- Recon / Разведка;
- Targets / Цели;
- History / История;
- Settings / Настройки;
- Diagnostics / Диагностика.

Release smoke создаёт настоящий `QApplication`/`MainWindow` и проверяет все 11 страниц при **1180×720** и **1440×900**.

## Browser contract — важно

V2 остаётся **attach-only** и следует решению `NO NAVIGATION BOUNDARY`.

Программа V2 использует уже открытые/подходящие Nemexia страницы через CDP и **не должна** автоматически:

- запускать браузер или создавать новую вкладку;
- обходить галактику 3×40;
- переключать системы/планеты;
- выполнять background browser navigation;
- запускать Rest Mode navigation loops;
- вызывать `refreshGalaxy` автоматически;
- использовать V2 `change_planet.php`;
- выполнять arbitrary `page.goto` navigation.

Для live операций пользователь вручную держит нужную страницу открытой: `fleets.php`, System messages на `options.php` или текущую `galaxy.php` — в зависимости от операции.

## Mutation safety

Текущий release сохраняет fail-closed контракты:

- raid/asteroid/debris remote mutation — exactly-one attempt после preparation/re-check;
- ambiguous remote side effect не повторяется автоматически;
- spy processing работает только с exact processable espionage fleet row через `processSpy(fleet_id)`, не `processSpy(0)`;
- если exact Spy fleet отсутствует, V2 не создаёт новый espionage route;
- CAPTCHA только обнаруживается → **STOP**; solve/click/bypass отсутствуют;
- automatic message deletion отсутствует;
- asteroid/debris unattended scheduler отсутствует;
- AutoFarm запускается вручную, session-only arm/Spy ID не переживают restart.

## Астероиды и обломки в V2

Qt release **не переносит** старый legacy automatic 3×40 traversal/autorenew workflow.

Текущий V2 workflow ограничен уже открытой системой:

```text
Read current system -> Prepare -> explicit confirmed dispatch -> Stop
```

Это deliberate limitation и не является release blocker.

## Сборка Windows EXE

Default Qt package:

```text
build_exe.bat
NemexiaRaidManager.spec
-> dist\NemexiaRaidManager.exe
```

Дополнительный явный Qt package path:

```text
build_qt_exe.bat
NemexiaRaidManagerQt.spec
```

Legacy fallback package:

```text
build_legacy_exe.bat
NemexiaRaidManagerLegacy.spec
-> dist\NemexiaRaidManagerLegacy.exe
```

Build scripts очищают только собственные artifacts, поэтому Qt и legacy packages не должны удалять друг друга при последовательной сборке.

## Проверка релиза

Обязательные CI gates:

- Windows Python 3.10: compileall + full pytest + legacy self-test;
- Windows Python 3.11: compileall + full pytest + legacy self-test;
- PySide6 / Python 3.11: real QApplication/MainWindow, все 11 routes, 1180×720 и 1440×900;
- Windows release black-box: real `install.bat`, clean-install/existing-user upgrade, `run_app.bat --release-smoke` = Qt/V2, `run_legacy.bat --release-smoke` = Tk/legacy, V2 restart, legacy DB integrity и DB unlock after shutdown.

Подробный финальный статус: `docs/v2-current-state.md` и `docs/releases/2026-08-09-v2-2.0.0-qt-cutover.md`.
