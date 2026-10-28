# EDITORIAL_V2_REQUIREMENTS_STATUS

Чеклист по `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` (заменяет v2.1).  
Легенда: `[x]` сделано · `[~]` частично / foundation · `[ ]` не сделано · `[!]` ждёт approval.

Фундамент Content Engine (каталог, affiliate, rich publisher, budget, factcheck) — см. также `REQUIREMENTS_STATUS.md` (v1). Здесь — **дельты Editorial Engine 2.2**.

Обновлено: 2026-10-28.

---

## 0. Инварианты (не ломать)

- [x] Каналы только `@wegotrip` / `@wegotrip_ru` (конфиг + publisher)
- [x] Affiliate `coupon=435` + UTM builder
- [x] EN/RU независимые рынки (без перевода)
- [x] VERIFY OR OMIT / quality gates / review mode
- [x] Idempotent Telegram publishing
- [x] Daily AI budget ~$3 + ledger
- [x] Max RU secondary publish (forward-only; не backfill)
- [x] Сохранены подписчики / history / message IDs (никакого recreate channel)

---

## 0.1. Позиционирование, названия, описания, pinned (§0.1) — НОВОЕ v2.2

### Документы и approval gate

- [x] Спека v2.2 добавлена в репозиторий
- [x] `CHANNEL_BRANDING_PROPOSAL.md` — current vs proposed, pinned drafts, чеклист владельца
- [x] Явная политика: **не применять** title/description/pin без approval
- [ ] Approval владельца получено (`approved_by` / дата) `[!]`
- [ ] Live `getChat` сверка title/description перед apply

### Целевые строки (draft)

- [x] RU title оставить: `WeGoTrip — Куда сходить и что посмотреть`
- [x] RU description draft с `https://wegotrip.ru` (201 chars ≤ 255)
- [x] EN title draft: `WeGoTrip — Things to Do & Travel Ideas` (38 ≤ 128)
- [x] EN description draft с `https://wegotrip.com` (203 ≤ 255)
- [x] RU/EN pinned welcome drafts в proposal
- [x] Альтернативы title задокументированы как ручной выбор only

### Продукт / админка Channel Identity

- [ ] Блок Channel Identity в admin (RU/EN независимо)
- [ ] Поля: chat_id, username RO, title, description, website_url, avatar_status, pinned_welcome_text, pinned_message_id, branding_version, status, approved_by, applied_at
- [ ] Preview proposed changes + length validation (Unicode)
- [ ] Apply через `setChatTitle` / `setChatDescription` / `pinChatMessage` при правах
- [ ] Manual checklist fallback при отсутствии прав
- [ ] `channel_branding_history` + откат
- [ ] Список существующих pins перед заменой (без silent unpin)
- [ ] Chief Editor **не** меняет профиль автоматически
- [ ] `CHANNEL_BRANDING_APPLY_ENABLED=false` по умолчанию
- [ ] Оформление не блокирует Editorial Engine при отсутствии прав
- [ ] Max RU branding sync после approval Telegram RU

### Acceptance §0.1 / §19.24–27

- [ ] Утверждённые title/description применены или выдана ручная инструкция
- [ ] `@username` прежние
- [ ] RU website `.ru`, EN website `.com` в bio
- [ ] Welcome posts только после отдельного approval
- [ ] Подписчики / публикации / Community неизменны

---

## 1. Миссия и аудитории (§0–§2)

- [ ] Редакционная миссия: travel & local discovery media (не SEO-витрина) — продуктово
- [ ] Audience tags: `local | traveler | both`
- [ ] RU mix hypothesis 50/35/15; EN 35/45/20 — конфиг, не жёсткая квота
- [ ] Анти-одногородковая лента

---

## 2. Частота (§3) — замена 10–20/день

- [ ] RU target 5–6/нед., hard cap 8
- [ ] EN target 4–5/нед., hard cap 7
- [ ] ≤1 основной пост/день (+ emergency flag)
- [ ] Min interval ≥6h (предпочитать 18–24h)
- [ ] Rich guide ≤1–2/месяц/канал
- [ ] Weekend/holiday planner hooks
- [ ] Выключить/ограничить старый mass article auto-scheduler флагом при rollout

