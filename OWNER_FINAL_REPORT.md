# Итог: WeGoTrip Editorial Engine v3.0

**Вердикт:** GO_WITH_CONDITIONS  
**Production:** confirmed  
**Repo commit / PR / deployment:** `00bbe9b` · [PR #12](https://github.com/avgolovatyy-code/telegram-articles/pull/12) · CI run 40757555872 success  
**Deployed at:** 28 октября 2026, 22:52 Europe/Moscow  
**Проверено:** 28 октября 2026, 22:57 Europe/Moscow

## Реально реализовано и работает

- Editorial Engine 3.0 на существующем droplet `/opt/wegotrip-content-engine`, SHA совпадает с PR.
- Миграция `c8f9a0b1d2e3` применена (слоты: mechanic/axis/geo/channel_targets + таблица спроса РФ).
- Живой OpenAI Chief Editor v3: RU и EN, модель `gpt-5.6-luna`, не mock. Стоимость прогона ~$0.011 из лимита $3, бюджет не поднимался.
- Футер в production-коде: TG RU → MAX, MAX → Telegram RU, EN без футера. Legacy MAX URL → HOLD.
- Спрос РФ: 10 наблюдений АТОР/РСТ, `organized_tour_sales` ≠ `hotel_bookings`.
- Каналы и брендинг уже соответствуют approved copy; пины не дублировались.
- `healthz` публично `ok`. Worker со scheduler включён, API scheduler выключен (как и задумано).

## Три канала

- **TG RU** (`https://t.me/wegotrip_ru`) — title/description match, `.ru` в описании, pin на месте. План 2026-11-01: `weekend_utility` / `ru_local_leisure` / `["telegram_ru","max_ru"]`. Футер в следующем Engine-посте.
- **TG EN** (`https://t.me/wegotrip`) — original English title/description, `.com`, без MAX. Слоты только `telegram_en`.
- **MAX RU** (`https://max.ru/channel_wegotrip`) — type=channel, slug match, title тот же RU. Футер на Telegram в рендерере. Не создавали новый канал.

Последний live RU пост (Дубай, article 4094) вышел в 22:08 MSK, **до** деплоя 22:52. Новых публикаций после выкладки не делали специально.

## Проверки

- Автотесты: **283 passed**; ruff/mypy/alembic — pass; CI GitHub — pass.
- Live: `wgt doctor` (openai_responses ok, telegram live, max enabled, coupon 435), `wgt check-max`, `wgt check-telegram`, getChat, dry-run футера.
- PASS по H1–H6, H8–H12. H7: рендерер PASS, live-пост с футером ещё не наблюдался.
- SOURCE-03 Trends: `UNAVAILABLE` (честно, объёмы не выдуманы).
- SOURCE-02 музейная афиша: `PARTIAL`.

## Редакционные примеры

- **RU (live plan):** «разбавляем лондонский кластер локальными» — тезис Chief Editor 22:56 MSK; слот Казань/выходные механика Gorbilet (`weekend_utility`).
- **EN (live plan):** independent international mix; слот `short_fact_plus_use` только в Telegram EN.
- **MAX:** не отдельный SQL-market; попадает в RU-слоты с `max_ru` в `channel_targets` и аудиенс-гейтом жителей России.
- Dry-run 36 черновиков: `EDITORIAL_SAMPLE_REVIEW.md`, `audit/v3/demo_plan.json` — **не публиковались**.

## Недостатки / блокеры

1. `LIVE_NEW_POST=NOT_YET_OBSERVED` — футер на реальной публикации ещё не снят с канала; следующий штатный слот (не dummy).
2. Нет живого Google Trends / Wordstat (нужна отдельная авторизация источника).
3. Нет легального live API музейных афиш.
4. Старые слоты до v3 могут иметь пустые `channel_targets` / mechanic — MAX fan-out по legacy-правилу, пока Chief Editor не перепишет слот.
5. `ENABLE_HASHTAGS` на проде выключен по спецификации (было true). Автопубликация не трогалась.

## Что нужно сделать владельцу

Ничего обязательного для самого релиза: деплой уже на production. По желанию — открыть ближайший пост в TG RU и MAX и убедиться глазами в кликабельном футере, когда он выйдет по расписанию. Merge PR #12 в базовую ветку, когда будете готовы зафиксировать историю (на droplet уже эта ветка).
