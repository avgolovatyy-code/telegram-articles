# REQUIREMENTS_STATUS

Чеклист по всей спецификации `WEGOTRIP_TELEGRAM_CONTENT_ENGINE_CURSOR_SPEC.md` и по
дополнительным требованиям из задания.

Легенда: `[x]` — сделано, `[~]` — сделано в объёме, доступном без внешних данных,
`[ ]` — не сделано (с причиной).

Обновлено: 2026-08-27.

---

## Foundation

- [x] Структура проекта, пакеты, точки входа
- [x] Конфигурация через `.env` / `Settings` (`app/config.py`)
- [x] `.env.example` и офлайн-профиль `.env.local.example`
- [x] PostgreSQL как прод-БД, SQLite для локальной разработки и тестов
- [x] Alembic-миграции (`migrations/`), проверены upgrade и downgrade
- [x] Docker + docker-compose (db, migrate, api, worker)
- [x] Structured logging со всеми полями из §50 (`job_id`, `article_id`, `topic_id`, `market`, `entity_type`, `entity_id`, `operation`, `model`, `cost_usd`, `duration_ms`, `status`, `error`)
- [x] Иерархия ошибок с делением retryable/terminal (`app/errors.py`)
- [x] CLI `wgt` для всех джоб

## Catalog (§4–§6)

- [x] Countries
- [x] Cities
- [x] Attractions
- [x] Categories (выводятся из `product.categories` — отдельного endpoint нет)
- [x] Collections (`Collection = normalized subcategory`, §4)
- [x] Products
- [x] Images (product cover/preview/images, city preview, attraction preview)
- [~] Audio previews — модель данных, `AudioPreviewProvider` и рендер-блок готовы; Affiliate API не отдаёт playable URL, поэтому блок не вставляется. URL не угадываются (§29)
- [x] Inventory synchronization (`sync_catalog`, `last_seen_at`, деактивация исчезнувших товаров)
- [x] `WeGoTripCatalogProvider` как единый интерфейс
- [x] Mock-провайдер на реальных зафиксированных payload-ах для офлайн-разработки
- [x] `catalog_snapshots` для аудита фактов
- [x] Product может относиться к стране, городу, нескольким attractions, categories и collections
- [x] Отсутствующие поля хранятся как `null`, а не выдумываются

## EN / RU как два независимых рынка (§3)

- [x] Отдельная синхронизация каталога по `lang`
- [x] Каталог хранится per market: уникальность `(market, external_id)`
- [x] Отдельные intent-кластеры EN и RU (не переводы)
- [x] Отдельные темы, статьи и очереди публикаций
- [x] Отдельные каналы `@wegotrip` / `@wegotrip_ru`
- [x] Отдельные домены `wegotrip.com` / `wegotrip.ru` и валюты
- [x] Запрет pipeline «EN → перевод → RU» (промпты, тест `test_no_translation_between_markets`)
- [x] Русская грамматика через падежи в паттернах (`{entity:loct}`) и pymorphy3

## Search Intent Engine (§7, §8)

- [x] `KeywordClusterRegistry` с seed-паттернами в YAML
- [x] Кластеры для всех уровней: country, city, attraction, category, collection, product
- [x] Полная seed-библиотека §8 для EN и RU
- [x] Запросы не захардкожены в бизнес-логике; кластеры редактируются в БД
- [x] `SearchDemandProvider` как интерфейс
- [~] Реальный demand-провайдер отсутствует — используется эвристика, `demand_source="heuristic"`, confidence ≤ 0.55, доля веса перераспределяется (§10)
- [x] `query_candidates` со всеми полями из §7
- [x] `search_demand_snapshots`

## Topic Engine (§9–§11)

- [x] Ежедневная генерация кандидатов по всем уровням каталога
- [x] Round-robin по типам сущностей, чтобы глубокий город не вытеснял остальные уровни
- [x] Topic score с весами из §10, все веса конфигурируемы
- [x] Перераспределение веса demand при отсутствии сигнала
- [x] Duplication penalty и thin-content penalty
- [x] Дедупликация: canonical query, entity+intent key, векторная похожесть
- [x] Cannibalization protection против «Things to do / Best things to do / Top things to do»
- [x] Учёт drafts, scheduled и published статей при дедупликации
- [x] Content calendar: `scheduled_for`, распределение по окну публикаций

