# Деплой на DigitalOcean

Движок должен работать в фоне круглосуточно: `worker` синхронизирует каталог, ищет
темы, генерирует статьи и публикует их по расписанию, `api` отдаёт админку и считает
клики по ссылкам `/r/<token>`.

Ниже — два варианта. Начните с **варианта A**, если хотите дешевле и с полным контролем,
или с **варианта B**, если не хотите заходить на сервер по SSH.

| | A. Droplet + Docker Compose | B. App Platform + Managed Postgres |
| --- | --- | --- |
| Стоимость | ~$12/мес (droplet 2 GB) | ~$22/мес (web + worker + БД) |
| Обновления | `bash deploy/update.sh` | автодеплой из GitHub при push |
| TLS | Caddy, автоматически | встроенный |
| Нужен домен | да (для https) | нет, даётся `*.ondigitalocean.app` |
| Нужен SSH | да | нет |
| Бэкапы БД | вручную (`pg_dump` по cron) | встроенные |

---

## Что нужно от вас

### 1. Секреты — добавьте их в Cursor, а не в чат

Откройте **[cursor.com/dashboard](https://cursor.com/dashboard) → Cloud Agents →
Secrets** и добавьте переменные из таблицы ниже. Они шифруются, подставляются в
окружение агента и **не попадают в репозиторий и в переписку**.

> Важно: секреты подставляются только в **новые** запуски агента. После того как вы их
> добавите, напишите мне следующим сообщением — я подхвачу их в новом окружении.
> Не присылайте токены текстом в чат: всё, что попало в переписку, считается
> скомпрометированным, и такой токен придётся отзывать.

| Переменная | Обязательна | Где взять | Зачем |
| --- | --- | --- | --- |
| `DIGITALOCEAN_ACCESS_TOKEN` | для деплоя мной | DO → API → Tokens → Generate New Token, scopes **read + write** | создать droplet/приложение, БД, DNS-записи |
| `OPENAI_API_KEY` | да | platform.openai.com → API keys | генерация статей |
| `TELEGRAM_BOT_TOKEN` | да | [@BotFather](https://t.me/BotFather) → `/newbot` или `/token` | публикация в каналы |
| `TELEGRAM_TEST_CHANNEL` | да | `@username` вашего приватного тест-канала | обязательная проверка вёрстки до продакшена |
| `DEPLOY_DOMAIN` | вариант A | ваш домен, например `content.wegotrip.com` | https для ссылок трекинга |
| `ACME_EMAIL` | вариант A | ваша почта | уведомления Let's Encrypt |
| `DEPLOY_SSH_PRIVATE_KEY` | вариант A, если разворачиваю я | приватный ключ, публичная часть которого загружена в DO → Settings → Security → SSH Keys | доступ к droplet |
| `WEGOTRIP_API_KEY` | нет | партнёрская программа WeGoTrip | сейчас Affiliate API работает без ключа |

Токен DigitalOcean нужен только если разворачиваю я. Если разворачиваете вы сами по
инструкции ниже, мне достаточно, чтобы вы просто прошли шаги — токен не понадобится.

### 2. Что могу сделать только вы, руками

Это нельзя автоматизировать токеном:

1. **Создать бота** в [@BotFather](https://t.me/BotFather) и получить токен.
2. **Создать приватный тест-канал** в Telegram (например `@wegotrip_content_test`) —
   именно в нём проверяется вёрстка перед продакшеном.
3. **Выдать боту права администратора** в трёх каналах: `@wegotrip`, `@wegotrip_ru` и
   тест-канале. Нужны права «Post messages» и «Edit messages of others».
   Без прав Bot API вернёт 403, и публикация не пройдёт.
4. **Направить домен на сервер** (вариант A): A-запись `content.example.com` → IP
   droplet. Без домена не будет https для ссылок трекинга.
5. **Пополнить баланс OpenAI.** Движок держится в $3/сутки, но при нулевом балансе API
   вернёт ошибку и генерация просто остановится.

---

## Вариант A. Droplet + Docker Compose

### A1. Создать droplet

DO → Create → Droplets:

* Region: **Frankfurt** или **Amsterdam** (ближе к WeGoTrip API и к Telegram);
* Image: **Ubuntu 24.04 LTS**;
* Size: **Basic → Regular → 2 GB / 1 vCPU / 50 GB** (~$12/мес). 1 GB тоже работает, но
  на сборке образа памяти впритык;
* Authentication: **SSH key** (загрузите свой публичный ключ);
* Hostname: `wegotrip-content-engine`.

Через минуту скопируйте IP.

### A2. Направить домен

В DNS домена добавьте A-запись:

```text
content.example.com.   A   <IP droplet>
```

Проверьте: `dig +short content.example.com` должен вернуть IP.

### A3. Подготовить сервер

```bash
ssh root@<IP>
curl -fsSL https://raw.githubusercontent.com/avgolovatyy-code/telegram-articles/main/deploy/setup-droplet.sh | bash
```

Скрипт ставит Docker, включает файрвол (открыты только 22, 80, 443), заводит
пользователя `wegotrip`, клонирует репозиторий в `/opt/wegotrip-content-engine` и
создаёт `.env` со сгенерированными паролями Postgres и админки.

### A4. Заполнить `.env`

```bash
nano /opt/wegotrip-content-engine/.env
```

Обязательно заполните:

```env
DEPLOY_DOMAIN=content.example.com
ACME_EMAIL=you@example.com

OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_TEST_CHANNEL=@wegotrip_content_test

# Проверьте, что осталось так — это режим ревью, без автопубликации
AUTO_PUBLISH_EN=false
AUTO_PUBLISH_RU=false
```

`POSTGRES_PASSWORD` и `ADMIN_PASSWORD` уже сгенерированы скриптом — запишите
`ADMIN_PASSWORD`, он нужен для входа в админку.

### A5. Запустить

```bash
cd /opt/wegotrip-content-engine
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

Первая сборка занимает 3–5 минут. Caddy сам получит сертификат Let's Encrypt.

### A6. Проверить и наполнить

```bash
C="docker compose -f deploy/docker-compose.prod.yml --env-file .env"

$C exec api wgt doctor            # конфигурация и подключение к БД
$C exec api wgt check-telegram    # токен бота и доступ к трём каналам
$C exec api wgt seed              # рынки, кластеры интентов, версии промптов
$C exec api wgt sync-catalog      # первая синхронизация, 5–15 минут
$C exec api wgt discover-topics
$C exec api wgt coverage          # сколько материала есть в каталоге
```

Откройте `https://content.example.com/admin` — логин `admin`, пароль из `ADMIN_PASSWORD`.

### A7. Обновление

```bash
cd /opt/wegotrip-content-engine && bash deploy/update.sh
```

### A8. Бэкап БД

```bash
# в crontab -e у пользователя root
0 3 * * * cd /opt/wegotrip-content-engine && docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T db pg_dump -U wegotrip wegotrip_engine | gzip > /root/backup-$(date +\%F).sql.gz
```

---

## Вариант B. App Platform

### B1. Подключить GitHub

DO → Apps → Create App → GitHub → авторизовать доступ к репозиторию
`avgolovatyy-code/telegram-articles`, ветка `main`.

### B2. Создать приложение из spec

Установите `doctl` локально и авторизуйтесь:

```bash
brew install doctl            # или snap install doctl
doctl auth init               # вставьте DIGITALOCEAN_ACCESS_TOKEN
doctl apps create --spec .do/app.yaml
```

Spec поднимает три компонента: pre-deploy job с миграциями, `web` (админка и трекинг) и
`worker` (планировщик), плюс managed PostgreSQL 16.

### B3. Задать секреты

DO → Apps → ваше приложение → Settings → App-Level Environment Variables. Замените
`REPLACE_ME` на реальные значения и отметьте **Encrypt**:

* `OPENAI_API_KEY`
* `TELEGRAM_BOT_TOKEN`
* `ADMIN_PASSWORD`
* `TELEGRAM_TEST_CHANNEL` (шифровать не обязательно)

`DATABASE_URL`, `TRACKING_BASE_URL` и `ADMIN_BASE_URL` подставляются автоматически.

### B4. Наполнить

```bash
doctl apps list                                   # узнать APP_ID
doctl apps console <APP_ID> --component web
# внутри консоли:
wgt doctor && wgt check-telegram && wgt seed && wgt sync-catalog && wgt discover-topics
```

Админка — по адресу `https://<app>.ondigitalocean.app/admin`.

---

## Первый запуск: порядок действий

Не включайте автопубликацию сразу. Правильная последовательность:

1. `wgt sync-catalog` — каталог EN и RU.
2. `wgt discover-topics` — кандидаты тем.
3. `wgt generate --max-articles 2` — две пробные статьи. Проверьте в админке расход:
   он должен быть около $0.05–0.09 за статью.
4. Откройте статью, нажмите **Publish to test** и посмотрите, как сообщение выглядит в
   тест-канале: заголовки, карточки товаров, кнопки, фото.
5. Проверьте ссылку из кнопки: в ней должен быть `coupon=435` и UTM-метки.
6. Если всё в порядке — **Approve** и **Publish now** в продакшен.
7. Понаблюдайте день-два в режиме ревью. Когда результат устраивает, включите
   автопубликацию по одному рынку за раз:

```env
AUTO_PUBLISH_RU=true
```

и перезапустите: `docker compose ... up -d worker` (вариант A) или сохраните переменную
в App Platform (вариант B).

---

## Как это работает в фоне

`worker` держит расписание (UTC):

| Время | Джоба | Что делает |
| --- | --- | --- |
| 02:00 | `sync_catalog` | каталог EN и RU, снапшоты, деактивация исчезнувших товаров |
| 03:00 | `discover_topics` | новые кандидаты тем, скоринг, дедупликация |
| 04:00, 10:00, 16:00 | `generate_daily_articles` | генерация в пределах дневного бюджета |
| 05:30, 11:30, 17:30 | `schedule_publications` | распределение публикаций по окну |
| каждые 5 минут | `process_publication_queue` | публикация того, что подошло по времени |
| каждые 30 минут | `cleanup_expired` | освобождение зависших резерваций бюджета |

**Публикация растянута на весь день.** Окно — 10:00–21:00 по Москве
(`PUBLISH_TIMEZONE=Europe/Moscow`). Статьи генерируются пачками, но выходят
поштучно: интервал считается как «оставшееся окно / количество постов», не плотнее
`MIN_POST_INTERVAL_MINUTES` (20 минут). Десять постов в свободном окне выходят примерно
раз в час, двадцать пять — раз в 27 минут, а всё, что не поместилось, переносится на
следующий день.

**Ограничивает только бюджет.** `DAILY_AI_BUDGET_USD=3.00` — жёсткий предел. Сначала
финансируются минимумы (10 EN + 10 RU, по очереди, чтобы ни один рынок не голодал),
потом на остаток пишется столько статей, сколько влезает. Потолка в 20 больше нет:
`EN_ARTICLES_MAX_PER_DAY=0` означает «без потолка». При средней цене $0.05 за статью
$3 хватает примерно на 45–55 статей в сутки суммарно. Если захотите вернуть потолок —
поставьте любое число больше нуля.

**Материал не высасывается из пальца.** Когда в каталоге не остаётся сочетаний
«сущность × интент» выше `MIN_TOPIC_SCORE`, движок останавливается и пишет об этом в
лог (`topics.exhausted`), в отчёт джобы и на дашборд. Он не понижает порог, не
переиспользует сущность со слабым интентом и не добирает норму любой ценой. Новые темы
появляются сами, когда `sync_catalog` увидит в Affiliate API новые товары, города или
достопримечательности. Посмотреть остаток материала: `wgt coverage`.

---

## Мониторинг

```bash
C="docker compose -f deploy/docker-compose.prod.yml --env-file .env"

$C logs -f worker            # что делает планировщик
$C logs -f api               # запросы и редиректы
$C exec api wgt budget       # расход и план на сегодня
$C exec api wgt coverage     # остаток материала
curl -s https://content.example.com/api/stats | jq
```

Логи структурированные (`LOG_FORMAT=json`), в каждой строке есть `job_id`,
`article_id`, `market`, `operation`, `cost_usd`, `duration_ms` и `status` — их можно
без обработки заливать в любой сборщик логов.

Что смотреть в первую очередь:

* `/admin` — дневной расход, счётчики по рынкам, остаток материала;
* `/admin/analytics` — клики, заказы, стоимость статьи;
* `/admin/ops` — очередь публикаций и ошибки;
* событие `topics.exhausted` в логах — материал закончился, это не ошибка.

---

## Безопасность

* Секреты только в `.env` (права `600`) или в шифрованных переменных App Platform.
  `.env` в `.gitignore`, в репозиторий не попадает.
* Файрвол оставляет открытыми только 22, 80 и 443.
* Админка закрыта HTTP basic auth (`ADMIN_PASSWORD`) поверх TLS.
* Контейнер работает от непривилегированного пользователя.
* Сырые IP не хранятся — клики привязаны к необратимому хешу.
* Если токен всё-таки утёк: отзовите его (BotFather → `/revoke`, OpenAI → Revoke key,
  DO → Delete token), выпустите новый и обновите `.env`.

---

## Стоимость

| Статья | Вариант A | Вариант B |
| --- | --- | --- |
| Сервер | $12 (2 GB droplet) | $10 (web + worker по $5) |
| PostgreSQL | в контейнере, $0 | $12 (managed, 1 GB) |
| Домен | ~$1 | не нужен |
| OpenAI | до $90 ($3 × 30 дней) | до $90 |
| **Итого** | **~$103/мес** | **~$112/мес** |

Расход на OpenAI — верхняя граница: в дни, когда материал в каталоге заканчивается,
движок просто не тратит бюджет.
