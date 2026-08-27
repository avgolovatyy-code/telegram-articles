# WeGoTrip Telegram Content Engine

Программируемый publishing-движок: синхронизирует каталог WeGoTrip, находит пересечения
«сущность × поисковый интент × рынок», генерирует статьи через OpenAI, проверяет
изменяемые факты, собирает Telegram Rich Message с нативными карточками товаров и
публикует его в [@wegotrip](https://t.me/wegotrip) и
[@wegotrip_ru](https://t.me/wegotrip_ru), удерживая расход на ИИ в пределах $3 в сутки.

* Спецификация: [`WEGOTRIP_TELEGRAM_CONTENT_ENGINE_CURSOR_SPEC.md`](WEGOTRIP_TELEGRAM_CONTENT_ENGINE_CURSOR_SPEC.md)
* План и архитектурные решения: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)
* Статус требований: [`REQUIREMENTS_STATUS.md`](REQUIREMENTS_STATUS.md)
* Деплой на DigitalOcean: [`DEPLOY.md`](DEPLOY.md)

---

## Что делает система

```text
Affiliate API → каталог (EN и RU раздельно) → темы по интентам → выбор товаров кодом
→ OpenAI (structured JSON) → проверка фактов → quality gate → Rich Message
→ ревью → тест-канал → продакшен → клики и стоимость
```

Пять правил, вокруг которых построен весь код:

1. **EN и RU — два независимых рынка.** Никаких переводов: свои товары, свои города,
   свои интенты, свои формулировки, свой канал.
2. **Модель не пишет ссылки и не пишет разметку.** Она возвращает Article JSON;
   `AffiliateLinkBuilder` и `RichMessageRenderer` делают всё остальное.
3. **VERIFY OR OMIT.** Изменяемый факт публикуется только с подтверждённым источником,
   иначе предложение удаляется целиком.
4. **Только медиа из WeGoTrip API.** Сгенерированная обложка — выключенное по умолчанию
   исключение.
5. **$3 в сутки — единственный предел.** Расход считается по фактическому `usage`,
   перед каждой генерацией резервируется бюджет. Потолка по числу статей нет: сколько
   влезает в бюджет, столько и пишется.
6. **Материал не выдумывается.** Когда в каталоге не остаётся тем выше порога качества,
   движок останавливается и говорит об этом, а не добирает норму слабыми статьями.

---

## Быстрый старт без ключей и без сети

Весь pipeline работает офлайн на зафиксированных ответах Affiliate API и на mock-модели.

```bash
make install                      # venv + зависимости
cp .env.local.example .env        # офлайн-профиль
.venv/bin/alembic upgrade head
.venv/bin/wgt seed                # рынки, кластеры интентов, версии промптов
.venv/bin/wgt sync-catalog
.venv/bin/wgt discover-topics
.venv/bin/wgt generate --max-articles 3
make run                          # http://localhost:8000/admin
```

В админке будут черновики с превью Telegram-сообщения, карточками товаров, ledger-ом
claims и стоимостью каждой статьи.

## Запуск с реальными сервисами

```bash
cp .env.example .env              # заполнить OPENAI_API_KEY и TELEGRAM_BOT_TOKEN
docker compose up -d              # postgres + миграции + api + worker
docker compose exec api wgt seed
docker compose exec api wgt doctor
docker compose exec api wgt check-telegram
```

Бот должен быть администратором в `@wegotrip`, `@wegotrip_ru` и в тест-канале.
`wgt check-telegram` это проверяет.

---

## Команды

| Команда | Что делает |
| --- | --- |
| `wgt seed` | Рынки, кластеры интентов, версии промптов |
| `wgt sync-catalog [--market en\|ru]` | Синхронизация каталога |
| `wgt discover-topics` | Кандидаты тем со скорингом и дедупликацией |
| `wgt generate [--max-articles N]` | Генерация в рамках дневного бюджета |
| `wgt schedule` | Распределение публикаций по суткам |
| `wgt publish-queue` | Публикация того, что подошло по времени |
| `wgt publish-test <article_id>` | Публикация одной статьи в тест-канал |
| `wgt cycle` | sync → discover → generate → schedule |
| `wgt budget` | Бюджет на сегодня и план генерации |
| `wgt coverage` | Сколько материала в каталоге ещё не описано |
| `wgt check-telegram` | Проверка токена и доступа к каналам |
| `wgt telegram-chats` | Показать id каналов, включая приватные без `@username` |
| `wgt import-conversions file.csv` | Импорт заказов из партнёрского кабинета |
| `wgt doctor` | Проверка конфигурации и подключения к БД |
| `wgt worker` | Планировщик в foreground |

---

## Admin UI

| Раздел | Содержимое |
| --- | --- |
| `/admin` | Каталог EN/RU, кандидаты, черновики, запланированные, опубликованные, дневной расход, средняя стоимость статьи |
| `/admin/topics` | Темы с фильтрами; действия generate / boost / ignore / exclude |
| `/admin/articles` | Список статей с фильтрами по рынку и статусу |
| `/admin/articles/{id}` | Превью Telegram, товары, медиа, claim ledger с источниками, quality scores, стоимость; approve / reject / regenerate / verify / publish test / schedule / publish |
| `/admin/articles/{id}/payload` | Готовый payload `sendRichMessage` и все исходящие ссылки |
| `/admin/analytics` | KPI, расход по дням, эффективность статей |
| `/admin/ops` | Ручной запуск джоб, расписание, очередь публикаций, эффективная конфигурация |

Basic-аутентификация включается заданием `ADMIN_PASSWORD`.

---

## Ключевые настройки

Полный список — в [`.env.example`](.env.example).

```env
WEGOTRIP_REFERER_ID=435          # маркер coupon=435 во всех ссылках
TELEGRAM_EN_CHANNEL=@wegotrip
TELEGRAM_RU_CHANNEL=@wegotrip_ru
TELEGRAM_TEST_CHANNEL=           # обязателен перед первой продакшен-публикацией

OPENAI_WRITER_MODEL=gpt-5.6-terra
OPENAI_UTILITY_MODEL=gpt-5.6-luna
OPENAI_FALLBACK_MODEL=gpt-5.6-sol

DAILY_AI_BUDGET_USD=3.00         # жёсткий предел, больше ничего не ограничивает
EN_ARTICLES_MIN_PER_DAY=10       # приоритетный минимум
RU_ARTICLES_MIN_PER_DAY=10
EN_ARTICLES_MAX_PER_DAY=0        # 0 = без потолка, ограничивает только бюджет
RU_ARTICLES_MAX_PER_DAY=0

PUBLISH_TIMEZONE=Europe/Moscow   # окно публикаций 10:00–21:00 по Москве
PUBLISH_WINDOW_START_HOUR=10
PUBLISH_WINDOW_END_HOUR=21
MIN_POST_INTERVAL_MINUTES=20     # только нижняя граница паузы между постами

AUTO_PUBLISH_EN=false            # режим ревью по умолчанию
AUTO_PUBLISH_RU=false
ALLOW_GENERATED_COVERS=false     # контролируемое исключение

MIN_QUALITY_SCORE=0.88
MIN_FACTUALITY_SCORE=0.97
MIN_TOPIC_SCORE=0.25             # ниже порога темы не пишутся вообще
ENABLE_HASHTAGS=true
```

Смена модели или её цены — это правка конфигурации и таблицы цен
(`app/ai/pricing.py`), бизнес-логику переписывать не нужно.

---

## Структура

```text
app/
├── config.py            настройки
├── errors.py            иерархия ошибок
├── logging_setup.py     structured logs
├── media_assets.py      MediaCandidate
├── db/                  модели, enum-ы, engine
├── catalog/             Affiliate API, нормализация, mock, синхронизация
├── links/affiliate.py   единственный билдер URL с coupon=435
├── topics/              кластеры интентов (YAML), морфология RU, скоринг, дедуп, discovery
├── ai/                  провайдеры, роутер моделей, бюджет, промпты, цены
├── generation/          Article JSON, выбор товаров, claims, верификация, writer, critic, gate
├── telegram/            rich blocks, product cards, media, Bot API, publisher
├── services/            рендер сохранённой статьи, editorial workflow
├── analytics/           tracking, отчёты
├── scheduler/           джобы и APScheduler
├── admin/               UI
└── api/                 /r/<token>, /api/stats, health
```

---

## Разработка

```bash
make check      # ruff + mypy + pytest
make test
make lint
make migrate
make revision m="описание"
```

Тесты (143 штуки) покрывают нормализацию API, разделение рынков, `coupon=435`, русскую
морфологию, дедупликацию, ранжирование товаров, бюджет, классификацию фактов,
VERIFY-OR-OMIT, сборку Rich Message, валидацию медиа, маршрутизацию каналов,
расписание публикаций, идемпотентность и полный сквозной цикл для EN и RU.

Тесты никогда не ходят в сеть и никогда не публикуют в продакшен-каналы: используются
mock-провайдер каталога, mock-модель и dry-run Telegram-клиент.

Фикстуры каталога перезахватываются с живого API:

```bash
.venv/bin/python scripts/capture_fixtures.py
```

---

## Как работает суточный цикл

`worker` держит расписание: синхронизация каталога в 02:00 UTC, поиск тем в 03:00,
генерация в 04:00 / 10:00 / 16:00, распределение публикаций в 05:30 / 11:30 / 17:30,
очередь публикаций каждые 5 минут.

**Публикация растянута на день.** Окно — 10:00–21:00 по Москве. Статьи генерируются
пачками, но выходят поштучно: интервал считается как «оставшееся окно / количество
постов» и не бывает плотнее `MIN_POST_INTERVAL_MINUTES`. Что не поместилось сегодня,
переносится на завтра.

**Ограничивает только бюджет.** Сначала финансируются минимумы 10 EN + 10 RU по очереди,
затем на остаток пишется столько статей, сколько влезает в $3. При средней цене около
$0.05 за статью это порядка 45–55 статей в сутки суммарно.

**Материал не выдумывается.** Когда сочетаний «сущность × интент» выше `MIN_TOPIC_SCORE`
не остаётся, движок останавливается, пишет `topics.exhausted` в лог и показывает это на
дашборде. Порог не понижается, слабые темы не берутся. Новые темы появляются сами, когда
`sync_catalog` увидит в Affiliate API новые товары. Остаток материала: `wgt coverage`.

## Деплой

Пошаговая инструкция для DigitalOcean — в [`DEPLOY.md`](DEPLOY.md): вариант с droplet и
Docker Compose (`deploy/`) и вариант с App Platform (`.do/app.yaml`).

Кратко, если разворачиваете куда-то ещё:

1. PostgreSQL 16 и переменные окружения из `.env.example`.
2. `alembic upgrade head`.
3. `uvicorn app.main:app` за реверс-прокси с TLS. Публичный адрес нужен для трекинга
   кликов `/r/<token>` — он задаётся в `TRACKING_BASE_URL`.
4. Отдельный процесс `wgt worker` для планировщика (в API-процессе выключите его через
   `SCHEDULER_ENABLED=false`, чтобы джобы не запускались дважды).
5. Первый запуск: `wgt seed`, `wgt sync-catalog`, `wgt discover-topics`, `wgt generate`.
6. Опубликуйте несколько статей в тест-канал, проверьте вёрстку, и только потом
   включайте `AUTO_PUBLISH_EN` / `AUTO_PUBLISH_RU`.

### Безопасность

* Секреты только в окружении; `.env` в `.gitignore`.
* `WEGOTRIP_REFERER_ID=435` — не секрет.
* Контейнер работает от непривилегированного пользователя.
* Сырые IP не хранятся: клики привязаны к необратимому хешу.
* Админку закрывайте `ADMIN_PASSWORD` и не выставляйте наружу без TLS.

---

## Известные ограничения внешних API

| Ограничение | Как обработано |
| --- | --- |
| `/languages/` отдаёт 404 | Список рынков берётся из конфигурации, причина логируется |
| Нет endpoint-ов категорий и коллекций | Собираются из `product.categories` и `product.subcategories`; `Collection = subcategory` |
| Нет audio preview URL | `AudioPreviewProvider` возвращает `None`, audio-блок не вставляется; URL не угадываются |
| `v3/attractions` игнорирует фильтр `city` | Используется `v2/attractions`, где фильтры работают |
| Нет API конверсий | Заказы импортируются через `wgt import-conversions` |

Подробности — в [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md), раздел 5.
