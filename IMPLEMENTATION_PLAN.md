# IMPLEMENTATION_PLAN — WeGoTrip Telegram Content Engine

Рабочий план разработки. Основной источник требований —
`WEGOTRIP_TELEGRAM_CONTENT_ENGINE_CURSOR_SPEC.md`. Здесь фиксируются архитектурные
решения, реальные ограничения внешних API и статус этапов.

Статус чеклиста требований — в `REQUIREMENTS_STATUS.md`.

---

## 1. Текущий stack

Репозиторий был пустым (только `README.md`), поэтому стек выбран с нуля под
требования: интеграция с REST API, cron/background jobs, PostgreSQL и admin UI, при
этом «просто для одного разработчика» (спец. §34, §57).

| Слой | Выбор | Почему |
| --- | --- | --- |
| Язык | Python 3.12 | Быстрая интеграция с HTTP API и OpenAI, богатая экосистема |
| Web / API | FastAPI + Uvicorn | Минимум кода, встроенная валидация, автодоки |
| Admin UI | Jinja2 + серверный рендеринг + один CSS-файл | Нет сборки фронтенда, нет SPA |
| ORM | SQLAlchemy 2.0 (синхронный) | Один и тот же код в API, worker и CLI |
| Миграции | Alembic | Стандарт для SQLAlchemy |
| БД | PostgreSQL 16 (prod), SQLite (локально и в тестах) | JSONB на Postgres, `JSON` на SQLite через `with_variant` |
| Планировщик | APScheduler в процессе worker | Celery/Kafka избыточны для 20–40 статей в сутки |
| Очередь публикаций | Таблица `publication_queue` + idempotency key | Не нужен Redis, идемпотентность на уровне БД |
| HTTP-клиент | httpx | Таймауты, ретраи, удобное тестирование |
| Логи | structlog | Structured logs с обязательными полями из §50 |
| CLI | Typer (`wgt`) | Ручной запуск любого джоба |
| Морфология RU | pymorphy3 | Падежи в русских поисковых запросах |
| Тесты / линт | pytest, ruff, mypy | — |

Зависимости: `pyproject.toml`. Локальный запуск без сети: `.env.local.example`.

---

## 2. Архитектура

```text
WeGoTrip Affiliate API ──▶ CatalogSyncService ──▶ нормализованный каталог (per market)
                                                        │
                                        KeywordClusterRegistry (YAML, per entity type)
                                                        │
                                            TopicDiscoveryService (scoring + dedup)
                                                        │
                                                ProductSelector (ранжирование кодом)
                                                        │
                                                  ContextBuilder (structured JSON)
                                                        │
                       BudgetManager ◀── LLMGateway ──▶ ArticleWriter (Terra)
                                                        │
                                     claim scan → FactResearchService (web search, Luna)
                                                        │
                                            strip_unverified (VERIFY OR OMIT)
                                                        │
                                              ArticleCritic (Luna) + QualityGate
                                                        │
                                        RichMessageRenderer + TelegramProductCardRenderer
                                                        │
                                       ArticleWorkflow (review → test → approve → publish)
                                                        │
                                     TelegramPublisher (idempotent) ──▶ @wegotrip / @wegotrip_ru
                                                        │
                                        TrackingService (/r/<token>) → AnalyticsService
```

Ключевое правило: **LLM не формирует Telegram-разметку и не создаёт ссылки**. Модель
возвращает Article JSON; рендерер и `AffiliateLinkBuilder` — единственные, кто строит
payload и URL.

---

## 3. Модули

| Модуль | Ответственность |
| --- | --- |
| `app/config.py` | Все настройки, `Settings`, per-market аксессоры |
| `app/errors.py` | Иерархия ошибок, деление на retryable/terminal |
| `app/logging_setup.py` | structlog, `job_context` с полями из §50 |
| `app/db/` | Модели, enum-ы, engine/session, JSONB-варианты |
| `app/catalog/` | HTTP-адаптер Affiliate API, нормализация, mock-провайдер, синхронизация |
| `app/links/affiliate.py` | **Единственный** билдер URL c `coupon=435` и UTM |
| `app/topics/` | Кластеры интентов (YAML), морфология RU, demand, scoring, dedup, discovery |
| `app/ai/` | `LLMProvider`, OpenAI Responses API, mock, model router, budget manager, промпты, цены |
| `app/generation/` | Схема Article JSON, выбор товаров, контекст, claims, верификация, writer, critic, quality gate, pipeline |
| `app/telegram/` | Rich blocks, product cards, media validation, Bot API client, идемпотентный publisher |
| `app/services/` | Ре-рендер сохранённой статьи, editorial workflow |
| `app/analytics/` | Tracking-ссылки, клики, отчёты и KPI |
| `app/scheduler/` | Джобы и APScheduler |
| `app/admin/` | Admin UI и HTML-превью Rich Message |
| `app/api/` | `/r/<token>`, `/api/stats`, health |
| `app/cli.py` | `wgt` |

