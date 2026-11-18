# Dzen handoff — acceptance report

**Date:** 18 Nov 2026, Europe/Moscow · **Branch:** `cursor/dzen-slack-handoff-01af` · **SHA:** `efecb81` · **PR:** https://github.com/avgolovatyy-code/telegram-articles/pull/16

Telegram RU/EN and MAX RU are unchanged. There is no Playwright/CDP/Dzen Studio bot.

## Checks

| # | Result | Evidence |
|---|---|---|
| 01 Independent Dzen plan + RU articles | PASS | Prod `wgt dzen-plan` created 4 RU slots; first kit is a Kazan long-form, not a Telegram mirror |
| 02 Structure, facts, optional RU products | PASS | Writer + claims + critic on prod; 3 RU products attached |
| 03 `coupon=435` once, never on images | PASS | Product URLs have `coupon=435`; cover URL has none |
| 04 HTTPS Publishing Kit + media | PASS | `GET /dzen/k/{token}` 200; ZIP 1.4 MB |
| 05 Copy title / rich / plain | PASS | Live kit buttons; copy-title and copy-rich confirmed in browser |
| 06 Paste into Dzen Studio | BLOCKED | Requires the employee's Studio session |
| 07 Direct image URLs | PASS | HTTPS WeGoTrip S3/CDN, no coupon |
| 08 ZIP cover + inline + manifest | PASS | `00_cover.jpg` + 4 inline + `media_manifest.txt` |
| 09 Mobile/desktop kit, no JSON/placeholders | PASS | 390px wrap verified; no `{{` placeholders |
| 10 One real transfer | BLOCKED | Staff has not published yet |
| 11 Slack channel | PASS | Existing editorial `C…` id in `DZEN_SLACK_CHANNEL_ID`; no new channel |
| 12 Mention `<@U03AE1ATKDJ>` | PASS (tests + policy) | Digest text has one mention; not sent today |
| 13 Monday off when TU,TH | PASS | `tests/test_dzen_policy.py` |
| 14 Tuesday 11:00, one mention, two kits | PASS | `tests/test_dzen_slack.py` |
| 15 Thursday does not resend | PASS | same |
| 16 Fri 23:59 / Sat / Sun | PASS | weekend = zero Slack calls |
| 17 Weekend drafts wait | PASS | weekdays_if_ready → Monday |
| 18 Duplicate worker | PASS | `already_sent_today` |
| 19 One ping per local day | PASS | mention budget |
| 20 No owner approval gate | PASS | `ready_for_handoff` is enough to hand off |
| 21 Thread URL or kit form | PASS | parser + kit confirm form live |
| 22 Bad URL not confirmed | PASS | `tests/test_dzen_confirm.py` |
| 23 `published_confirmed` only with URL | PASS | same; prod `published_url` is still null |
| 24 No Dzen autopublish jobs | PASS | `DZEN_NATIVE_AUTOPUBLISH_ENABLED=false` |
| 25 Telegram/MAX regression | PASS | pytest 324; prod scheduler still has Telegram/MAX jobs |
| 26 Kit auth | PASS | admin Basic + unguessable `/dzen/k/{token}` |
| 27 Prod digest screenshot | N/A until TU/TH 11:00 | 18 Nov 2026 Wednesday: `wgt dzen-digest --force` → `sent=false`, `mentioned=false`, `not_delivery_day` |
| 28 Provenance | PASS | models, llm_runs, claim ledger, media from catalog |

## Production evidence (18 Nov 2026, Europe/Moscow)

- Droplet `/opt/wegotrip-content-engine` on `efecb81`; alembic `d1e2f3a4b5c6`.
- Flags kept: `AUTO_PUBLISH_EN=true`, `AUTO_PUBLISH_RU=true`, `EDITORIAL_V2_ENABLED=true`, `DAILY_AI_BUDGET_USD=3.0`. Dzen spend today ≈ $0.08; remaining ≈ $2.92.
- `healthz`/`readyz` 200. Worker jobs include existing Telegram cadence **and** `dzen_planner` 03:45, `dzen_generate` 04:30, `dzen_slack_digest` 11:00 Europe/Moscow.
- First ready kit: «Казань на зимний уикенд: два дня от Кремля до тёплых вечерних улиц» (`MQ5kQ398DFQ`, planned Thu 19 Nov 2026).
- Three leftover candidates for 24 Nov / 26 Nov / 1 Dec (not generated today, to keep the shared AI budget).
- First staff Slack mention waits for the next **Tuesday or Thursday 11:00 Europe/Moscow** with `ready_for_handoff` kits.
- `published_confirmed` is not claimed until the employee posts a real `dzen.ru` URL.
