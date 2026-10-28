# WeGoTrip Editorial Engine — FINAL UNIFIED SPECIFICATION & AUTONOMOUS RELEASE

**Version:** 3.0 · **Date:** 2026-10-28 · **Status:** OWNER-REQUESTED IMPLEMENTATION AND RELEASE

**Audience:** Cursor Agent / Cursor Cloud Agent in the **existing production repository**.
**Working language:** Russian for plans, conversations, reports and documentation. Source code, identifiers and tests may use English.

> **MASTER INSTRUCTION TO CURSOR.** This file is the single source of truth for the *latest* requirements. Audit what exists, fix gaps, implement, run tests, prepare migrations, deploy through the project's existing safe CI/CD mechanism, verify production and report evidence. Do **not** stop after writing a plan or making a PR. Do **not** ask for routine approval at each step. The owner has explicitly authorized implementation **and release** of these requirements. Never claim release succeeded if deployment or verification did not actually succeed. If external credentials, permissions or infrastructure genuinely block a step, execute every unblocked step and report a precise, minimal manual action.

---

## 0. Project identification, priorities and scope

This is **an upgrade of the working WeGoTrip Editorial Engine**, not a greenfield application.

### Current production channels and target audiences

| Channel | Public URL | Platform | Editorial language | Target reader | Primary product domain |
|---|---|---|---|---|---|
| Telegram RU | https://t.me/wegotrip_ru | Telegram | Russian | Russian-speaking locals/travelers; Russia is a key origin market but not exclusive | `https://wegotrip.ru` |
| Telegram EN | https://t.me/wegotrip | Telegram | Natural international English | Global locals/travelers | `https://wegotrip.com` |
| MAX RU | https://max.ru/channel_wegotrip | MAX | Russian | **Residents of Russia**; domestic leisure and practical trips from Russia | `https://wegotrip.ru` |

**Never create replacement channels or change usernames.** MAX `https://max.ru/id[REDACTED]` is a **legacy address/identifier**, not the public link to insert in new posts. MAX `https://max.ru/id[BOT]_bot` is a bot, **not** the promoted channel. Discover and preserve the actual MAX API `chat_id`: do not infer it from the URL.

### External commercial integration

- WeGoTrip Affiliate API documentation: https://gist.github.com/4eRTuk/6b6a4b06b5f6d4ce90973e1931052991
- Affiliate partner identifier: **435**.
- Product / applicable storefront affiliate links must correctly include `coupon=435`, preserving existing parameters. No affiliate coupon in channel-to-channel links, source links, bios or unrelated sites.
- Russian storefront: `wegotrip.ru` displays Russian-language products. Global storefront: `wegotrip.com` supports products in multiple audio-guide languages and excludes Russia-based products under the site's business rules. **Do not confuse UI language with tour audio language** or merge distinct product IDs for different guide languages.

### Source requirements consolidated here

This document supersedes overlapping directions in:

1. `WEGOTRIP_TELEGRAM_EDITORIAL_ENGINE_V2_2_CURSOR.md` (Telegram editorial engine + channel branding).
2. `WEGOTRIP_RU_MARKET_TRAVEL_MEDIA_ADDENDUM_V2_3_CURSOR.md` (Russia demand, media diversity, competitor audit).
3. `WEGOTRIP_RU_CROSS_PLATFORM_CHANNEL_PROMOTION_V2_4_CURSOR.md` (mandatory cross-channel footer).
4. `WEGOTRIP_MAX_EDITORIAL_ADDENDUM_V1_1_CURSOR.md` (MAX channel, Russia-focused editorial policy and API).
5. `WEGOTRIP_EDITORIAL_POST_DEPLOY_AUDIT_CURSOR.md` (evidence-based tests and release gate).
6. `CHANNEL_BRANDING_PROPOSAL.md` (**Telegram branding already approved by owner in earlier conversation**).
7. Legacy `WEGOTRIP_TELEGRAM_CONTENT_ENGINE_CURSOR_SPEC.md` (catalog, affiliate, analytics, factual correctness, product rendering; its former high-volume article mandate **is cancelled**).

**Conflict rules:** latest explicit owner instructions in this file override older specifications. Keep older non-conflicting behavior. Previously requested 'do not change production without owner approval' is superseded *for the implementation, safe deployment and approved branding changes in this file* by the owner's new explicit autonomous-release request. Irreversible/destructive operations and new expenses outside established limits remain **not authorized**.

### Definition of the product

WeGoTrip is now **an engaging travel and local-discovery media brand**, not a stream of long SEO articles, ticket advertisements or travel restrictions. Readers should enjoy it even if they will not travel for months. It serves simultaneously:

- **Locals:** how to spend weekends and holidays; exhibitions, museums, walks, family plans, unfamiliar places in familiar cities.
- **Travelers:** inspiration, destinations, unusual landmarks, short itineraries, culture, practical changes and things to see during a trip.

The offer of a tour or ticket is optional and contextual, not the definition of a successful post.

---

## 1. Non-negotiable product outcomes

A successful deployed system must **prove**:

1. Each of three channels has its own real editorial strategy, local language, format and cadence.
2. **OpenAI API** is the real **Chief Editor** (topic selection and daily replanning), **Writer** (final text), and independent **Critic** (review). No simulated AI decisions or static cron-only selection passed off as AI planning.
3. New information comes from legitimate, up-to-date sources: official museums/cultural institutions, travel/tourism authorities, news providers, event calendars, search trends, plus WeGoTrip Affiliate API. Historical signals are never represented as live facts.
4. Topic selection prioritizes **reader interest and usefulness**, not presence of purchasable WeGoTrip products.
5. Russian editorial planning reflects **actual domestic travel + outbound demand from Russia**, with visas/logistics/payment/availability checked **only when relevant**, and with room for surprising stories unrelated to immediate travel.
6. MAX is **Russia-origin-focused**, while Telegram RU is wider Russian-speaking travel media. Telegram EN is independent global media.
7. Telegram RU **every publication from the Engine** ends with a clickable MAX channel link; MAX RU reciprocates with clickable Telegram RU link. Telegram EN never receives this RU cross-promo.
8. Long articles are rare; short posts, useful lists, breaking items, interactive material, photo stories, mini-guides and culture/entertainment are genuinely represented.
9. Every important claim is auditable; unverified mutable claims are omitted/held. External URLs are minimized in public copy *without concealing mandatory attribution or critical official advice*.
10. Brand voice is recognizable: friendly, smart, observant, lightly witty, without plagiarism, false claims, clickbait or snide/demeaning jokes.
11. Scheduling, generation, media, affiliate links, link rendering, retries, publication logging, admin review, dashboards and cost guardrails work end to end.
12. Cursor **releases** the code and configuration safely to the working production infrastructure and verifies the deployed revision by genuine live evidence; tests/PR alone are insufficient.

---

## 2. Competitor research: preserve the editorial mechanisms, not the copy

Existing qualitative research as of 2026-10-28 (not a standardized quantitative efficiency study):

