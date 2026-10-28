# Post-deploy audit — Editorial Engine 3.0

**Время аудита:** 28 октября 2026, 22:57 Europe/Moscow  
**Production SHA:** `00bbe9b385af592156023fbf8801d653028b8949`  
**Ветка:** `cursor/editorial-engine-v3-01af`  
**PR:** https://github.com/avgolovatyy-code/telegram-articles/pull/12  
**CI:** https://github.com/avgolovatyy-code/telegram-articles/actions/runs/40757555872 — success  
**Хост:** `/opt/wegotrip-content-engine` на существующем droplet, compose `deploy/docker-compose.prod.yml` (Caddy).  
**Публичный healthz:** `https://209-38-45-22.sslip.io/healthz` → `{"status":"ok"}`

Деплой через `DEPLOY_BRANCH=cursor/editorial-engine-v3-01af bash deploy/from-agent.sh`. Новые каналы не создавались, `DAILY_AI_BUDGET_USD=3.0` не менялся, dummy-посты не отправлялись.

## Hard gates

| Gate | Статус | Evidence |
|---|---|---|
| H1 три канала | PASS | TG EN `@wegotrip`, TG RU `@wegotrip_ru`, MAX `https://max.ru/channel_wegotrip` (type=channel, slug match) |
| H2 OpenAI Chief Editor | PASS | live `wgt chief-editor`: EN run `c758d79b-…` prompt `chief_editor_en` **v3**; RU run `a6adf2c6-…` prompt `chief_editor_ru_market_v2_3` **v3**; model `gpt-5.6-luna`; `llm_runs` 6482/6483 status=ok |
| H3 спрос РФ без монокультуры | PASS | 10 `russia_demand_observations`; TR/EG/AE/TH/VN/CN = `organized_tour_sales`; RU = `hotel_bookings`; RU thesis разбавляет лондонский кластер локальными сюжетами |
| H4 native EN / RU / MAX | PASS | разные промпты; слот 2026-11-01 EN `channel_targets=["telegram_en"]`; RU `["telegram_ru","max_ru"]` |
| H5 13 рубрик | PASS | код + живой календарь (weekend_ideas, trip_planning, place_story, exhibitions_museums, community_poll, …) |
| H6 факт/права | PASS | practicality HOLD в тестах; live injector HOLD на legacy MAX URL; VERIFY OR OMIT в промптах |
| H7 футер RU, не EN | PASS (рендерер) / LIVE_NEW_POST=NOT_YET_OBSERVED | prod dry-run: RU HTML → `max.ru/channel_wegotrip`; MAX HTML → `t.me/wegotrip_ru`; EN без MAX. Последний live-пост RU id=4094 в 22:08 MSK **до** деплоя 22:52 |
| H8 coupon=435 | PASS | `wgt doctor` referer_id=435 |
| H9 без дублей/backfill | PASS | пины не дублировались; smoke `--post` не вызывался |
| H10 админка | PASS | колонки mechanic/axis/channels в задеплоенном коде |
| H11 CI + deploy | PASS | CI green; SHA на дроплете = head PR; api healthy; worker `SCHEDULER_ENABLED=true`; alembic `c8f9a0b1d2e3` |
| H12 evidence | PASS | doctor, check-max, check-telegram, getChat, openai_responses, live chief editor — не mock |

## Каналы (read-only getChat / MAX API)

| Канал | Title | Описание / сайт | Pin |
|---|---|---|---|
| TG RU | `WeGoTrip — Куда сходить и что посмотреть` (match) | `wegotrip.ru`, без `.com` | pin 339, уже есть — **не дублировали** |
| TG EN | `WeGoTrip — Things to Do & Travel Ideas` (match) | `wegotrip.com`, без `.ru` | pin 352, уже есть — **не дублировали** |
| MAX RU | `WeGoTrip — Куда сходить и что посмотреть` | public `channel_wegotrip`, is_public=true | numeric chat_id сохранён, не выводится |

`apply-telegram-branding` не вызывался: title/description уже совпадают с approved copy.

## Флаги после деплоя

- `EDITORIAL_RU_MARKET_V3_ENABLED=true`
- `CROSS_PROMO_FOOTER_ENABLED=true`
- `ENABLE_HASHTAGS=false` (было true; приведено к спецификации 3.0)
- `MAX_COMMERCIAL_POST_SHARE=0.20`
- `AUTO_PUBLISH_EN=true` / `AUTO_PUBLISH_RU=true` — **сохранены**
- `DAILY_AI_BUDGET_USD=3.0` — **не увеличен**
- `editorial_voice_version=wegotrip_voice_v3`

## Негативные проверки на production (без публикации)

- Legacy MAX bot URL в payload → HOLD.
- EN injector не добавляет MAX.
- Google Trends не выдумываются (`invented_trends: false` на `wgt russia-demand-refresh`).

## Вердикт аудита

`GO_WITH_CONDITIONS` — продукт задеплоен и живой Chief Editor v3 подтверждён. Условие: новый live-пост с футером ещё не выходил по расписанию (`LIVE_NEW_POST=NOT_YET_OBSERVED`). Trends/Wordstat и живая музейная афиша остаются `UNAVAILABLE` / `PARTIAL`.
