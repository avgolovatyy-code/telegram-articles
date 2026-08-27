# WeGoTrip Telegram Content Engine
## Спецификация для разработки в Cursor

**Статус:** ready for implementation  
**Версия:** 1.0  
**Дата:** 27 августа 2026  

---

## 0. Контекст и исходные ссылки

Проект должен автоматически создавать, проверять, оформлять и публиковать поисково-ориентированные travel-статьи в двух независимых Telegram-направлениях WeGoTrip.

### Telegram targets

- **Global / English:** https://t.me/wegotrip
- **Russia / Russian:** https://t.me/wegotrip_ru

Эти ссылки использовать как production targets для публикации. Если технически они являются каналами внутри соответствующих Telegram Communities, бот всё равно публикует непосредственно в канал по `@username`; membership канала в Community не меняет механизм публикации через Bot API.

### WeGoTrip Affiliate API

Документация, которую нужно использовать как основной источник интеграции:

https://gist.github.com/4eRTuk/6b6a4b06b5f6d4ce90973e1931052991

Документация описывает API WeGoTrip, включая страны, города, достопримечательности, языки, валюты, товары, детали товаров, категории/подкатегории, отзывы и построение affiliate links.

### Affiliate identifier

Во всех ссылках на WeGoTrip использовать:

```text
REFERER_ID = 435
```

Маркер:

```text
?coupon=435
```

Пример URL:

```text
https://wegotrip.ru/barcelona-d3128760/?coupon=435
```

Для product URL придерживаться структуры Affiliate API:

```text
EN:
https://wegotrip.com/{city-slug}-d{city-id}/{product-slug}-p{product-id}/?coupon=435

RU:
https://wegotrip.ru/{city-slug}-d{city-id}/{product-slug}-p{product-id}/?coupon=435
```

Разрешено добавлять UTM-параметры после `coupon=435`, но `coupon=435` нельзя терять или заменять.

---

# 1. Цель проекта

Создать автономный **Telegram Content Engine** для WeGoTrip, который:

1. регулярно синхронизирует ассортимент WeGoTrip через Affiliate API;
2. разделяет каталог на EN и RU рынки;
3. строит тематические кластеры статей на основе структуры каталога;
4. использует поисковые интенты и популярные query-patterns отдельно для каждого типа сущности;
5. выбирает наиболее перспективные темы;
6. генерирует качественные статьи через OpenAI API;
7. проверяет факты, которые нельзя брать напрямую из WeGoTrip API;
8. использует только разрешённые медиа;
9. нативно вставляет товары WeGoTrip в статьи;
10. публикует статьи как Telegram Rich Messages;
11. генерирует 10–20 статей в сутки на каждый язык при общем дневном AI-бюджете не выше $3;
12. собирает аналитику по статьям, темам, кликам и расходам;
13. предотвращает дубли, thin content и AI-hallucinations.

Целевая схема:

```text
WeGoTrip Affiliate API
        ↓
Catalog Sync
        ↓
Normalized Catalog
        ↓
Entity + Search Intent Engine
        ↓
Topic Candidates
        ↓
Topic Scoring / Deduplication
        ↓
Product Selection
        ↓
Fact Research
        ↓
OpenAI Article Generation
        ↓
Quality + Factual Validation
        ↓
Telegram Rich Message Renderer
        ↓
Scheduler / Publisher
        ↓
@wegotrip / @wegotrip_ru
        ↓
Analytics + Cost Feedback Loop
```

---

# 2. Главный продуктовый принцип

Это **не SMM-бот** и не генератор случайных travel-постов.

Главная единица системы:

```text
ENTITY × SEARCH INTENT × MARKET
```

Пример:

```text
Paris × things_to_do × EN
Hermitage × what_to_see × RU
Walking Tours × best_in_city × EN
Movie & TV Tours × themed_experience × EN
```

Каждая статья должна существовать потому, что:

- есть реальная сущность или группа сущностей в каталоге WeGoTrip;
- есть понятный пользовательский поисковый интент;
- есть достаточный объём полезного материала;
- статья не дублирует уже опубликованный материал;
- WeGoTrip может нативно предложить релевантные товары.

---

# 3. Разделение EN и RU

EN и RU — два независимых контентных рынка.

Запрещён pipeline:

```text
EN article → translate → RU article
```

или наоборот.

Правильная схема:

```text
EN catalog + EN search intent → EN article → @wegotrip
RU catalog + RU search intent → RU article → @wegotrip_ru
```

## 3.1. Определение рынка товара

Использовать данные API:

- `lang` в list endpoints;
- `locale` в товаре;
- `Accept-Language`;
- язык product content.

Минимальная логика:

```text
locale == "ru" → RU market
locale == "en" → EN market
```

При синхронизации получать ассортимент отдельно:

```text
/products/popular/?lang=en
/products/popular/?lang=ru
```

и аналогично для cities / attractions там, где endpoint поддерживает `lang`.

Не смешивать продукты разных языков внутри одной статьи, если это явно не разрешено отдельным правилом.

---

# 4. Структура каталога WeGoTrip

Нормализованная модель должна поддерживать:

1. **Countries / Страны**
2. **Cities / Города**
3. **Attractions / Достопримечательности**
4. **Categories / Категории**
5. **Collections / Коллекции / подкатегории**
6. **Products / Товары**

В текущей документации Affiliate API категории доступны в product details как `categories`, а подкатегории — как `subcategories`. Для целей проекта:

```text
Collection = normalized subcategory
```

Если позднее появится отдельный endpoint Collections, подключить его через provider без изменения бизнес-логики.

## 4.1. Связи

