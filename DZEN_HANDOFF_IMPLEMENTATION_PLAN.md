# Dzen Slack handoff — implementation plan

**Date:** 18 Nov 2026 · **Base:** `cursor/editorial-country-code-01af` (`d793334`)  
**Scope:** add an independent Dzen editorial contour to the existing WeGoTrip Editorial Engine. Telegram RU/EN and MAX RU stay untouched.

## GAP

| Capability | Before | After |
|---|---|---|
| Dzen article AST / long-form RU magazine | absent | `dzen_articles` + `app/dzen` |
| Independent Dzen calendar (not Telegram slots) | absent | planner, 2 articles/week TU/TH |
| Publishing Kit (copy HTML, images, ZIP, product links) | absent | `/admin/dzen` + tokenized `/dzen/k/{token}` |
| Weekday Slack digest, one mention/day, never weekend | absent | `DzenSlackDigestService` + Moscow TZ cron |
| Confirm public `dzen.ru` URL | absent | kit form + optional Slack thread parse |
| Playwright / Dzen Studio bot | none (keep none) | hard-disabled `DZEN_NATIVE_AUTOPUBLISH_ENABLED=false` |

Reuse: OpenAI `LLMGateway`, RU Affiliate catalog, `AffiliateLinkBuilder` (`coupon=435`), `MediaValidator`, Slack client, admin Basic auth, scheduler, budget manager.

Do **not** raise `DAILY_AI_BUDGET_USD`. Dzen spends inside the existing cap.

## Components

- `app/dzen/policy.py` — Europe/Moscow weekdays, batch modes, mention budget
- `app/dzen/planner.py` — independent briefs (not a Telegram mirror)
- `app/dzen/pipeline.py` — research / write / critic / fact+media gates
- `app/dzen/kit.py` — HTML/plain/ZIP/clipboard payload
- `app/dzen/slack_digest.py` — one digest, one `<@U03AE1ATKDJ>`
- `app/dzen/confirm.py` — public URL sanity
- Alembic `20261118_dzen_handoff`

## Slack channel

Use the existing articles channel via `DZEN_SLACK_CHANNEL_ID` or a confirmed `C…` `SLACK_CHANNEL`. Never invent a channel by name. Do not ping the staff member during implementation; first production mention waits for the next TU/TH 11:00 Europe/Moscow slot.

## Risks

- OpenAI spend vs $3/day cap — generate at most the weekly quota
- Slack scopes for thread replies may be missing — kit URL confirm is the mandatory fallback
- Image republish rights: reject unresolved assets rather than invent permission
- Employee still publishes manually; `published_confirmed` only after a real public URL
