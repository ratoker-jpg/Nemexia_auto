# Реестр формул и расчётных правил

Baseline: `a33632bc092ede70f7d6e6c4a819dd65b055bf1d`  
Назначение: зафиксировать все существенные расчёты, допущения и несоответствия между кодом и документацией.

## Статусы

- **OK** — формула логична и покрыта базовыми тестами.
- **CONTRACT** — формула зависит от правил/DOM Nemexia и требует contract test.
- **RISK** — есть допущение, способное изменить результат.
- **DEAD** — код существует, но текущий продукт его не использует.
- **DOC MISMATCH** — документация описывает другое поведение.

## 1. Приоритет целей

### 1.1. Эффективность по энергии

Файл: `models.py`, `Target.efficiency`.

```text
round_trip_minutes = round_trip_seconds / 60
efficiency = energy / round_trip_minutes
```

Защита:

- если цикл отсутствует или не положительный — `None`;
- знаменатель не меньше одной минуты.

Статус: **DEAD**.

Причина: текущий экран и генератор очереди не используют `Target.efficiency`.

### 1.2. Score по энергии, времени и свежести

Файл: `models.py`, `Target.score()`.

```text
trip_minutes = max(1, (round_trip_seconds or 3600) / 60)
base = energy / trip_minutes
```

Коэффициент свежести:

```text
freshness = 1.55, если рейдов ещё не было
freshness = clamp(elapsed_minutes / repeat_minutes, 0.15, 2.0), иначе
score = base * freshness
```

Статус: **DEAD + DOC MISMATCH**.

Проблемы:

- коэффициенты `1.55`, `0.15`, `2.0` не объяснены данными;
- формула не вызывается текущим `ranked_targets()`;
- README продолжает описывать рейтинг по энергии, циклу и давности.

Решение: либо удалить формулу, либо вернуть как отдельный режим с тестовыми примерами и прозрачной расшифровкой score.

### 1.3. Фактический приоритет плана

Файл: `app.py`, `ranked_targets()`.

Цель допускается, если одновременно:

```text
enabled = true
blacklisted = false
coord not in active_attack_targets
last_spy_at is not null
metal is not null
metal >= min_metal_for_queue
```

Фактический приоритет:

```text
priority = metal
sort = metal DESC, coord ASC
```

Статус: **OK как простая политика, но DOC MISMATCH**.

Ограничения:

- не учитывается время полёта;
- не учитывается расход газа;
- не учитывается возраст разведки;
- не учитываются последний рейд и возврат;
- координата используется как tie-breaker, а не экономическая эффективность.

Рекомендуемая базовая формула для будущего режима эффективности:

```text
expected_loot = min(reported_metal, transport_capacity)
cycle_hours = round_trip_seconds / 3600
priority = expected_loot / cycle_hours
```

Дополнительные множители должны вводиться только после измерений, а не как скрытые магические коэффициенты.

## 2. Размер очереди и волны

### 2.1. Генерация очереди

```text
queue_count = max(1, configured_queue_size)
queue = first queue_count targets from ranked_targets
```

Статус: **OK**.

Ограничение: верхний предел зависит от UI, а не проверяется на уровне domain policy.

### 2.2. Свободные слоты обычных рейдов

Текущая формула:

```text
free_slots = max(0, max_slots - count(attack_flights))
```

Статус: **RISK / P0**.

Причина: `attack_flights` получены через `sync_flights()` и не включают астероиды, транспортировку, шпионаж и другие миссии.

Корректный контракт:

```text
free_slots = max(0, max_slots - count(all_active_flights))
```

При этом защита от дубля цели должна использовать отдельный набор:

```text
active_attack_targets = targets of active flights where mission == attack
```

### 2.3. Число рейсов к астероидам

Файл: `browser.py`, `_run_dynamic_asteroid_cycle()`.

```text
capacity_by_recyclers = available_recyclers // recycler_count
requested = min(max_flights, free_slots, capacity_by_recyclers)
```

Все входы нормализуются к неотрицательным значениям, `recycler_count` защищён от деления на ноль.

Статус: **OK**.

## 3. Кандидаты астероидов

### 3.1. Размер партии кандидатов