```text
Country
  └── City
       ├── Attraction
       ├── Category
       │    └── Collection / Subcategory
       └── Product
```

Product может одновременно относиться к:

- стране;
- городу;
- нескольким attractions;
- нескольким categories;
- нескольким collections/subcategories.

Не упрощать модель до `city → products`.

---

# 5. Нормализованные сущности

## 5.1. Country

```json
{
  "id": "...",
  "slug": "...",
  "name": "...",
  "locale": "en|ru",
  "media": [],
  "product_count": 0,
  "city_count": 0
}
```

## 5.2. City

```json
{
  "id": "...",
  "slug": "...",
  "name": "Paris",
  "country_id": "...",
  "locale": "en",
  "popular": true,
  "media": [],
  "product_count": 0,
  "attraction_count": 0
}
```

## 5.3. Attraction

```json
{
  "id": "...",
  "slug": "...",
  "name": "Louvre Museum",
  "city_id": "...",
  "country_id": "...",
  "locale": "en",
  "preview": "...",
  "media": [],
  "product_count": 0
}
```

## 5.4. Category

```json
{
  "id": "...",
  "slug": "walking-tours",
  "title": "Walking Tours",
  "locale": "en"
}
```

## 5.5. Collection

Источник на MVP: `subcategories` из product details.

```json
{
  "id": "...",
  "slug": "movie-tv-tours",
  "title": "Movie & TV Tours",
  "locale": "en"
}
```

## 5.6. Product

Хранить максимум подтверждённых данных из API:

```json
{
  "id": 63,
  "slug": "...",
  "title": "...",
  "locale": "en",
  "description": "...",
  "short_description": "...",
  "highlights": [],
  "cover": "...",
  "preview": "...",
  "images": [],
  "price": null,
  "currency_code": null,
  "rating": null,
  "reviews_count": null,
  "duration_min": null,
  "duration_max": null,
  "distance": null,
  "available": true,
  "published": true,
  "types": {},
  "inclusions": [],
  "exclusions": [],
  "important_info": [],
  "country": {},
  "city": {},
  "attractions": [],
  "categories": [],
  "collections": [],
  "reviews": [],
  "media": [],
  "audio_preview_url": null,
  "updated_at": "..."
}
```

Если поля нет в API — хранить `null`, а не придумывать значение.

---

# 6. WeGoTrip API Adapter

Нельзя размазывать raw API schema по business logic.

Создать интерфейс:

```text
WeGoTripCatalogProvider
```

Пример методов:

```text
getLanguages()
getCurrencies()
getCountries(locale)
getCities(locale, filters)
getAttractions(locale, filters)
getProducts(locale, filters)
getProduct(productId, locale, currency)
getProductReviews(productId)
search(query, locale)
```

Добавить отдельный слой:

```text
AffiliateLinkBuilder
```

Он обязан централизованно добавлять:

```text
coupon=435
```

Нельзя формировать affiliate URL непосредственно внутри prompt или LLM output.

---

# 7. Search Intent Engine

Для каждого типа каталожной сущности использовать свой кластер поисковых интентов.

Система должна иметь `KeywordClusterRegistry` с seed patterns и `SearchDemandProvider` для подтверждения/уточнения формулировок.

## Важно

Не утверждать, что query является «популярным», если нет реального demand signal.

Каждый query candidate хранит:

```json
{
  "query": "things to do in Paris",
  "market": "en",
  "entity_type": "city",
  "entity_id": "...",
  "intent": "things_to_do",
  "demand_score": null,
  "demand_source": "heuristic|seo_provider|search_data",
  "confidence": 0.0
}
```

Если подключён keyword/SEO provider — использовать объём/тренд.
Если нет — использовать seed cluster + semantic relevance + catalog popularity и маркировать `demand_source=heuristic`.

Архитектура должна позволять позднее подключить DataForSEO / другой keyword provider / внутренние SEO-данные WeGoTrip без переписывания core logic.

---

# 8. Кластеры запросов по типам сущностей

Ниже — обязательная seed-библиотека. Это не список статей, а intent patterns.

## 8.1. Country articles

### EN

```text
things to do in {country}
best places to visit in {country}
{country} travel guide
{country} itinerary
best cities to visit in {country}
best attractions in {country}
what to see in {country}
{country} with kids
best museums in {country}
{country} first time guide
```

### RU

```text
что посмотреть в {country}
куда поехать в {country}
лучшие города {country}
достопримечательности {country}
путеводитель по {country}
маршрут по {country}
что посмотреть в {country} самостоятельно
{country} с детьми
лучшие музеи {country}
что нужно знать перед поездкой в {country}
```

Country article генерировать только если каталог достаточно глубокий, чтобы статья не была пустой.

---

## 8.2. City articles

### EN

```text
things to do in {city}
best things to do in {city}
what to see in {city}
{city} itinerary
{city} in one day
{city} in 2 days
{city} in 3 days
best attractions in {city}
best museums in {city}
{city} with kids
things to do in {city} when it rains
things to do in {city} at night
{city} first time guide
self guided tour {city}
walking tour {city}
```

### RU

```text
что посмотреть в {city}
куда сходить в {city}
достопримечательности {city}
{city} за 1 день
{city} за 2 дня
{city} за 3 дня
маршрут по {city}
лучшие музеи {city}
{city} с детьми
куда сходить в {city} в дождь
что посмотреть в {city} самостоятельно
пешеходный маршрут по {city}
аудиогид по {city}
экскурсии по {city} самостоятельно
```

---

## 8.3. Attraction articles

### EN