| Channel/reference | Observed successful mechanism | What WeGoTrip adopts | What to avoid |
|---|---|---|---|
| [Горбилет СПб](https://t.me/gorbilet) | timely weekend itineraries, local cultural listings, new routes | practical city leisure with precise dates | high-volume commercial event spam |
| [Горбилет Москва](https://t.me/gorbilet_msk) | Moscow-specific event utility | clear city relevance and approachable headlines | treating all of Russia as Moscow |
| [Sputnik8](https://t.me/sputnik8_official) | short place facts, tour recommendation when logical | fact -> curiosity -> optional product | every post ending in a sale |
| [Tripster](https://t.me/tripsterofficial) | unusual places, surprising angles, narrative hooks | editorial surprise and interesting stories | copying tone, structure or distinctive jokes |
| [Авиасейлс](https://t.me/aviasales) | amusing travel observations, timely strange news, humor | witty but humane relevance without a commercial link | coarse sarcasm, too much frequency |
| [ПСЖР](https://t.me/psgr_aviasales) | calm travel-media pacing | sustainable reader-friendly cadence | publishing for quota alone |
| [Туту](https://t.me/tutu_travel) | people, food, traditions and practical planning | human stories and cultural breadth | discount-only feed |
| [Яндекс Путешествия](https://t.me/yandex_travel) | visual selection, accessible overseas travel details, polls/games | visual explainers and Russia-specific practical context | huge repetitive checklists |
| [KudaGo](https://t.me/kudagospb) | constantly updated city events | event discovery and reliable deadlines | their extremely high publication density |

Prior indicative posting observations (heterogeneous measurement windows; do **not** represent as fresh synchronized analytics): Tripster ~7/week; Aviasales ~13/week; PСЖР ~5/week; Gorbilet SPb ~2/day; KudaGo can publish many times/day. WeGoTrip **should not emulate** the fast-affiche frequency. Audit more competitor posts periodically for **rubric inspiration only** and store examples/URLs/dates; never scrape against platform restrictions or reproduce protected text/media.

`editorial_mechanic` taxonomy:

- `weekend_utility` (Gorbilet);
- `surprising_place` (Tripster);
- `curious_travel_news` (Aviasales);
- `short_fact_plus_use` (Sputnik8);
- `practical_from_russia` (Yandex Travel);
- `culture_and_people` (Tutu);
- `playful_interaction` (Tripster/Yandex Travel);
- `editorial_feature` (original long feature).

Every topic proposal must include **one primary mechanism**, not only `city` or `keyword`.

---

## 3. Three distinct channel policies

### 3.1 Telegram RU (`telegram_ru`)

- Russian-language media for residents of Russia and Russian-speakers elsewhere.
- Both domestic leisure and trips abroad, including places for which WeGoTrip sells tours in rubles.
- **Russia is a key origin market**. Use current Russia outbound/domestic signals when choosing tourist destinations, but do not hide interesting Europe/U.S./world cultural stories merely because visiting is difficult today.
- Default audience mix as an **editorial hypothesis**, not quota: ~50% local discovery, ~35% trip planning, ~15% broadly interesting culture/inspiration.
- Content can be relevant outside Russia if it is still worth reading (surprising architecture, museums, global travel news).
- Target **5–6 quality posts/week**, typically **0–1/day**; skip days with no good topic.
- Core branding (keep existing channel): **`WeGoTrip — Куда сходить и что посмотреть`**.
- Public domain in description: `https://wegotrip.ru`.

### 3.2 Telegram EN (`telegram_en`)

- **Original international English**, not Russian copy machine; English-readable language for global locals and travelers.
- Independent trends, calendars, holidays, local discovery cities, search intents and source selection; culture/inspiration beyond Europe.
- Default mix hypothesis: ~35% local discovery, ~45% trip planning, ~20% cultural interest.
- Target **4–5 quality posts/week**; typically **0–1/day**.
- Approved name: **`WeGoTrip — Things to Do & Travel Ideas`**.
- Description links to `https://wegotrip.com`.
- **No MAX cross-platform footer**, no Russia-only rules, no translated RU post batches.
- Distinguish English **site language** from products' **audio-guide language**. A global-English article may link to a tour in another language only if the language is clearly indicated and relevant; do not call it “English audio guide” without proof.

### 3.3 MAX RU (`max_ru`)

- **Intended for people living in Russia**, not a global Russian-language audience; do not assert the actual location or nationality of every subscriber.
- ~75% local experiences/domestic Russia and ~25% realistically relevant outbound trips **as a soft, re-evaluated editorial hypothesis**, not a rigid quota.
- Add travel interest without requiring a tour: fun facts, museums, weekend suggestions, regional culture, discoveries, traditions, human stories, light humor.
- Avoid overconcentration on Moscow/SPb; rotate regions and event locations on evidence.
- Handle overseas destination content from the perspective of departure from Russia: travel feasibility, transport, entry rules, payment/product access only after verification when mentioned.
- Target **3–4 quality posts/week**; generally 0–1/day.
- Channel already exists: `https://max.ru/channel_wegotrip` (do not create a new one).
- Keep existing approved name **`WeGoTrip — Куда сходить и что посмотреть`**, refresh description only if mismatched and access permits; confirm actual current state first.

### Frequency limits across channels

- Normal rule: max 1 main post per channel per calendar day.
- An exceptional breaking story may create a second post after extra validation, with >=6h spacing.
- Caps: TG RU <=8/week, TG EN <=7/week; MAX normally <=5/week. Going above approved limits requires a documented operational change, not auto-optimization.
- Full rich articles **max 1–2/month/channel** in Telegram; MAX has platform-specific length limits and should primarily be short posts.
- No bulk backfill, no 10–20 articles/day, no queue dump on restart.
- Publication time uses timezone-aware UTC storage with `Europe/Moscow` as MAX/RU scheduling baseline; local event timezone explicit if needed. EN slots chosen per global audience and observed performance, never hardcoded Russian holidays.

---

## 4. Language, localization and market adaptation: required architecture

**This section is a release blocker if it is missing.** Language adaptation is **not literal translation** and not a generic RU/EN flag.

Maintain three distinct dimensions on each content idea/variant:

```json
{
  "content_language": "ru | en",
  "channel_id": "telegram_ru | telegram_en | max_ru",
  "editorial_market": "ru_speaking_global | international | residents_of_russia",
  "audience_intent": "local | traveler | both",
  "audience_origin_context": "russia | global | relevant_region",
  "geographical_scope": ["country/city/region IDs"],
  "published_platform": "telegram | max"
}
```

### Localization/selection decision tree

1. **Find the audience question** for each market independently (what to do this weekend? what is worth seeing in this city? what actually matters to an outbound tourist from Russia?).
2. **Score source relevance** for that market: season, geography, public holidays, real trips/demand, calendar, language/cultural nuance, ability to benefit.
3. **Select topic per channel**, then choose format/angle. A single universal event may be selected for 1, 2 or 3 channels, but that is a deliberate editorial decision, not automatic translation or mirroring.
4. **Create shared verified facts** where a story overlaps; create **separate original variants** using channel-specific OpenAI Writer prompts. Never insert unverified extra facts in a local adaptation.
5. **Localize specific details**, if relevant: local name/transliteration, date/time and timezone, currencies/prices when verified, holidays, entry requirements by explicit nationality/status, departure context, spelling, product types and audio language.
6. **Select eligible products** for platform/site. RU channels use RU-language product segment on `wegotrip.ru`; EN uses global site `wegotrip.com` with truthful audio language. Exclude unsupported market products; do not fabricate alternatives.
7. **Render and publish** only through the correct platform renderer and final validators. Keep channel-specific analytics and revision lineage.

### Example of different angles for one topic (illustrative, not live news)

**Topic:** a new exhibition at a Tokyo museum.

- TG EN: what is new/curious about the exhibition and why visitors to Tokyo may enjoy it.
- TG RU: a surprising story about the exhibit, plus optional travel implications if currently relevant to Russians.
- MAX RU: publish only if it has meaningful Russia-audience value and practical conditions have been checked where needed; otherwise choose a higher-value domestic weekend story.

### Example of overlapping RU content

**Shared signal:** a newly opened museum exhibition in Kazan.

- Telegram RU: distinctive story/curiosity, possible broader Russian-speaking appeal.
- MAX RU: concise weekend recommendation emphasizing local dates, logistics if verified, with different narrative hook and no blind truncation.
- Both use same verified event source facts but **different** public drafts, posting dates and links.

### Language validation

- Automated detection plus LLM review for native, fluid RU/EN; proper nouns and necessary foreign names allowed.
- No robotically translated idioms or generic “Dear traveler” language.
- Locale-specific accents/humor are **culturally understandable**, avoid stereotypes/national mockery.
- Configuration supports adding new languages later, but **this release is three channel variants**, not 27 public channels.

---

## 5. Content pillars and mix: variety is non-negotiable

All 13 pillars from the previous editorial specification must remain available:

| `content_pillar` | Idea / user value | Formats | Typical commercial behavior |
|---|---|---|---|
| `weekend_plans` | What to do this weekend | 3–5 ideas, photo+caption, quick itinerary | optional |
| `exhibitions_museums` | New/exiting exhibitions and cultural events | short news, museum review, shortlist | optional |
| `travel_updates` | Practical news affecting plans | concise news + impact | often none |
| `short_routes` | City in a day, neighborhood exploration | small route, stops, photos | 0–1 products |
| `hidden_gems` | Unexpected places, odd architecture | fact-led short story | often none |
| `place_stories` | History of a location, surprising detail | narrative, quiz | none/optional |
| `museum_without_boredom` | What to notice in an exhibition | detail, visual explainers, Q&A | contextual |
| `occasion_specific` | With children, date, free, bad weather | user-useful selection | optional |
| `trip_planning` | City/country, timing, budget, practical tips | brief how-to, checklist | optional |
| `fresh_angle` | A different perspective on a city | photo story, comparison, mini game | usually none |
| `engagement` | Poll, quiz, question | native interactive where possible | no product |
| `wegotrip_native` | Tour/audio guide worth knowing | specific real product, short story | direct, capped |
| `deep_guide` | Infrequent fuller travel guide | Telegram rich article | optional |

**Format taxonomy:** `short_news`, `travel_observation`, `photo_story`, `quick_list`, `weekend_selection`, `mini_itinerary`, `museum_tip`, `faq_tip`, `quiz`, `poll`, `video_note`, `audio_preview`, `native_product_card`, `rich_article`. Only show a format as available if the real platform can publish it correctly. Each variant stores `content_pillar`, `post_format`, `editorial_mechanic`, `audience_intent`, `why_now`, `audience_value`, `product_relation`, `source_evidence_refs`, `verification_status`.

### Editorial mix and anti-repetition gates

- In rolling 30-day previews, cover >=6 distinct pillars and >=4 distinct supported formats **when sufficient good material exists**; missing data is `INSUFFICIENT_DATA`, not auto-FAIL for brand-new channels.
- No >2 consecutive posts with the same primary mechanism or near-identical headline shape.
- No >2 consecutive stories exclusively about the same city unless significant new breaking news.
- Avoid 3 consecutive purely commercial posts; normal direct sales-led posts <=~20% of a rolling month (configurable soft maximum). In general **most content needs no CTA**.
- At least ~25% of ordinary candidate pool should be cultural/curiosity/entertainment **independent of product inventory**, subject to quality. Never force a stale or low-value post to achieve percentages.
- Collect a reason for why a topic is genuinely interesting even if `relevant_products=[]`.
- Hashtags: off by default; use 0–2 only if demonstrably useful. Avoid keyword stuffing, noisy emojis, repetitive hooks.
- Link count: source URLs internal evidence by default; necessary legal/official/rights citations and actionable documents can appear publicly. Optimize discoverability/resharing, **do not assert that fewer links guarantee higher search ranking**.

### Timing rules

- Prefer preparing weekend ideas in midweek/Thursday, with **explicit applicable city and dates**.
- Prepare holiday/school-holiday topics ahead only after real calendars checked for relevant region.
- A fresher, higher-value verified story can replace a planned evergreen slot. Superseded plan items archived (never silently erased).
- Scheduling is adaptive, not a fixed 13-item weekly rotation.

---

## 6. OpenAI Chief Editor as the decision maker

### Required daily and event-driven pipeline

```text
Source discovery (museums / tourism / official news / trends / API / events)
          ↓
Normalization, deduplication, provenance, trust rating, date/time TTL
          ↓
Russia / International Market Briefs (audience-specific)
          ↓
OpenAI Chief Editor: select/replace/drop topics + format + channel + why now
          ↓
Rolling 30d calendar (editable, versioned; 7d priority, 48h urgent)
          ↓
Verified Fact Bundles / claims ledger / optional product matching
          ↓
OpenAI Writer: unique platform+market variant
          ↓
Independent Fact Gate + OpenAI Critic + structural QA + compliance
          ↓
Final platform render incl. RU cross-promo footer
          ↓
Dry run / editorial policy approval or auto gate → Scheduled Publication
          ↓
Telegram RU / Telegram EN / MAX RU
          ↓
Metrics / feedback / Editorial Memory / next daily plan
```

- Daily scheduled **real OpenAI API** editorial plan refresh for each relevant market; additionally react to major events/source corrections, product removal, nearing deadlines and meaningful performance signals.
- Chief Editor must receive **structured** signals, not blindly browse random pages or accept an unsourced headline.
- Every run has model ID, token/cost accounting, prompt version, actual provider request identifier (where exposed), before/after calendar diff, motivations for choices, selected and rejected topic IDs.
- Run outcomes: `SUCCESS`, `PARTIAL`, `SOURCE_STALE`, `BUDGET_HELD`, `API_FAILED`. Do not claim Chief Editor used API unless real request and valid response exists.
- Model selection configurable (`OPENAI_EDITOR_MODEL`, `OPENAI_WRITER_MODEL`, `OPENAI_CRITIC_MODEL`, `OPENAI_FAST_MODEL`); prefer a high-quality current model for writing and cost-effective tools for extraction/ranking. **Do not hardcode potentially non-existent marketing model names**; use currently available models/Responses API and strict schemas, confirm actual account compatibility.
- Never rely on current ChatGPT conversation memory when using API. Put editorial policy, examples, style rules and feedback in versioned prompts and database; feed relevant history to each call.
- No fake 'self-learning': log edits, approval/rejection reasons, actual post performance; change ranking weights only when backed by sufficient evidence.

### Daily planning output (schema example)

```json
{
  "editorial_run_id": "...",
  "run_date": "2026-10-28",
  "market": "ru_speaking_global",
  "input_signal_refs": ["..."],
  "proposals": [{
    "idea_id": "...",
    "channel_targets": ["telegram_ru"],
    "pillar": "exhibitions_museums",
    "mechanic": "weekend_utility",
    "format": "short_news",
    "headline_angle": "...",
    "why_now": "...",
    "audience_intent": "local",
    "russia_demand_relevance": "medium",
    "required_claim_ids": ["..."],
    "product_ids": [],
    "publish_window": {"not_before": "...", "not_after": "..."},
    "selection_reason": "..."
  }],
  "calendar_mutations": [{"action": "insert|move|replace|cancel", "reason": "..."}],
  "rejected_ideas": [{"id": "...", "reason": "..."}]
}
```

Use JSON Schema / structured output; validate all IDs, time windows and field enums. The LLM does **not** execute publishing, call arbitrary endpoints or choose secret configuration values.

### Editorial memory

Persist latest used places, headings, formats, jokes and subject angles, recently rejected themes, reader comments if legally available, manual edits, quality scores, publication metrics. Provide compact relevant excerpts to the Chief Editor. Rejected or low-performing angles must not reappear verbatim the next day.

### Operating modes

- `review`: drafts require explicit human editorial approval.
- `auto`: articles can publish automatically **only after the release gates pass** and current platform's auto flag is enabled; no bulk unreviewed backfill.
- Existing approved auto-publication setting must be preserved during deployment unless unsafe; user authorized **safe release**, not an unlimited new publication cadence.
- Run a canary (test channel / staging) before production; once verified, safely switch production engine to the new pipeline with rollback switch. Final scheduled posts must pass prepublish quality gates again.

---

## 7. Evidence-driven intelligence and Russia demand

### Source connectors / adapters

Implement or reuse:

- `MuseumInstitutionProvider`: museum/attraction official sites, exhibitions, permanent/temporary changes.
- `EventsCalendarProvider`: verified city cultural listings / organizers; pay attention to *start/end times and local timezone*.
- `TravelOfficialProvider`: tourism boards, state authorities, immigration/visa, airlines/rail/transport official notices (only if relevant).
- `NewsProvider`: credible dated travel/culture news with original source resolution.
- `TrendsProvider`: global Google Trends and licensed search/keyword sources where available; don't misrepresent index values as actual searches.
- `RussiaTrendsProvider`: Yandex Wordstat/search trends or other permissible RU-market signals **when authorized**, plus verifiable travel/booking demand sources.
- `RussiaOutboundRulesProvider`: dated rules for applicable nationality/residency/visa status; never declare travel “visa-free” in general without qualification.
- `WeGoTripAffiliateCatalogProvider`: catalog, inventory, product photos and potential audio previews.
- `CultureCuriosityProvider`: meaningful evergreen museum/place/history facts with sources.

Source ingest should use legitimate RSS/APIs/public accessible pages with licensing and rate limits; no CAPTCHA bypass or unauthorized scraping. When a source is inaccessible, report `UNAVAILABLE` and use permitted alternative; don't fabricate data.

### Market signal methodology

Store `demand_signal_type` explicitly: `search_interest`, `actual_arrivals`, `organized_tour_sales`, `hotel_bookings`, `air_ticket_searches`, `museum_interest`, `wegotrip_orders`. These are **not equivalent**, cannot combine as if one metric, must include source, sample, geography, date range and methodology caveat.

For Russia outbound examples, **China, Vietnam, Thailand, UAE, Turkey, Egypt, CIS and others** are *dynamic discovery candidates*, not a fixed “Asia always wins” content rule. Conversely Europe isn't banned as cultural subject matter. Once weekly, rank actual demand and practical accessibility; update editorial briefs. Distinguish tourism demand from visa access, flight accessibility, payment possibilities and actual product eligibility.

For MAX, content about outbound travel must pass `MaxRussiaAudienceGate` with at least concrete benefit and no unsupported practical travel claim. *This gate is not an automatic rejection of fun international culture stories if they are genuinely relevant and framed without bogus logistics.*

### Factuality and provenance

Keep for each atomic claim:

```json
{
  "claim_id": "...",
  "normalized_claim": "...",
  "fact_class": "stable|mutable|high_impact",
  "source_type": "affiliate_api|official_primary|credible_secondary",
  "source_url": "...",
  "source_published_at": "...",
  "verified_at": "...",
  "valid_until": "...",
  "location": "...",
  "applicability": "...",
  "status": "verified|disputed|stale|unverifiable|not_applicable"
}
```

- **VERIFY OR OMIT.** Mutable/high-impact facts (ticket price, opening hours, current exhibitions, visa/entry rules, hours/road/rail, payability, restrictions, availability) are checked against current trusted sources before publish; if not verifiable → rewrite safely, omit or HOLD.
- Critical claims require official primary source; secondary news source can trigger discovery but cannot alone confirm current restriction/availability.
- Check `event.start_at/end_at`, actual local time, deadlines, time zone, closures, product current state and link validity before sending.
- Store fact lineage, not raw fabricated model citations. LLM cannot turn a guess into a source.
- Editorial updates after publication should be tracked as correction versions; never silently change a news date to fake freshness.
- Cross-channel adaptation must **not invent** new facts, even if it improves style.

### Public links and citation policy

The editorial aspiration is **shareability/quotability**, not link hiding at all costs:

- Default: sources retained in an internal **Evidence Ledger**; the post usually mentions source names in prose where useful instead of displaying multiple external URLs.
- Always preserve compulsory attribution/licensing requirements, necessary official links for safety/legal/practical claims and accurate product disclosures.
- **If using OpenAI hosted web-search output displayed to end users, follow the API tool's current mandatory citation rendering requirements**; do not strip `url_citation` links or hide required credits. Prefer independent source ingest + verified fact bundles + separate Writer, subject to permissions.
- No unsupported promise that removing external URLs improves Telegram/Google indexing, ranking, citations or forwarding.
- Search-friendly, **human-first** headings, accurate named entities, memorable original insights, concise hooks; no keyword stuffing.

---

## 8. Original WeGoTrip brand voice and readable formatting

### Positioning sentence

**“Умный приятель, который знает, куда сходить, и умеет интересно об этом рассказать — не как экскурсовод с микрофоном и не как отдел продаж.”**

EN equivalent: “A well-traveled friend with great local tips and a sense of humor — never an ad brochure.”

### Good voice rules

- Friendly, observant, easy-to-read, confident but not pompous.
- Real insight in the first 1–2 sentences. Lead with something surprising, useful or vivid; immediately answer the reader's question.
- Smart, low-pressure situational humor. No need for a joke in every post; zero humor is better than weak humor.
- Natural short paragraphs, varied rhythm, at most a few well-chosen emojis, avoid overformatting.
- One main idea per short post, no generic motivational signoff, no ritual “save this for later” in every issue.
- In a themed roundup, cite precise event city, dates and who benefits; avoid pretending a local event matters to the whole country.
- Reference Aviasales and T—Ж **for general readability, wit and lively practical writing only**. Never copy their slogans, jokes, phrasing, media or trademark voice.
- No national/religious/racial/gender stereotypes, political tribal bait, humiliation, patronizing familiarity or mockery of tourists.

### Bad examples / anti-patterns

- “Погрузитесь в атмосферу незабываемого путешествия…”, “уникальная жемчужина”, “обязательно к посещению”, “секретное место, о котором никто не знает” without grounding.
- Generic numbered lists repeated every 2 days; fake first-person anecdotes or false ‘we visited yesterday’ reporting.
- Coercive CTAs, unverified ‘best/cheapest’ or ‘last chance’ claims.
- Long introductions, AI-sounding moral conclusions, invented quotes of visitors.

### Prepublish editorial scoring

Independent critic returns 0–5 each for: `relevance`, `specificity`, `accuracy`, `originality`, `readability`, `voice`, `light_humor_appropriateness`, `share_potential`, `format_fit`, `market_fit`. Safety/accuracy are *hard gates* independent of average score. At least 2 independent evaluations for a weekly sample and all major editorial failures. Persist critical comments and repair before auto-publish.

### Typography and format

- Telegram: short posts + images, carousels/collections, quizzes and rare Rich Articles. Use official supported `sendRichMessage` for appropriate rich drafts; do not force all content into rich messages. Detect official Bot API capabilities at runtime/version and degrade safely or hold.
- MAX: its own renderer, supported text formatting and media/inline buttons. **Do not send Telegram rich JSON to MAX**; honor its documented text/media limits after including the footer.
- Visually inspect representative final payloads/previews in platform clients if possible. Device/browser access missing → `UNVERIFIED`, not invented screenshot PASS.

---

## 9. Commercial products, partner links, media

### Catalog and segment truth

Reuse existing country/city/attraction/category/collection-subcategory/product model. Keep `Collections` as a meaningful app entity, but if the Affiliate API doesn't expose a dedicated endpoint, infer only from documented `subcategories` or existing reliable sources and mark missing relationships `not_available`. **Never invent product categories or IDs.**

WeGoTrip products can have separate audio-language product IDs; language-specific variants are not merged unless source provides explicit stable relationship. Correct market and permitted domain checked before inserting CTA.

### Commercial restraint

- Post useful editorial content even with `matched_products=[]`.
- Product insertion optional, relevant to intent, usually 0–1; max ~2 in general list posts where truly useful.
- No fake prices, ratings, inclusions, availability, “skip the line”, discounts, accessibility claims or working payment methods.
- Product-centric articles/cards not exceed ~20% of normal publication mix unless actual performance justifies a deliberate documented change.

### AffiliateUrlBuilder

```text
wegotrip.ru/.../?coupon=435&utm_source=telegram&utm_medium=content&utm_campaign=...
wegotrip.com/.../?coupon=435&utm_source=telegram&utm_medium=content&utm_campaign=...
wegotrip.ru/.../?coupon=435&utm_source=max&utm_medium=content&utm_campaign=...
```

Examples are schematic; **actual URLs come from the API and existing canonical URL builder**, never guessed. Preserve fragments and query syntax. `coupon=435` applied **once**; UTM article/channel IDs unique; link tests check destination and site locale/market. Cross-platform footers remain direct social URLs **without** `coupon=435` and without invented UTM links.

### Media policy

- Primary use: licensed/allowed media actually from WeGoTrip API (city, attraction, product) and existing allowed media library.
- For news/exhibitions where API has no relevant image, **either text-only or approved, legally usable official press media with recorded rights**; never scrape an image and assume it's free. If the configured policy forbids outside-API media in some use case, respect it.
- AI-generated illustrative covers only if explicitly enabled, within authorized cost cap, labeled/handled so they cannot be mistaken for real museum/event photographs; do not fake actual artworks/venues.
- Existing product audio preview only if returned legitimately in API/authorized source and platform player/API support verified; never derive hidden media URLs or synthesize nonexistent previews.
- Rights metadata, dimensions, source URL, attribution requirements and expiry persisted.

---

## 10. Required cross-platform navigation in **every Engine-produced RU post**

Implement as **final renderer-injected footer**, never as a Writer prompt. Strictly one footer, after editorial and commercial blocks, in same publication unit.

### Telegram RU public footer

Visible:

> Ещё мы в **MAX** — читайте там, где удобнее.

The word `MAX` is clickable inline link pointing to **`https://max.ru/channel_wegotrip`**.

### MAX RU public footer

Visible:

> Ещё мы в **Telegram** — читайте там, где удобнее.

The word `Telegram` is clickable inline link pointing to **`https://t.me/wegotrip_ru`**.

### Telegram EN

**No RU footer.**

### Engineering constraints

- Idempotent `CrossPlatformFooterInjector` derives target from `publication.channel`, not text language or mentioned city.
- Must handle regular text, rich Telegram text, image/video with caption and MAX text/media. For native poll/media-only formats which cannot carry inline footer in same supported message, **do not silently bypass the requirement**. Use a well-designed single-publication fallback when possible, otherwise `HOLD_UNSUPPORTED_FORMAT` and flag in admin dashboard; do not emit a spammy second message.
- The model must never be told to translate/rephrase the fixed footer. Publisher must not duplicate it after retries/edits.
- MAX: reserve footer budget within the documented text-length limit (prior version used 4,000 chars; verify current API). Shorten content *semantically*, not byte-truncate text or source qualifiers.
- Inline links must be clickable; do not display a large outbound link preview that swamps the story when platform controls permit disabling preview.
- Mandatory navigation links are **not counted** as external source links or as product CTAs; in logging count as distinct `brand_navigation` category.
- Direct social URLs by default; no intermediate redirect/tracking workaround. Logs can track rendered state; don't invent measured actual transfer conversions without provider support.
- Editorial Engine-produced manual admin posts also receive footer. Posts manually authored outside the Engine cannot be guaranteed; monitor for them if read-only capability exists and alert, do not self-edit historical posts.

**Release blocker:** all newly published eligible RU posts via the Engine include exactly one correct clickable footer; no unsupported special format is silently published without one.

---

## 11. Channel branding: apply already approved proposals, don't rename usernames

Previous owner approval was explicitly provided for the two Telegram channels. Applying those exact proposed changes is within the requested autonomous release scope, **if they are not already applied**.

### Telegram RU

- Title: **`WeGoTrip — Куда сходить и что посмотреть`** (keep).
- Description, exactly unless already current:

> Куда сходить в выходные и куда поехать дальше? Музеи, выставки, необычные места, маршруты и новости для местных и путешественников. Пишем по делу, с любопытством и иногда с улыбкой. https://wegotrip.ru

- Pinned welcome content: use approved version from `CHANNEL_BRANDING_PROPOSAL.md` and compare existing pinned message; do not add a duplicate if already pinned.

### Telegram EN

- Title: **`WeGoTrip — Things to Do & Travel Ideas`**.
- Description, exactly unless already current:

> Good ideas for this weekend and your next trip. Museums, exhibitions, surprising places, city routes and travel updates for locals and travelers. Useful, curious, occasionally witty. https://wegotrip.com

- Pinned welcome: use approved version from `CHANNEL_BRANDING_PROPOSAL.md` and compare existing; no duplicates.

### MAX RU

- Keep existing name **`WeGoTrip — Куда сходить и что посмотреть`**, existing public URL and identity.
- Draft/reconcile platform-appropriate description conveying weekend ideas, exhibitions, routes, unusual places, local/domestic and outward travel relevant to Russia. Where such change was not separately approved as exact text, **apply only the already approved content / existing current value; for new copy prepare a preview and apply only if it is non-destructive, within existing editorial identity settings and supported rights.** Do not touch unrelated profile fields.

### Approved pinned welcome posts (exact initial copy; create only if needed)

**Telegram RU:**

> Привет! Это WeGoTrip 👋
>
> Здесь ищем ответы на два вечных вопроса: куда выбраться в выходные и что посмотреть, когда уже выбрались. Подсказываем интересные музеи, выставки, прогулки и необычные места, рассказываем истории городов и делимся новостями, которые действительно пригодятся в поездке.
>
> Иногда советуем аудиогиды и экскурсии WeGoTrip — когда они к месту. Иногда просто рассказываем что-то классное.
>
> Если у вас пока нет планов на выходные, считайте, что теперь есть с чего начать.
>
> English channel: @wegotrip

**Telegram EN:**

> Hi, we're WeGoTrip 👋
>
> For the weekends when you want to get out, and the trips when you want to see more than the usual checklist. Expect clever city ideas, exhibitions, museums, unusual places, useful travel updates and the odd story worth sharing.
>
> Sometimes there's a WeGoTrip audio tour that fits perfectly. Sometimes a good idea is all you need.
>
> Your next plan might be one post away.
>
> По-русски: @wegotrip_ru

Keep the approved copy unless current live channel contains a newer owner-approved pinned version. Pinned welcome posts are identity/setup exceptions; the mandatory RU-to-MAX footer applies to **new ordinary Editorial Engine publications**. If creating a new welcome post through the Engine, include its final approved footer where technically supported; never retroactively modify an existing approved pin merely to add the footer.

### Operational behavior

Use real Telegram `getChat` and MAX chat info/rights; apply via official supported APIs only if permissions suffice. If not, give **precise manual UI instructions**, but continue unblocked release steps. Save before/after snapshots (no secrets), mutation logs, moderation responses, URLs and rollback directions. Preserve subscribers, old posts, message IDs, Community links and unrelated old pinned posts (never unpin important ones silently).

OpenAI Chief Editor **must never** autonomously change channel usernames/titles/bios/pinned posts as part of daily planning.

---

## 12. Architecture and schema: evolve existing code

Inspect existing repo/CI/production runtime first. Reuse working modules, migrations, queue and analytics. Avoid redesign for vanity. Recommended logical services:

```text
CatalogSync / AffiliateAdapter
SourceRegistry / News & Event Providers / Trends & RussiaDemand
SignalNormalizer / EvidenceStore / ClaimLedger / RightsStore
OpenAIChiefEditor / TopicScorer / RollingEditorialCalendar
FactBundleBuilder / ProductMatcher / OpenAIWriter / OpenAICritic
ChannelVariantAdapter (Telegram RU, Telegram EN, MAX RU)
PlatformRenderers (TelegramRich, TelegramStandard, MAX)
CrossPlatformFooterInjector / URLBuilder / MediaValidator
EditorialReview / Scheduler / IdempotentPublishers / DeliveryLedger
Analytics / CostManager / EditorialMemory / AdminUI
```

### Core data entities (reuse/adapt current schema)

- `Channel`: platform, title, URL, locale, editorial_market, audience profile, timezone, planned frequency, enabled flags, API IDs.
- `ContentPillar`, `Format`, `EditorialMechanic`, `AudienceIntent`.
- `SourceFeed`, `SourceItem`, `NewsSignal`, `TrendSignal`, `MarketDemandSignal`, `Event`, `Exhibition`.
- `VerifiedFact`, `Claim`, `EvidenceLink`, `SourceLicense`, `MediaAsset`.
- `IdeaCandidate`, `EditorialDecision`, `PlanRun`, `CalendarSlot`, `PlanMutation`.
- `Story` (shared validated facts and editorial idea), `ChannelVariant` (original text per channel), `VariantRevision`, `ProductRecommendation`.
- `PublicationJob`, `PublicationRecord`, `PlatformPayload`, `CrossPromoFooterState`.
- `PromptVersion`, `AIInvocation`, `CostLedger`, `PerformanceSnapshot`, `FeedbackEvent`.
- `BrandingSnapshot`, `Deployment`, `AcceptanceRun`, `AuditEvidence`.

### Core invariants

- Unique `(platform_channel_id, publication_variant_id)` for completed delivery, with retry/reconciliation states.
- A `Story` may have 0–3 `ChannelVariant`s; not every channel receives every story.
- Each `ChannelVariant` has independent status and schedule; shared source facts are immutable snapshots with version.
- Old unverified content is never silently promoted into a new `VerifiedFact`.
- Product link locale, source, language and affiliate ID tested.
- `publication.status` cannot become `published` without actual platform response/reference/confirmation.
- Failed third-party integration for one channel must not halt other channels except where shared source facts are unsafe.
- All calls can be retried safely with bounded retries, exponential backoff and uncertainty reconciliation.

### Admin UX (must work)

- Dashboard per channel: last AI plan run, sources status/freshness, drafts, queue, published, errors, spend, metrics.
- 30-day editorial plan, 7-day actionable queue and 48-hour urgent view; show channel-specific variants side by side.
- Topic candidate review/approve/ignore, reason, source evidence, market fitness, product match, duplicate warnings.
- Post preview **including** final footer and CTA, exact destination, media rights and length/format validations.
- Approve/reject/edit/schedule/retry test/publish now, with permission checks and audit trail.
- Channel branding state comparison and approved application log.
- Settings: per-channel cadence, content mix, AI model selection, budget caps, review/auto status, source list, market weighting, crosspromo flags and alert thresholds.
- No hidden debug-only toggles required for normal operation.

---

## 13. Publication safety and operations

- `TelegramPublisher` uses official Bot API appropriate to current post structure (Rich Messages only where useful); verify real bot admin rights to publish and edit.
- `MaxPublisher` uses official MAX API and actual existing channel `chat_id`/bot permissions; use currently documented host/version, attachment and text limits, rate limits, caption behavior. No userbots/unofficial automation.
- Store platform returned IDs and URLs where actually available. Do not guess MAX public message URLs.
- Webhook/cron/jobs are observable with timestamped logs, retries, dead-letter queue (or existing equivalent), manual recovery path.
- Verify no duplicate scheduled jobs across workers, after deploy or process restart; acquire locks/unique constraints.
- Before every publish: source time validity, anti-duplicate check, market/language, accurate product/media, final footer, current API payload limits, cost/quality/permissions.
- On platform timeout where delivery is uncertain, **reconcile actual delivery** before trying again; do not instantly double-post.
- On later product disappearance, do not automatically rewrite every old post; flag/update only material factual issues and preserve versions.
- Logs never expose tokens, user personal data, API keys or paid source payload beyond usage rights.
- Keep backups, rollback plan and useful health alerts. Explicitly document expected env vars; no secrets in git.

### AI and other costs

Carry forward existing **~$3/day AI cost target if it is active**, with configurable hard daily limit. It is now a low-volume multi-channel media engine, not the old 20–40 articles/day target. Track separate AI planning/writing/review costs, external paid search/source costs and optional image generation. Do not secretly exceed configured spend, silently drop verification to save money or claim 5 posts when no safe budget remains. On budget exhaustion: reuse verified data when valid, postpone noncritical work, alert, and preserve safety gates. Model pricing is updated in configuration from real provider pricing, not guessed.

---

## 14. Analytics: value of media before ecommerce

By post/channel record when genuinely available:

- impressions/views, reach (where provided), reactions, shares/forwards, comments, subscriber trends, engagement per view;
- article/product link clicks (only with controlled, legitimate tracking), sessions, orders, GMV, contribution, post-attributed revenue;
- `source`/`utm_medium`/`campaign` plus `coupon=435` for **real WeGoTrip commerce** links;
- per-post AI cost, publication issues, source accuracy, editorial quality score, manual edit rate, fact-correction rate;
- performance by content pillar/mechanic, region/market, weekday, post format and length;
- cross-platform footer presence, link health, aggregated downstream effects **without pretending to know unique cross-platform subscribes**.

If API metrics aren't available, show `N/A / unavailable`, not zeros or made-up conversion rates. Build Metabase-friendly tables/views or integrate existing dashboards. A content item can be successful without revenue; the media KPIs are primary, commercial KPIs secondary.

---

## 15. Automated comprehensive acceptance test suite

### Audit protocol

- Test **actual deployed revision**, env/flags/schedule (without leaking secrets), production channel IDs and **actual recent publication examples**.
- Status for every case: `PASS | FAIL | PARTIAL | BLOCKED | INSUFFICIENT_DATA`.
- Each status includes test ID, repo version/commit, deployed version, timestamp, evidence path/response ID, channel, failure reason and owner-facing action if blocked.
- A green PR CI cannot count as production verification; a mock doesn't count as proof of live API capability.
- Do not fabricate screenshots/clickability/costs/sales. If cannot access a mobile client, mark platform UI portions `BLOCKED` and run verifiable API/payload checks independently.
- Always do automated unit/contract/integration tests, one real end-to-end staging/test-channel scenario per platform where access exists, and sample live production audit of already published **real** content.
- For live verification of new engine, use planned **real editorial publications** in a controlled canary, not dummy messages in public channels.

### Acceptance matrix: required tests

| ID | What Cursor must test | PASS criterion / evidence |
|---|---|---|
| ENV-01 | existing repo/infrastructure | deployment/working repo identified, migrations compatible, old data preserved |
| ENV-02 | authenticated external API | correct real Telegram/MAX/WeGoTrip/OpenAI responses, permission checks |
| ENV-03 | CI/CD and health | tests green; production commit/version matches deployed artifact; logs/health OK |
| ENV-04 | backup / rollback | tested or documented restore path and actual rollback flag, no destructive migration |
| BRAND-01 | TG RU branding | actual approved title/description/domain, correct username, no duplicate pins |
| BRAND-02 | TG EN branding | approved new title/description/domain, username unchanged |
| BRAND-03 | MAX identity | existing channel with `max.ru/channel_wegotrip` public address, no new channel/IDs guessed |
| BRAND-04 | branding protection | Chief Editor can't mutate profile; permissions/audit logs, important pins preserved |
| CH-01 | channel routing | TG RU/TG EN/MAX RU are three distinct targets, correct timezone/locale |
| LOC-01 | native EN/RU | samples scored for fluent native writing, not blind machine translation |
| LOC-02 | market-aware choice | same input yields sensible channel-specific selection / rejection with reasons |
| LOC-03 | RU product market | RU-language products at `.ru`, global English at `.com`, distinct guide-language IDs |
| LOC-04 | Russia outbound relevance | Russia-origin brief weighs actual demand, access, payments when necessary |
| LOC-05 | MAX vs TG RU | MAX Russia-only audience positioning vs wider TG RU; not identical posts |
| LOC-06 | holidays/timezones | local holiday/calendar/date/timezone applicable, no past weekend listings |
| COMP-01 | competitor lessons | samples demonstrate local value, surprise, humor, culture, practical changes |
| COMP-02 | noncopying | no reproduced competitor text, distinctive voice or unlicensed media |
| PLAN-01 | daily API-led refresh | real OpenAI Chief Editor request and structured, persisted output for RU/EN/MAX |
| PLAN-02 | dynamic calendar | valid rolling 30d plan / 7d priority / 48h urgent, diff tracked |
| PLAN-03 | real trend correction | newer sourced event can replace old planned slot with recorded reason |
| PLAN-04 | commercial independence | verified useful topic with `matched_products=[]` can be selected/written |
| PLAN-05 | duplication | recent topic/format/headline/place repetition controlled |
| PLAN-06 | cadence | RU 5–6/week target, EN 4–5/week, MAX 3–4/week; no spam/out-of-bound dumps |
| PLAN-07 | scarcity | no filler published just to meet quota; skipped slots annotated |
| PLAN-08 | regional breadth | MAX not just Moscow/SPb; Russia regional opportunities included when supported |
| PLAN-09 | market signal validity | sources and denominators distinguish search, sales, arrivals, bookings |
| EDIT-01 | 13 pillars | config/UI/DB supports all and chooses real mix |
| EDIT-02 | multiple formats | test at least 4 supported formats and one rare rich guide |
| EDIT-03 | strong travel media | random recent sample contains noncommercial interesting culture/discovery |
| EDIT-04 | humor quality | natural, situational, non-insulting; no AI clichés/generic fillers |
| EDIT-05 | editorial criticism | distinct critic, traceable edits, review scores/reasons |
| EDIT-06 | original vs localized | MAX adaptation is original but derived from same verified source facts |
| SOURCE-01 | ingestion | provider runs; real provenance, freshness, dedup and API failure handling |
| SOURCE-02 | museum events | dates, location, ended exhibitions filtered, correct source TTL |
| SOURCE-03 | RU and global trends | actual connected sources, useful context, no invented keyword volumes |
| SOURCE-04 | visas/practical matters | explicit applicability and current primary sources; no unsupported blanket claims |
| FACT-01 | claim ledger | mutable claims link to verified evidence, time, source, validity |
| FACT-02 | prepublish gate | stale/unsupported critical claims -> rewrite/omit/HOLD; never publish false claim |
| FACT-03 | contradictions | two conflicting sources are flagged; not collapsed into fabricated certainty |
| FACT-04 | external link policy | public minimal sources consistent with legal/licensing/API citation duties |
| FACT-05 | no invention | products/times/ratings/quotes/events/travel stats never hallucinated |
| MEDIA-01 | rights | media only from API/authorized source, rights/credit stored |
| MEDIA-02 | audio/cover | only actual supported, licensed audio or separately permitted illustrations |
| COM-01 | partner 435 | correct `coupon=435` **once**, right market domain, UTM for product only |
| COM-02 | content not sales spam | product optional, relevant, no high-pressure CTA, direct product ratio controlled |
| CP-01 | TG RU footer | exactly one clickable **MAX** → `https://max.ru/channel_wegotrip` |
| CP-02 | MAX footer | exactly one clickable **Telegram** → `https://t.me/wegotrip_ru` |
| CP-03 | EN no footer | no MAX link / RU footer in TG EN |
| CP-04 | media and rich variants | footer in same publication unit (or documented HOLD for unsupported), no duplicate messages |
| CP-05 | idempotency/limits | footer never duplicates on edit/retry, MAX text limit safe, original CTAs intact |
| CP-06 | manual admin posts | Engine-admin draft includes footer and preview; direct external posts audited if possible |
| CP-07 | direct URLs | no legacy MAX link, no fake redirect/coupon/UTM added to social URLs |
| PUB-01 | Telegram rich renderer | valid supported messages and relevant headings/media/link structure |
| PUB-02 | MAX renderer | official supported API payload, media, length, clickability evidence where accessible |
| PUB-03 | preview/review | exact final payload, verified facts/links/quality/market reason visible |
| PUB-04 | scheduled publish | actual safe end-to-end, recorded platform IDs and errors |
| PUB-05 | retry safety | timeout/worker restart does not duplicate production posts |
| PUB-06 | circuit breaker | bad quality/API or footer failure holds only affected jobs/channels |
| ANAL-01 | metrics | real sources for impressions/views etc, unavailable values marked N/A |
| ANAL-02 | commerce attribution | links, clicks/sessions/orders when supported, no made-up ROAS |
| ANAL-03 | cross-platform | footer status and links recorded; no invented follower attribution |
| ANAL-04 | cost cap | OpenAI usage logged, daily cap respected, failure alarms |
| SEC-01 | secrets/data | no credentials in repo/logs/artifacts; roles and permissions reasonable |
| SEC-02 | source safety | rejects malicious source prompt-injection and disallowed/unlicensed data |
| REGR-01 | legacy baseline | prior catalog/analytics/web/mini app/player functionality unchanged |
| RELEASE-01 | real deploy | deployment completed via existing CI/CD, prod commit and health verified |
| RELEASE-02 | canary/rollback | controlled publish tested, feature flags recover safely |
| RELEASE-03 | post-deploy quality | actual posts after rollout match brand/market/footer/mix, evidence attached |

### Mandatory negative tests (automate where possible)

1. API returns product with missing `locale` or wrong domain; must not silently select it.
2. A tour in Chinese on global site is called an English audio guide; must reject/rewrite.
3. Current exhibition has ended; do not announce it as upcoming.
4. Visitor hours conflict between outdated source and museum official site; use official/hold.
5. News headline appears but original source cannot be verified; no invented details.
6. Visa/travel access differs by nationality/residency; do not generalize from Russia origin.
7. Search trend API unavailable; planner must not invent trends or search-volume metrics.
8. Chief Editor API outage; no silent fallback to posting unverified fixed templates.
9. OpenAI returns malformed JSON or unapproved destinations; reject/retry/hold safely.
10. Source article contains prompt injection telling the AI to disregard instructions; ignore source-side directives.
11. Two near-identical topics selected in same market; deduplicate.
12. Draft with 3 commercial CTAs and no meaningful content; reject.
13. Profanity/derogatory joke or fake quotation; critic/quality gate blocks.
14. Photo without rights attribution/permission; reject or text-only.
15. MAX text + footer exceeds allowed length; semantic rewrite / HOLD, not byte truncation.
16. Telegram RU image/caption cannot fit footer; single-publication fallback / HOLD, not 2 posts.
17. Telegram EN mistakenly receives MAX footer; block and report.
18. Retry after uncertain Telegram/MAX delivery; must reconcile before resend.
19. Old deprecated MAX public link appears in a new post; block.
20. Product link is missing `coupon=435`, duplicates it, or points to wrong market; block.
21. User manually edits post in admin and removes footer; renderer re-attaches exactly once.
22. Bot lacks posting rights to one platform; others continue; affected job remains pending.
23. Restart scheduler while queued slots exist; no flood/backfill burst.
24. Planned 30-day content contains 80% identical ‘top five’ lists; diversification flags.
25. Russia audience topics exclude all European cultural curiosities for geopolitical reasons; test the ability to choose a genuinely interesting non-travel story.
26. Incorrect AI attribution such as claiming live Google Trends when only a cached stale report exists; fail.
27. Cost cap exhausted; generation pauses appropriately, does not skip verification or bill beyond limit.
28. Introductory pin already exists; second deploy must not duplicate it.
29. Production channel URL is replaced by a test channel or bot URL; release gate blocks.
30. External source links removed where mandatory citation, rights or practical safety demands them; reject.

### Editorial sampling tests

- Sample at least latest 20 publication variants per channel if available; otherwise all existing + **12 dry-run drafts per channel** across at least 6 pillars and both local/traveler audience intents.
- Review with an independent critic and structured human-readable evidence. Score every example on 0–5 scale (usefulness, originality, style, market fit, factual support, readable typography, shareability, commercialization pressure).
- Include a **side-by-side plan for one week**: which themes go TG RU, which MAX RU, which TG EN; not a single syndicated copy list.
- Demonstrate realistic 30-day rolling calendar per channel and tracked daily mutations.
- Treat publication frequency and 30-day retention/engagement metrics as **future observational data** when not yet available; don't pretend instant launch has proved long-term success.

---

## 16. Autonomous implementation + release protocol for Cursor

**OWNER AUTHORIZATION:** The owner explicitly directs Cursor to *finish everything and release*, covering all latest requirements. Carry out all safe authorized routine engineering work without stopping for serial approvals.

### Phase A — Discovery and requirements mapping

1. Read this entire document and existing repo; read older specs only to resolve implementation details not covered here.
2. Determine what has been implemented, deployed, partially implemented or undocumented. Inspect PR #6/merged revision if available but **do not assume** CI green means prod deployed.
3. Create/update:
   - `IMPLEMENTATION_PLAN.md` (phase steps, dependencies, risks, how to deploy);
   - `REQUIREMENTS_STATUS.md` (all test IDs and implementation requirements mapped to existing code/files);
   - `ARCHITECTURE_DECISIONS.md` (only material choices); and
   - `DEPLOYMENT_RUNBOOK.md` (secrets excluded, deploy/rollback/health checks).
4. Record actual known platform IDs, routes, job schedulers and configured AI models **without exposing secrets**.

### Phase B — Implement missing requirements

5. Reuse existing code instead of duplicating it; do additive migrations only, with backwards-compatible rollout.
6. Build language/market adaptations and independent 3-channel variants; integrate RU trend/demand intelligence and market fact gates.
7. Ensure OpenAI Chief Editor planning, OpenAI Writer and Critic are real and log evidence; add differentiated rubrics and new content formats; preserve current paid API limits.
8. Integrate full cross-platform footer, real canonical URLs, affiliate tracking, separate renderers; patch MAX and Telegram as needed.
9. Align approved Telegram branding only if not yet applied; preserve pins and identities.
10. Wire admin review, calendar, observability, analytics, outage/retry/duplicate protection.

### Phase C — Automated tests and staging

11. Run unit tests, integration, schema migration smoke tests, security/lint/type checks, source/market/locale checks, deterministic mock-negative scenarios.
12. Run **real** OpenAI planning + writing from authorized credentials in test mode; produce three 30-day illustrative plans (one/channel) and at least 12 high-quality drafts/channel for review evidence. Use test-mode cost caps and preserve market specificity. **Do not publish dummy content to production.**
13. Validate Telegram and MAX payloads using current official APIs, test-channel publication if available, check final footers and real product URLs.
14. Create `PRE_RELEASE_ACCEPTANCE_REPORT.md` with test-by-test evidence and unresolved blockers. Fix P0/P1 failures before proceeding.

### Phase D — Git / CI / production deployment: DO IT

15. Implement changes on branch, create PR if standard workflow, wait for **green CI**, resolve review comments and automatically merge if authorized and protected branch policy permits. If organization security blocks merge or requires a human reviewer, do not bypass; report precise PR and required reviewer action.
16. Deploy through existing approved CI/CD route (Docker/SSH/hosting platform as applicable, discovered from repo) with **feature flags and minimal downtime**. Do not invent credentials, paths, infrastructure or commands. If access exists, perform deployment. If there is no deploy permission, report actual blocker with ready artifacts, not an invented success.
17. Apply compatible migrations with backup and rollback plan; never drop tables/production data, alter business payments, revoke admin roles or remove old posts to meet test expectations.
18. Verify live deployed commit hash, app health, workers, scheduler, queue, source freshness, OpenAI plan job, real platform publish permissions, channel descriptions and channel destinations.
19. Enable new pipeline in controlled **canary mode**: route a valid, fact-checked, approved-quality post into test channel/staging first if accessible. For production, transition **at a regular scheduled publication slot**, with a genuine relevant editorial post; no unsolicited test messages. Preserve current review vs auto settings unless existing owner-approved configuration says otherwise. Since the owner authorized autonomous release, the pipeline **may be deployed and activated** once hard gates pass; no separate routine 'OK to deploy?' question.
20. Validate at least one actual live newly delivered post per platform *as it naturally becomes due*, checking footer/links/locale/IDs. If no post is due during the execution, use real production read-only checks and report `LIVE_NEW_POST=NOT_YET_OBSERVED`; do not make up a future result. Do not promise asynchronous future monitoring unless already implemented by scheduler/alerts in deployed product.
21. Turn on required footer feature flags for Telegram RU and MAX RU once renderer/checks pass; keep TG EN footer OFF. Ensure one channel failure can't cross-contaminate others.
22. If a release-blocking failure occurs after deploy: **rollback** new flags/release to last working version, preserve logs and prepare a corrected release; never leave broken automatic publishing running.

### Phase E — Self-audit and fix loop

23. Run entire acceptance matrix against actual deployed version, including negative cases and editorial sampling. Compare expected behavior to actual code, DB and real API evidence.
24. Fix any P0/P1 defects and rerun tests + deploy safely; P2 issues affecting basic readability and brand voice should be fixed before marking GO.
25. Generate:
   - `POST_DEPLOY_AUDIT_REPORT.md` — true status, PASS/FAIL/PARTIAL/BLOCKED, evidence;
   - `PRODUCT_GAP_BACKLOG.md` — remaining issues with priorities, reproducible steps and owners;
   - `RELEASE_NOTES.md` — version, changes, migrations, deployment time, rollback steps;
   - `EDITORIAL_SAMPLE_REVIEW.md` — representative actual/dry-run posts, critique and examples of RU/EN/MAX adaptation;
   - `OWNER_FINAL_REPORT.md` — concise Russian summary, actual production URL/commit, tests, what still cannot be verified.
26. One final **release verdict**: `GO`, `GO_WITH_CONDITIONS`, `NO_GO` or `UNVERIFIED`. `GO` only if all release-blocker conditions pass and live deploy is confirmed.

### What Cursor is expressly authorized to do without more approval

- Read repository, build/fix code, migrate additively, run tests and dry runs, write documentation, create PRs, deploy through existing permitted CI/CD, apply previously approved Telegram branding, integrate existing MAX channel, switch relevant new-feature flags after gates, publish **genuine planned editorial posts** through pre-existing approved automation.

### Actions Cursor must NOT do autonomously

- Create new brands/channels/bots, change public usernames, delete historical publications/subscribers, reassign ownership, make irreversible database changes without tested rollback, purchase services/advertising or raise API budgets, bypass branch protections or platform terms, expose secrets, publish synthetic test posts to live channels, send unverified sensitive advice, retroactively alter past posts on a mass scale.

### If human input is truly necessary

Ask only **one compact, actionable blocker question** listing the missing credential/permission/review approval and exactly where owner must click, then carry out every step that does not depend on it. Never claim deployment completed if blocked. If an external system requires irreversible consent, respect it.

---

## 17. Hard release gates / completion checklist

Must be **PASS**, not `PARTIAL`:

- [ ] H1: Three *correct existing* production channels and separate market-aware routing.
- [ ] H2: AI-led daily content planning and genuinely OpenAI-written texts, real invocations proven.
- [ ] H3: Regional Russia trends influence RU topics dynamically **without** destroying content diversity.
- [ ] H4: Native EN writing + distinct RU and MAX adaptations, truthful product/audio language segmentation.
- [ ] H5: Useful media variety: 13 pillars supported, preview calendar not a perpetual article factory.
- [ ] H6: Fact/rights/market gate rejects risky invented information and invalid media.
- [ ] H7: Exactly one clickable RU cross-platform footer in every supported Engine publication; impossible formats fail safely. No footer in EN.
- [ ] H8: Correct real affiliate products `coupon=435`, channel/site alignment, correct source links policy.
- [ ] H9: No duplicate posts, spamming, unwanted backfill or shared failure.
- [ ] H10: Admin preview/review/scheduling and operational observability work.
- [ ] H11: Actual CI green, deployed commit confirmed, runtime health and safe rollback available.
- [ ] H12: Audit reports have **verifiable evidence**, production API checks are not mocked.

Quality goals measured only over time (not blockers for day-one deployment): long-term subscriber retention, exact citation/share rates, 30-day topic performance, subscriber cross-platform conversions where provider lacks tracking.

**Important:** If all software tests pass but live deployment is missing → `NO_GO / NOT_DEPLOYED`. If production deployed but significant functionality cannot be independently verified → `UNVERIFIED` or `GO_WITH_CONDITIONS` with exact evidence gaps, never false `GO`.

---

## 18. Final report format (must be sent in Russian by Cursor)

```markdown
# Итог: WeGoTrip Editorial Engine v3.0

**Вердикт:** GO / GO_WITH_CONDITIONS / NO_GO / UNVERIFIED
**Production:** confirmed / not confirmed
**Repo commit / PR / deployment:** <verified identifiers>
**Deployed at:** <actual time>

## Реально реализовано и работает
...

## Три канала
- TG RU — фактическое оформление, план, тест/пост, footer -> MAX
- TG EN — локализация, план, пост, no footer
- MAX RU — РФ-аудитория, план, фактическая публикация, footer -> TG RU

## Проверки
- PASS / FAIL / PARTIAL / BLOCKED: counts and links to evidence
- Source/factual tests, model invocation, product links, publication safety, rollback.

## Редакционные примеры
- RU idea/post + source proof
- EN idea/post + source proof
- MAX adapted idea/post + source proof

## Недостатки / блокеры
...

## Что нужно сделать владельцу (только если действительно необходимо)
...
```

---

## 19. Authoritative technical documentation Cursor must consult when implementing

- Telegram Bot API (Rich Messages, chat metadata, publishing): https://core.telegram.org/bots/api
- Telegram Mini Apps/deep links if touched: https://core.telegram.org/bots/webapps
- MAX messaging API (including media and limits): https://dev.max.ru/docs-api/methods/POST/messages
- MAX documentation and authorization: https://dev.max.ru/docs-api
- WeGoTrip Affiliate API: https://gist.github.com/4eRTuk/6b6a4b06b5f6d4ce90973e1931052991
- OpenAI API text generation/Responses: https://developers.openai.com/api/docs/guides/text/
- OpenAI API Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs/
- OpenAI API hosted web search (attribution conditions if used): https://developers.openai.com/api/docs/guides/tools-web-search/
- Official Google Trends / data-access policy and permitted Yandex Wordstat interfaces: consult actual current terms before connecting.

Implement from **real current schemas**, not stale examples copied unverified from earlier LLM responses. Store a brief `API_COMPATIBILITY_REPORT.md` showing inspected versions and any changed constraints.

---

## 20. One-shot command for Cursor

> Прочитай `WEGOTRIP_EDITORIAL_ENGINE_FINAL_CURSOR_AUTORELEASE.md` полностью. Это единый основной контракт, заменяющий предыдущие отдельные дополнения. У тебя есть разрешение самостоятельно довести реализацию до **production-релиза** с соблюдением защитных ограничений из раздела 16. Сначала проаудируй существующий код, требования, доступы и CI/CD; затем последовательно исправь все пробелы, прогони полную матрицу тестов, создай/обнови PR, выполни безопасный деплой и проверь фактический production. Не останавливайся на плане, PR или зелёном CI. Если только внешнее право/доступ делает конкретный шаг невозможным — выполни остальные и укажи ровно нужное действие владельца. Результат: действующий Editorial Engine для Telegram RU, Telegram EN и MAX RU и доказательный post-deploy отчёт по всем hard gates. Общайся со мной по-русски.

