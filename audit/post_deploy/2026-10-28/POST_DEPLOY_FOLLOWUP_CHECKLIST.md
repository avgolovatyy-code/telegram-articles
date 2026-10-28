# Follow-up Checklist

## После пополнения OpenAI (owner)

- [ ] `wgt doctor` — OpenAI ok
- [ ] Один `wgt generate --market ru --max-articles 1` → `needs_review`
- [ ] Test → prod RU + Max fan-out (owner approval)
- [ ] Обновить матрицу AI-04b, AUTO-05

## После merge fix-PR

- [ ] Подтвердить worker logs: `legacy_scheduler skipped` на generate/schedule
- [ ] Обновить SCHED-01 → PASS

## 7 дней (plan)

- [ ] Ежедневно: worker errors, OpenAI spend, queue depth
- [ ] Частота постов / канал (не ожидать v2 caps без Phase C)

## 28 дней (plan)

- [ ] Пересчитать rubric/format mix, reactions/forwards if API available
- [ ] Re-audit Gate E

## Owner approvals required

- [ ] AUTO_PUBLISH on/off policy
- [ ] Editorial voice sample (`POST_DEPLOY_EDITORIAL_REVIEW.md`)
- [ ] Pinned posts
- [ ] Max profile (separate from Telegram)
