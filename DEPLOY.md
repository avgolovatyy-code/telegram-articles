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

# Деплой из Cloud Agent

Секреты из Dashboard попадают **только в новый** агент. Если текущий чат
стартовал раньше, чем вы их добавили, команда «задеплой» здесь ничего не сделает.

1. [cursor.com/agents](https://cursor.com/agents) → **New agent**.
2. Репозиторий `telegram-articles`, ветка `cursor/wegotrip-telegram-content-engine-64e7`.
3. Промпт: `задеплой: bash deploy/from-agent.sh`

Скрипт берёт `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY` как есть и не
перезаписывает чужой сервис на том же droplet (если заняты 80/443, а каталога
движка ещё нет — останавливается).

---

# Чеклист владельца

Ниже — всё, что нужно сделать вам. Порядок важен: шаги 1–6 занимают около 40 минут и
не требуют ни сервера, ни моего участия. Шаг 7 — развернуть.

## Шаг 1. Создать Telegram-бота — 3 минуты

1. Откройте [@BotFather](https://t.me/BotFather) и отправьте `/newbot`.
2. Введите отображаемое имя, например `WeGoTrip Content Engine`.
3. Введите username — он обязан заканчиваться на `bot`, например `wegotrip_content_bot`.
4. BotFather пришлёт строку вида `8123456789:AAF...`. Это `TELEGRAM_BOT_TOKEN`.
   Токен потом всегда можно посмотреть: `/mybots` → бот → API Token.

Если бот уже есть — просто возьмите его токен через `/mybots`.

## Шаг 2. Создать приватный тест-канал — 2 минуты

Telegram → New Channel → название, например `WeGoTrip Content Test` → тип **Private**.
Задайте ему публичный username (в настройках канала), например
`wegotrip_content_test` — движку нужен `@username`, а не числовой id.

Это канал, где вы своими глазами увидите вёрстку до того, как её увидят подписчики.
Публикация в продакшен без предварительной тестовой публикации заблокирована в коде.

## Шаг 3. Выдать боту права администратора в трёх каналах — 5 минут

Для каждого из `@wegotrip`, `@wegotrip_ru` и тест-канала:

1. Откройте канал → значок канала сверху → **Administrators** → **Add Administrator**.
2. Найдите бота по username из шага 1.
3. Включите **Post Messages** и **Edit Messages of Others**, остальное можно выключить.

Без этих прав Bot API вернёт 403, и публикация не пройдёт. В `@wegotrip` и
`@wegotrip_ru` вы должны быть владельцем или админом с правом назначать админов.

## Шаг 4. Получить ключ OpenAI и пополнить баланс — 5 минут

1. [platform.openai.com](https://platform.openai.com) → API keys → **Create new secret key**.
   Скопируйте сразу: второй раз ключ не покажут. Это `OPENAI_API_KEY`.
2. Billing → добавьте платёжный способ и пополните баланс. Достаточно $20–30 на месяц:
   движок держится в $3/сутки, но при нулевом балансе генерация просто остановится.
3. По желанию поставьте в Billing → Limits месячный лимит $100 как страховку.

## Шаг 5. Домен — можно пропустить

Домен не обязателен. Скрипт установки сам подставит бесплатный адрес вида
`134-209-1-2.sslip.io`, где цифры — это IP вашего сервера. Сервис sslip.io просто
превращает такой адрес в IP, сертификат Let's Encrypt на него выдаётся штатно, и https
работает.

Свой домен можно подключить в любой момент позже: добавить A-запись на IP сервера и
поменять `DEPLOY_DOMAIN` в `.env`.

## Шаг 6. Подготовить DigitalOcean — 10 минут

1. Убедитесь, что в аккаунте есть платёжный способ.
2. Загрузите SSH-ключ: DO → Settings → Security → **Add SSH Key**. Если ключа нет:
   `ssh-keygen -t ed25519 -C "wegotrip-deploy"`, затем вставьте содержимое
   `~/.ssh/id_ed25519.pub`.
3. Если хотите, чтобы сервер поднял я — создайте API-токен:
   DO → API → Tokens → **Generate New Token**, scopes **read + write**.

## Шаг 7. Передать секреты, чтобы сервер поднял я

Секреты нельзя присылать сообщением: переписка не шифруется и не удаляется, поэтому
любой токен из чата считается скомпрометированным. Есть отдельное защищённое место.

Что сделать, по шагам:

1. Откройте [cursor.com/dashboard](https://cursor.com/dashboard).
2. Слева выберите **Cloud Agents**, затем вкладку **Secrets**.
3. Нажмите **Add secret**. Откроются два поля: имя и значение.
4. Добавьте записи из таблицы ниже. Имя пишите **точно** как в первой колонке.
   Уже лежащие в Dashboard имена с другой стороны тоже принимаются.
5. Секреты попадают только в **новый** Cloud Agent. В уже идущем чате их не будет,
   даже если они видны в Dashboard. После добавления откройте новый агент на этой
   ветке и напишите «задеплой».

| Имя (скопируйте как есть) | Что вставить в значение | Уже есть в Dashboard под именем |
| --- | --- | --- |
| `OPENAI_API_KEY` | ключ OpenAI из шага 4 | `OPENAI_API_KEY` |
| `TELEGRAM_BOT_TOKEN` | токен бота из шага 1 | `TELEGRAM_BOT_TOKEN` |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token | `SLACK_BOT_TOKEN_TG` |
| `SLACK_SIGNING_SECRET` | Signing Secret | `SLACK_SIGNING_SECRET_TG` |
| `SLACK_CHANNEL` | `#telegram-articles` | `SLACK_CHANNEL` |
| `DEPLOY_HOST` | IP или hostname droplet | `DEPLOY_HOST` |
| `DEPLOY_USER` | пользователь SSH | `DEPLOY_USER` |
| `DEPLOY_SSH_PRIVATE_KEY` | приватный SSH-ключ целиком | `DEPLOY_SSH_KEY` |
| `TELEGRAM_TEST_CHANNEL` | id тест-канала | — |
| `DIGITALOCEAN_ACCESS_TOKEN` | только если нужен **новый** droplet | — |
| `ACME_EMAIL` | почта для сертификата | — |
| `ADMIN_PASSWORD` | пароль админки; можно сгенерировать на сервере | — |

Дальше я сам создам сервер, разверну систему, наполню каталог и покажу первые статьи в
тест-канале.

> Если предпочитаете сделать всё сами — токены мне не нужны, идите в раздел
> [«Вариант A»](#вариант-a-droplet--docker-compose): там три команды.

## Шаг 8. Что вы увидите после запуска

Система работает сама: синхронизирует каталог, пишет статьи и публикует их с 10:00 до
21:00 по Москве. Вмешиваться не нужно. Ваша задача — один раз посмотреть на результат.

1. Я пришлю вам адрес админки и первые статьи в тест-канале.
2. Откройте тест-канал в Telegram и просто прочитайте пару статей: заголовки, фото,
   карточки товаров, кнопки.
3. Нажмите кнопку товара под статьёй — она должна вести на сайт WeGoTrip, а в адресе
   должно быть `coupon=435`. Это значит, что продажа засчитается вам.
4. Если что-то не нравится — тон, факты, оформление — напишите мне, поправлю.
5. Если нравится — ничего делать не нужно, статьи начнут выходить в основные каналы
   сами.

Захотите вмешаться позже — есть два способа: админка в браузере или Slack (см. ниже).
Оба необязательны.

---

---

## Нужен ли Slack, если публикация автоматическая

Короткий ответ: **не нужен**. Система полностью работает без него, и по умолчанию он
выключен (`SLACK_ENABLED=false`). Всё то же самое видно в админке в браузере.

Slack решает одну проблему: чтобы узнать, что происходит, не нужно никуда заходить.
При автопубликации это единственное, чего не хватает — вы не видите, что вышло, пока
сами не откроете канал или админку.

Что Slack даёт:

| | |
| --- | --- |
| Уведомление о каждой публикации | ссылка на пост, стоимость, поисковый запрос |
| Сводка раз в день | сколько потрачено из $3, сколько вышло, сколько тем осталось |
| Алерты | бот потерял права в канале, кончился баланс OpenAI, упала джоба |
| Кнопка «Снять» | если статья вышла неудачной — убрать одним нажатием, не заходя в админку |
| `/wegotrip status` | быстрый ответ по бюджету и очереди прямо из чата |

Утверждать статьи через Slack не требуется — при автопубликации кнопки нужны только для
исключений. Если вам это не нужно, оставьте `SLACK_ENABLED=false` и пользуйтесь
админкой; включить можно в любой момент, это три переменные окружения.

### Как включить, когда понадобится

1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From scratch.
2. **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `commands`. Установите
   приложение в workspace и скопируйте **Bot User OAuth Token** (`xoxb-…`).
3. **Basic Information** → скопируйте **Signing Secret**.
4. **Interactivity & Shortcuts** → включите, Request URL:
   `https://<ваш адрес>/slack/interactions`.
5. **Slash Commands** → Create: команда `/wegotrip`, URL
   `https://<ваш адрес>/slack/commands`.
6. Пригласите бота в канал: `/invite @имя_приложения`.
7. В `.env`:

```env
SLACK_ENABLED=true
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_CHANNEL=#telegram-articles
```

Каждый входящий запрос от Slack проверяется по подписи `X-Slack-Signature`, запросы
старше пяти минут отклоняются. Если Slack недоступен, публикация всё равно проходит:
ошибки уведомлений подавляются и не могут остановить конвейер.

Если заданы все три значения (`SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`,
`SLACK_CHANNEL`), интеграция включается сама — отдельный `SLACK_ENABLED=true`
не нужен. Проверка без публикации статьи: `wgt slack-check` (и `--post`, чтобы
отправить тестовое сообщение в канал).

**Токены нельзя писать в чат с агентом.** Положите их в Cursor Dashboard →
Cloud Agents → Secrets или на сервере через `wgt secrets set SLACK_BOT_TOKEN`.

### Если приложение Slack уже создано

Осталось:

1. Три секрета (имена точно такие): `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`,
   `SLACK_CHANNEL` (`#telegram-articles` или `C0BTME6R546`). Суффикс `_TG` тоже
   принимается (`SLACK_BOT_TOKEN_TG` → `SLACK_BOT_TOKEN`).
2. После того как droplet получит адрес — два URL в Slack App:
   * Interactivity Request URL: `https://<хост>/slack/interactions`
   * Slash Command `/wegotrip`: `https://<хост>/slack/commands`
3. На сервере: `wgt slack-check --post`.

---

## Справка: какие секреты за что отвечают

| Переменная | Обязательна | Где взять | Зачем |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | да | шаг 4 | генерация статей |
| `TELEGRAM_BOT_TOKEN` | да | шаг 1 | публикация в каналы |
| `TELEGRAM_TEST_CHANNEL` | да | шаг 2 | обязательная проверка вёрстки до продакшена |
| `ADMIN_PASSWORD` | да | генерируется скриптом | вход в админку |
| `DEPLOY_DOMAIN` | нет | шаг 5 | свой домен вместо бесплатного `*.sslip.io` |
| `ACME_EMAIL` | нет | ваша почта | уведомления Let's Encrypt |
| `SLACK_BOT_TOKEN` | нет | api.slack.com/apps | уведомления и кнопки в Slack |
| `SLACK_SIGNING_SECRET` | нет | api.slack.com/apps | проверка подписи запросов Slack |
| `SLACK_CHANNEL` | нет | id или `#имя` канала | куда слать уведомления |
| `DIGITALOCEAN_ACCESS_TOKEN` | только если разворачиваю я | шаг 6 | создать droplet и DNS-записи |
| `DEPLOY_SSH_PRIVATE_KEY` | только если разворачиваю я | шаг 6 | доступ к droplet |
| `WEGOTRIP_API_KEY` | нет | партнёрская программа WeGoTrip | сейчас Affiliate API работает без ключа |

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
$C exec api wgt slack-check --post  # Slack: auth.test и тестовое сообщение
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

## Включение автопубликации

Порядок приёмки описан в [шаге 8](#шаг-8-приёмка--20-минут). Когда результат
устраивает, включайте автопубликацию по одному рынку за раз:

```env
AUTO_PUBLISH_RU=true
```

и перезапустите worker: `docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d worker`
(вариант A) или сохраните переменную в App Platform (вариант B).

Даже в автоматическом режиме статья проходит все автоматические проверки и всё равно
сначала публикуется в тест-канал.

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

## Как хранятся ключи

Ключи не лежат на сервере в открытом виде. Они шифруются алгоритмом Fernet
(AES-128-CBC + HMAC-SHA256) и хранятся в `var/secrets/secrets.enc`; мастер-ключ лежит
отдельным файлом `var/secrets/master.key` с правами `600`. Приложение расшифровывает их
в память при старте — ни в `.env`, ни в истории команд, ни в бэкапах открытого ключа нет.

```bash
C="docker compose -f deploy/docker-compose.prod.yml --env-file .env"

$C exec api wgt secrets set OPENAI_API_KEY      # значение спросит, не показывая на экране
$C exec api wgt secrets set TELEGRAM_BOT_TOKEN
$C exec api wgt secrets list                    # покажет только маски вида sk-p…GHIJ
$C exec api wgt secrets import-env .env         # перенести из существующего .env
$C exec api wgt secrets rotate-key              # перешифровать под новым мастер-ключом
```

Второй слой — маскирование в логах: любое значение известного секрета и всё, что похоже
на ключ по форме (`sk-…`, `xoxb-…`, `123456:AA…`, приватный PEM), заменяется на `***`
до того, как строка попадёт в вывод. Даже случайно залогированный ключ не окажется в
логах.

Честная граница этой защиты: она снимает открытые ключи с диска, из `.env`, из бэкапов и
из `docker inspect`, но не спасает от того, у кого уже есть root на этом сервере —
процесс обязан уметь расшифровать, значит ключ ему доступен. Для защиты и от этого нужен
внешний KMS; код изолирован так, что подключается он правкой одного файла.

Отдельно: ключ, который побывал в переписке, мессенджере или тикете, шифрованием на
сервере не спасти — он уже видел посторонних. Такой ключ нужно перевыпустить, и только
новое значение класть в хранилище.

## Безопасность

* Ключи шифруются на диске, `.env` содержит только несекретные настройки.
* Плейнтекстовый `.env` в `.gitignore`, в репозиторий не попадает.
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
