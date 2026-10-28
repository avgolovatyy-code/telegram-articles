# Предложение по оформлению каналов WeGoTrip — на одобрение

**Статус:** APPROVED (Telegram RU/EN) — применено через Bot API. Max профиль — отдельно, ждёт своего approval.  
**Спецификация:** `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` §0.1  
**Дата черновика:** 28.10.2026  
**Approved by:** владелец (чат Cursor) · **Date:** 28.10.2026 (Europe/Moscow)

## Что нельзя менять

| Сохранить | Значение |
|---|---|
| RU username / URL | `@wegotrip_ru` → https://t.me/wegotrip_ru |
| EN username / URL | `@wegotrip` → https://t.me/wegotrip |
| Подписчики, история постов, message IDs, Community | без изменений |
| Affiliate `coupon=435` | только в product links, **не** в bio |
| Работающий бот и публикации | без остановки |

Перед применением сверить фактические `getChat` title/description с таблицей ниже.

---

## Current → Proposed

### RU `@wegotrip_ru`

| Поле | Сейчас (публичная карточка на 28.10.2026) | Предложение | Действие |
|---|---|---|---|
| Title | `WeGoTrip — Куда сходить и что посмотреть` | **то же** | **не менять** |
| Description | содержит `wegotrip.com` (уточнить live) | см. строку ниже | **обновить** |
| Website в bio | должно быть `https://wegotrip.ru` | `https://wegotrip.ru` | исправить, если сейчас `.com` |
| Username | `@wegotrip_ru` | `@wegotrip_ru` | не менять |

**Новое описание RU (201 символ ≤ 255):**

```
Куда сходить в выходные и куда поехать дальше? Музеи, выставки, необычные места, маршруты и новости для местных и путешественников. Пишем по делу, с любопытством и иногда с улыбкой. https://wegotrip.ru
```

**Pinned welcome RU (draft):**

```
Привет! Это WeGoTrip 👋

Здесь ищем ответы на два вечных вопроса: куда выбраться в выходные и что посмотреть, когда уже выбрались. Подсказываем интересные музеи, выставки, прогулки и необычные места, рассказываем истории городов и делимся новостями, которые действительно пригодятся в поездке.

Иногда советуем аудиогиды и экскурсии WeGoTrip — когда они к месту. Иногда просто рассказываем что-то классное.

Если у вас пока нет планов на выходные, считайте, что теперь есть с чего начать.

English channel: @wegotrip
```

---

### EN `@wegotrip`

| Поле | Сейчас | Предложение | Действие |
|---|---|---|---|
| Title | `WeGoTrip — Things to Do & Tickets` | `WeGoTrip — Things to Do & Travel Ideas` | **переименовать** |
| Description | (уточнить live) | см. строку ниже | **обновить** |
| Website в bio | `https://wegotrip.com` | `https://wegotrip.com` | оставить EN-домен |
| Username | `@wegotrip` | `@wegotrip` | не менять |

**Новое название EN (38 ≤ 128):**

```
WeGoTrip — Things to Do & Travel Ideas
```

**Новое описание EN (203 ≤ 255):**

```
Good ideas for this weekend and your next trip. Museums, exhibitions, surprising places, city routes and travel updates for locals and travelers. Useful, curious, occasionally witty. https://wegotrip.com
```

**Pinned welcome EN (draft):**

```
Hi, we're WeGoTrip 👋

For the weekends when you want to get out, and the trips when you want to see more than the usual checklist. Expect clever city ideas, exhibitions, museums, unusual places, useful travel updates and the odd story worth sharing.

Sometimes there's a WeGoTrip audio tour that fits perfectly. Sometimes a good idea is all you need.

Your next plan might be one post away.

По-русски: @wegotrip_ru
```

---

## Альтернативы (только ручной выбор, не по умолчанию)

- RU title alt: `WeGoTrip — Идеи для выходных и поездок` — **не рекомендуется** как основное; текущий RU title лучше.
- EN title alt: `WeGoTrip — Places to Go & Things to Do` — запасной вариант.

## Правила применения

1. Показать preview current vs proposed в админке (Phase B) **или** этот файл.
2. Явное approval владельца (`approved_by` + timestamp).
3. Bot API: `setChatTitle` / `setChatDescription` / при необходимости `pinChatMessage` — только при правах admin; иначе copy-ready manual checklist.
4. Не раззакреплять существующие важные пины молча — сначала список пинов.
5. Chief Editor / ежедневный план **никогда** не меняет профиль автоматически.
6. Смена оформления **не блокирует** остальной Editorial Engine.
7. Max RU branding синхронизировать **отдельно** и только после approval Telegram RU (см. `app/max/branding.py`).

## Чеклист одобрения владельца

- [x] Согласовано: RU title оставить
- [x] Согласовано: RU description (текст выше)
- [x] Согласовано: EN title rename
- [x] Согласовано: EN description
- [x] Согласовано: тексты pinned RU/EN (или правки вписаны ниже)
- [x] Подтверждено: не создавать новые каналы / не менять username
- [x] Способ применения: Bot API
- [x] Approved by: владелец (Cursor chat)  Date: 2026-10-28 (Europe/Moscow)

### Правки владельца (если нужны)

```
(нет — применено как в proposal)
```

### Применение (факт)

- Telegram RU: description + pinned welcome
- Telegram EN: title + description + pinned welcome
- Max RU branding: **не** применялось в этом approval (см. `MAX_IMPLEMENTATION_PLAN.md`)