---

## 4. Структура БД

Все таблицы из §37 реализованы (миграция `migrations/versions/*_initial_schema.py`).

**Каталог** (каждая строка принадлежит одному рынку — уникальность `(market, external_id)`):
`markets`, `countries`, `cities`, `attractions`, `categories`, `collections`, `products`,
`product_categories`, `product_collections`, `product_attractions`, `product_media`,
`catalog_snapshots`, `sync_runs`.

**Поиск и темы:** `keyword_clusters`, `query_candidates`, `search_demand_snapshots`,
`topic_candidates`.

**Статьи:** `articles`, `article_versions`, `article_claims`, `article_sources`,
`article_products`, `article_media`.

**Публикация:** `publication_queue`, `telegram_publications`.

**Аналитика:** `tracking_links`, `click_events`, `conversion_events`.

**AI:** `llm_runs`, `cost_ledger`, `budget_reservations`, `prompt_versions`,
`verified_fact_cache`, `system_settings`.

Крупные payload-ы (API snapshot, Article JSON, rendered message) хранятся в JSONB.

---

## 5. Внешние интеграции и реальные ограничения API

### 5.1. WeGoTrip Affiliate API

Проверено на живом API 2026-08-27 (`app/catalog/wegotrip.py` содержит ту же таблицу):

| Endpoint | Версия | Особенности |
| --- | --- | --- |
| `/currencies/` | v2 | обёрнут в `data` |
| `/countries/` | v2 | обёрнут; локализация через `Accept-Language` |
| `/cities/` | v2 | `lang` меняет и названия, и `itemsCount` (EN 698 городов, RU 395) |
| `/attractions/` | v2 | фильтры `city` / `country` работают |
| `/products/popular/` | v2 | `lang`, `city`, `country`, `attraction`, `currency` |
| `/products/{id}/` | v2 | отдаёт канонический `url`, `categories`, `subcategories`, `attractions` |
| `/products/{id}/reviews/` | v2 | обёрнут |
| `/search/` | v2 | обёрнут |
| `/languages/` | — | **404 на v2 и v3** |
| `/attractions/` (v3) | v3 | ответ без обёртки `data`, **фильтр `city` игнорируется** |

**Зафиксированные ограничения (не выдуманы, задокументированы):**

1. `/languages/` недоступен → `get_languages()` возвращает сконфигурированный список
   рынков и логирует причину.
2. Отдельного endpoint для **категорий** нет → категории собираются из
   `product.categories` при загрузке деталей товара.
3. Отдельного endpoint для **Collections** нет → `Collection = normalized subcategory`
   (`product.subcategories`). Интерфейс `CollectionProvider` заведён на будущее.
4. **Audio preview URL не документирован и не отдаётся.** Есть только метаданные
   (`types.audioguide`, `tour.mediaSize`, `tour.eventsCount`). Введён
   `AudioPreviewProvider`; по умолчанию `NullAudioPreviewProvider` возвращает `None`,
   рендерер просто не вставляет audio-блок. URL не угадываются.
5. ID городов — geonames-подобные (Париж = `2988507`), примеры из документации (`city=3`)
   устарели.
6. Конверсий/заказов в Affiliate API нет → `conversion_events` наполняется импортом
   (`wgt import-conversions file.csv`).

### 5.2. Telegram Bot API

Проверено по актуальной документации: Rich Messages появились в Bot API 10.0,
`sendRichMessage` и `InputRichBlock*` существуют, лимиты — 32768 символов, 500 блоков,
50 медиа, 20 колонок в таблице, 16 уровней вложенности. Реализованы в
`app/telegram/blocks.py` вместе с валидатором. Никаких userbot-ов.

### 5.3. OpenAI

Responses API (`POST /v1/responses`) со structured outputs (`text.format.json_schema`,
`strict: true`) и инструментом `web_search`. Цены на 2026-08-27:

| Модель | Input $/MTok | Output $/MTok | Роль |
| --- | --- | --- | --- |
| `gpt-5.6-terra` | 2.00 | 12.00 | writer |
| `gpt-5.6-luna` | 0.20 | 1.20 | classification, claims, research, critic |
| `gpt-5.6-sol` | 4.00 | 20.00 | escalation (только 3-я попытка) |

Неизвестная модель получает пессимистичную оценку $4/$20, чтобы бюджет не «протёк».

---

## 6. Background jobs

| Джоба | Расписание (UTC) | Что делает |
| --- | --- | --- |
| `sync_catalog` | 02:00 | Синхронизация EN и RU каталогов, snapshot-ы, деактивация исчезнувших товаров |
| `discover_topics` | 03:00 | Кандидаты тем по всем уровням каталога, скоринг, дедупликация, отчёт о покрытии |
| `generate_daily_articles` | 04:00, 10:00, 16:00 | Генерация в рамках дневного бюджета; останавливается, если материал исчерпан |
| `schedule_publications` | 05:30, 11:30, 17:30 | Распределение публикаций по окну 10:00–21:00 МСК |
| `process_publication_queue` | каждые 5 мин | Публикация того, что подошло по времени |
| `cleanup_expired` | каждые 30 мин | Освобождение зависших budget-резерваций, деактивация мёртвых товаров |

Все джобы идемпотентны и запускаются вручную: `wgt <command>` или Admin → Ops.

---

## 7. Telegram publishing flow

```text
Article JSON ──▶ RichMessageRenderer ──▶ validate_rich_message
                                              │
                       publish_test ──▶ TELEGRAM_TEST_CHANNEL
                                              │
                             approve ──▶ schedule (spacing) ──▶ publication_queue
                                              │
                     TelegramPublisher.claim → sendRichMessage → telegram_publications
```

Идемпотентность: ключ `article:<id>:v<version>:<target>` уникален и в очереди, и в
`telegram_publications`. Перед отправкой publisher проверяет существующую публикацию и
захватывает строку очереди блокировкой. Таймаут трактуется как «неизвестный исход» —
строка остаётся захваченной, повторная отправка не выполняется.

---

## 8. AI generation flow

```text
Topic → ProductSelector → ContextBuilder → BudgetManager.reserve
      → ArticleWriter (Terra, structured JSON)
      → scan_document (детерминированный сканер claims)
      → FactResearchService (web search, только для volatile claims)
      → strip_unverified (VERIFY OR OMIT)
      → ArticleCritic (Luna)
      → QualityGate (technical / content / factual / search)
      → media validation → RichMessageRenderer → draft
```

До 3 попыток; на 3-й разрешена эскалация на Sol, если бюджет позволяет. Каждая попытка
получает список конкретных замечаний предыдущей.

---

## 9. Factual verification flow

Два независимых слоя:

1. **Детерминированный сканер** (`app/generation/claims.py`) — двуязычные паттерны для
   часов работы, выходных, цен, выставок, ограничений, транспорта, доступности,
   skip-the-line, расписаний, адресов и числовых фактов с единицами измерения.
   Работает, даже если модель забыла объявить claim.
2. **LLM-экстрактор** (`CLAIM_EXTRACTOR`) — вторая пара глаз.

Числа, которые дословно есть в `catalog_facts` из API, помечаются как
`wegotrip_api` и не требуют проверки. Остальное уходит в `FactResearchService`:
web search на дешёвой модели, приоритет источников по §14, тир источника считается по
домену. `verified` ставится только при наличии URL, приемлемого тира и confidence ≥ 0.7.
Всё непроверенное **удаляется** вместе с предложением, а не смягчается.

Verified evergreen-факты кешируются в `verified_fact_cache` с TTL по категории
(часы работы — 7 дней, текущие выставки — 3 дня, исторические — год).

---

## 10. Analytics

Цепочка: `article → product card/button → /r/<token> → WeGoTrip → order`.

`tracking_links` уникальны по `(article, product, placement)`; редирект считает клики и
уникальных посетителей (SHA-256 от IP+UA, сырой IP не хранится). Целевой URL всегда
содержит `coupon=435` и UTM — атрибуция не теряется, даже если редирект обойдут.

Заказы/GMV импортируются CSV-командой, потому что Affiliate API их не отдаёт.
`AnalyticsService.entity_performance()` даёт сигнал обратной связи для будущего
взвешивания тем.

---

## 11. Budget control

