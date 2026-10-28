# Editorial Engine 3.0 — статус требований

Источник: `WEGOTRIP_EDITORIAL_ENGINE_FINAL_CURSOR_AUTORELEASE.md`.  
Обновлено: 2026-10-28, Europe/Moscow.

## Hard gates

| Gate | Статус | Где |
|---|---|---|
| H1 три канала | PASS (код) | `channel_targets`, MAX policy |
| H2 OpenAI Chief Editor | PASS схема/prompt; live — после деплоя | `chief_editor_ru_market_v2_3`, `chief_editor_en` v3 |
| H3 тренды РФ без монокультуры | PASS | `RussiaDemandProvider` + diversity |
| H4 native EN / RU / MAX | PASS (промпты + MAX adaptation) | `writer_ru_brand_v2_3`, EN isolated brief |
| H5 13 рубрик | PASS | `pillars.py` + aliases |
| H6 факт/права | PASS существующий gate + practicality HOLD | |
| H7 футер RU, не EN | PASS | `app/editorial/footer.py` |
| H8 coupon=435 | PASS существующий AffiliateUrlBuilder | |
| H9 без дублей/backfill | PASS существующая очередь | |
| H10 админка | PASS колонки mechanic/axis/channels | |
| H11 CI + deploy | в работе | |
| H12 evidence | этот файл + PRE_RELEASE + pytest | |

## Не делаем в этом релизе

- Новые каналы / username.
- Массовая правка исторических постов.
- Рост `DAILY_AI_BUDGET_USD`.
- Живой Google Trends / Wordstat без авторизованного доступа (`UNAVAILABLE`).
