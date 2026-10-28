# Post-Deploy Test Results

**Дата:** 28.10.2026

## Локальный прогон (audit VM)

```bash
cd /workspace && python3 -m pip install -e ".[dev]" && python3 -m pytest -q
```

**Результат:** все тесты зелёные (248 passed, ~23s).

Релевантные наборы для audit:

| Область | Файлы |
|---------|--------|
| Editorial cutoff | `tests/test_editorial_eligibility.py` |
| Scheduling / test channel | `tests/test_scheduling.py` |
| Affiliate / coupon | `tests/test_affiliate_links.py` |
| Claims / verification | `tests/test_claims_and_verification.py` |
| Max audience | `tests/test_max_audience.py` |
| Telegram publish | `tests/test_telegram.py` |
| Branding proposal | `tests/test_branding_proposal.py` |

## Production (read-only)

| Команда | Результат |
|---------|-----------|
| `wgt doctor` | DB, Telegram, OpenAI key present, Max enabled; plaintext secrets warning |
| `wgt check-telegram` | EN/RU/test OK |
| `wgt check-max` | channel_wegotrip OK |
| OpenAI probe (agent env) | `429 credit_balance_exhausted` on `/v1/responses` |
| `getChat` RU/EN | title/description match branding proposal |

## Verification R2 (28.10.2026 ~20:45 MSK)

**Production SHA:** `852bc00` · ветка `cursor/editorial-v2-compliance-cc0c`

| Команда | Результат |
|---------|-----------|
| `pytest` (audit VM) | **256 passed** (~21s) |
| `wgt doctor` | OpenAI **ok**; `! auto_publish_off` (AUTOPUBLISH true) |
| `wgt chief-editor --market ru` | ok, `dry_run`, LLM ~24s |
| `wgt chief-editor --market en` | ok, `dry_run`, LLM ~19s |
| `wgt generate --market ru` | `editorial_v2_plan`, 0 generated (no slots) |
| SQL `editorial_plan_slots` | **0 rows** |

Отчёт: `POST_DEPLOY_VERIFICATION_R2.md` · матрица: `POST_DEPLOY_REQUIREMENTS_MATRIX_R2.csv`

## Не запускалось на production

- `pytest` в prod-образе (tests не в образе) — **ожидаемо**; прогон на audit VM.
- End-to-end publish v2 после cutoff — **нет слотов** (`EDITORIAL_V2_DRY_RUN=true`).
- Negative fixtures NEG-01 end-to-end — **PARTIAL** (failed runs пишутся; policy «keep last plan» без теста).

## Новые тесты в fix-ветке

- `test_legacy_scheduler_off_skips_generate_and_schedule` — проверяет остановку v1 generate/schedule при `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=false`.