```text
{attraction} guide
what to see at {attraction}
{attraction} highlights
{attraction} tickets
{attraction} audio guide
how to visit {attraction}
how long to spend at {attraction}
best time to visit {attraction}
things to do near {attraction}
{attraction} with kids
{attraction} self guided tour
{attraction} ticket and audio guide
```

### RU

```text
что посмотреть в {attraction}
путеводитель по {attraction}
билеты в {attraction}
аудиогид по {attraction}
как посетить {attraction}
сколько времени нужно на {attraction}
что посмотреть рядом с {attraction}
{attraction} с детьми
маршрут по {attraction}
билет и аудиогид {attraction}
главные экспонаты {attraction}
```

**Важно:** запросы типа opening hours / цена / расписание допустимы только при обязательной свежей верификации.

---

## 8.4. Category articles

Пример категорий: Walking Tours, Theme Tours, Sightseeing Tours, Family Friendly Tours, Art & Museums.

### EN

```text
best {category} in {city}
{category} {city}
self guided {category} {city}
best {category} in {country}
{category} for first time visitors in {city}
{category} with kids in {city}
```

### RU

```text
лучшие {category} в {city}
{category} в {city}
самостоятельные {category} в {city}
{category} для первого визита в {city}
{category} с детьми в {city}
```

Формулировку адаптировать к естественному языку. Нельзя механически подставлять русское название категории в плохую грамматику.

---

## 8.5. Collection / Subcategory articles

Подкатегории отражают более узкую тему и должны давать более long-tail статьи.

Примеры:

```text
Movie & TV Tours
City Tours
Walking Tours
```

### EN examples

```text
best movie and tv tours in {city}
film locations in {city}
{theme} tour {city}
best city tours in {city}
self guided walking routes in {city}
```

### RU examples

```text
места из фильмов в {city}
тематические маршруты по {city}
лучшие городские маршруты {city}
пешеходные маршруты по {city}
{theme} экскурсия {city}
```

Collection semantics должны анализироваться LLM или classifier-моделью до query expansion.

---

## 8.6. Product-led articles

Product не должен автоматически получать отдельную рекламную статью.

Статья возможна, если product соответствует существующему поисковому intent.

### EN

```text
{attraction} audio guide
{attraction} self guided tour
{attraction} ticket with audio guide
{theme} walking tour in {city}
self guided {theme} tour {city}
```

### RU

```text
аудиогид {attraction}
самостоятельная экскурсия {attraction}
билет с аудиогидом {attraction}
{theme} маршрут по {city}
самостоятельная {theme} экскурсия {city}
```

Product-led content обязан оставаться полезной статьёй, а не product description, растянутым до 5 000 знаков.

---

# 9. Topic Discovery

Каждый день система генерирует topic candidates на основании:

- новых/обновлённых продуктов;
- популярных городов и attractions;
- глубины ассортимента;
- categories / collections;
- historical article performance;
- поискового demand signal;
- freshness;
- отсутствия похожей статьи.

Пример:

```json
{
  "market": "en",
  "entity_type": "city",
  "entity_id": 3,
  "entity_name": "Paris",
  "intent": "things_to_do",
  "primary_query": "things to do in Paris",
  "secondary_queries": [
    "best things to do in Paris",
    "what to see in Paris"
  ],
  "relevant_product_ids": [25, 44, 71],
  "inventory_depth": 27,
  "topic_score": 0.91,
  "status": "candidate"
}
```

---

# 10. Topic Score

Рекомендованный score:

```text
30% search demand / intent confidence
25% inventory depth
15% entity popularity
10% product quality
10% commercial relevance
5% freshness
5% content diversity
- duplication penalty
- thin-content penalty
```

Все веса configurable.

Если search demand provider отсутствует, его долю перераспределить на inventory/popularity, но сохранить `confidence` ниже.

---

# 11. Deduplication и cannibalization

Нельзя создавать:

```text
Things to do in Paris
Best things to do in Paris
What are the best things to do in Paris
Top things to do in Paris
```

как четыре почти одинаковых материала.

Использовать:

1. normalized entity;
2. normalized intent;
3. canonical query;
4. embedding similarity;
5. существующие drafts;
6. scheduled articles;
7. published articles.

Если semantic similarity выше threshold, candidate:

- отклоняется;
- или переводится в другой intent;
- или становится update существующей статьи.

---

# 12. OpenAI integration

Использовать **OpenAI API**, не UI-автоматизацию ChatGPT.

Рекомендуемый endpoint:

```text
Responses API
```

## 12.1. Модели

### Основной writer

```text
gpt-5.6-terra
```

Использовать как основной генератор финального текста: хороший баланс качества и стоимости.

### Дешёвые supporting tasks

```text
gpt-5.6-luna
```

Использовать для:

- topic expansion;
- classification;
- deduplication assistance;
- metadata extraction;
- initial quality checks;
- claim extraction;
- lightweight rewrites.

### Escalation

```text
gpt-5.6-sol
```

Не использовать массово.
Разрешить только как fallback для статьи, которая дважды не прошла quality threshold, и только если дневной budget позволяет.

---

# 13. AI Budget Manager

Жёсткое требование:

```text
TOTAL_DAILY_AI_BUDGET_USD = 3.00
```

В этот бюджет включать:

- LLM generation;
- LLM review;
- web-search tool calls;
- image generation, если она включена;
- любые OpenAI tool charges.

Система должна считать фактическую стоимость по usage из API, а не только прогноз.

Настройки:

```text
RU_ARTICLES_MIN_PER_DAY=10
RU_ARTICLES_MAX_PER_DAY=20
EN_ARTICLES_MIN_PER_DAY=10
EN_ARTICLES_MAX_PER_DAY=20
DAILY_AI_BUDGET_USD=3.00
```

