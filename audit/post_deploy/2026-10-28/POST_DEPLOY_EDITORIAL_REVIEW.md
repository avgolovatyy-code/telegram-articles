# Editorial Review (sample)

**Статус выборки:** `INSUFFICIENT_DATA` для post-cutoff v2; ниже — **10+10 последних legacy-постов** (09.10.2026) для baseline v1.

## Метод

Автоматический Critic по production не запускался (нет writer_run_id в БД). Оценки — **редакционный аудит по заголовкам/известному v1-шаблону**; финальный вердикт — **owner**.

Шкала 0–5 (см. audit spec §8.2). `not_rated` для post-cutoff (0 постов).

## RU — последние 10 (published 2026-10-09)

| # | id | Заголовок (сокр.) | Hook | Value | Factuality | Originality | Commercial | Notes |
|---|-----|-------------------|------|-------|------------|-------------|------------|-------|
| 1 | 1410 | Аудиогид по Сочи | 2 | 3 | 3 | 2 | 2 | SEO product-led |
| 2 | 1414 | Петергоф маршруты | 3 | 3 | 3 | 2 | 2 | турист, не local weekend |
| 3 | 1413 | Н.Новгород 4 прогулки | 3 | 3 | 3 | 2 | 2 | |
| 4 | 1411 | Кунсткамера экспонаты | 3 | 4 | 3 | 2 | 2 | |
| 5 | 1416 | Казань маршруты | 3 | 3 | 3 | 2 | 2 | |
| 6 | 1412 | Москва 4 маршрута | 3 | 3 | 3 | 2 | 2 | |
| 7 | 1420 | (batch) | — | — | — | — | — | см. t.me/wegotrip_ru |
| 8–10 | … | audio tour / tickets pattern | 2–3 | 2–3 | 3 | 1–2 | 2–3 | однотипные интенты |

**Средний ориентир RU legacy:** ~2.5–3/5 по «живому медиа»; **не соответствует** v2.2 (local/traveler mix, rubrics, commercial restraint).

## EN — последние 10 (published 2026-10-09)

| Pattern | Examples |
|---------|----------|
| "Best … audio tours" | Vienna, Chicago museums |
| "What to See at …" | Amsterdam, Notre Dame |
| City itineraries | Naples, Florence, Lisbon |

**EN independent market:** PASS (отдельные темы, не перевод RU). **Voice/format:** v1 SEO longform, not v2 short/native.

## Owner human review (TODO)

Поля для 6–10 постов владельца:

- [ ] `approve_voice`
- [ ] `needs_rewrite`
- [ ] `reject_topic`

Ссылки: https://t.me/wegotrip_ru/336 … /341 (341 снят 28.10)

## Anti-template scan (60d heuristic)

Частые паттерны в заголовках legacy: «Лучшие …», «What to See at», «audio guide», «skip the line», «Walking Tour». **P2:** обновить Style Gate / voice guide при Phase B.