`DAILY_AI_BUDGET_USD=3.00` — жёсткий и единственный предел. Он покрывает LLM, web search
и генерацию изображений.

* `cost_ledger` — фактические расходы по данным `usage` из API, не прогноз. Стоимость
  статьи читается обратно из ledger-а, чтобы она не расходилась с реально потраченным.
* `budget_reservations` — холд перед джобой генерации; зависшие резервации истекают за 45 минут.
* `plan_daily_generation()` — сначала минимумы (10 EN + 10 RU) по одной статье
  поочерёдно, чтобы ни один рынок не голодал, затем весь остаток бюджета.
* Потолка по количеству нет: `EN_ARTICLES_MAX_PER_DAY=0` означает «без потолка».
  Оператор может вернуть лимит, поставив любое число больше нуля.
* `can_start_article()` — отказ, если прогноз превышает остаток минус запас.
* Публикация уже готовых статей бюджетом не блокируется.

Оценка при 12k символов контекста и 10k символов вывода ≈ $0.05–0.09 на статью, то есть
$3 хватает примерно на 45–55 статей в сутки суммарно по двум рынкам.

## 11.1. Расписание публикаций и исчерпание материала

**Растянутая публикация.** Окно задаётся в локальных часах `PUBLISH_TIMEZONE`
(по умолчанию `Europe/Moscow`, 10:00–21:00). В БД всё хранится в UTC, конверсия делается
только в двух функциях планировщика, поэтому переход на летнее время в других зонах
ничего не ломает. Интервал считается как «оставшееся окно / (количество постов − 1)» и
не бывает плотнее `MIN_POST_INTERVAL_MINUTES`; лишнее переносится в окно следующего дня.
`schedule_publications` запускается несколько раз в сутки и учитывает уже
запланированное, чтобы не умножать дневную норму.

**Исчерпание материала.** `MIN_TOPIC_SCORE` — пол качества для генерации.
`select_topics_for_generation()` не возвращает ничего ниже порога, а
`assess_coverage()` (`app/topics/coverage.py`) объясняет, почему тем не осталось: пустой
каталог, только слабые кандидаты, или всё уже описано. Дневные цифры трактуются как
потолок, а не как обязательство: движок не понижает порог, не ослабляет `min_inventory`
и не берёт сущность со слабым интентом ради нормы. Событие `topics.exhausted` попадает в
лог, в отчёт джобы и на дашборд. Новый материал появляется сам после `sync_catalog`.

---

## 12. Этапы реализации

| Этап | Состав | Статус |
| --- | --- | --- |
| 1. Foundation | Структура, конфиг, БД, миграции, Docker, логи, ошибки | ✅ |
| 2. Catalog | API-адаптер, нормализация, EN/RU, все уровни каталога, `AffiliateLinkBuilder`, sync | ✅ |
| 3. Topic Engine | Кластеры интентов, морфология RU, demand, scoring, dedup, календарь | ✅ |
| 4. AI Generation | Provider, router, budget, writer, claims, verification, critic | ✅ |
| 5. Telegram | Rich blocks, product cards, media, audio, кнопки, test-канал, edit, идемпотентность | ✅ |
| 6. Editorial | Draft, preview, approve/reject, regenerate, schedule, publish, auto-publish | ✅ |
| 7. Analytics | Tracking URLs, клики, заказы, GMV, cost, feedback | ✅ (заказы — импортом) |
| 8. Production readiness | Тесты, мониторинг, ретраи, rate limits, scheduler, документация, security, деплой | ✅ |

---

## 13. Принятые архитектурные решения

1. **Синхронный SQLAlchemy.** Нагрузка — десятки статей в сутки; синхронный код проще
   для джоб, CLI и одного разработчика.
2. **Никакого Celery/Redis.** Очередь публикаций — обычная таблица с idempotency key и
   блокировкой строки. Меньше движущихся частей, идемпотентность гарантирована БД.
3. **Каталог хранится per market.** Один и тот же `external_id` существует и в EN, и в
   RU с разными названиями и глубиной ассортимента; смешивать их нельзя (§3).
4. **`Collection = subcategory`.** Модель и провайдер заведены отдельно, чтобы будущий
   реальный endpoint подключался без изменения бизнес-логики.
5. **Дедупликация без эмбеддингов от API.** Хешированные символьные n-граммы дают
   semantic-like похожесть офлайн и бесплатно — дедупликация не тратит AI-бюджет.