## AI (§12, §44, §45, §48)

- [x] `LLMProvider` как абстракция, модель меняется через конфиг
- [x] OpenAI Responses API, structured outputs (`json_schema`, `strict`)
- [x] Model router: writer = Terra, utility = Luna, escalation = Sol только на 3-й попытке
- [x] `OPENAI_WRITER_MODEL` / `OPENAI_UTILITY_MODEL` / `OPENAI_FALLBACK_MODEL` / `OPENAI_REVIEW_MODEL`
- [x] Версионированные промпты, сохраняются в `prompt_versions`
- [x] `llm_runs` с моделью, версией промпта, токенами, tool calls, стоимостью, длительностью
- [x] Cost optimizations §48: компактный product payload, Luna для bulk, кеш verified facts, web search только для volatile claims, фактический usage
- [x] Mock-провайдер для офлайн-разработки и CI

## Budget control (§13)

- [x] Жёсткий лимит `DAILY_AI_BUDGET_USD=3.00`
- [x] Учёт input/output токенов, кешированного ввода, web-search вызовов, генерации изображений
- [x] Фактическая стоимость по `usage` из API, а не прогноз
- [x] `cost_ledger` и `budget_reservations`
- [x] Rolling average cost/article
- [x] Оценка `projected cost` перед каждой генерацией
- [x] Приоритет: сначала 10 EN + 10 RU, затем рост на весь остаток бюджета
- [x] Round-robin в фазе минимумов, чтобы ни один рынок не голодал
- [x] Потолок по количеству снят: `*_ARTICLES_MAX_PER_DAY=0` — ограничивает только бюджет (уточнение заказчика от 27.08)
- [x] Бюджет никогда не превышается автоматически
- [x] Публикация готовых статей бюджетом не блокируется
- [x] Дашборд с бюджетом, потрачено/остаток, счётчиками EN/RU и средней стоимостью

## Article generation (§14, §15, §21)

- [x] Structured JSON-контекст вместо «напиши статью про Париж»
- [x] Поля контекста: market, primary/secondary queries, entity, catalog_context, catalog_facts, verified_facts, products, allowed_media, brand_style, forbidden_claims, article_constraints
- [x] Товары выбираются кодом до промпта
- [x] LLM видит только выбранные товары и разрешённые медиа
- [x] Article JSON как внутренний формат (§31)
- [x] Отдельный renderer для Telegram
- [x] Целевая длина 4 000–10 000 символов, допустимо 2 500–20 000
- [x] До 3 попыток с конкретной обратной связью, эскалация на Sol

## Factual verification (§16–§18)

- [x] Категории A / B / C: `wegotrip_api`, `verified_external`, `narrative`
- [x] Детерминированный сканер volatile-фактов на EN и RU
- [x] LLM-экстрактор claims как вторая проверка
- [x] Обязательная верификация для opening hours, closing days, цен, ограничений, адресов, расписаний, выставок, транспорта, доступности, skip-the-line, cancellation policy, числовых фактов
- [x] Web search через Responses API
- [x] Приоритет источников §14, тир источника по домену
- [x] `VERIFY OR OMIT`: непроверенное предложение удаляется целиком
- [x] Запрет «правдоподобно заполнить пробел» в промптах и в коде
- [x] Кеш verified evergreen facts с TTL по категории
- [x] Refresh product data перед публикацией, если черновик старше 24 часов

## Claim ledger (§17)

- [x] `article_claims` с claim, типом, категорией, `requires_verification`, статусом, источником, тиром, confidence, временем проверки
- [x] `article_sources` с URL, заголовком и тиром
- [x] API-факты связаны с `product_id` и `api_snapshot_id`
- [x] Критические claims перед публикацией имеют `verified` или удалены
- [x] Ledger виден в admin UI

## Style (§19, §20)

