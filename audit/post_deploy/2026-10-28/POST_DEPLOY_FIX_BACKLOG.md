# Fix Backlog (prioritized)

## P0

| ID | Issue | Repro | Root cause | Fix | Owner | AC |
|----|-------|-------|------------|-----|-------|-----|
| P0-OPENAI | No generation | `wgt generate` → failed 429 | OpenAI `credit_balance_exhausted` | Top up billing | Owner | `/responses` 200, 1 needs_review post |
| P0-V2-PLAN | No Chief Editor | No table/job | Phase C not built | Implement planner + migrations | Eng | AI-01 matrix PASS |

## P1

| ID | Issue | Fix | Branch |
|----|-------|-----|--------|
| P1-SCHED-LEGACY | OLD_ARTICLE=false but generate ran | Early return in generate+schedule | `cursor/post-deploy-audit-fixes-cc0c` |
| P1-AUTOPUBLISH | AUTO_PUBLISH true vs review pilot | Set false in .env (owner) | ops |
| P1-FREQ | 10+/day mins vs 5–6/week | Wire weekly caps; disable v1 mins when v2 | future PR |
| P1-FLAGS | EDITORIAL_V2_ENABLED unused | Wire or document as placeholder | future PR |
| P1-CONTENT | Legacy SEO flood history | Already cutoff+archive; no v1 publish | done |

## P2

| ID | Issue | Fix |
|----|-------|-----|
| P2-SLACK-URL | Interactivity URLs | Owner configures Slack app |
| P2-SECRETS | Plaintext ADMIN_PASSWORD in .env | `wgt secrets import-env` |
| P2-PIN | Pinned welcome not verified | Owner check + optional apply |
| P2-MAX-LEGACY | Max post from #462 | Manual delete in Max UI if needed |

## P3

| ID | Issue |
|----|-------|
| P3-VOICE | Style gate + anti-template corpus |
| P3-ANALYTICS | Forward/reaction collectors v2 |

## Safe fixes in PR (this audit)

- `app/scheduler/jobs.py`: honor `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED` for generate + schedule.
- `tests/test_editorial_eligibility.py`: regression test.

**Rollback risk:** low — only skips v1 jobs when flag already false on prod.
