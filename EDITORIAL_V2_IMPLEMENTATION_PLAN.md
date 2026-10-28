# EDITORIAL_V2_IMPLEMENTATION_PLAN — WeGoTrip Telegram Editorial Engine 2.2

Рабочий план миграции с Content Engine v1 / Editorial v2.1 → **v2.2**.  
Основной источник: `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` (заменяет v2.1).  
Статус требований: `EDITORIAL_V2_REQUIREMENTS_STATUS.md`.  
Предложение по оформлению каналов (approval first): `CHANNEL_BRANDING_PROPOSAL.md`.

Предыдущий план Content Engine (`IMPLEMENTATION_PLAN.md` + `REQUIREMENTS_STATUS.md`) **сохраняется** как история реализованного фундамента; новые этапы ведутся здесь.

---

## 0. Непереговорные инварианты

| Инвариант | Значение |
|---|---|
| Каналы | Только `@wegotrip` и `@wegotrip_ru` — **не создавать** новые |
| URL / username / ID / Community / подписчики / история постов | без изменений |
| Affiliate | `coupon=435`, домены `wegotrip.com` / `wegotrip.ru` |
| Бюджет AI | ~$3/сутки, ledger, reservations |
| VERIFY OR OMIT | фактчек, review mode, idempotent publish |
| Max RU | вторичный fan-out; не ломать; branding Max — отдельно после approval Telegram |
| Оформление каналов | **только после явного approval**; не блокер редакционных фич |
| Старый cadence 10–20 статей/день | **отменён**; цели: RU 5–6/нед., EN 4–5/нед. |

---

## 1. Phase B.0 — Позиционирование и оформление каналов (§0.1) — ПРИОРИТЕТ №1

### Зачем

Каналы становятся travel & local discovery media, а не SEO-витриной билетов. Профиль должен это отражать **без** потери бренда WeGoTrip и без смены адресов.

### Утверждённый draft (см. `CHANNEL_BRANDING_PROPOSAL.md`)

| Market | Title | Description website | Title action |
|---|---|---|---|
| RU | `WeGoTrip — Куда сходить и что посмотреть` | `https://wegotrip.ru` | **оставить** |
| EN | `WeGoTrip — Things to Do & Travel Ideas` | `https://wegotrip.com` | **переименовать** с `… & Tickets` |

Описания и pinned welcome — полные тексты в proposal-файле; длины ≤ лимитов Bot API (title 128, description 255).

### Реализация в продукте (после/параллельно с approval UX)

1. Админка: блок **Channel Identity / Оформление каналов** (RU/EN независимо).  
   Поля: `telegram_chat_id`, `username` (RO), `title`, `description`, `website_url`, `avatar_status`, `pinned_welcome_text`, `pinned_message_id`, `branding_version`, `status`, `approved_by`, `applied_at`.
2. **Preview proposed changes**: current vs proposed, счётчик символов, предупреждения.
3. Apply только после approval: Bot API `setChatTitle`, `setChatDescription`, при необходимости `pinChatMessage`; иначе copy-ready manual checklist.
4. История `channel_branding_history` + откат; не silent unpin важных пинов.
5. OpenAI Chief Editor **запрещено** менять title/description/avatar/pin при daily rebuild (максимум отдельный draft-совет).
6. Аналитика (позже): `branding_change_at`, сравнение profile_views → joins 14/30д при наличии данных.
7. Max: обновить `app/max/branding.py` под новое RU description **только после** approval Telegram RU.

### Порядок работ

```text
[1] Proposal файл + чеклист approval          ← сейчас
[2] Admin Channel Identity (draft/preview)    ← Phase B
[3] Owner approval                            ← человек
[4] Apply via Bot API или manual checklist
[5] Sync Max RU chrome (optional, separate)
```

Смена оформления **не блокирует** Phase C–G.

---

## 2. Маппинг existing → new