- [x] Правила голоса в промптах EN и RU
- [x] Явные правила юмора и явные запреты (унижение, стереотипы, панибратство, сарказм над пользователем)
- [x] Список запрещённых AI-шаблонов в промптах
- [x] Автоматическая проверка запрещённых фраз в quality gate
- [x] Проверка повторяющихся предложений
- [x] Требование коротких абзацев и одной мысли на абзац

## Search optimization (§22)

- [x] Primary query в title, во вступлении и в heading
- [x] Entity name в первых 300–500 символах (проверяется gate-ом)
- [x] Осмысленные H2/H3
- [x] Secondary queries раскрываются естественно
- [x] Проверка keyword stuffing по плотности сущности
- [x] Ключевая информация не спрятана в изображениях
- [x] Hashtags: `ENABLE_HASHTAGS`, 0–4 штуки, отдельная стратегия нормализации

## Telegram (§23, §24, §26, §30, §40, §41)

- [x] Официальный Bot API, `sendRichMessage`, без userbot-ов
- [x] Rich blocks: heading, paragraph, list, ordered list, quote, expandable quote, pull quote, divider, table, photo, collage, slideshow, audio, voice note, details, buttons, footer, map, anchor
- [x] Валидация лимитов: 32768 символов, 500 блоков, 50 медиа, 20 колонок, 16 уровней
- [x] `TelegramProductCardRenderer`: hero, compact, collection
- [x] Rating / duration / price показываются только если их вернул API
- [x] 1–5 товаров на статью, проверка «не витрина»
- [x] Media validation: доступность, тип, размер, дубликаты, принадлежность сущности
- [x] Test channel `TELEGRAM_TEST_CHANNEL` и обязательная тестовая публикация до продакшена
- [x] Сохранение `chat_id`, `channel_username`, `message_id`, `published_at`, `telegram_response`, `article_version`
- [x] Edit существующего Rich Message для правок
- [x] Idempotency: ключ `article:<id>:v<version>:<target>`, уникален в очереди и в публикациях
- [x] Обработка 429 с `retry_after`
- [x] Таймаут трактуется как неизвестный исход, повторная публикация не выполняется
- [x] `TELEGRAM_DRY_RUN` для проверки payload без отправки

## Affiliate links (§26)

- [x] Единый `AffiliateLinkBuilder`, ручная сборка URL в коде запрещена
- [x] `coupon=435` во всех ссылках
- [x] Корректное добавление к URL с существующим query (через `&`, без дублей `?`)
- [x] Замена устаревшего coupon
- [x] UTM: `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`
- [x] Product, city, country, attraction, category, collection, checkout и landing ссылки
- [x] Канонический `url` из API переиспользуется и переводится на домен рынка
- [x] Проверка маркера в quality gate и в tracking-сервисе
- [x] LLM не генерирует ссылки; `_strip_urls` вычищает попытки

## Media (§27, §28)

- [x] По умолчанию только медиа из WeGoTrip API
- [x] Приоритет обложки: attraction → city → product
- [x] Запрет случайных изображений из Google/Unsplash/Wikimedia
- [x] `ALLOW_GENERATED_COVERS=false` по умолчанию
- [x] Generated cover только как hero, только при отсутствии API-обложки, только в рамках бюджета
- [x] Промпт генерации запрещает изображать узнаваемые объекты, чтобы не вводить в заблуждение
- [x] Стоимость генерации входит в дневной лимит

## Quality gate (§32, §33)

- [x] Technical: валидный JSON, валидный Rich Message, лимиты Telegram, валидные URL, affiliate-маркер, валидные медиа, правильный канал и локаль
- [x] Content: ответ на primary query, отсутствие воды, повторов, шаблонных вступлений, выдуманных товаров, избыточной рекламы
- [x] Factual: у всех volatile claims есть источник, product-факты сверены с API snapshot, цены обновляются перед публикацией
- [x] Search: title соответствует интенту, сущность явно указана, осмысленные заголовки, отсутствие переспама
- [x] LLM critic на дешёвой модели
- [x] `MIN_QUALITY_SCORE=0.88`, `MIN_FACTUALITY_SCORE=0.97`
- [x] При недостаточной factuality публикация блокируется

## Editorial workflow (§34, §39)