Алгоритм:

1. сначала обеспечить до 10 EN + 10 RU, если бюджет позволяет;
2. затем наращивать до 20 + 20;
3. использовать rolling average cost/article;
4. до каждого generation job оценивать `projected_daily_cost`;
5. если projected cost > remaining budget — не запускать job;
6. никогда не превышать hard budget автоматически;
7. публикация уже готовых статей не блокируется исчерпанием AI-бюджета.

Сделать dashboard:

```text
Today budget: $3.00
Spent: $1.87
Remaining: $1.13
EN generated: 14
RU generated: 13
Average article AI cost: $0.069
```

---

# 14. Article generation pipeline

Не давать LLM один prompt вида «напиши статью про Париж».

Pipeline:

```text
Topic Candidate
↓
Catalog Context Builder
↓
Relevant Product Ranking
↓
Search Intent Context
↓
Fact Research Plan
↓
Fact Verification
↓
Article Outline
↓
Final Article Generation
↓
Claim Audit
↓
Style Audit
↓
Rich Message Render
```

---

# 15. Context для writer-модели

Передавать structured JSON:

```json
{
  "market": "en",
  "primary_query": "things to do in Paris",
  "secondary_queries": [],
  "entity": {},
  "catalog_context": {},
  "verified_external_facts": [],
  "products": [],
  "media": [],
  "brand_style": {},
  "forbidden_claims": [],
  "article_constraints": {}
}
```

LLM не должна сама искать продукты по памяти.

---

# 16. Factual Verification — критическое требование

Любая информация должна относиться к одной из категорий:

```text
A. Trusted API Fact
B. Verified External Fact
C. General narrative / opinion
```

## 16.1. Trusted API Fact

Можно использовать без дополнительного web search, если значение пришло из актуального Affiliate API:

- название товара;
- описание;
- highlights;
- duration;
- distance;
- price;
- currency;
- rating;
- review count;
- inclusions;
- exclusions;
- category;
- collection;
- city;
- attraction;
- product media;
- availability flag;
- address/start point, если API их возвращает.

Перед публикацией dynamic product facts желательно перечитать из API.

## 16.2. Verified External Fact

Обязательная верификация для:

- opening hours;
- ticket office hours;
- актуальных цен самого музея/объекта;
- дат закрытия;
- ремонтных работ;
- входных правил;
- временных ограничений;
- current exhibitions;
- transport disruptions;
- сезонных правил;
- актуального расписания;
- любых других time-sensitive данных.

Использовать web search через OpenAI Responses API либо подключаемый `FactResearchProvider`.

Приоритет источников:

1. официальный сайт attraction/museum;
2. официальный tourism/government source;
3. официальный transport/operator source;
4. другие авторитетные первичные источники;
5. только затем качественные вторичные источники.

Нельзя подтверждать time-sensitive факт только LLM knowledge.

## 16.3. Если факт не подтверждён

```text
OMIT, DON'T GUESS
```

Не писать «скорее всего», не выдумывать и не дополнять логически.

---

# 17. Claim ledger

Для каждой статьи сохранять:

```json
{
  "claim": "The museum is open until 21:00 on Fridays",
  "type": "verified_external",
  "source_url": "...",
  "source_title": "...",
  "verified_at": "...",
  "confidence": 0.98
}
```

Для API facts:

```json
{
  "claim": "The tour lasts 90 minutes",
  "type": "wegotrip_api",
  "product_id": 25,
  "api_snapshot_id": "..."
}
```

Это нужно для дебага hallucinations.

---

# 18. Freshness policy

По умолчанию writer должен избегать лишних volatile facts.

Если они нужны:

```text
opening hours / closures / current rules → verify at generation time
product price / availability → refresh before publication
evergreen historical fact → source once and retain provenance
```

При scheduled publication старше 24 часов:

- перечитать product data;
- перепроверить все volatile facts либо удалить их.

---

# 19. Стиль WeGoTrip articles

Референсы по ощущению:

- Aviasales;
- Т—Ж / Tinkoff Journal.

Не копировать конкретные формулировки и не имитировать конкретного автора.

## Voice

- дружелюбно;
- просто;
- умно без снобизма;
- содержательно;
- немного живо;
- допускается лёгкий юмор;
- без рекламного пафоса;
- без AI-канцелярита.

## Humor rules

Допустим:

- наблюдение;
- самоироничная бытовая шутка;
- лёгкий travel humor;
- доброжелательная метафора.

Запрещено:

- унижение людей/народов/городов;
- панибратство;
- сарказм над пользователем;
- шутки на основе пола, расы, национальности, религии и других чувствительных признаков;
- грубость;
- мемы, которые быстро устареют и ломают evergreen value.

---

# 20. Запрещённый AI-style

Не использовать шаблоны:

```text
погрузитесь в удивительный мир
незабываемое путешествие
отправьтесь в захватывающее приключение
жемчужина, которая никого не оставит равнодушным
whether you're a seasoned traveler or...
from iconic landmarks to hidden gems...
```

если они не оправданы конкретным контекстом.

Не начинать каждый section одинаково.
Не перегружать текст прилагательными.

---

# 21. Структура хорошей статьи

Не делать единый жёсткий template, но использовать общие правила.

Типичная статья:

1. **Search-oriented title**
2. Короткий полезный intro
3. Основной ответ на query
4. 3–8 содержательных sections
5. Нативные product recommendations в релевантных местах
6. Практические советы
7. Optional FAQ, только если действительно полезен
8. Короткий closing / next step
9. 0–4 полезных hashtags

Целевая длина:

```text
4 000–10 000 символов
```

