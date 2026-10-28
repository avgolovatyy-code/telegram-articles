# Content Plan Review (30/7/2)

**Статус:** **NOT_IMPLEMENTED** — в production нет `editorial_slots`, `DailyEditorialBrief`, `editorial_run_id`.

## Наблюдаемое вместо календаря v2

| Механизм | Факт |
|----------|------|
| Topic discovery | `wgt discover-topics` / cron 03:00 |
| Generation | `generate_daily_articles` — budget + **min 10/market/day** (v1) |
| Schedule | `schedule_publications` — окно 10–21 MSK, spacing 20 min |
| Post-cutoff | `EDITORIAL_SPEC_CUTOFF_DATE=2026-10-28`, backlog archived |
| Chief Editor | **нет job** |

## Следующие 7 / 14 дней

**План от OpenAI:** отсутствует (`INSUFFICIENT_DATA`).

**Очередь publication_queue:** pending due = 0 (на момент аудита).

**Scheduled articles:** 0 post-cutoff `needs_review`.

## Locked slots / AI decisions

Не применимо — нет модели календаря.

## Рекомендация

До Phase C использовать **review-only** + ручной/`wgt publish-test` пилот; не включать v1 mass generation (`OLD_ARTICLE_AUTO_SCHEDULER=false` + патч generate/schedule).