- [x] Статусы из §38 полностью
- [x] `REVIEW_MODE` по умолчанию, `AUTO_PUBLISH_EN=false`, `AUTO_PUBLISH_RU=false`
- [x] Approve / reject / regenerate / verify again / edit JSON / publish test / schedule / publish now
- [x] Даже в auto-режиме статья проходит все автоматические gate-ы
- [x] Редактирование Article JSON поднимает версию и сбрасывает idempotency key

## Scheduler (§35, §36)

- [x] От 10 статей в сутки на рынок и столько сверху, сколько позволяет бюджет
- [x] Публикации растянуты на весь день: интервал = оставшееся окно / число постов
- [x] `MIN_POST_INTERVAL_MINUTES` как нижняя граница паузы, а не как фиксированный шаг
- [x] Окно 10:00–21:00 в локальном времени `PUBLISH_TIMEZONE=Europe/Moscow`
- [x] Дневная норма не умножается повторными запусками джобы
- [x] Не поместившееся в окно переносится на следующий день
- [x] Ежедневный `sync_wegotrip_catalog`
- [x] `refresh_article_products` перед публикацией
- [x] Исчезнувший товар убирается из статьи и payload перерисовывается
- [x] Все джобы идемпотентны

## Admin UI (§39)

- [x] Dashboard: размер каталога EN/RU, новые товары, кандидаты тем, черновики, запланированные, опубликованные сегодня, дневной AI-расход, средняя стоимость, ошибки валидации
- [x] Topics: market, entity, intent, primary query, search confidence, inventory depth, score, статус; действия generate / boost / ignore / exclude
- [x] Articles: список с фильтрами, детальная страница
- [x] Article detail: превью, источник, интент, товары, медиа, verified facts с источниками, quality scores, оценочная и фактическая стоимость, Telegram-превью и payload
- [x] Ops: ручной запуск джоб, расписание, очередь публикаций, эффективная конфигурация
- [x] Analytics: KPI, расход по дням, эффективность статей
- [x] HTTP basic auth (включается заданием `ADMIN_PASSWORD`)

## Analytics (§42, §43)

- [x] Сохранение article_id, market, message ID, темы, сущностей, товаров, времени публикации, AI-стоимости
- [x] Все outbound-ссылки трекаются через `/r/<token>`
- [x] Clicks и unique clicks
- [x] `conversion_events` для orders, GMV, revenue
- [x] KPI: сгенерировано, опубликовано, клики, заказы, GMV, revenue, conversion rate, revenue/article, AI cost/article, AI cost/order
- [x] `entity_performance()` как сигнал обратной связи для будущего скоринга
- [~] Автоматический импорт заказов — Affiliate API не отдаёт конверсии; сделан CSV-импорт `wgt import-conversions`

## Error handling (§49)

- [x] WeGoTrip timeout, ретраи с экспоненциальной задержкой и jitter
- [x] Pagination failure
- [x] Product schema change (`CatalogSchemaError`)
- [x] Telegram 429
- [x] Rich Message validation error
- [x] Broken media
- [x] OpenAI timeout
- [x] Tool call failure
- [x] Malformed structured output (`LLMOutputError`)
- [x] Budget exceeded
- [x] Duplicate post
- [x] Stale product
- [x] Failed fact verification
- [x] Rate limits для WeGoTrip и Telegram

## Tests (§51)

- [x] API normalization
- [x] Locale segmentation
- [x] Entity graph
- [x] Category / subcategory mapping
- [x] Affiliate URL builder
- [x] `coupon=435` preservation
- [x] Topic canonicalization
- [x] Deduplication
- [x] Product ranking
- [x] Budget manager
- [x] Fact claim classification
- [x] Rich Message builder
- [x] Media validation
- [x] Telegram channel routing
- [x] Integration: Affiliate API → Catalog → Topic
- [x] Integration: Topic → Products → Article JSON
- [x] Integration: Article → Fact validation
- [x] Integration: Article JSON → Telegram RichMessage payload
- [x] CI никогда не публикует в продакшен-каналы (`TELEGRAM_DRY_RUN=true`, dry-run клиент)
- [x] RU-морфология и грамматичность запросов