---

## 3. Рубрики и форматы (§4–§5)

- [ ] `ContentPillar` + `PostFormat` модели
- [ ] Форматы: short_post, story_post, weekend_digest, event_alert, museum_spotlight, city_micro_itinerary, visual_carousel, poll/quiz, product_spotlight, rich_guide
- [ ] Нативные Telegram methods по формату (`sendMessage` / photo / media group / poll / rich)
- [ ] Collapsed details для rich body (уже в dual-format branch) `[~]`
- [ ] Brand voice `wegotrip_voice_v1` + Style Gate
- [ ] Анти-повтор форматов/тем/городов/углов

---

## 4. OpenAI Chief Editor + календарь (§6)

- [ ] Daily `OpenAIChiefEditor` RU/EN раздельно (обязательный вызов)
- [ ] Structured `EditorialDecisionSet` + schema validation
- [ ] Horizons 30 / 7 / 2 days
- [ ] No silent SQL-only rebuild при падении AI
- [ ] Locked slots / diversity / caps
- [ ] `EditorialPreferenceLog` (human overrides)
- [ ] Dry-run 30 дней до production calendar

---

## 5. Sources & news (§7–§8)

- [ ] `SourceRegistry` + trust tiers A/B/C
- [ ] Event/Exhibition objects + TTL
- [ ] EvidenceRecord vs PublishedSourceReference
- [ ] Source minimalism + high-risk link exceptions
- [ ] Hosted web_search для public posts по умолчанию **выкл.**
- [ ] Newsworthiness + HighRiskTravelInfoGate
- [ ] CorrectionTask workflow

---

## 6. Медиа и коммерция (§9–§10)

- [x] Приоритет медиа WeGoTrip API
- [x] Generated covers off by default
- [ ] LicensedMediaProvider (MVP off)
- [ ] CTA policy `none | optional | required` по рубрике
- [ ] Commercial share ≤25%; product_spotlight ≤1/нед.
- [ ] Пост без товара допустим

---

## 7. Admin / publication / analytics (§15–§16)

- [ ] Calendar UI + review + pre-publish
- [ ] Test channel / pause queue
- [ ] Metrics: frequency, pillar/format, forwards/shares when available
- [ ] `branding_change_at` + 14/30d profile funnel (если данные есть)
- [ ] Frequency auto-adjust не раньше 4 недель данных

---

## 8. Миграция и флаги (§17)

- [x] План маппинга existing → new (`EDITORIAL_V2_IMPLEMENTATION_PLAN.md`)
- [ ] `EDITORIAL_V2_ENABLED=false` в Settings
- [ ] `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED` управляемый
- [ ] `EDITORIAL_V2_DRY_RUN=true`
- [ ] Не удалять старые articles / claims / telegram IDs
- [ ] Обратная совместимость edit старых Rich Messages

---

## 9. Definition of Done (выжимка §19)

- [ ] Старый mass schedule не работает параллельно новому
- [ ] Chief Editor вызывается на каждый daily rebuild
- [ ] Writer + Critic на каждый новый публикуемый текст
- [ ] Каналы: RU title сохранён, descriptions/EN title по approval
- [ ] Usernames и Community сохранены
- [ ] Branding apply/history/manual fallback
- [ ] Pinned welcome только после approval

---

## Открытые блокеры

| Пункт | Статус | Причина |
|---|---|---|
| Apply channel branding | `[!]` | Ждёт явного approval владельца (`CHANNEL_BRANDING_PROPOSAL.md`) |
| Live getChat snapshot | `[ ]` | Нужен рабочий SSH/prod или локальный `wgt` с bot token |
| Bot admin rights for setChat* | `[ ]` | Проверить права перед apply |
| Editorial V2 code | `[ ]` | Phase B–G по плану; флаги default off |
