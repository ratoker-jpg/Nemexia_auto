param([Parameter(Mandatory = $true)][string]$Key)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$messages = @{
  using_python = "Используется Python $env:LAUNCHER_PYTHON_VERSION x64: $env:LAUNCHER_PYTHON_COMMAND"
  python_not_found = "ОШИБКА: не найден подходящий Python x64 версии 3.10 или новее. Установите Python 3.10/3.11 x64 и повторите запуск."
  create_venv = "Создание виртуального окружения .venv..."
  upgrade_pip = "Обновление pip..."
  install_requirements = "Установка зависимостей..."
  compile_sources = "Проверка исходного кода..."
  run_self_test = "Запуск быстрой самопроверки..."
  install_success = "Установка завершена. Для запуска используйте run_app.bat или launcher.bat."
  venv_create_error = "ОШИБКА: не удалось создать виртуальное окружение .venv."
  venv_invalid_error = "ОШИБКА: виртуальное окружение .venv повреждено. Удалите папку .venv и запустите install.bat повторно."
  pip_upgrade_error = "ОШИБКА: не удалось обновить pip в .venv."
  requirements_error = "ОШИБКА: не удалось установить зависимости из requirements.txt. Проверьте подключение к интернету и вывод выше."
  compile_error = "ОШИБКА: проверка синтаксиса Python завершилась с ошибкой."
  self_test_error = "ОШИБКА: самопроверка self_test.py завершилась с ошибкой."
  venv_missing = "Виртуальное окружение .venv отсутствует или повреждено."
  install_question = "Запустить install.bat сейчас?"
  setup_cancelled = "Запуск отменён. Сначала выполните install.bat."
  install_failed = "Установка не завершилась успешно. Код завершения: $env:LAUNCHER_INSTALL_EXIT"
  app_failed = "Приложение завершилось с кодом: $env:LAUNCHER_APP_EXIT"
  logs_location = "Логи: $env:LOCALAPPDATA\NemexiaRaidManager\logs"
  build_requirements = "Установка зависимостей сборки в .venv..."
  build_success = "Готово: dist\NemexiaRaidManager.exe"
  venv_missing_build = "ОШИБКА: виртуальное окружение .venv отсутствует или повреждено. Сначала выполните install.bat."
  build_requirements_error = "ОШИБКА: не удалось установить зависимости сборки в .venv."
  pyinstaller_error = "ОШИБКА: сборка PyInstaller завершилась с ошибкой. Проверьте вывод выше."
  launcher_install = "Виртуальное окружение .venv отсутствует или повреждено. Запускается установка..."
}
if ($messages.ContainsKey($Key)) { Write-Output $messages[$Key]; exit 0 }
Write-Output "ОШИБКА: неизвестное сообщение запуска."
exit 1