## Материал каталога (уточнение заказчика от 27.08)

- [x] Дневные цифры трактуются как потолок, а не как обязательная норма
- [x] `MIN_TOPIC_SCORE` — тема ниже порога не пишется вообще
- [x] `assess_coverage()` различает пустой каталог, только слабые темы и полное покрытие
- [x] Событие `topics.exhausted` в логах, в отчёте джобы и на дашборде
- [x] Порог и `min_inventory` не понижаются ради заполнения нормы
- [x] `wgt coverage` показывает остаток материала и дату последнего нового товара
- [x] Новые темы появляются автоматически после `sync_catalog`

## Деплой (уточнение заказчика от 27.08)

- [x] Пошаговая инструкция `DEPLOY.md` со списком нужных токенов
- [x] Вариант A: droplet + docker compose, Caddy с автоматическим TLS
- [x] Вариант B: App Platform, spec `.do/app.yaml` с managed PostgreSQL
- [x] `deploy/setup-droplet.sh` — провижининг: Docker, файрвол, пользователь, `.env`
- [x] `deploy/update.sh` — обновление с миграциями и проверкой здоровья
- [x] Планировщик работает в отдельном процессе, в API он выключен
- [x] Раздел про то, какие шаги может выполнить только владелец аккаунта

## Security (§46)

- [x] Секреты только в окружении, `.env` в `.gitignore`
- [x] `.env.example` без реальных значений
- [x] `WEGOTRIP_REFERER_ID` как несекретная настройка
- [x] Токены не попадают в логи
- [x] Сырые IP не хранятся — только необратимый хеш
- [x] Docker-образ работает от непривилегированного пользователя
- [x] Опциональная basic-аутентификация admin UI

## Definition of Done (§56)

- [x] EN/RU каталоги разделяются корректно
- [x] Все уровни каталога участвуют в topic discovery
- [x] На каждый entity type свой intent cluster
- [x] Статьи не дублируются
- [x] Writer использует GPT-5.6 Terra
- [x] Utility-задачи используют дешёвую модель
- [x] Dynamic facts проходят верификацию
- [x] Неподтверждённые факты удаляются
- [x] Медиа берётся из WeGoTrip API
- [x] Generated covers выключены по умолчанию и являются контролируемым исключением
- [~] Audio используется только при реальном API audio URL — API его не отдаёт, поддержка готова
- [x] Товары встроены нативными rich blocks
- [x] Все ссылки содержат `coupon=435`
- [x] Публикация идёт Rich Message в правильный канал
- [x] Бюджет никогда автоматически не превышает $3/день
- [x] Система может генерировать 10–20 статей на рынок
- [x] Публикации распределяются равномерно
- [x] Есть test channel
- [x] Есть admin preview
- [x] Есть cost ledger
- [x] Есть article/source/claim traceability

---

## Открытые пункты и причины

| Пункт | Статус | Причина |
| --- | --- | --- |
| Audio preview в статьях | `[~]` | Affiliate API не документирует и не возвращает playable URL. Модель данных, `AudioPreviewProvider` и рендер-блок готовы; URL не угадываются (§29) |
| Реальный demand-провайдер | `[~]` | Нет доступа к DataForSEO или внутренним SEO-данным. Интерфейс готов, эвристика честно помечена `demand_source="heuristic"` |
| Автоматический импорт заказов | `[~]` | В Affiliate API нет endpoint-а конверсий. Реализован CSV-импорт и таблица `conversion_events` |
| Country-статьи на офлайн-фикстурах | `[~]` | В mock-наборе мало товаров с country-привязкой, порог `min_inventory=12` не достигается. На полном каталоге кластеры работают |
| Проверка `sendRichMessage` на живом канале | `[ ]` | Нужен `TELEGRAM_BOT_TOKEN` и права администратора в каналах. Payload валидируется локально; проверка выполняется командой `wgt check-telegram` и публикацией в тест-канал |
| Проверка генерации на живом OpenAI | `[ ]` | Нужен `OPENAI_API_KEY`. Весь pipeline проверен на mock-провайдере, стоимость и лимиты покрыты тестами |
