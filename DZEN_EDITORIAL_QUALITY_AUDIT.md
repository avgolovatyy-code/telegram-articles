# Аудит универсального качества Дзена

**Дата:** 18 ноября 2026, Europe/Moscow  
**Ветка:** `cursor/dzen-editorial-quality-01af`  
**Спецификация:** `WEGOTRIP_DZEN_UNIVERSAL_EDITORIAL_QUALITY_CURSOR.md`  
**Вердикт:** `GO_WITH_CONDITIONS`

## 1. Корневые причины — и как исправлена система

Слабые тексты возникали не из «Казани», а из устройства пайплайна:

1. Writer запускался сразу, без исследовательского досье.
2. Критик ставил оценку 1–10, а не `accept|revise|needs_research|hold`.
3. Был один rewrite, без лимита targeted revisions.
4. Гейты ловили казанские слова («согревайтесь каждые полтора часа», Свияжск), а не классы ошибок.
5. Pitch товара обещал web player, когда FAQ и how-it-works расходились.

Исправление — универсальный контур на любой город и жанр:

- жанровый контракт до текста (`app/dzen/genre.py`);
- `ArticleResearchDossier` из каталога + utility-research (`app/dzen/dossier.py`);
- детерминированные проверки хронологии, маршрута, повторов, playback (`chronology`, `itinerary`, `redundancy`, `products`);
- независимый `EditorialDecision` и максимум 2 правки (`MAX_REVISIONS`);
- при `BudgetExceeded` на research — только каталожное досье, hold вместо выдумки.

Казань осталась регрессионным примером: Марджани 1767 не «после указа 1773»; аудио 1,5–2 ч ≠ весь день; канал воспроизведения не утверждается при расхождении FAQ/how-it-works.

## 2. Изменённые компоненты

| Слой | Что |
|---|---|
| Промпты | `dzen_research_v1`, `dzen_writer_v2`, `dzen_critic_v2`; chief editor задаёт `genre` + `reader_promise` |
| Схемы | `ArticleResearchDossier`, `EditorialDecision`, `genre`/`reader_promise` в бриф |
| Пайплайн | research → outline → write → critic → fact-check → revise≤2 → kit или hold |
| Модели | research/outline — utility; write — writer; critic — dzen critic model |
| Каталог | `listen_in_browser` только при однозначном web player; `playback_discrepancy` блокирует категоричный браузер |
| Админка | колонка качества/жанра/причины hold |
| Тесты | 12 сценариев + негативы + 4 sample kit |

Telegram RU/EN, MAX, Slack-расписание, `DAILY_AI_BUDGET_USD` и автопубликация Дзена не менялись.

## 3. 12 сценариев

Таблица сгенерирована тестом (`audit/dzen_quality/scenarios.json`):

| ID | Жанр | Место | Promise | Критические проверки | Gate |
|---|---|---|---|---|---|
| 1 | itinerary | Казань | два дня | хронология Марджани; аудио ≠ день | accept |
| 2 | museum | Барселона | залы без выдуманной кассы | inclusions; locale=ru | accept |
| 3 | culture | Париж | Маре без ложного запрета | нет выдуманного въезда | accept |
| 4 | itinerary | Стамбул | два дня | аудио не заменяет день | accept |
| 5 | culture | Токио | Янака без экзотизации | нет «все местные» | accept |
| 6 | itinerary | Нижний Новгород | оба дня | named places day 1/2 | accept |
| 7 | museum | Лондон | без выдуманных часов | hours omitted | accept |
| 8 | story | Санкт-Петербург | 1703 как дата, не причина | chronology | accept |
| 9 | howto | Париж | оплата только конкретный checkout | нет «любой билет» | accept |
| 10 | news | Лондон | объявлено ≠ действует | статус + дата | accept |
| 11 | comparison | Санкт-Петербург | критерии и trade-off | нет рейтинга из воздуха | accept |
| 12 | story | Казань | легенда Сююмбике | folklore vs document | accept |

Негативы (hard fail, кроме repetition=soft revise): полый второй день; «после 1773» при стройке 1767; аудио как весь день; мечеть как комната для согрева; любой зарубежный билет картой РФ; first-person без заметок; часы без даты проверки; false free + locale=en; три копии одного тезиса.

## 4. Четыре тестовых Publishing Kit

Не для публикации, только evidence жанровых структур:

- [`audit/dzen_quality/samples/city_guide.html`](audit/dzen_quality/samples/city_guide.html) — Стамбул, city guide
- [`audit/dzen_quality/samples/howto.html`](audit/dzen_quality/samples/howto.html) — Париж, how-to оплаты
- [`audit/dzen_quality/samples/itinerary.html`](audit/dzen_quality/samples/itinerary.html) — Нижний Новгород, два дня
- [`audit/dzen_quality/samples/museum.html`](audit/dzen_quality/samples/museum.html) — Лондон, музейный гид

Зачины и каркас различаются: маршрут держит «День первый/второй», how-to — проблему/шаги/ограничения, музей — петлю залов.

## 5. Backlog по данным каталога

- Карточка WeGoTrip 1526: FAQ «только в приложении», how-it-works — браузер. Система больше не выбирает удобную версию. Нужна сверка владельца данных, не редакционная догадка.
- Production description 1526 без маркера «в браузере» → `listen_in_browser=false`, `playback_discrepancy=false` на живом снимке; текст Казани не обещает браузер категорично.

## 6. Health / Slack / бюджет

- Полный `pytest` зелёный локально (offline mock LLM).
- Slack-тесты: вторник одно упоминание, четверг без старых карточек, выходные `weekend`, слабый copy → `empty_queue` без пинга.
- Extra-ping `<@U03AE1ATKDJ>` не отправлялся.
- `DAILY_AI_BUDGET_USD` не повышался. Extra stages идут на utility; при исчерпании бюджета research деградирует в catalog-only.

## 7. Вердикт

**`GO_WITH_CONDITIONS`**

Новые материалы Дзена проходят жанровый контракт и детерминированные hard blockers до handoff. Условия:

1. CI на PR должен быть зелёным.
2. Safe deploy через `deploy/from-agent.sh` без `dzen-digest`.
3. Живую Казань обновить только фактическим AST (Марджани / длительность / playback), без косметики и без внепланового Slack.
4. Live OpenAI-writer по-прежнему зависит от бюджета $3/день: при hold календарь не заполняется выдумкой.

Успех этой работы — качество следующих публикаций, а не бесконечная правка одной казанской статьи.