```text
candidate_limit = min(200, max(1, requested) + max(0, reserve))
reserve = 5
```

Статус: **OK технически, CONTRACT продуктово**.

Проблема: резерв 5 и предел 200 являются магическими значениями без метрики пропусков/успехов.

Рекомендация: логировать `candidates → valid → sent` и выбирать резерв по фактической доле отбраковки.

### 3.2. Динамический добор

Первый проход:

```text
wanted = requested
batch_limit = wanted + reserve
```

Следующие проходы:

```text
missing = requested - sent
wanted = missing
batch_limit = missing + reserve
```

Общий предел:

```text
all_candidates <= 200
```

Статус: **OK**, покрыт self-test сценариями.

## 4. Движение астероидов

### 4.1. Период движения

```text
period_seconds = next_move - last_move
```

Fallback:

```text
period_seconds = tooltip_speed_minutes * 60
```

Статус: **OK**, если tooltip содержит серверное время в поддержанном формате.

### 4.2. Перенос координаты

Для 24 позиций в системе:

```text
linear = (system - 1) * 24 + (position - 1) + steps
new_system_zero, new_position_zero = divmod(linear, 24)
new_system = new_system_zero + 1
new_position = new_position_zero + 1
```

Примеры:

```text
3:38:24 + 1 → 3:39:1
3:39:24 + 1 → 3:40:1
```

Ограничение:

```text
new_system <= 40
```

Статус: **OK**, покрыт тестами границы 24 → 1 и системы 40.

### 4.3. Число перемещений до прибытия

```text
effective_arrival = arrival + max(0, safety_seconds)
```

Если:

```text
effective_arrival < next_move
```

то:

```text
shifts = 0
```

Иначе:

```text
elapsed = effective_arrival - next_move
shifts = 1 + floor(elapsed / period_seconds)
```

Статус: **OK**.

Граница трактуется консервативно: прибытие ровно в момент движения относится уже к следующей клетке.

### 4.4. Запас до ближайшей границы движения

До первого движения:

```text
margin = next_move - arrival
```

После первого движения:

```text
remainder = (arrival - next_move) mod period
margin = min(remainder, period - remainder)
```

Статус: **OK**.

### 4.5. Итеративный расчёт конечной клетки

Алгоритм:

1. выбрать предварительную клетку;
2. получить время полёта из формы Nemexia;
3. вычислить положение астероида на момент прибытия;
4. если клетка изменилась — повторить;
5. максимум 8 итераций.

Статус: **CONTRACT**.

Плюсы:

- не дублируется формула скорости флота;
- учитывается зависимость времени полёта от конечной клетки.

Риски:

- предел 8 не обоснован;
- нет сохранённого convergence trace;
- при попадании в safety window цель отклоняется, а не перестраивается на следующую клетку.

## 5. Время полёта

### 5.1. Получение времени

`one_way_seconds`, `round_trip_seconds` и газ читаются после вызова штатной `FlyCheck()` игры.

Статус: **CONTRACT / правильный архитектурный выбор**.

Программа не должна самостоятельно воспроизводить неизвестную формулу скорости Nemexia, пока результат доступен из игры.

Требуемые contract tests:

- обычная атака;
- добыча газа;
- разные скорости;
- недостаток газа;
- отключённая кнопка;
- изменение DOM/имен глобальных переменных.

### 5.2. Абсолютные времена после отправки

Для программной отправки:

```text
arrival_at = sent_at + one_way_seconds
return_at = sent_at + round_trip_seconds
```

Статус: **OK**, если `sent_at` фиксируется после подтверждённого ответа и до значительной задержки.

### 5.3. Восстановление времени отправки из таблицы

Текущая формула:

```text
sent_at = arrival_at + (arrival_at - return_at)
sent_at = 2 * arrival_at - return_at
```

Эквивалентно:

```text
sent_at = arrival_at - (return_at - arrival_at)
```

Статус: **RISK**.

Допущение:

```text
return_at - arrival_at = one_way_duration
```

Это требует подтверждения для каждой миссии и модификатора.

Рекомендация: хранить `sent_at_source = exact | inferred | unknown`.

## 6. Автопродление астероидов

