# Post-Deploy Verification R2 — Editorial v2.2 readiness

**Дата:** 28.10.2026, ~20:45 (Europe/Moscow)  
**Production SHA:** `852bc00` (`cursor/editorial-v2-compliance-cc0c`)  
**Исполнитель:** Cloud Agent (полная верификация по запросу владельца)

## Вердикт

| Область | Вердикт |
|---------|---------|
| **Content Engine v1** (инфра, Telegram/Max, affiliate, factcheck, idempotency) | **GO** — стабилен, 256/256 unit-тестов |
| **Editorial Engine v2.2** (продукт по спеке) | **NO_GO** — Phase C частично, календарь пустой, контент-пайплайн v2 не замкнут |
| **Gate B (Product concept)** | **FAIL** |
| **Gate A (Safety)** | **FAIL** — `AUTO_PUBLISH_EN/RU=true` при пустом v2-календаре |
| **Gate C (Factcheck v1)** | **PASS** |
| **Gate D (Ops)** | **PARTIAL** — OpenAI восстановлен; 4 failed Chief Editor runs до ключа |
| **Gate E (Analytics)** | **INSUFFICIENT_DATA** — нет постов после cutoff |

**Итог одной строкой:** деплой и OpenAI в порядке, Chief Editor **вызывается и отвечает**, но **production rollout v2.2 не готов** — решения не материализуются в календарь (`DRY_RUN`), слотов 0, автопубликация включена.

---

## Что проверено (scope)

1. Production SSH: git SHA, effective settings из контейнера, `wgt doctor`, `check-telegram`, `check-max`
2. Smoke: `wgt chief-editor` RU + EN, `wgt generate`, `wgt schedule`
3. БД: `editorial_runs`, `editorial_plan_slots`, публикации после cutoff
4. Worker logs 48h, cron jobs (chief editor 3×/день)
5. Локально: полный `pytest` (256 tests)
6. Сверка кода с `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` + `EDITORIAL_V2_REQUIREMENTS_STATUS.md`

**Не делалось (без явного approval):**

- `EDITORIAL_V2_DRY_RUN=false` на проде (запись слотов в календарь)
- Изменение `AUTO_PUBLISH_*`
- Production publish / test-channel UAT с новым контентом

---

## Production snapshot (факты)

| Параметр | Значение |
|----------|----------|
| `EDITORIAL_V2_ENABLED` | `true` |
| `EDITORIAL_V2_DRY_RUN` | `true` |
| `OLD_ARTICLE_AUTO_SCHEDULER_ENABLED` | `false` |
| `OPENAI_CHIEF_EDITOR_Daily` (effective) | `true` |
| `AUTO_PUBLISH_EN` / `AUTO_PUBLISH_RU` | `true` / `true` |
| `EN/RU_ARTICLES_MIN_PER_DAY` | `10` (legacy noise в .env) |
| `EDITORIAL_SPEC_CUTOFF_DATE` | `2026-10-28` |
| OpenAI probe (`doctor`) | **ok** (ключ обновлён) |
| `editorial_plan_slots` | **0** строк |
| `editorial_runs` | 2× `dry_run`, 4× `failed` (ошибки до пополнения ключа) |
| Публикации TG после cutoff | **0** |
| `generate_daily_articles` mode | `editorial_v2_plan` → `ru_generated=0` (нет слотов) |

### Chief Editor smoke (28.10, после деплоя)

| Market | ok | status | LLM |
|--------|-----|--------|-----|
| RU | true | `dry_run` | `task=chief_editor`, ~24s |
| EN | true | `dry_run` | `task=chief_editor`, ~19s |

Run IDs: RU `e6b8617e-…`, EN `75fad4f5-…` (тезисы сохранены в `editorial_runs`, слоты **не** созданы из‑за dry_run).

### Scheduler

Cron зарегистрирован: `run_chief_editor` 03:30/09:30/15:30, `generate_articles` 04:00/10:00/16:00.  
Публикационная очередь: `published=0` (ожидаемо без слотов/статей).

---

## Матрица требований — изменения vs R1 audit