6. **Морфология вместо перевода.** RU-паттерны объявляют падеж (`{entity:loct}`), а
   pymorphy3 склоняет название. Это отдельный рынок, а не перевод EN.
7. **Детерминированный сканер фактов первым.** Нельзя полагаться на то, что модель сама
   объявит все проверяемые утверждения.
8. **Рендерер владеет всеми URL.** Writer физически не видит ссылок, а `_strip_urls`
   вычищает всё, что он попытался написать сам.
9. **Tracking-редирект включаем флагом.** `USE_TRACKING_REDIRECT=true` по умолчанию;
   целевой URL всегда содержит `coupon=435`, так что маркировка не зависит от редиректа.
10. **Mock-провайдеры каталога и LLM.** Весь pipeline запускается офлайн, без ключей и
    без расходов — это делает возможными интеграционные тесты в CI.
11. **Дневные цифры — потолок, а не обязательство.** Единственный жёсткий лимит —
    бюджет. Количество статей ограничивается деньгами и наличием материала, а не
    произвольным числом, иначе система начнёт добирать норму слабыми темами.
12. **Окно публикаций в локальном времени.** Хранение в UTC, конверсия в
    `PUBLISH_TIMEZONE` только в планировщике: «10:00 по Москве» остаётся 10:00 по Москве
    круглый год.
13. **Деплой — один droplet с docker compose.** Postgres, api, worker и Caddy рядом.
    App Platform поддержан через `.do/app.yaml` для тех, кто не хочет SSH.

---

## 14. Риски

| Риск | Митигация |
| --- | --- |
| Schema drift в Affiliate API | `CatalogSchemaError`, нормализация терпима к отсутствующим полям, фикстуры перезахватываются скриптом |
| `sendRichMessage` может отличаться в проде от документации | Payload валидируется локально; `TELEGRAM_DRY_RUN=true` и обязательный тест-канал до продакшена |
| Рост цен OpenAI | Цены — данные в `app/ai/pricing.py`; неизвестная модель считается дорогой |
| Неверная верификация факта | Тир источника + порог confidence + `MIN_FACTUALITY_SCORE=0.97`; при сомнении факт удаляется |
| Telegram 429 | `TelegramRateLimited` с `retry_after`, повторная постановка в очередь, лимит 0.25 rps на канал |
| Дубликат публикации при таймауте | Таймаут = «неизвестный исход»: строка остаётся захваченной, повтор не выполняется |
| Каннибализация тем | Три слоя дедупликации + penalty в скоринге |
| Исчезновение товара между генерацией и публикацией | `refresh_article_products` перед публикацией, ре-рендер без мёртвого товара |
| Бюджет «протекает» из-за неизвестной модели | Пессимистичная цена по умолчанию + резервации + safety margin |

---

## 15. Неизвестные и открытые вопросы

1. **Audio preview.** Нужен ли отдельный endpoint/поле в Affiliate API. Пока
   `AudioPreviewProvider` возвращает `None`; модель данных и рендерер готовы.
2. **Реальный demand-провайдер.** Сейчас только эвристика с confidence ≤ 0.55 и
   `demand_source="heuristic"`. Интерфейс `SearchDemandProvider` готов под DataForSEO
   или внутренние SEO-данные WeGoTrip.
3. **Импорт заказов.** Формат выгрузки партнёрского кабинета не известен; сделан
   универсальный CSV-импортёр и таблица `conversion_events`.
4. **Права бота в каналах.** Нужно вручную выдать боту admin-права в `@wegotrip`,
   `@wegotrip_ru` и тест-канале; `wgt check-telegram` это проверяет.
5. **Точная цена web-search вызова.** Заложено $0.01 за вызов
   (`WEB_SEARCH_CALL_USD`); при уточнении меняется одной строкой.
6. **Country-статьи на mock-фикстурах.** В офлайн-наборе слишком мало товаров с
   country-привязкой, поэтому country-темы отсекаются порогом `min_inventory=12`. На
   полном каталоге порог достигается.

---

## 16. Ограничения, зафиксированные как TODO

TODO допускаются только для внешне заблокированных или явно необязательных вещей:

* подключить реальный keyword/SEO-провайдер, когда появится доступ;
* подключить audio preview, если Affiliate API начнёт его отдавать;
* заменить CSV-импорт заказов на API партнёрского кабинета, когда он появится;
* генерация обложек (`ALLOW_GENERATED_COVERS`) реализована как контролируемое
  исключение и по умолчанию выключена.