После успешной волны:

```text
next_cycle_at = max(return_at of results) + buffer_minutes
```

По умолчанию:

```text
buffer_minutes = 5
```

Статус: **OK**.

Обязательное условие: учитывать только подтверждённые отправки. Неопределённый рейс должен останавливать автопродление.

## 7. Ресурсы и добыча

### 7.1. Суммарная добыча

```text
total_loot = metal + minerals + gas
```

Отсутствующее значение считается нулём.

Статус: **OK арифметически**.

Ограничение: корректность результата полностью зависит от HTML-парсера чисел.

### 7.2. Парсинг чисел

Текущая операция:

```text
digits = remove_everything_except_0_to_9(text)
number = int(digits)
```

Статус: **RISK**.

Пример неоднозначности:

```text
"Металл 12 000 / вместимость 25 000" → 1200025000
```

Правило должно извлекать одно конкретное значение из конкретной ячейки или атрибута.

## 8. Возраст разведки

Метрика в БД:

```text
cutoff = utc_now - stale_hours
fresh = last_spy_at >= cutoff
stale = last_spy_at < cutoff
```

Статус: **OK как метрика**.

Но фактическая очередь этот cutoff не применяет.

Статус планирования: **RISK / DOC MISMATCH**.

Рекомендуемый фильтр:

```text
eligible = last_spy_at >= utc_now - max_spy_age_hours
```

## 9. Дедупликация

### 9.1. Отчёты

При наличии `message_id`:

```text
key = kind + message_id
```

Иначе:

```text
key = SHA256(kind, coord, report_at, selected_values)
```

Статус: **OK**.

Ограничение: изменение парсера выбранных значений может изменить fallback-key одного и того же исходного отчёта.

### 9.2. История полётов

Предпочтительно используется `fleet_id`. Fallback строится из нормализованной цели и времён.

Статус: **OK**, но времена предварительно округляются до секунды и могут зависеть от формулы inferred `sent_at`.

## 10. Хранение и retention

### 10.1. Backup базы

```text
keep_last = 10
```

Статус: **OK**.

Недостаток: backup без автоматического `integrity_check` и без UI восстановления.

### 10.2. Ручные снимки страниц

```text
keep_last = 10 folders
```

Статус: **OK локально**.

Критичный внешний контракт:

```text
saved_pages must never be tracked by Git
```

Сейчас контракт нарушен.

## 11. Временные зоны

Используются три разных класса времени:

1. UTC-aware — `utc_now()`;
2. local-aware — `datetime.now().astimezone()` при отправке;
3. naive server time — астероидные tooltip и `window.currentTime`.

Статус: **RISK**.

Дополнительно HTML-отчёты получают UTC tzinfo без преобразования, несмотря на сервер UTC+04:00.

Целевой контракт:

- все persistent datetime — UTC-aware;
- серверные строки сначала локализуются в `GAME_SERVER_TIMEZONE`;
- UI переводит UTC в локальную зону пользователя;
- naive datetime запрещены на границе domain/persistence.

## 12. Формулы, которых в проекте нет

Проект осознанно не содержит собственной формулы:

- скорости корабля;
- расхода газа;
- времени атаки;
- вместимости транспорта;
- добычи астероида.

Это правильно, пока источником истины выступает штатная форма Nemexia. Такие формулы нельзя добавлять по догадке: нужен подтверждённый игровой контракт и набор контрольных примеров.

## 13. Обязательные тестовые наборы

1. Golden ranking: фиксированный список целей → фиксированный порядок.
2. Stale reports: разведка старше лимита не попадает в автоматический план.
3. Slot accounting: атака + астероид + транспорт → занято 3 слота.
4. Send verification: нет новой строки → `UnverifiedSendError`.
5. Unknown response: нет явного success → неопределённый результат.
6. Timezone: UTC+04 server timestamp корректно переводится в UTC.
7. Asteroid property tests: границы 1/24, системы 1/40, точная граница времени.
8. ZIP safety: absolute path, `..`, zip bomb limits.
9. Parser ambiguity: несколько чисел в одной строке не склеиваются.
10. Manual snapshot: retention и запрет Git tracking.