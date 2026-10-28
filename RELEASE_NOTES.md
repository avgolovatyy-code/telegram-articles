# Release notes — Editorial Engine 3.0

**Ветка:** `cursor/editorial-engine-v3-01af`  
**Коммит / production:** `00bbe9b` · задеплоен 28 октября 2026, 22:52 Europe/Moscow  
**Миграция:** `c8f9a0b1d2e3` (аддитивная: колонки слотов + `russia_demand_observations`)  
**Откат:** `alembic downgrade b7e8f9a0c1d2`; флаги `CROSS_PROMO_FOOTER_ENABLED=false`, `EDITORIAL_RU_MARKET_V3_ENABLED=false`.

## Что вошло

- Редакционные механики (Горбилет / Tripster / Sputnik8 / Авиасейлс / Туту / Яндекс Путешествия).
- Russia demand ledger (АТОР/РСТ октябрь 2026) без смешения metric_type.
- Независимый practicality gate vs editorial interest.
- Clickable футер TG RU → MAX и MAX → TG RU; EN без футера.
- Chief Editor / Writer промпты v3; MAX не получает слот без `max_ru` в `channel_targets`.
- 36 демо-черновиков и 30-дневные планы трёх каналов (не публикуются).

## Что не меняется без отдельного действия

- Production username каналов.
- `AUTO_PUBLISH_EN` / `AUTO_PUBLISH_RU` (код дефолтов не форсирует включение).
- Исторические публикации.
