# EDITORIAL_V2_REQUIREMENTS_STATUS

Чеклист по `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` (заменяет v2.1).  
Легенда: `[x]` сделано · `[~]` частично / foundation · `[ ]` не сделано · `[!]` ждёт approval.

Фундамент Content Engine (каталог, affiliate, rich publisher, budget, factcheck) — см. также `REQUIREMENTS_STATUS.md` (v1). Здесь — **дельты Editorial Engine 2.2**.

Обновлено: 2026-10-28 (verification R2, prod `852bc00`).

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
- [x] Approval владельца получено (`approved_by` / дата 2026-10-28)
- [x] Live `getChat` сверка title/description перед apply

### Целевые строки (draft)

- [x] RU title оставить: `WeGoTrip — Куда сходить и что посмотреть`
- [x] RU description draft с `https://wegotrip.ru` (201 chars ≤ 255)
- [x] EN title draft: `WeGoTrip — Things to Do & Travel Ideas` (38 ≤ 128)
- [x] EN description draft с `https://wegotrip.com` (203 ≤ 255)
- [x] RU/EN pinned welcome drafts в proposal
- [x] Альтернативы title задокументированы как ручной выбор only

### Продукт / админка Channel Identity

- [~] Блок Channel Identity в admin (RU/EN независимо) — `/admin/branding` preview
- [~] Поля: chat_id, username RO, title, description, website_url, avatar_status, pinned_welcome_text, pinned_message_id, branding_version, status, approved_by, applied_at — DB `channel_branding_history` + proposal
- [x] Preview proposed changes + length validation (Unicode)
- [ ] Apply через `setChatTitle` / `setChatDescription` / `pinChatMessage` при правах
- [ ] Manual checklist fallback при отсутствии прав
- [ ] `channel_branding_history` + откат
- [ ] Список существующих pins перед заменой (без silent unpin)
- [ ] Chief Editor **не** меняет профиль автоматически
- [x] `CHANNEL_BRANDING_APPLY_ENABLED=false` по умолчанию
- [x] `app/branding/apply.py` — Bot API apply gated by flag / `--yes`
- [x] Оформление не блокирует Editorial Engine при отсутствии прав
- [ ] Max RU branding sync после approval Telegram RU (отдельный Max approval)

### Acceptance §0.1 / §19.24–27

- [x] Утверждённые title/description применены (Telegram RU/EN)
- [x] `@username` прежние
- [x] RU website `.ru`, EN website `.com` в bio
- [x] Welcome posts после approval владельца
- [x] Подписчики / публикации / Community неизменны

---

## 1. Миссия и аудитории (§0–§2)

- [ ] Редакционная миссия: travel & local discovery media (не SEO-витрина) — продуктово
- [ ] Audience tags: `local | traveler | both`
- [ ] RU mix hypothesis 50/35/15; EN 35/45/20 — конфиг, не жёсткая квота
- [ ] Анти-одногородковая лента

---

## 2. Частота (§3) — замена 10–20/день

- [~] RU target 5–6/нед., hard cap 8 — `app/editorial/cadence.py` + Settings
- [~] EN target 4–5/нед., hard cap 7 — wired в scheduler/budget при `EDITORIAL_V2_ENABLED`
- [~] ≤1 основной пост/день (+ emergency flag) — `max_posts_per_day` + publish caps
- [~] Min interval ≥6h (предпочитать 18–24h) — `effective_min_post_interval_minutes`
- [ ] Rich guide ≤1–2/месяц/канал
- [ ] Weekend/holiday planner hooks
- [x] Выключить/ограничить старый mass article auto-scheduler флагом при rollout

---

## 3. Рубрики и форматы (§4–§5)

- [~] `ContentPillar` + `PostFormat` модели — `app/editorial/pillars.py` + slot fields
- [ ] Форматы: short_post, story_post, weekend_digest, event_alert, museum_spotlight, city_micro_itinerary, visual_carousel, poll/quiz, product_spotlight, rich_guide
- [ ] Нативные Telegram methods по формату (`sendMessage` / photo / media group / poll / rich)
- [ ] Collapsed details для rich body (уже в dual-format branch) `[~]`
- [ ] Brand voice `wegotrip_voice_v1` + Style Gate
- [ ] Анти-повтор форматов/тем/городов/углов

---

## 4. OpenAI Chief Editor + календарь (§6)

- [x] Daily `OpenAIChiefEditor` RU/EN раздельно — `ChiefEditorService` + cron + `wgt chief-editor`
- [x] Structured `EditorialDecisionSet` + schema validation — `app/editorial/schemas.py`
- [~] Horizons 30 / 7 / 2 days — admin UI 30d; 7/2 и locked slots не выделены
- [~] No silent SQL-only rebuild при падении AI — failed `editorial_runs`; нет автотеста NEG-01
- [~] Locked slots / diversity / caps — cadence caps wired; planner diversity partial
- [~] `EditorialPreferenceLog` (human overrides) — модель в БД, UI/workflow нет
- [ ] Dry-run 30 дней до production calendar — prod: `DRY_RUN=true`, **0** plan slots

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

- [~] Calendar UI + review + pre-publish — `/admin/editorial` (30d slots; пусто на prod R2)
- [ ] Test channel / pause queue
- [ ] Metrics: frequency, pillar/format, forwards/shares when available
- [ ] `branding_change_at` + 14/30d profile funnel (если данные есть)
- [ ] Frequency auto-adjust не раньше 4 недель данных

---

## 8. Миграция и флаги (§17)

- [x] План маппинга existing → new (`EDITORIAL_V2_IMPLEMENTATION_PLAN.md`)
- [x] `EDITORIAL_V2_ENABLED` — cadence, budget, scheduler, Chief Editor path
- [x] `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED` управляемый
- [x] `EDITORIAL_V2_DRY_RUN=true` в Settings / env
- [ ] Не удалять старые articles / claims / telegram IDs
- [ ] Обратная совместимость edit старых Rich Messages

---

## 9. Definition of Done (выжимка §19)

- [ ] Старый mass schedule не работает параллельно новому
- [~] Chief Editor вызывается на каждый daily rebuild — cron 3×/день; prod пока только `dry_run` runs
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
| Editorial V2 rollout | `[ ]` | Phase C smoke OK; **NO_GO** — DRY_RUN, 0 slots, AUTO_PUBLISH on (см. `POST_DEPLOY_VERIFICATION_R2.md`) |
| OpenAI billing | `[x]` | R2: chief_editor + doctor ok на prod |