Допустимо:

```text
2 500–20 000
```

Не раздувать текст ради длины.

Telegram hard limit должен валидироваться по актуальному Bot API.

---

# 22. Search / Telegram indexing optimization

Telegram имеет Public Post Search по содержимому публичных каналов, поэтому article renderer должен делать текст максимально понятным и индексируемым.

## Rules

- primary query близко к title;
- entity name в title;
- ключевая сущность естественно присутствует в первых 300–500 символах;
- H2/H3 отражают реальные sub-intents;
- не прятать важную информацию только на изображении;
- использовать полные названия attractions;
- использовать natural synonyms;
- не keyword-stuffing;
- не повторять city name в каждом абзаце;
- абзацы короткие;
- списки там, где они действительно облегчают чтение;
- одна смысловая мысль на paragraph;
- таблицы использовать только для сравнения/структурированных данных;
- FAQ только когда он отвечает на отдельные query intents.

## Hashtags

Не считать hashtags SEO-фактором по умолчанию.
Использовать только как навигацию/дополнительный discovery signal.

Обычно:

```text
0–4 hashtags/article
```

Пример EN:

```text
#Paris #Louvre #ParisTravel
```

RU:

```text
#Париж #Лувр #Путешествия
```

Не делать hashtag wall.

---

# 23. Rich Text / Telegram rendering

Публиковать через официальный Telegram Bot API `sendRichMessage`.

Не использовать userbot.

Rich Message Builder должен поддерживать:

- headings;
- paragraphs;
- lists;
- quotes;
- dividers;
- tables;
- photo blocks;
- collage/slideshow, если уместно;
- audio blocks;
- voice-note blocks, если источник валиден;
- buttons;
- details/expandable blocks, если они улучшают UX.

Бот должен быть admin соответствующего канала и иметь права публикации/media.

---

# 24. Нативные product cards

Товары нельзя упоминать только как голый URL.

Создать `TelegramProductCardRenderer`.

## Hero card

Для основного товара:

```text
[Product image]

🎧 Product title
1–2 коротких предложения: зачем это пользователю.

⭐ rating · duration · from price

[Open tour / Get ticket & audio tour]
```

Показывать rating/duration/price только если API их возвращает.

## Compact card

Для 2–5 рекомендаций:

```text
Product title
Short benefit
From €XX
[View on WeGoTrip]
```

## Collection block

Для обзорных статей:

```text
Explore Paris with WeGoTrip
• Product A
• Product B
• Product C
[See tours]
```

Количество товаров обычно:

```text
1–5/article
```

Не превращать article в витрину.

---

# 25. Product selection

Товары выбираются кодом ДО writer prompt.

```text
article topic
↓
matching products
↓
product ranking
↓
selected products
↓
LLM receives only selected products
```

Recommended rank:

```text
45% semantic relevance
20% popularity
15% rating/reviews quality
10% availability
10% diversity/commercial fit
```

Если данных нет — перераспределить веса.

Никогда не выбирать нерелевантный товар только ради продажи.

---

# 26. Affiliate links

Единый builder:

```text
AffiliateLinkBuilder
```

Обязательная маркировка:

```text
coupon=435
```

Дополнительный tracking:

```text
utm_source=telegram
utm_medium=content
utm_campaign=wegotrip_en | wegotrip_ru
utm_content={article_id}
utm_term={topic_slug}
```

Пример logic:

```text
?coupon=435&utm_source=telegram&utm_medium=content&...
```

Не допускать duplicate `?` или потери query params.

---

# 27. Медиа

Главное правило:

> Все обычные media внутри статьи должны приходить из WeGoTrip API.

Приоритет:

1. city/attraction cover из API;
2. product cover/preview;
3. product images;
4. attraction preview;
5. другое media, явно возвращаемое API.

Нельзя автоматически брать случайные изображения из Google Images, Unsplash, Wikimedia и т. п.

---

# 28. Generated covers — исключение

Требования «использовать только API media» и «при необходимости генерировать cover» разрешить так:

```text
ALLOW_GENERATED_COVERS=false
```

по умолчанию.

Если флаг включён, generated image разрешён ТОЛЬКО:

- как hero cover;
- если API не даёт подходящего cover;
- если budget manager разрешает;
- без добавления в изображение ложных объектов/фактов;
- без имитации фотографии конкретного музея/экспоната, если генерация может ввести пользователя в заблуждение.

Inline illustrations и product imagery всё равно должны идти из API.

Image generation входит в лимит $3/day.

Если budget не позволяет — статья публикуется без generated cover.

---

# 29. Audio previews

Telegram Rich Messages поддерживают audio block.

Если Affiliate API реально возвращает доступный аудиофайл/preview для товара:

- можно вставлять preview аудиогида прямо в статью;
- использовать только продуктовый audio preview;
- не генерировать аудио из текста статьи;
- обязательно связывать audio с соответствующим product ID.

## Важное ограничение текущей документации

В предоставленном gist видны признаки аудиогида и metadata (`types.audioguide`, `tour.mediaSize`, `eventsCount`), но прямой `audio_preview_url` не документирован.

Поэтому:

```text
if audio_preview_url exists → render InputRichBlockAudio
else → omit audio block
```

Не пытаться угадывать URL или извлекать закрытые media paths.

Создать интерфейс:

```text
AudioPreviewProvider
```

на будущее.

---

# 30. Media validation

Перед публикацией:

- URL доступен;
- media type поддерживается Telegram;
- content-length допустим;
- нет broken file;
- изображение не duplicate;
- media принадлежит нужной entity/product;
- не публиковать пустые media blocks.

---

# 31. Article JSON — source of truth

