# Отчёт: исправление Windows-запуска

## Причина ошибки

`install.bat` определял наличие Windows Python Launcher (`py`), но после этого всегда назначал команду `py -3.11`. На компьютере, где установлен только Python 3.10, создание `.venv` закономерно завершалось ошибкой «Requested Python version (3.11) not installed». Кроме того, кириллица внутри UTF-8 BAT-файлов может быть неверно разобрана CMD ещё до выполнения `chcp`, что повреждает текст и синтаксис скрипта.

## Совместимость

На проверяемом компьютере найдены Python 3.10.11 x64 (`py -3.10`, 64-bit). Исходные файлы `app.py`, `browser.py`, `asteroids.py`, `models.py`, `reports.py`, `storage.py` и `self_test.py` успешно проходят `py -3.10 -m py_compile`. Зависимости из `requirements.txt` не требуют Python 3.11; проект совместим с Python 3.10 x64.

## Изменения

- `install.bat` включает UTF-8, переходит в папку скрипта, ищет Python в порядке `py -3.11` → `py -3.10` → `python` → `python3`, принимает только x64 и версию не ниже 3.10, создаёт `.venv`, устанавливает пакеты через `.venv\Scripts\python.exe` и запускает компиляцию с `self_test.py`.
- `run_app.bat` и `run_console.bat` включают UTF-8, запускают приложение только через `.venv\Scripts\python.exe`, предлагают запустить установку при отсутствии или повреждении окружения и оставляют окно открытым при ошибке.
- `build_exe.bat` использует только Python из `.venv` для установки PyInstaller и сборки с текущим `NemexiaRaidManager.spec`.
- Добавлен `launcher.bat`: при готовом `.venv` он запускает приложение, иначе сначала выполняет установку.
- Добавлен `launcher_messages.ps1` с русскими сообщениями в UTF-8. BAT-файлы содержат только ASCII-код, а перед выводом включают `chcp 65001`; это устраняет повреждение русских строк при разборе CMD.
- `README_RU.md` дополнен инструкцией для Python 3.10/3.11, первого запуска и переустановки `.venv`.

Файл `run_app_console.bat` в проекте отсутствует; его существующий консольный аналог `run_console.bat` приведён к той же логике.

## Команды проверки

```bat
py -0
py -3.10 -m py_compile app.py browser.py asteroids.py models.py reports.py storage.py self_test.py
install.bat
.venv\Scripts\python.exe self_test.py
run_app.bat
```

## Результаты проверки

- `py -3.10 --version` → Python 3.10.11.
- `py -3.10 -m py_compile app.py browser.py asteroids.py models.py reports.py storage.py self_test.py` → успешно.
- Чистый запуск `install.bat` → создана `.venv` на Python 3.10.11 x64; установлены Playwright 1.62.0, BeautifulSoup 4.15.0, pystray 0.19.5 и Pillow 11.3.0; быстрая самопроверка завершилась `OK`.
- `.venv\Scripts\python.exe -m pip check` → `No broken requirements found`.
- `.venv\Scripts\python.exe self_test.py` → `OK: база, стартовые цели, очередь и резервная копия`.
- `run_app.bat` запущен с отдельным тестовым `%LOCALAPPDATA%`: процесс `.venv\Scripts\python.exe app.py` появился и был закрыт без обращения к пользовательской SQLite-базе.
- После проверки удалены только созданные для неё `.venv` и `_launcher_smoke_localappdata` в каталоге проекта.

## Не проверено

Сборка EXE не запускается в рамках этой проверки, чтобы не удалять существующие папки `build` и `dist`. Точно Python 3.10.6 проверить не удалось: фактически доступен Python 3.10.11, который относится к той же поддерживаемой ветке. Игровая автоматизация, реальные рейсы и пользовательская SQLite-база не затрагиваются.

## Итоговые артефакты

- Изменённые файлы: `install.bat`, `run_app.bat`, `run_console.bat`, `build_exe.bat`, `README_RU.md`.
- Новые файлы: `launcher.bat`, `launcher_messages.ps1`.
- Резервные копии BAT-файлов: `install.bat.backup_20260804_230717`, `run_app.bat.backup_20260804_230717`, `run_console.bat.backup_20260804_230717`, `build_exe.bat.backup_20260804_230717`.
- Команда первого запуска: `install.bat`.
