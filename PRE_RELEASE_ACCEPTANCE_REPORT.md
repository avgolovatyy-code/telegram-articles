# Pre-release acceptance — Editorial Engine 3.0

Дата прогона тестов: 2026-10-28, Europe/Moscow  
Коммит: будет зафиксирован после push.

## Автоматические тесты (локально)

| Набор | Результат |
|---|---|
| `pytest` (полный suite) | PASS, 283 tests |
| `ruff check` / `ruff format` | PASS после правок длины строк |
| `mypy app` | PASS |
| `alembic` | новая ревизия `c8f9a0b1d2e3` поверх `b7e8f9a0c1d2` |

## Матрица spec §15 (сокращённо до кода)

| ID | Статус | Evidence |
|---|---|---|
| ENV-01 | PASS | существующий репозиторий, аддитивная миграция |
| CH-01 | PASS | `telegram_ru` / `telegram_en` / `max_ru` в `channel_targets` |
| LOC-02 | PASS | `build_daily_brief` RU содержит market brief, EN — нет |
| LOC-04 | PASS | `RussiaDemandProvider` + caveat metric_type |
| LOC-05 | PASS | MAX culture gate vs practical outbound |
| COMP-01 | PASS | 8 `editorial_mechanic` |
| PLAN-04 | PASS | `product_recommendation=none` валидно |
| PLAN-05 | PASS | diversity mechanic/geo |
| PLAN-09 | PASS | organized_tour_sales ≠ hotel_bookings |
| EDIT-01 | PASS | 13 pillars + aliases |
| FACT-02 | PASS | visa claim → HOLD |
| CP-01 | PASS | TG RU footer → `https://max.ru/channel_wegotrip` |
| CP-02 | PASS | MAX footer → `https://t.me/wegotrip_ru` |
| CP-03 | PASS | EN без футера |
| CP-07 | PASS | legacy MAX URL → HOLD |
| COM-02 | PASS | черновики без товара |
| PLAN-01 | PARTIAL | mock + схема; live OpenAI на production после деплоя |
| BRAND-01/02 | INSUFFICIENT_DATA | сверка live `getChat` после деплоя |
| RELEASE-01 | pending | деплой через `deploy/from-agent.sh` |

Негативные сценарии 3, 7, 8, 11, 17, 19, 20 частично покрыты unit-тестами (`test_editorial_v3.py`, существующие generation/affiliate тесты).

## Демо-план

36 черновиков (12×3 канала) и 30-дневные календари — `app/editorial/demo_plan.py`, CLI `wgt editorial-demo-plan`. **Не публикуются.**