LLM не должна возвращать Telegram payload напрямую.

Внутренний формат:

```json
{
  "article_id": "...",
  "market": "en",
  "entity_type": "city",
  "entity_id": "3",
  "primary_query": "things to do in Paris",
  "title": "Things to Do in Paris: ...",
  "intro": "...",
  "sections": [
    {
      "heading": "...",
      "blocks": []
    }
  ],
  "product_placements": [],
  "media_placements": [],
  "audio_placements": [],
  "faq": [],
  "hashtags": [],
  "claims": [],
  "sources": []
}
```

Затем отдельный renderer строит Telegram `InputRichMessage`.

---

# 32. Quality Gate

До публикации статья проходит несколько проверок.

## Technical

- valid JSON;
- valid Rich Message;
- лимиты Telegram;
- URLs valid;
- affiliate marker present;
- media valid;
- correct channel;
- correct locale.

## Content

- отвечает primary query;
- нет воды;
- нет repeated paragraphs;
- нет шаблонного AI intro;
- нет invented products;
- нет unsupported claims;
- нет избыточной рекламы;
- читаемая структура;
- корректный русский/английский.

## Factual

- все volatile claims имеют source;
- product facts совпадают с API snapshot;
- price и availability refreshed перед публикацией.

## Search

- title соответствует intent;
- entity явно указана;
- headings meaningful;
- secondary queries покрыты естественно;
- нет keyword stuffing.

---

# 33. LLM Review

Использовать отдельный critic pass.

Для экономии — сначала Luna.

Выход:

```json
{
  "usefulness": 0.92,
  "factuality": 0.98,
  "readability": 0.91,
  "search_intent_match": 0.95,
  "natural_language": 0.93,
  "product_relevance": 0.90,
  "spam_risk": 0.03,
  "issues": []
}
```

Минимум:

```text
MIN_QUALITY_SCORE=0.88
MIN_FACTUALITY_SCORE=0.97
```

Если factuality ниже threshold — не публиковать.

---

# 34. Publication modes

Поддержать:

```text
REVIEW_MODE
AUTO_PUBLISH_MODE
```

На старте default:

```text
AUTO_PUBLISH_EN=false
AUTO_PUBLISH_RU=false
```

После проверки качества можно включить auto publish отдельно для каждого рынка.

Даже в auto-mode article должна пройти все automatic gates.

---

# 35. Scheduler

Каждый день генерировать:

```text
10–20 EN articles
10–20 RU articles
```

Но не публиковать 20 сообщений подряд.

Scheduler должен равномерно распределять публикации по суткам.

Настройки:

```text
EN_PUBLISH_PER_DAY=10..20
RU_PUBLISH_PER_DAY=10..20
MIN_POST_INTERVAL_MINUTES=<configurable>
```

Статьи могут быть сгенерированы batch-ом, но published с spacing.

---

# 36. Inventory Sync

Cron минимум раз в сутки:

```text
sync_wegotrip_catalog
```

Перед публикацией article:

```text
refresh_article_products
```

Сохранять:

- created_at;
- updated_at;
- last_seen_at;
- API snapshot;
- available/published status.

Если product исчез/недоступен:

- убрать product block;
- либо заменить релевантным;
- перепроверить связанный paragraph.

---

# 37. Data model

Минимальные таблицы:

```text
markets
countries
cities
attractions
categories
collections
products
product_categories
product_collections
product_attractions
product_media
catalog_snapshots

keyword_clusters
query_candidates
search_demand_snapshots

topic_candidates
articles
article_versions
article_claims
article_sources
article_products
article_media

publication_queue
telegram_publications

tracking_links
click_events
conversion_events

llm_runs
cost_ledger
prompt_versions
system_settings
```

Можно использовать JSONB для больших snapshots/article tree.

---

# 38. Article statuses

```text
candidate
researching
generating
draft
validation_failed
needs_review
approved
scheduled
publishing
published
failed
archived
```

---

# 39. Admin UI

Нужен минимальный web-admin.

## Dashboard

Показывать:

- catalog size EN/RU;
- new products;
- topic candidates;
- drafts;
- scheduled;
- published today;
- daily AI spend;
- avg cost/article;
- validation failures.

## Topics

Поля:

```text
market
entity
intent
primary query
search confidence
inventory depth
score
status
```

Actions:

```text
generate
ignore
boost
exclude
```

## Article

Показывать:

- article preview;
- source entity;
- search intent;
- products;
- media;
- verified facts + sources;
- quality scores;
- estimated/factual cost;
- Telegram preview.

Actions:

```text
regenerate
edit
verify again
approve
publish test
schedule
publish now
reject
```

---

# 40. Test channel

Обязательная настройка:

```text
TELEGRAM_TEST_CHANNEL=
```

Перед production должен быть action:

```text
Publish to Test
```

Production publication нельзя использовать как preview mechanism.

---

# 41. Telegram publisher

После публикации сохранять:

```text
chat_id
channel_username
message_id
published_at
telegram_response
article_version
```

Поддержать edit existing Rich Message для:

- typo;
- broken affiliate link;
- factual correction;
- removed product.

Не переписывать evergreen article каждый день без причины.

---

# 42. Analytics

Минимальная attribution цепочка:

```text
article
→ product card/button
→ WeGoTrip
→ session
→ order
```

Каждая ссылка уникальна по `article_id`.

KPI:

```text
articles generated
articles published
clicks
unique clicks
CTR if impressions available
product opens
orders
GMV
revenue
conversion rate
revenue/article
revenue/topic
revenue/entity
AI cost/article
AI cost/order
```

---

# 43. Performance feedback loop

