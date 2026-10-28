# MAX Implementation Plan — WeGoTrip (addendum v1.1)

**Спека:** `WEGOTRIP_MAX_EDITORIAL_ADDENDUM_V1_1_CURSOR.md`  
**База:** `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` (не заменяется)  
**Статус-чеклист:** `MAX_REQUIREMENTS_STATUS.md`  
**Дата:** 28.10.2026  

## Канал (не создавать заново)

| Поле | Значение |
|---|---|
| Канонический URL | https://max.ru/channel_wegotrip |
| Legacy alias | прежний `https://max.ru/id*_biz` того же канала (только миграция) |
| API `chat_id` | существующий numeric `MAX_RU_CHANNEL_ID` — **не менять** при смене публичного URL |
| Title | `WeGoTrip — Куда сходить и что посмотреть` |
| Аудитория | люди **в России** (не «все русскоязычные») |
| Бот в описании | `https://max.ru/id7816636266_bot` (отдельный объект; проверить роль) |

## Архитектура (сохраняем)

```
RU idea pool (общий OpenAI Chief Editor)
        ├─ Telegram RU  → InputRichMessage / sendRichMessage
        └─ MAX RU       → MaxRussiaEditorialPolicy → Max HTML/MD + buttons
```

Telegram остаётся primary. Max fan-out best-effort; ошибки Max не ломают TG.

## Редакционная политика MAX (§6.1) — приоритет

1. **`MaxRussiaAudienceGate`** — eligibility для жителей РФ; зарубежное только как поездка *из* России.
2. **`RussianRegionCoveragePlanner`** — ротация регионов; не монополия Москва/СПб.
3. **`russia_calendar_context`** — выходные и фиксированные праздники РФ.
4. **Баланс ~75% domestic / ~25% outbound** — soft target (`MAXAPP_RU_*_SHARE_TARGET`).
5. Каталог RU (`wegotrip.ru`, `coupon=435`), CTA с `utm_source=max`.

## Фазы

### MAX-A — Audit & preservation (в работе / частично done)

- [x] Интеграция `app/max/*` уже есть (client, renderer, publisher, chat_id resolve)
- [x] Канонический URL `channel_wegotrip` в коде; numeric chat_id не трогаем
- [x] Документы плана/статуса
- [ ] Live `GET /chats/{id}` сверка type/link при наличии токена (read-only `wgt check-max`)
- [ ] Snapshot профиля MAX перед любым branding apply

### MAX-B — Provider + renderer (done, polish)

- [x] `MaxBotClient`, `MaxPublisher`, `MaxPostRenderer` (HTML ≤4000)
- [x] Dual-format: TG blocks ≠ Max payload
- [x] Product buttons с `coupon` + `utm_source=max`
- [ ] Media upload / audio preview (gated, later)
- [ ] Отдельный test channel publish path

### MAX-C — Editorial integration (эта итерация)

- [x] `MaxRussiaAudienceGate` + `MaxRussiaEditorialPolicy`
- [x] `RussianRegionCoveragePlanner` + RU holidays helper
- [x] Fan-out передаёт DB session для geo resolve
- [x] `adapt_for_max` + `max_publications` idempotency / mid storage
- [x] Daily/weekly Max quotas on fan-out
- [ ] Полный platform variant calendar (Telegram / Max slots) в Editorial V2
- [ ] RussiaTrendsProvider / LLM Max tone adapter (optional polish)

### MAX-D / MAX-E — Ops & roll-out

- [ ] Admin Channels → MAX RU
- [ ] Kill switch уже есть (`MAX_PUBLISH_RU` / credentials)
- [ ] Autopublish Max отдельно от Telegram (`MAXAPP_AUTO_PUBLISH=false`)
- [ ] Profile/pin Max — только после явного approval (не в этой итерации без запроса)

## Конфиг (новые ключи)

См. `.env.example` (`MAXAPP_*`). Существующие `MAX_BOT_TOKEN` / `MAX_RU_CHANNEL_ID` сохраняются.

## Не делать

- Новый канал MAX
- Смена numeric `chat_id` из‑за нового публичного URL
- Дублирующий OpenAI daily budget
- Production Max posts / profile changes без явного разрешения владельца
- Регрессии Telegram RU/EN