| ID | Было (R1) | Сейчас (R2) | Комментарий |
|----|-----------|-------------|-------------|
| PROD-01 | SHA 4e304da | **PASS** `852bc00` | Новая ветка на дроплете |
| AI-01 | NOT_IMPLEMENTED | **PARTIAL** | Код + cron + таблицы; prod только dry_run |
| AI-04b | FAIL (429) | **PASS** | Billing восстановлен |
| GATE-B | FAIL | **FAIL** | AI есть, продуктового календаря нет |
| SCHED-01 | FAIL | **PASS** | Legacy off → `editorial_v2_plan` |
| AUTO-01 | FAIL | **PASS** | Флаги wired в `jobs.py` / cadence |
| AUTO-03 | FAIL | **FAIL** | Autopublish всё ещё true |
| PUB-04 | NOT_IMPLEMENTED | **PARTIAL** | `/admin/editorial` 30d UI, данных нет |
| EDIT-03 | NOT_IMPLEMENTED | **PARTIAL** | 13 pillar codes + formats в `pillars.py`, нет router |
| EDIT-03b | NOT_IMPLEMENTED | **FAIL** | Нет `sendPoll` / native format router |
| NEG-01 | NOT_IMPLEMENTED | **PARTIAL** | Failed runs пишутся; нет «keep last plan» policy test |

Полный CSV: `POST_DEPLOY_REQUIREMENTS_MATRIX_R2.csv`.

---

## P0 — блокеры до GO v2.2

1. **Снять `EDITORIAL_V2_DRY_RUN=false`** (с approval) и прогнать Chief Editor RU+EN → убедиться, что `editorial_plan_slots` > 0 и `/admin/editorial` заполнен.
2. **Выключить `AUTO_PUBLISH_EN/RU=false`** до первого успешного цикла review → test channel → prod (Gate A). Сейчас `wgt doctor` помечает `! auto_publish_off`.
3. **Замкнуть цикл generate → writer → schedule** от слотов (сейчас generate=0 без слотов; legacy min 10/день в .env сбивает с толку — понизить или документировать).
4. **30-дневный dry-run / pilot** по §6 (decision diff, caps, diversity) — не выполнен.
5. **Native formats + voice gate** (§4–5) — в коде модели/enum, не в publisher.

## P1 — после P0

- Horizons 7/2, locked slots, `EditorialPreferenceLog` usage
- SourceRegistry / news monitor (§7–8)
- Writer run trace per publication (§6)
- Forward metrics (§16)
- Почистить 4× failed `editorial_runs` или задокументировать как historical
- `wgt secrets import-env` для plaintext в .env (doctor warning)

## P2 — продукт / owner

- Ручная оценка voice на первых v2 постах
- Pin welcome verification (BRAND-ALL-05)
- Max calendar sync после Telegram RU pilot

---

## Definition of Done §19 (выжимка)

| Критерий | Статус |
|----------|--------|
| Старый mass schedule не параллелит новому | **PASS** (`OLD_ARTICLE=false`) |
| Chief Editor на каждый daily rebuild | **PARTIAL** (cron есть; prod dry_run, не success+slots) |
| Writer + Critic на каждый новый текст | **FAIL** (v1 pipeline, нет v2 slot path end-to-end) |
| 5–6 RU / 4–5 EN в неделю фактически | **FAIL** (0 постов после cutoff) |
| Branding / usernames | **PASS** (prior audit) |

---

## Рекомендуемый следующий шаг (операционный)

1. Owner: **approve** `EDITORIAL_V2_DRY_RUN=false` + `AUTO_PUBLISH_*=false`.
2. Agent/ops: redeploy или `sed` .env + restart worker, `wgt chief-editor --market ru`, `--market en`, проверить слоты, один `generate` + preview в admin.
3. Повторная верификация **R3** с критерием GO только при слотах + test-channel publish.

См. также: `POST_DEPLOY_PRODUCTION_SNAPSHOT.json` (обновлён), `POST_DEPLOY_TEST_RESULTS.md` (секция R2).
