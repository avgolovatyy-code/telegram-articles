# Post-Deploy Audit Report — WeGoTrip Editorial Engine

**Дата:** 28.10.2026 (Europe/Moscow)  
**Production SHA:** `4e304da` (ветка `cursor/max-russia-audience-acd7`)  
**Вердикт:** **NO_GO** (технический и продуктовый rollout v2.2 не подтверждён)

## Executive summary

Production **стабилен как v1 Content Engine** (контейнеры, Telegram/Max API, affiliate, idempotent publish, factcheck v1, branding Telegram). **Editorial Engine v2.2 как продукт не развёрнут:** нет Chief Editor, календаря 30/7/2, рубрик, native-форматов и целевой частоты 5–6 RU / 4–5 EN в неделю. После cutoff 28.10 **новых production-постов в Telegram нет** (backlog архивирован; ошибочный пост #462 снят). **OpenAI на момент аудита не генерирует контент** (`credit_balance_exhausted` / HTTP 429).

## Что подтверждено в production

| Блок | Статус | Доказательство |
|------|--------|----------------|
| Deployed version | PASS | `POST_DEPLOY_PRODUCTION_SNAPSHOT.json`, SSH `git rev-parse` |
| Telegram RU/EN branding (title/description) | PASS | `getChat` 28.10 — совпадает с `CHANNEL_BRANDING_PROPOSAL.md` |
| Telegram bot access (EN/RU/test) | PASS | `wgt check-telegram` |
| MAX RU channel + gate config | PASS | `wgt check-max`, `max.ru/channel_wegotrip` |
| Idempotency / test-before-prod pipeline | PASS | код + `tests/test_scheduling.py` |
| VERIFY OR OMIT (v1) | PASS | quality gates + claim tests |
| `coupon=435` / market domains | PASS | `tests/test_affiliate_links.py`, catalog host tests |
| Editorial cutoff / legacy backlog archive | PASS | 3263 archived, publish gate active |
| Исторические посты до 09.10 | PASS | 680 published (legacy v1) |

## Критические несоответствия задумке v2.2

1. **P0 — OpenAI billing:** нет кредитов → генерация и любой «живой» v2-контент заблокированы.
2. **P0 — Chief Editor / daily plan:** `OpenAIChiefEditor`, `DailyEditorialPlanner`, календарь — **отсутствуют в коде** (`NOT_IMPLEMENTED`).
3. **P1 — Старый mass-scheduler:** конфиг всё ещё ориентирован на **≥10 статей/день/рынок** (`EN/RU_ARTICLES_MIN_PER_DAY`); флаг `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=false` **до патча не останавливал** `generate_daily_articles` (исправление в ветке `cursor/post-deploy-audit-fixes-cc0c`).
4. **P1 — Частота v2.2:** фактическая лента сентября — **~18–22 поста/неделю/канал** (v1 SEO rich articles), не 5–6 / 4–5.
5. **P1 — AUTO_PUBLISH=true** на production при заявленном переходе на новые спеки и review-first пилот.
6. **P1 — Контент-модель:** доминируют audio-tour / skip-the-line SEO шаблоны, нет 13 рубрик, poll/quiz, audience split.

## MAX (in scope)

- Интеграция **технически работает** (check-max, отдельный renderer, audience gate, quota).
- После cutoff один Max-пост от **legacy** статьи #462 (до takedown в TG); **не считать** образцом v2.

## Live URLs

- RU: https://t.me/wegotrip_ru  
- EN: https://t.me/wegotrip  
- MAX: https://max.ru/channel_wegotrip  
- Admin: https://209-38-45-22.sslip.io/admin  

## Gates (§15)

| Gate | Result |
|------|--------|
| A Safety | PARTIAL — нет P0 publish-bypass, но autopublish on + нет v2 gates |
| B Product concept | **FAIL** |
| C Factcheck | **PASS** (v1 scope) |
| D Ops | PARTIAL — worker up, OpenAI/alerting слабые |
| E Analytics | **INSUFFICIENT_DATA** |

## 5 приоритетных действий

1. **Пополнить OpenAI** и подтвердить генерацию одного post-cutoff поста в test → prod.
2. **Выключить AUTO_PUBLISH_*** до готовности v2 (owner approval) — review-only.
3. **Принять PR** `cursor/post-deploy-audit-fixes-cc0c` (остановка legacy generate/schedule при `OLD_ARTICLE_AUTO_SCHEDULER=false`).
4. **Запланировать Phase C** (Chief Editor + calendar) — без этого **NO_GO → GO** невозможен.
5. **Owner:** ручная оценка `POST_DEPLOY_EDITORIAL_REVIEW.md` на исторической выборке v1 + pin-посты.

## Требуют одобрения владельца

- Включение autopublish после v2.
- Apply pinned welcome / EN title уже applied — pin не проверен.
- Max profile/branding (отдельно от Telegram).

## Осознанно не баги

- Снижение числа постов после cutoff — **политика**, не регресс.
- MAX в отдельном scope — Telegram audit не FAIL из-за незавершённого calendar MAX.
- 680 legacy posts в истории — сохранены намеренно (не удалялись в аудите).