| Существующий компонент | Действие | Новый / изменённый компонент |
|---|---|---|
| `app/catalog/*`, Affiliate sync | **reuse** | CatalogProvider, NormalizedCatalog |
| `app/links/affiliate.py` (`coupon=435`) | **reuse** | без изменений контракта |
| `app/topics/*` discovery/scoring | **refactor** | IdeaCandidate + diversity; cadence weekly |
| `app/ai/*` LLMGateway, budget, prompts | **extend** | Chief Editor + Writer + Critic + voice |
| `app/generation/*` Article JSON pipeline | **extend** | PostFormat / short formats + rare rich_guide |
| `app/telegram/*` RichMessage, publisher | **extend** | `sendMessage`/`sendPhoto`/`sendMediaGroup`/`sendPoll` + rich; collapsed details |
| `app/max/*` RU fan-out | **reuse** | не ломать; branding sync later |
| `app/services/workflow.py` | **extend** | editorial statuses, pre-publish |
| `app/admin/*` | **extend** | Channel Identity, calendar, evidence |
| `app/analytics/*` | **extend** | media metrics, forwards when available |
| `app/scheduler/jobs.py` | **refactor** | flags: disable mass article auto-publish |
| Daily 10–20 articles target | **deprecate** | RU 5–6 / EN 4–5 per week |
| SEO-first longform every day | **deprecate as default** | rich_guide 1–2/month/channel |

---

## 3. Feature flags (конвенция проекта)

Привести к `Settings` / env (имена ориентировочные):

```env
EDITORIAL_V2_ENABLED=false
OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=true
EDITORIAL_V2_DRY_RUN=true
REVIEW_MODE / AUTO_PUBLISH_* — уже есть
RU_POSTS_PER_WEEK_MIN=5
RU_POSTS_PER_WEEK_MAX=6
EN_POSTS_PER_WEEK_MIN=4
EN_POSTS_PER_WEEK_MAX=5
MAX_POSTS_PER_DAY=1
MAX_LONGFORM_ARTICLES_PER_MONTH=2
MAX_COMMERCIAL_POST_SHARE=0.25
OPENAI_CHIEF_EDITOR_DAILY=true
EDITORIAL_VOICE_VERSION=wegotrip_voice_v1
OPENAI_HOSTED_WEB_SEARCH_FOR_PUBLIC_POSTS=false
CHANNEL_BRANDING_APPLY_ENABLED=false
```

Старый scheduler нельзя оставить публикующим десятки статей **параллельно** новому календарю после rollout.

---

## 4. Этапы (как в §18 спецификации)

| Phase | Содержание | Зависимость от branding |
|---|---|---|
| **A** | Audit, эти два файла плана/статуса, маппинг | proposal готов |
| **B.0** | Channel identity draft/preview/approval/apply | **approval first** |
| **B.1** | Brand voice, pillars, PostFormat, style gate | независимо |
| **C** | OpenAI Chief Editor + rolling calendar 30/7/2 | независимо |
| **D** | SourceRegistry, museums/events/news | независимо |
| **E** | Admin calendar + publication UX | после C skeleton |
| **F** | Analytics media quality | после E |
| **G** | Dry-run → review-mode → selective autopublish | после C+E; branding желателен, не блокер |

---

## 5. Архитектура целевого цикла (кратко)

```text
Catalog + Sources + Holidays + Trends
        → Evidence / FactBundles
        → OpenAI Chief Editor (RU | EN daily)
        → Constraints / Diversity / Caps
        → OpenAI Writer + Critic (+ voice)
        → PrePublishValidator
        → Telegram (native format by PostFormat) [+ Max RU fan-out]
        → Metrics → next editorial run
```

LLM **не** владеет affiliate URL и **не** меняет channel profile.

---

## 6. Частота и коммерция (замена старых норм)

- RU: **5–6**/нед. (hard cap 8); EN: **4–5**/нед. (hard cap 7).
- Обычно ≤1 основной пост/день; пустой день ок.
- Min gap 6h (лучше 18–24h для non-urgent).
- Rich guide: 1–2/месяц на канал.
- Прямой selling ≤1/нед.; CTA-посты ≤ ~25% ленты.
- Товар необязателен; `coupon=435` только когда есть реальный product link.

---

## 7. Риски миграции

| Риск | Митигация |
|---|---|
| Случайная смена username / новый канал | жёсткий запрет в коде/доках; apply только title/description/pin |
| Auto-apply branding Chief Editor | запрет в промпте + флаг `CHANNEL_BRANDING_APPLY_ENABLED` |
| Двойная публикация old+new schedulers | flags; выключить old auto после dry-run |
| Потеря rich articles | сохранить pipeline; редкий format `rich_guide` |
| Max устаревший bio | sync после Telegram RU approval |

---

## 8. Ближайшие конкретные шаги

1. ✅ Спека v2.2 в репозитории; proposal оформления; этот план + чеклист.  
2. Добавить feature flags Editorial V2 (default off) в `Settings`.  
3. Admin Channel Identity: preview current vs proposed (без apply).  
4. Voice pack + PostFormat skeleton.  
5. Chief Editor dry-run (structured decisions, no publish).  
6. После approval владельца — apply branding + обновить Max RU description.
