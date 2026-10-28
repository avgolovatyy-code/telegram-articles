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

## Не запускалось на production

- `pytest` в prod-образе (pytest не установлен в runtime image) — **ожидаемо**.
- UAT сценарии §18 с live OpenAI — **BLOCKED** (billing).
- Negative fixtures NEG-01, NEG-03, NEG-04 end-to-end — **NOT_IMPLEMENTED** (нет Chief Editor job).

## Новые тесты в fix-ветке

- `test_legacy_scheduler_off_skips_generate_and_schedule` — проверяет остановку v1 generate/schedule при `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED=false`.
