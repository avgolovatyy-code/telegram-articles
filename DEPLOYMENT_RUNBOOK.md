# Deployment runbook — Editorial Engine 3.0

Секреты в этот файл не входят. Production droplet: `/opt/wegotrip-content-engine`.

## Путь деплоя

Единственный разрешённый агентный путь: `bash deploy/from-agent.sh`.

Требуемые секреты агента: `DEPLOY_HOST`, `DEPLOY_USER` (обычно `root`), `DEPLOY_SSH_KEY` или `DEPLOY_SSH_PRIVATE_KEY`.

Опционально прокидываются в encrypted store: `OPENAI_API_KEY` / `OPENAI_KEY_TG_MAX`, `TELEGRAM_BOT_TOKEN`, Slack tokens.

Ветка релиза 3.0: `cursor/editorial-engine-v3-01af`. Перед запуском:

```bash
export DEPLOY_BRANCH=cursor/editorial-engine-v3-01af
export DEPLOY_MODE="${DEPLOY_MODE:-caddy}"   # существующий режим; не менять без причины
bash deploy/from-agent.sh
```

Compose поднимает стек (`deploy/docker-compose.prod.yml` или `deploy/docker-compose.proxy.yml`), затем `wgt doctor`.

## Миграции

Ревизия `c8f9a0b1d2e3` аддитивна: колонки `editorial_plan_slots` + таблица `russia_demand_observations`.  
Контейнер migrate/api применяет `alembic upgrade head`. Не drop-таблиц, не wipe публикаций.

## Флаги (без роста бюджета и без новых каналов)

| Переменная | Ожидание 3.0 |
|---|---|
| `EDITORIAL_RU_MARKET_V3_ENABLED` | `true` |
| `CROSS_PROMO_FOOTER_ENABLED` | `true` |
| `ENABLE_HASHTAGS` | `false` |
| `MAX_COMMERCIAL_POST_SHARE` | `0.20` |
| `AUTO_PUBLISH_EN` / `AUTO_PUBLISH_RU` | **не менять** этим релизом |
| `DAILY_AI_BUDGET_USD` | **не увеличивать** |

Каналы: `@wegotrip`, `@wegotrip_ru`, MAX `https://max.ru/channel_wegotrip`. Username не трогать.

## Проверки после деплоя

На дроплете:

```bash
cd /opt/wegotrip-content-engine
docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api wgt doctor
docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api wgt check-max
docker compose -f deploy/docker-compose.prod.yml --env-file .env exec -T api git rev-parse HEAD
```

Сверить `git rev-parse HEAD` с SHA ветки. Не публиковать dummy-посты в живые каналы.

## Откат

1. Флаги: `CROSS_PROMO_FOOTER_ENABLED=false`, `EDITORIAL_RU_MARKET_V3_ENABLED=false`, recreate api/worker.
2. Git: `git checkout <previous-sha>` + compose `--build`.
3. БД: `alembic downgrade b7e8f9a0c1d2` только если новые колонки ломают рантайм (обычно не требуется: старый код их игнорирует).