Позднее Topic Score должен учитывать:

```text
historical CTR
orders
GMV
conversion
article age
query/entity family
```

Пример:

```text
Louvre articles convert well
→ increase Louvre-related topic priority
```

Но не создавать десятки семантически одинаковых материалов.

---

# 44. Prompt architecture

Все prompts versioned.

Минимум:

```text
topic_discovery_en_v1
topic_discovery_ru_v1
article_writer_en_v1
article_writer_ru_v1
claim_extractor_v1
fact_research_v1
quality_review_en_v1
quality_review_ru_v1
```

Сохранять для каждого run:

```text
model
prompt_version
input_tokens
output_tokens
tool_calls
cost_usd
created_at
```

---

# 45. System prompt — writer principles

Writer обязан:

1. писать для путешественника, а не для SEO-бота;
2. сразу отвечать на intent;
3. не придумывать факты;
4. использовать только предоставленные product facts;
5. не создавать fake quotations/reviews;
6. не менять цены/ratings;
7. не обещать skip-the-line, если API этого не говорит;
8. не писать opening hours без verified fact context;
9. интегрировать WeGoTrip нативно;
10. не вставлять affiliate URLs самостоятельно;
11. возвращать structured article JSON.

---

# 46. Security

Secrets только в environment / secret store:

```text
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
WEGOTRIP_API_KEY=
```

Никогда не commit secrets.

Affiliate identifier не secret:

```text
WEGOTRIP_REFERER_ID=435
```

---

# 47. Config

Минимум:

```text
WEGOTRIP_API_BASE_URL=https://app.wegotrip.com/api/v3
WEGOTRIP_REFERER_ID=435

TELEGRAM_EN_CHANNEL=@wegotrip
TELEGRAM_RU_CHANNEL=@wegotrip_ru
TELEGRAM_TEST_CHANNEL=
TELEGRAM_BOT_TOKEN=

OPENAI_API_KEY=
OPENAI_WRITER_MODEL=gpt-5.6-terra
OPENAI_UTILITY_MODEL=gpt-5.6-luna
OPENAI_FALLBACK_MODEL=gpt-5.6-sol

DAILY_AI_BUDGET_USD=3.00
EN_ARTICLES_MIN_PER_DAY=10
EN_ARTICLES_MAX_PER_DAY=20
RU_ARTICLES_MIN_PER_DAY=10
RU_ARTICLES_MAX_PER_DAY=20

AUTO_PUBLISH_EN=false
AUTO_PUBLISH_RU=false
ALLOW_GENERATED_COVERS=false

MIN_QUALITY_SCORE=0.88
MIN_FACTUALITY_SCORE=0.97
```

Base URL фактически проверить по текущему API; документация упоминает v2 и v3.

---

# 48. Cost optimizations

Для удержания $3/day:

1. кешировать catalog context;
2. не передавать writer полный product JSON;
3. передавать только релевантные поля;
4. Luna для bulk classification;
5. Terra только для final article;
6. web-search только для claims, реально требующих verification;
7. избегать volatile facts, если они не нужны intent;
8. кешировать verified evergreen facts;
9. batch topic scoring;
10. считать фактические token usage;
11. generated images выключены по умолчанию;
12. Sol использовать только fallback.

---

# 49. Error handling

Обработать:

- WeGoTrip API timeout;
- pagination failure;
- product schema change;
- Telegram 429;
- Rich Message validation error;
- broken media;
- OpenAI timeout;
- tool call failure;
- malformed structured output;
- budget exceeded;
- duplicate post;
- stale product;
- failed fact verification.

Все jobs idempotent.

Не повторять публикацию, если неизвестно, ушёл ли предыдущий request.

---

# 50. Logging / observability

Structured logs:

```text
job_id
article_id
topic_id
market
entity_type
entity_id
operation
model
cost_usd
duration_ms
status
error
```

Отдельный `cost_ledger` обязателен.

---

# 51. Tests

Unit:

- API normalization;
- locale segmentation;
- entity graph;
- category/subcategory mapping;
- affiliate URL builder;
- `coupon=435` preservation;
- topic canonicalization;
- deduplication;
- product ranking;
- budget manager;
- fact claim classification;
- Rich Message builder;
- media validation;
- Telegram channel routing.

Integration:

```text
Affiliate API → Catalog → Topic
Topic → Products → Article JSON
Article → Fact validation
Article JSON → Telegram RichMessage payload
```

CI никогда не публикует в production Telegram channels.

---

# 52. MVP scope

MVP обязан иметь end-to-end flow:

```text
1. Sync EN/RU catalog
2. Build entity graph
3. Generate query/topic candidates
4. Deduplicate
5. Pick products
6. Verify required facts
7. Generate article with OpenAI
8. Validate
9. Render Telegram Rich Message
10. Preview in admin
11. Publish to test
12. Schedule/publish to EN or RU
13. Store publication ID
14. Track affiliate click URLs
15. Track AI spend
```

---

# 53. Не делать в MVP

- отдельный канал на каждый город;
- userbot;
- массовый scraping Telegram;
- перевод EN → RU как основной workflow;
- случайные stock images;
- генерацию product facts;
- 20 generated covers/day;
- собственный полноценный SEO SaaS;
- сложное ML ranking;
- automatic checkout;
- Telegram Mini App без отдельной необходимости.

---

# 54. Первый EN acceptance scenario

