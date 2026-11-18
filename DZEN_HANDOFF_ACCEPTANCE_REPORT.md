# Dzen handoff — acceptance report

**Date:** 18 Nov 2026, Europe/Moscow · **Branch:** `cursor/dzen-slack-handoff-01af`

Telegram RU/EN and MAX RU are unchanged. There is no Playwright/CDP/Dzen Studio bot.

## Checks

| # | Result | Evidence |
|---|---|---|
| 01 Independent Dzen plan + RU articles | PASS (tests) | `tests/test_dzen_pipeline.py` |
| 02 Structure, facts, optional RU products | PASS (tests) | pipeline + mock writer + gates |
| 03 `coupon=435` once, never on images | PASS | `tests/test_dzen_links.py` |
| 04 HTTPS Publishing Kit + media | PASS | kit page + ZIP manifest |
| 05 Copy title / rich / plain | PASS (UI) | `dzen_kit.html` clipboard buttons |
| 06 Paste into Dzen Studio | BLOCKED | requires the employee's Studio session |
| 07 Direct image URLs | PASS (tests) | https WeGoTrip CDN, no coupon |
| 08 ZIP cover + inline + manifest | PASS | `tests/test_dzen_pipeline.py` |
| 09 Mobile/desktop kit, no JSON/placeholders | PASS (UI + tests) | CSS + forbidden markers |
| 10 One real transfer | BLOCKED | staff has not published yet |
| 11 Slack channel | PASS after prod verify | `C…` only, never invented by name |
| 12 Mention `<@U03AE1ATKDJ>` | PASS (tests) | exactly one in digest text |
| 13 Monday off when TU,TH | PASS | `tests/test_dzen_policy.py` |
| 14 Tuesday 11:00, one mention, two kits | PASS | `tests/test_dzen_slack.py` |
| 15 Thursday does not resend | PASS | same |
| 16 Fri 23:59 / Sat / Sun | PASS | weekend = zero Slack calls |
| 17 Weekend drafts wait | PASS | weekdays_if_ready → Monday |
| 18 Duplicate worker | PASS | `already_sent_today` |
| 19 One ping per local day | PASS | mention budget |
| 20 No owner approval gate | PASS | `ready_for_handoff` is enough to hand off |
| 21 Thread URL or kit form | PASS | parser + kit confirm |
| 22 Bad URL not confirmed | PASS | `tests/test_dzen_confirm.py` |
| 23 `published_confirmed` only with URL | PASS | same |
| 24 No Dzen autopublish jobs | PASS | `DZEN_NATIVE_AUTOPUBLISH_ENABLED=false` |
| 25 Telegram/MAX regression | PASS | full pytest 324 passed |
| 26 Kit auth | PASS | admin Basic + unguessable `/dzen/k/{token}` |
| 27 Prod digest screenshot | N/A until TU/TH 11:00 | no staff ping on 18 Nov (Wednesday) |
| 28 Provenance | PASS | models, llm_runs, claim ledger, media rights source |

## Production notes

- First staff Slack mention waits for the next **Tuesday or Thursday 11:00 Europe/Moscow** with `ready_for_handoff` kits.
- `published_confirmed` is not claimed until the employee posts a real `dzen.ru` URL.
