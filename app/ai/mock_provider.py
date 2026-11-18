"""Deterministic offline LLM provider.

Enable with ``LLM_PROVIDER=mock``. It returns schema-valid payloads derived from the
structured context it is given, which makes the whole pipeline — including the
Telegram renderer and the quality gates — runnable and testable without an API key or
any spend. It is a development harness, not a content generator.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.ai.pricing import approx_tokens
from app.ai.provider import Citation, LLMRequest, LLMResponse, Usage


class MockLLMProvider:
    name = "mock"

    def __init__(self, *, fail_quality: bool = False) -> None:
        self.fail_quality = fail_quality
        self.calls: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        context = _load_context(request.input)
        payload = self._payload(request, context)
        text = json.dumps(payload, ensure_ascii=False)
        usage = Usage(
            input_tokens=approx_tokens(request.instructions + request.input),
            output_tokens=approx_tokens(text),
            web_search_calls=1 if request.enable_web_search else 0,
            tool_calls=1 if request.enable_web_search else 0,
        )
        citations = (
            [Citation(url="https://example.org/official", title="Official source")]
            if request.enable_web_search
            else []
        )
        return LLMResponse(
            text=text,
            parsed=payload,
            model=request.model,
            usage=usage,
            citations=citations,
            duration_ms=1,
            raw={"mock": True},
        )

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> bytes | None:
        return None

    # ---------------------------------------------------------------- payloads
    def _payload(self, request: LLMRequest, context: dict[str, Any]) -> dict[str, Any]:
        name = request.schema_name
        if name == "article":
            return _article(context)
        if name == "quality_review":
            return _review(fail=self.fail_quality)
        if name == "claim_extraction":
            return {"claims": []}
        if name == "fact_verification":
            return {
                "results": [
                    {
                        "claim": _claim_text(item),
                        "status": "verified",
                        "corrected_statement": None,
                        "source_url": "https://www.louvre.fr/en/visit",
                        "source_title": "Official source",
                        "confidence": 0.98,
                    }
                    for item in context.get("claims", [])
                ]
            }
        if name == "editorial_decision_set":
            return _editorial_decision_set(context)
        if name == "dzen_decision_set":
            return _dzen_decision_set(context)
        if name == "dzen_article":
            return _dzen_article(context)
        if name == "dzen_critic":
            return {
                "pass_gate": not self.fail_quality,
                "quality_score": 0.0 if self.fail_quality else 0.9,
                "factuality_score": 0.0 if self.fail_quality else 0.95,
                "issues": ["mock fail"] if self.fail_quality else [],
                "rewrite_hints": [],
            }
        if name == "dzen_editorial":
            return _dzen_editorial(fail=self.fail_quality)
        if name == "dzen_research":
            return _dzen_research(context)
        if name == "dzen_outline":
            return {"sections": ["контекст", "маршрут", "ограничения"], "notes": "mock outline"}
        if name == "dzen_claims":
            return {"claims": []}
        return {}


def _editorial_decision_set(context: dict[str, Any]) -> dict[str, Any]:
    market = context.get("market", "en")
    run_date = context.get("run_date", "2026-10-28")
    candidates = context.get("candidate_signals") or []
    decisions: list[dict[str, Any]] = []
    if candidates:
        first = candidates[0]
        ru = market == "ru"
        decisions.append(
            {
                "action": "add",
                "slot_id": None,
                "candidate_id": str(first.get("id")),
                "planned_date": run_date,
                "audience": "both",
                "pillar": "weekend_ideas",
                "format": "weekend_digest",
                "editorial_mechanic": "weekend_utility",
                "audience_axis": "ru_local_leisure" if ru else "en_local",
                "channel_targets": ["telegram_ru", "max_ru"] if ru else ["telegram_en"],
                "destination_country": "RU" if ru else "FR",
                "destination_city": first.get("entity_name"),
                "angle": "Mock editorial angle for tests",
                "reader_value": "Pick a plan for the weekend",
                "hook_hypothesis": "Start with a relatable planning moment",
                "fact_ids_needed": [],
                "product_recommendation": "none",
                "source_link_policy": "internal_sources_only",
                "priority": 80,
                "why_now": "Mock run",
                "why_replace_existing": None,
                "why_worth_reading_without_purchase": "A usable weekend idea without a ticket",
                "travel_practicality_status": "not_applicable",
                "russia_demand_evidence_ids": [],
                "market_fit_reason": "local leisure",
                "needs_human_review": False,
            }
        )
    return {
        "market": market,
        "run_date": run_date,
        "editorial_thesis": "Mock thesis",
        "decisions": decisions,
        "empty_slots_justification": [] if decisions else ["No mock candidates"],
        "daily_summary": "Mock daily summary",
        "risks": [],
        "rejected_topics": [],
        "diversity_analysis": {
            "notes": "mock",
            "mechanic_mix": "weekend_utility",
            "geo_mix": "mixed",
        },
    }


def _claim_text(item: Any) -> str:
    return str(item.get("claim", "")) if isinstance(item, dict) else str(item)


def _load_context(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _article(context: dict[str, Any]) -> dict[str, Any]:
    market = context.get("market", "en")
    entity = context.get("entity", {}) or {}
    entity_name = entity.get("name") or "this destination"
    primary_query = context.get("primary_query") or entity_name
    products = context.get("products", []) or []
    media = context.get("allowed_media", []) or []
    secondary = context.get("secondary_queries", []) or []
    must_mention = [
        str(name).strip()
        for name in (context.get("must_mention_attractions") or [])
        if str(name).strip()
    ]
    if not must_mention:
        must_mention = [
            str(item.get("name") or "").strip()
            for item in (context.get("catalog_attractions") or [])
            if item.get("name")
        ]
    # Keep enough named places for the concrete-attractions quality gate.
    named_places = must_mention[:6] or [entity_name]

    sentence_case = primary_query[:1].upper() + primary_query[1:]
    places_joined = ", ".join(named_places[:4])
    if market == "ru":
        title = f"{sentence_case}: практический путеводитель"
        intro = (
            f"Коротко о главном: {primary_query}. Ниже — что успеть, сколько это занимает "
            f"и на чём не стоит терять время. Ориентир — {entity_name}. "
            f"В маршруте: {places_joined}."
        )
        headings = [
            sentence_case,
            "Маршрут на полдня",
            "Что стоит забронировать заранее",
            "Практические детали",
            "Чего можно не делать",
            "Если остался лишний час",
        ]
        body_lines = [
            "Первый заход лучше делать утром: людей меньше, свет для фотографий приятнее, "
            "и первый час обычно достаётся почти в единоличное пользование.",
            "Между точками маршрута удобно идти пешком — расстояния небольшие, а по дороге "
            "попадаются самые обычные городские сцены, ради которых сюда и едут.",
            "Если времени в обрез, выбирайте одну большую точку и две небольшие рядом: так "
            "остаётся запас и на кофе, и на то, чтобы просто посидеть и посмотреть по сторонам.",
            "Аудиоформат выручает, когда не хочется зависеть от расписания групповых экскурсий "
            "и подстраиваться под темп чужой группы.",
            "Можно остановиться там, где интересно, и спокойно пропустить то, что не цепляет — "
            "никто не подгоняет и не ждёт у выхода.",
            "Заранее решите, что важнее: охват или глубина. Совместить оба подхода за один день "
            "обычно не выходит, и попытка заканчивается усталостью.",
            "Обувь важнее плана: по брусчатке пара лишних километров ощущается совсем иначе, чем "
            "по ровному тротуару у дома.",
            "Билеты с фиксированным временем входа экономят больше нервов, чем кажется на этапе "
            "бронирования, особенно в выходные.",
            "Ближе к вечеру центр пустеет медленно, и это лучшее время для второй прогулки — "
            "уже без карты и без задачи что-то успеть.",
            "Обед стоит планировать в сторону от главной улицы: там дешевле, спокойнее и меньше "
            "меню, переведённых сразу на шесть языков.",
            "Один незапланированный поворот во двор часто даёт больше впечатлений, чем ещё одна "
            "галочка в списке обязательных мест.",
            "Заранее посмотрите, где ближайшая станция транспорта: обратная дорога всегда кажется "
            "длиннее, чем дорога туда.",
            "Возьмите с собой воду. Это звучит банально ровно до того момента, пока не окажется, "
            "что ближайшая лавка закрыта.",
            "Не стройте маршрут только по рейтингам: половина мест из топ-10 хороша именно тем, "
            "что рядом с ними есть места попроще.",
            "Если едете вдвоём, договоритесь заранее о темпе. Разный темп ломает планы надёжнее "
            "любого дождя.",
            "Дождь — не повод отменять прогулку, но повод переставить местами уличную и закрытую "
            "части маршрута.",
            "Оставьте себе право уйти раньше. Досиживать до конца из принципа — плохая стратегия "
            "в отпуске.",
            "И последнее: сохраните офлайн-карту. Связь в старых кварталах бывает капризной.",
        ]
        closing = "Сохраните маршрут — пригодится прямо на месте."
    else:
        title = f"{sentence_case.title()}: A Practical Guide"
        intro = (
            f"Short answer first: {primary_query}. Here is what to see, how long it takes "
            f"and what is worth skipping. The anchor point is {entity_name}. "
            f"On the route: {places_joined}."
        )
        headings = [
            sentence_case.title(),
            "A half-day route",
            "What to book ahead",
            "Practical details",
            "What you can skip",
            "If you have a spare hour",
        ]
        body_lines = [
            "Go early. There are fewer people, the light is better, and the first hour of the "
            "day is usually yours alone.",
            "Walking between the stops is faster than it looks on a map, and the ordinary street "
            "scenes on the way are half the reason people come here.",
            "If your time is tight, pick one big stop and two small ones nearby. That leaves room "
            "for coffee and for simply sitting still for a while.",
            "An audio format helps when you would rather not follow a group schedule or match "
            "somebody else's pace through a room.",
            "You linger where it is interesting and move on where it is not, and nobody waits for "
            "you by the exit while you finish reading a label.",
            "Decide up front whether you want coverage or depth. Trying to do both in one day "
            "rarely ends well and usually ends tired.",
            "Shoes matter more than the plan once cobblestones are involved; two extra kilometres "
            "feel very different on old paving.",
            "Timed-entry tickets save more nerves than they seem to at the booking stage, "
            "especially at weekends.",
            "The centre empties slowly towards the evening, which makes it the best window for a "
            "second walk with no map and no agenda.",
            "Plan lunch a couple of streets away from the main drag: it is cheaper, calmer, and "
            "the menu is not translated into six languages at once.",
            "One unplanned turn into a courtyard often beats ticking another must-see off a list.",
            "Check where the nearest transport stop is before you set out. The way back always "
            "feels longer than the way there.",
            "Carry water. That sounds obvious right up until the nearest shop turns out to be "
            "closed for the afternoon.",
            "Do not build the whole route from rankings: half of the top-ten places are good "
            "precisely because there is something plainer next door.",
            "If you are travelling as a pair, agree on a pace first. A mismatched pace ruins more "
            "plans than rain does.",
            "Rain is not a reason to cancel a walk, but it is a good reason to swap the outdoor "
            "and indoor halves of the route.",
            "Give yourself permission to leave early. Sitting something out on principle is a "
            "poor holiday strategy.",
            "One last thing: save an offline map. Signal in the older quarters can be moody.",
        ]
        closing = "Save the route — it is handy once you are on the ground."

    checklist = (
        [
            "Заложите на дорогу между точками 15–20 минут.",
            "Возьмите наушники — без них аудиоформат бесполезен.",
            "Проверьте заряд телефона перед выходом.",
            "Оставьте вечер свободным: планы обычно сдвигаются.",
        ]
        if market == "ru"
        else [
            "Allow 15-20 minutes of walking between stops.",
            "Bring headphones — an audio format is useless without them.",
            "Charge your phone before you head out.",
            "Keep the evening loose: plans slip more often than not.",
        ]
    )

    sections = []
    for index, heading in enumerate(headings):
        chunk = [body_lines[(index * 3 + offset) % len(body_lines)] for offset in (0, 1, 2)]
        # Weave catalogue attraction names into section copy so offline CI clears
        # the concrete-places quality gate.
        place = named_places[index % len(named_places)]
        if market == "ru":
            chunk[0] = f"{place}: {chunk[0]}"
        else:
            chunk[0] = f"{place}: {chunk[0]}"
        blocks: list[dict[str, Any]] = [
            {"type": "paragraph", "text": line, "items": [], "rows": []} for line in chunk
        ]
        if index == 1:
            blocks.append({"type": "list", "text": None, "items": checklist, "rows": []})
        sections.append({"heading": heading, "level": 2, "blocks": blocks})

    placements = []
    for index, product in enumerate(products[:3]):
        placements.append(
            {
                "product_id": str(product.get("id")),
                "placement": "compact",
                "after_section": min(index, len(sections) - 1),
                "pitch": product.get("title", "")[:120],
            }
        )

    media_placements = [
        {"media_id": str(item.get("id")), "after_section": 0, "caption": None} for item in media[:1]
    ]

    hashtags = [f"#{re.sub(r'[^0-9A-Za-zА-Яа-яЁё]', '', entity_name)}"] if entity_name else []

    # Unique FAQ answers — reusing the intro here used to trip the repeated-sentence gate.
    faq_items: list[dict[str, str]] = []
    for faq_index, question in enumerate(secondary[:2]):
        place = named_places[faq_index % len(named_places)]
        if market == "ru":
            answer = (
                f"Для «{question}» удобная точка старта — {place}. "
                f"Заложите 60–90 минут и не пытайтесь закрыть всё соседнее за один заход."
            )
        else:
            answer = (
                f"For “{question}”, a practical starting point is {place}. "
                f"Budget 60–90 minutes and resist the urge to clear every neighbour in one go."
            )
        faq_items.append({"question": question, "answer": answer})

    return {
        "title": title,
        "intro": intro,
        "sections": sections,
        "product_placements": placements,
        "media_placements": media_placements,
        "audio_placements": [],
        "faq": faq_items,
        "hashtags": hashtags,
        "claims": [],
        "closing": closing,
    }


def _review(*, fail: bool) -> dict[str, Any]:
    if fail:
        return {
            "usefulness": 0.4,
            "factuality": 0.5,
            "readability": 0.6,
            "search_intent_match": 0.4,
            "natural_language": 0.5,
            "product_relevance": 0.4,
            "spam_risk": 0.6,
            "issues": ["mock provider configured to fail the quality gate"],
        }
    return {
        "usefulness": 0.93,
        "factuality": 0.99,
        "readability": 0.92,
        "search_intent_match": 0.94,
        "natural_language": 0.93,
        "product_relevance": 0.91,
        "spam_risk": 0.02,
        "issues": [],
    }


def _dzen_decision_set(context: dict[str, Any]) -> dict[str, Any]:
    dates = context.get("needed_dates") or [context.get("run_date") or "2026-11-19"]
    cities = context.get("sample_cities") or ["Стамбул", "Казань"]
    briefs = []
    formats = [
        "dzen_city_guide",
        "dzen_travel_hack",
        "dzen_weekend_itinerary",
        "dzen_attraction_guide",
    ]
    pillars = ["city_guides", "travel_hacks", "weekend_events", "museums"]
    genres = ["city_guide", "howto", "itinerary", "museum"]
    country_by_index = ["ES", "FR", "GB", "TR", "RU"]
    for index, day in enumerate(dates[:4]):
        raw_city = cities[index % len(cities)]
        if isinstance(raw_city, dict):
            city = str(raw_city.get("name") or "Стамбул")
            country = (raw_city.get("country_id") or country_by_index[index % 5])[:2]
            if not str(country).isalpha():
                country = country_by_index[index % 5]
        else:
            city = str(raw_city)
            country = country_by_index[index % 5]
        briefs.append(
            {
                "planned_date": day,
                "format": formats[index % 2],
                "pillar": pillars[index % 2],
                "audience": "russian_speaking_global",
                "destination_country": str(country)[:2].upper(),
                "destination_city": city,
                "angle": f"{city}: как провести день без гонки и без выдуманных секретов",
                "reader_value": "Практичный каркас дня и список того, что нужно сверять на месте",
                "reader_promise": f"Собрать полезный день в {city} без универсального каркаса",
                "genre": genres[index % len(genres)],
                "why_now": "независимый слот журнала Дзена",
                "supporting_queries": [f"что посмотреть в {city}"],
                "product_recommendation": "optional",
                "factual_risk": "low",
                "intent": "independent_dzen",
            }
        )
    return {
        "run_date": str(context.get("run_date") or "2026-11-18"),
        "editorial_thesis": "Независимый русский travel-журнал, не зеркало Telegram",
        "briefs": briefs,
        "empty_slots_justification": "",
    }


def _dzen_editorial(*, fail: bool) -> dict[str, Any]:
    return {
        "decision": "revise" if fail else "accept",
        "blocking_issues": (
            [
                {
                    "code": "unsupported_claim",
                    "claim_id": None,
                    "span": "",
                    "explanation": "mock fail",
                    "proposed_fix": "rewrite",
                }
            ]
            if fail
            else []
        ),
        "non_blocking_issues": [],
        "coverage": {
            "reader_promise_met": not fail,
            "days_complete": True,
            "new_information_by_section": True,
        },
        "scores": {
            "reader_value": 0.2 if fail else 0.9,
            "originality": 0.2 if fail else 0.9,
            "specificity": 0.2 if fail else 0.9,
            "clarity": 0.2 if fail else 0.9,
            "structure": 0.2 if fail else 0.9,
            "factual_support": 0.1 if fail else 0.95,
            "commercial_naturalness": 0.8,
        },
        "evidence_ids": ["mock"],
        "prompt_version": "dzen_editorial_quality_v1",
    }


def _dzen_research(context: dict[str, Any]) -> dict[str, Any]:
    city = context.get("city") or "Стамбул"
    return {
        "article_id": str(context.get("article_id") or "mock"),
        "genre": context.get("genre") or "city_guide",
        "reader_promise": f"Понять {city} без универсального каркаса",
        "thesis_and_angle": str(context.get("headline_hint") or city),
        "facts": [],
        "unknowns_and_risks": ["не выдумывать часы работы"],
        "editorial_constraints": [],
        "product_data_discrepancies": [],
    }


def _b(kind: str, text: str | None = None, items: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": kind,
        "text": text,
        "level": 2,
        "items": items or [],
        "media_asset_id": None,
        "caption": None,
        "product_id": None,
        "after_heading": None,
    }


def _dzen_article(context: dict[str, Any]) -> dict[str, Any]:
    city = context.get("city") or "Стамбул"
    products = context.get("products") or []
    media = context.get("media") or []
    cover = (media[0] or {}).get("id") if media else None
    product_id = str(products[0]["id"]) if products else None
    fmt = context.get("format") or "dzen_city_guide"
    landmarks = {
        "Казань": ("Кремль", "улица Баумана", "озеро Кабан", "Старо-Татарская слобода"),
        "Стамбул": ("Галатская башня", "Каракёй", "Султанахмет", "Кадыкёй"),
        "Барселона": ("Эшампле", "Готический квартал", "Монжуик", "Борн"),
        "Париж": ("Маре", "набережная Сены", "д'Орсэ", "Пантеон"),
        "Лондон": ("Британский музей", "Саутбанк", "Блумсбери", "Сохо"),
        "Токио": ("Янака", "Уэно", "Киёсуми", "Сибуя"),
        "Нижний Новгород": ("Кремль", "Рождественская", "Стрелка", "Чкаловская лестница"),
        "Санкт-Петербург": ("Эрмитаж", "Васильевский", "Коломна", "Петропавловка"),
    }
    a, b, c, d = landmarks.get(city, ("Центр", "Набережная", "Старый рынок", "Холм"))
    fmt_l = str(fmt)
    if "itinerary" in fmt_l or "weekend" in fmt_l:
        headline = f"{city} за два дня: {a}, {b} и другая ось"
        lead = (
            f"В {city} легко схлопнуть всё в один круг. Этот текст разделяет два дня: "
            f"первый держит линию {a} → {b}, второй уводит к {c} и {d}. "
            "Аудиогид, если он есть, — короткий слой внутри дня, не замена программе."
        )
        blocks = [
            _b("heading", f"День первый: {a} и {b} (утро и день)"),
            _b(
                "paragraph",
                f"Начните с {a}: это якорь {city} с XVIII–XIX века, и его лучше не оставлять "
                f"на вечерний свет. Заложите 60–90 минут, затем переход к {b} пешком, без "
                "попытки закрыть весь центр. В 1767 году город уже строился в камне — даты "
                "здесь для масштаба, не как причина каждого фасада.",
            ),
            _b(
                "paragraph",
                f"{b} даёт плотный поток и короткие паузы. 40–50 минут хватит, чтобы понять "
                "ритм улицы и не застрять в сувенирах. Если есть аудиогид на 1,5–2 часа, "
                "он покрывает эту линию, а не «весь первый день»: еда, интерьеры и фото — "
                "отдельное время.",
            ),
            _b("heading", f"День второй: {c}, {d} и спокойная география"),
            _b(
                "paragraph",
                f"Второй день не повторяет {a}. {c} показывает другой масштаб: вода, дворы, "
                "университетский шаг. 40 минут на короткий отрезок, затем {d} как панорама "
                "на полчаса. Легенды здешних мест слушайте как фольклор, не как архив.",
            ),
            _b(
                "paragraph",
                f"Еду второго дня держите локальной один раз, не как экзамен. Вечером можно "
                f"вернуться к подсветке {b} на пятнадцать минут и не проходить заново всю "
                f"линию {a}. Так {city} не схлопывается в одну открытку.",
            ),
            _b("heading", "Как не сломать эти два дня"),
            _b(
                "list",
                items=[
                    f"Не добавляйте дальнюю вылазку к двум дням в {city}.",
                    "Точные часы входа сверяйте в день поездки, здесь их нет.",
                    "Аудиогид — опция внутри дня, не расписание целиком.",
                ],
            ),
        ]
        takeaway = f"День 1 — {a} и {b}. День 2 — {c} и {d}. Аудиогид не заменяет световой день."
    elif "museum" in fmt_l or "attraction" in fmt_l:
        headline = f"{a} без гонки: что успеть за визит в {city}"
        lead = (
            f"{a} легко превратить в бесконечный коридор. Здесь три опоры: один зал с "
            "именем, один маршрут без петли и одно ограничение, которое нельзя угадать "
            "по пересказу. Год основания и состав коллекции — из досье, не из памяти."
        )
        blocks = [
            _b("heading", f"Зачем ехать именно в {a}"),
            _b(
                "paragraph",
                f"{a} в {city} собирает не «шедевры вообще», а конкретную линию: "
                f"смотрите {b} как вход, затем один именной зал, связанный с {c}. "
                "В 1852 году музейные здания часто уже стояли — это масштаб, не часы кассы.",
            ),
            _b("heading", f"Как пройти {b} и не заблудиться"),
            _b(
                "paragraph",
                f"Держите петлю: {b} → именной зал → выход к {d}. Не обещаем точное время "
                "сеанса. Билет WeGoTrip, если он в тексте, закрывает вход только когда "
                "это написано во включениях карточки.",
            ),
            _b("heading", "Что нельзя выдумать"),
            _b(
                "paragraph",
                "Текущие выставки, цены и дни закрытия здесь не названы: без даты проверки "
                "это гадание. Легенда о ночном стороже остаётся легендой.",
            ),
            _b("list", items=[f"{b} как вход", "Один именной зал", f"Выход к {d}"]),
        ]
        takeaway = f"Одна петля по {a}, без выдуманных часов и без «посмотрите всё»."
    elif "hack" in fmt_l or "explainer" in fmt_l:
        headline = f"Как оплатить музей в {city} российской картой — только проверенный путь"
        lead = (
            "Универсального «любой зарубежный билет российской картой» нет. Есть конкретный "
            "сценарий: билет на WeGoTrip, оплата в рублях, если страница заказа это показывает. "
            "Ниже — шаги и ограничения на сегодняшнюю логику, без обещания на все музеи мира."
        )
        blocks = [
            _b("heading", "Какая проблема"),
            _b(
                "paragraph",
                f"Карта российского банка часто не проходит на кассе {a} в {city}. "
                "Обход — не «любой билет», а конкретный товар с оплатой у посредника, "
                "если checkout это подтверждает.",
            ),
            _b("heading", "Что сделать"),
            _b(
                "list",
                items=[
                    "Открыть карточку WeGoTrip нужного музея, locale=ru.",
                    "Проверить валюту и способ оплаты на странице заказа, не в пересказе.",
                    "Если карты нет в списке — не выдумывать обход через «любой билет».",
                ],
            ),
            _b("heading", "Ограничения"),
            _b(
                "paragraph",
                "Утверждение действует только для выбранного товара. Выставки, часы и "
                "въездные правила сюда не входят. Дата актуальности — день, когда вы "
                "смотрите checkout, а не текст статьи 2026 года как вечную норму.",
            ),
            _b(
                "paragraph",
                f"{b} и {c} здесь ни при чём: это не маршрут, а платёжный how-to. "
                "В 2024–2026 схемы оплаты менялись, поэтому без страницы заказа нет факта.",
            ),
        ]
        takeaway = "Только конкретный checkout. Никакого «любой билет российской картой»."
    elif "comparison" in fmt_l:
        headline = f"{city} или другой берег: кому какой темп"
        lead = (
            f"Сравнивать {a} и {c} по «красоте» бессмысленно. Критерии здесь простые: "
            "плотность пешком, нужна ли бронь, сколько часов без транспорта. Ниже — "
            "кому какой вариант, без рейтинга из воздуха."
        )
        blocks = [
            _b("heading", "Критерии"),
            _b(
                "paragraph",
                "Три оси: пешая плотность, плата за вход, запас по времени. Источник — "
                "каталог и очевидная география, не тайный рейтинг редакции.",
            ),
            _b("heading", f"{a} против {c}"),
            _b(
                "paragraph",
                f"{a} выигрывает, если вы уже рядом и готовы к очередям. {c} выигрывает, "
                f"если нужен воздух и {d} как пауза. {b} — переход, не третья столица.",
            ),
            _b("heading", "Кому что"),
            _b(
                "list",
                items=[
                    f"Короткий слот — {a}.",
                    f"День без кассы — {c} и {d}.",
                    "С детьми не тащите оба якоря подряд.",
                ],
            ),
            _b(
                "paragraph",
                f"В {city} в 1703 или 1852 году якоря уже стояли по-разному — это фон, "
                "не аргумент «кто лучше». Trade-off честный: плотность против воздуха.",
            ),
        ]
        takeaway = f"{a} — плотность. {c} — воздух. Рейтинга нет."
    elif "fact_story" in fmt_l or "cultural" in fmt_l:
        headline = f"Как {a} в {city} стал легендой — и что из этого факт"
        lead = (
            f"Про {a} в {city} рассказывают охотно, и часть историй правда. "
            f"Ниже отделяем документ от фольклора: дата, связанная с {b}, "
            f"легенда у {c}, и почему {d} сюда не приплетать."
        )
        blocks = [
            _b("heading", f"Что известно про {a}"),
            _b(
                "paragraph",
                f"Документированная линия: {a} связан с {city} не позже XIX века. "
                "В 1852 году это уже городская ткань. Точный указ-причина здесь не выдуман.",
            ),
            _b("heading", f"Легенда у {c}"),
            _b(
                "paragraph",
                f"История про {c} остаётся легендой: гиды её любят, архив не подтверждает. "
                f"{b} в этом сюжете только сосед, не доказательство.",
            ),
            _b("heading", "Чего нельзя утверждать"),
            _b(
                "paragraph",
                f"{d} не «первый в мире» без источника. Версии помечаем как версии. "
                "Личного «я там был» нет.",
            ),
        ]
        takeaway = f"Факт про {a} отдельно, легенда про {c} отдельно."
    else:
        headline = f"{city} без спешки: {a}, {b} и то, что обычно пропускают"
        lead = (
            f"Если {city} кажется набором обязательных точек, соберите день вокруг {a} "
            f"и {b}, а {c} оставьте светлому часу. Это не универсальный «музей-кафе-прогулка»: "
            "ниже — зачем именно эти места и чем {d} отличается как запас."
        )
        blocks = [
            _b("heading", f"{a}: с чего начать в {city}"),
            _b(
                "paragraph",
                f"{a} стоит первым, потому что задаёт масштаб {city}, а не потому что так "
                "пишут все гиды. Заложите спокойный час. Год вроде 1767 или 1852 здесь "
                "про возраст ткани города, не про кассу.",
            ),
            _b("heading", f"От {b} к {c} без гонки"),
            _b(
                "paragraph",
                f"{b} — плотная ось. Не отдавайте ей сутки. Переход к {c} меняет скорость: "
                "вода, дворы, другой шаг. Легенда района остаётся легендой.",
            ),
            _b("heading", f"{d} как запас, не как галочка"),
            _b(
                "paragraph",
                f"{d} имеет смысл, если свет и ноги ещё есть. Это не «обязательно посетите», "
                "а развилка. Аудиогид WeGoTrip — опция рядом с местом, которое вы уже описали.",
            ),
            _b(
                "list",
                items=[
                    f"Утро — {a}.",
                    f"{b} коротко, без сувенирной ямы.",
                    f"{c} на свет, {d} по остатку сил.",
                ],
            ),
        ]
        takeaway = f"{a} утром, {b} коротко, {c} на свет. Без выдуманных часов."

    if len(lead) < 210:
        lead = (
            lead + " Читатель получает конкретный порядок мест и одно ограничение, "
            "которое нельзя угадать по пересказу."
        )
    extra = [
        f"{city}: {a} в разные годы звучал по-разному, и это видно по кладке, не по слогану.",
        f"Отдельный факт про {b}: поток туристов не отменяет жилой ткани вокруг.",
        f"{c} чаще фотографируют издалека; подойти имеет смысл, только если это ваш темп.",
        f"{d} в {city} работает как пауза, а не как третья обязательная касса.",
        "Редакция не была «там лично»: это собранный гид по открытым фактам и каталогу.",
        "Покупка не обязательна. Если товара нет в тексте — так и задумано.",
    ]
    for sentence in extra:
        blocks.append(_b("paragraph", sentence))
    flavors = (
        "купеческий",
        "ярмарочный",
        "университетский",
        "набережный",
        "крепостной",
        "трамвайный",
        "монастырский",
        "театральный",
        "аптечный",
        "садовый",
        "рыночный",
        "портовый",
    )
    pad = 0
    while sum(len(block.get("text") or "") for block in blocks) + len(lead) < 2600:
        flavor = flavors[pad % len(flavors)]
        pad += 1
        blocks.append(
            _b(
                "paragraph",
                f"{flavor.capitalize()} слой {pad} в {city}: {a} рядом с {flavor} тканью, "
                f"{b} звучит иначе, {c} держит паузу, {d} остаётся развилкой номер {pad}.",
            )
        )
        if pad > 12:
            break
    if product_id:
        blocks.append(_b("product_mention"))
        blocks[-1]["product_id"] = product_id
    return {
        "headline": headline,
        "lead": lead,
        "format": fmt,
        "pillar": context.get("pillar") or "city_guides",
        "audience": "russian_speaking_global",
        "destination_country": context.get("country"),
        "destination_city": city,
        "blocks": blocks,
        "cover_media_asset_id": cover,
        "product_ids": [str(p.get("id")) for p in products[:3]],
        "practical_takeaway": takeaway,
        "claims": [],
        "reader_value": "Польза читателя без обязательной покупки",
        "originality_angle": "Жанровый контракт, не универсальный каркас",
    }


__all__ = ["MockLLMProvider"]