```text
1. Sync Paris EN catalog.
2. Найти Paris / Louvre products.
3. Создать candidate "things to do in Paris" или Louvre-specific intent.
4. Выбрать 2–4 релевантных продукта.
5. Получить API media.
6. Определить claims, требующие web verification.
7. Проверить их или исключить.
8. GPT-5.6 Terra генерирует structured EN article.
9. Luna critic проверяет article.
10. Product cards получают URL с coupon=435.
11. Rich Message renderer строит Telegram payload.
12. Publish to test.
13. После approval publish to @wegotrip.
14. Сохранить message_id и cost.
15. Повтор job не создаёт duplicate.
```

---

# 55. Первый RU acceptance scenario

```text
1. Sync RU catalog.
2. Выбрать российский город/attraction с достаточным ассортиментом.
3. Создать естественный русский query cluster.
4. Выбрать только RU products.
5. Проверить mutable facts.
6. GPT-5.6 Terra пишет оригинальную RU article, не перевод EN.
7. Product URLs используют wegotrip.ru + coupon=435.
8. Rich Message публикуется в test.
9. После approval publish to @wegotrip_ru.
10. Все источники/claims/cost сохраняются.
```

---

# 56. Definition of Done

Система считается готовой к первому production запуску, если:

- EN/RU каталоги разделяются корректно;
- countries, cities, attractions, categories, collections и products участвуют в topic discovery;
- на каждый entity type работает свой intent cluster;
- articles не дублируются;
- writer использует GPT-5.6 Terra;
- utility tasks используют дешёвую модель;
- dynamic facts проходят verification;
- unsupported facts удаляются;
- media берётся из WeGoTrip API;
- generated covers отключены по умолчанию и являются controlled exception;
- audio используется только при реальном API audio URL;
- products встроены нативными rich blocks;
- все ссылки содержат `coupon=435`;
- публикация идёт Rich Message в правильный канал;
- бюджет никогда автоматически не превышает $3/day;
- система может генерировать от 10 до 20 статей на каждый market, если стоимость позволяет;
- публикации равномерно распределяются;
- есть test channel;
- есть admin preview;
- есть cost ledger;
- есть article/source/claim traceability.

---

# 57. Порядок разработки в Cursor

Cursor должен сначала изучить текущий repository и не переписывать существующий stack без причины.

Если repository пустой — выбрать простой production-ready stack, подходящий для API integration, cron/background jobs, PostgreSQL и admin UI.

## Шаг 1 — Planning

Создать:

```text
IMPLEMENTATION_PLAN.md
```

В нём описать:

- текущий stack;
- архитектуру;
- модули;
- DB schema;
- background jobs;
- Telegram integration;
- OpenAI integration;
- неизвестные поля Affiliate API;
- порядок реализации.

Не останавливать работу из-за minor неизвестных.

## Шаг 2 — Catalog

Реализовать:

```text
WeGoTrip API adapter
DB schema
EN/RU segmentation
Catalog sync
Entity graph
AffiliateLinkBuilder
```

## Шаг 3 — Topics

```text
KeywordClusterRegistry
SearchDemandProvider interface
Topic discovery
Topic scoring
Deduplication
```

## Шаг 4 — AI

```text
OpenAI provider
Budget manager
Fact claim extraction
Fact research
Article writer
Critic
```

## Шаг 5 — Telegram

```text
Rich Message renderer
Product cards
Media blocks
Audio blocks
Buttons
Test publishing
Production publishing
```

## Шаг 6 — Admin + Scheduler

```text
Dashboard
Article preview
Approval
Scheduler
Daily generation quotas
```

## Шаг 7 — Analytics

```text
Tracking URLs
Clicks
Conversions interface
Cost analytics
Performance feedback
```

После каждого шага:

- tests;
- README update;
- migrations;
- no critical TODO-only implementation.

---

# 58. Важная инструкция Cursor

Не пытайся улучшить требования за счёт скрытого упрощения.

Особенно нельзя потерять:

1. два независимых языка/рынка;
2. все уровни каталога;
3. entity-specific query clusters;
4. `coupon=435`;
5. Rich Messages, а не обычный plain text;
6. native product cards;
7. factual verification;
8. API-only media by default;
9. audio support when API provides playable preview;
10. $3/day hard cap;
11. 10–20 articles/day per market as dynamic target;
12. no hallucinated facts;
13. no thin/duplicate AI content.

Если конкретный API field или Telegram capability отличается от спецификации, сначала проверить актуальную официальную документацию и реализовать ближайший корректный вариант, сохраняя продуктовый смысл требования.

---

# 59. Reference documentation

### WeGoTrip Affiliate API

https://gist.github.com/4eRTuk/6b6a4b06b5f6d4ce90973e1931052991

### Telegram Bot API

https://core.telegram.org/bots/api

Использовать актуальную версию Bot API с `sendRichMessage` и rich blocks.

### Telegram Rich Text / Communities announcement

https://telegram.org/blog/communities-editor-invisible-messages

### Telegram Public Post Search

https://telegram.org/blog/post-search-story-albums-and-more

### OpenAI Models

https://developers.openai.com/api/docs/models

### OpenAI Responses API

https://developers.openai.com/api/reference/resources/responses

---

# 60. Краткое целевое состояние

```text
Catalog knows what WeGoTrip sells
        ↓
Search Intent Engine knows what travelers ask
        ↓
Topic Engine finds intersections
        ↓
OpenAI writes useful original articles
        ↓
Verification prevents hallucinations
        ↓
Rich Message makes the article readable in Telegram
        ↓
Native WeGoTrip cards monetize relevant intent
        ↓
Analytics learns what actually works
        ↓
Budget manager keeps the system under $3/day
```

Конечная цель — не просто автоматически публиковать много контента, а построить **программируемый Telegram travel publishing engine**, который масштабируется на весь каталог WeGoTrip и превращает search intent в полезный контент и продажи.
