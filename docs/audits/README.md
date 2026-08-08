# Аудиты проекта

## Текущий V2 asteroid action audit — 2026-08-08

[`2026-08-08-v2-asteroid-contract-audit.md`](2026-08-08-v2-asteroid-contract-audit.md) фиксирует V2-51: эффективные legacy call sites, asteroid selectors/endpoints, UTC+04 movement semantics, 24-position coordinate math, iterative flight-time stabilization, recycler/mission facts, SendFleet verification и различия безопасности V2.

Ключевой scope: contract/fixtures only — без live scan, SendFleet, SQLite mutation, Qt action или scheduler. V2 остаётся attach-only; automatic retry после потенциального remote effect не переносится.

## Актуальный V2 raid-loop parity gate — 2026-08-08

[`2026-08-08-v2-raid-loop-parity-gate.md`](2026-08-08-v2-raid-loop-parity-gate.md) фиксирует фактическое состояние V2 после V2-41→V2-49: exact-fleet fresh spy acquisition, V2-owned recon, deterministic refill, persisted no-target cooldown и continuous recovery без legacy mutation code.

Ключевые ограничения сохранены: attach-only browser, legacy SQLite read-only, CAPTCHA fail-closed, отсутствие automatic retry после ambiguity, без message deletion и без `processSpy(0)`.

## Базовый полный аудит — 2026-08-06

Baseline: `a33632bc092ede70f7d6e6c4a819dd65b055bf1d`.

Документы:

1. [`2026-08-06-owner-decisions.md`](2026-08-06-owner-decisions.md) — **актуальный утверждённый scope**: принятые и отклонённые рекомендации владельца. Этот документ имеет приоритет над исходным roadmap.
2. [`2026-08-06-full-project-audit.md`](2026-08-06-full-project-audit.md) — общий аудит архитектуры, отправки, данных, безопасности, тестов и документации.
3. [`2026-08-06-formula-register.md`](2026-08-06-formula-register.md) — полный реестр формул, расчётных правил, допущений и несоответствий.
4. [`2026-08-06-ui-ux-audit.md`](2026-08-06-ui-ux-audit.md) — визуальная система, информационная архитектура, безопасность действий и responsive/DPI.
5. [`2026-08-06-remediation-roadmap.md`](2026-08-06-remediation-roadmap.md) — первоначальная последовательность рекомендаций; применяется только в части, подтверждённой owner decisions.

## Утверждено к исправлению

- обычный рейд требует подтверждённую новую строку полёта;
- свободные слоты считаются по всем активным миссиям;
- отключённая игрой кнопка отправки не разблокируется программно;
- ответ сервера считается успешным только при явном положительном `pass`;
- неизвестный результат получает состояние `unverified` без автоматического повтора;
- формула восстановления времени отправки проверяется и маркируется как вычисленная;
- время отчётов приводится из подтверждённого часового пояса сервера;
- старая разведка ограничивается по возрасту для автоматического плана;
- бот привязывается к конкретной выбранной вкладке Nemexia.

## Осознанно не принимается в работу

- удаление `saved_pages` и реальных целей из GitHub;
- изменение сортировки целей по металлу;
- остальные архитектурные, тестовые, CI и UI/UX-рекомендации текущего аудита.

## Приоритет реализации

```text
1. RAID-VERIFICATION-AND-RESPONSE-GATE
2. ALL-FLIGHT-SLOT-ACCOUNTING
3. REPORT-TIMEZONE-AND-FRESHNESS
4. FLIGHT-TIME-PROVENANCE
5. BOUND-NEMEXIA-TAB
```

Все пять implementation-блоков завершены и слиты в `main` через PR #5–#9.

## Следующая утверждённая продуктовая концепция

[`../plans/2026-08-06-rest-mode-and-attack-watch.md`](../plans/2026-08-06-rest-mode-and-attack-watch.md) фиксирует будущий **«Режим отдыха»**:

- обновление раздела «Полёты» раз в 5 минут;
- наблюдение за входящими атаками и локальные уведомления;
- предупреждение за 25 минут до проверки активности;
- остановка при CAPTCHA и только ручное прохождение проверки;
- реализация отдельными PR `REST-MODE-ACTIVITY-WATCH` и `INCOMING-ATTACK-WATCH`.

Для точной реализации парсера атак требуется сохранённая HTML/MHTML-страница в момент реальной входящей атаки.
