# MAX Requirements Status — addendum v1.1

**Спека:** `WEGOTRIP_MAX_EDITORIAL_ADDENDUM_V1_1_CURSOR.md`  
**План:** `MAX_IMPLEMENTATION_PLAN.md`  
**Обновлено:** 28.10.2026 (Europe/Moscow)

Легенда: `[x]` done · `[~]` partial · `[ ]` todo · `[!]` blocked on owner

---

## 0. Канал и URL

- [x] Канонический публичный URL: `https://max.ru/channel_wegotrip`
- [x] Константы `CANONICAL_PUBLIC_URL` / `CANONICAL_PUBLIC_SLUG` в `app/max/chat_id.py`
- [x] Numeric `MAX_RU_CHANNEL_ID` не перезаписывается публичным slug
- [x] Legacy URL поле `MAXAPP_CHANNEL_LEGACY_URL` (optional, migration-only)
- [ ] Live API подтверждение `type=channel` + link ↔ public URL `[~]` via `wgt check-max`
- [x] Новый канал **не** создаётся кодом

## 1. Аудитория Россия (§6.1)

- [x] `MaxRussiaAudienceGate` — structured decision JSON fields
- [x] Block: expired local events; foreign without RU-store access; expat/local-only foreign
- [x] Allow: domestic Russia leisure/trips; outbound-from-RU catalogue topics
- [x] Soft mix targets 75/25 (`MAXAPP_RU_DOMESTIC_SHARE_TARGET` / `OUTBOUND`)
- [x] `RussianRegionCoveragePlanner` — capital share cap + hub boost
- [x] `russia_calendar_context` — fixed RF holidays + weekend/pre-weekend labels
- [x] `MaxRussiaEditorialPolicy` orchestrates gate + regions + calendar + balance
- [x] Publisher applies policy before Max send; session-aware geo resolve
- [ ] Admin filters / 30-day mix dashboard
- [ ] RussiaTrendsProvider (Yandex Wordstat etc.)

## 2. Интеграция / publisher

- [x] Existing Max client + TLS CA path preserved
- [x] Fan-out after Telegram RU production only
- [x] Max errors do not fail Telegram publish
- [x] Renderer independent of `rendered_message` (TG rich blocks)
- [x] Product links: `coupon=435`, `utm_source=max`
- [ ] Independent Max scheduler slots (3–4/week) in Editorial V2 calendar
- [ ] `adapt_for_max` OpenAI writer
- [ ] Idempotent Max publication records / mid storage in DB (beyond log)

## 3. Профиль / branding Max

- [x] Draft description for Russia audience in `app/max/branding.py`
- [ ] Owner approval for Max profile/pin `[!]`
- [ ] Apply Max branding only after approval (Telegram branding is separate)

## 4. Конфиг

- [x] `.env.example` documents `MAXAPP_*` + canonical URL
- [x] `Settings.maxapp_*` fields
- [x] Kill switch `MAX_PUBLISH_RU` / missing credentials → inactive
- [x] `MAXAPP_AUTO_PUBLISH=false` default

## 5. Тесты

- [x] Chat id resolve / numeric preferred
- [x] Max payload ≠ Telegram rich message
- [x] Audience gate domestic / outbound / block cases
- [x] Region planner capital share
- [x] Holiday helper fixed dates
- [x] Max product URL uses `utm_source=max`
- [ ] Live connection smoke (manual / secrets)

## 6. Acceptance (спека §19)

| # | Критерий | Статус |
|---|---|---|
| 1 | URL = существующий канал, новый не создан | [x] |
| 2 | Бот / токен задокументирован или инструкция | [~] |
| 3 | `GET /chats/{id}` + права | [~] check-max |
| 4 | RU plan → TG and/or Max; Max = Russia audience | [~] gate on fan-out |
| 5 | Уникальный Max-текст из fact bundle | [ ] writer |
| 6 | Renderer короткие посты + кнопки | [x] |
| 7 | Review / preview / kill switch | [~] kill switch |
| 8 | Links coupon=435 + utm_source=max | [x] |
| 9 | Persist mid / URL / stats | [~] mid in API result |
| 10 | TG без регрессий | [x] dual-format |
| 11 | Manual approval на старте | [x] no auto profile |
| 12 | Нет тем «для всех RU speakers» без РФ-пользы | [x] gate |
| 13 | Ссылки на channel_wegotrip | [x] |
