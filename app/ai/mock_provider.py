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
    briefs: list[dict[str, Any]] = []
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
        fmt_index = index % len(formats)
        if briefs and briefs[-1]["genre"] == genres[fmt_index]:
            fmt_index = (fmt_index + 1) % len(formats)
        briefs.append(
            {
                "planned_date": day,
                "format": formats[fmt_index],
                "pillar": pillars[fmt_index],
                "audience": "russian_speaking_global",
                "destination_country": str(country)[:2].upper(),
                "destination_city": city,
                "angle": f"{city}: как провести день без гонки и без выдуманных секретов",
                "reader_value": "Практичный каркас дня и список того, что нужно сверять на месте",
                "reader_promise": f"Собрать полезный день в {city} без универсального каркаса",
                "genre": genres[fmt_index],
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


_LANDMARKS = {
    "Казань": ("Кремль", "улица Баумана", "озеро Кабан", "Старо-Татарская слобода"),
    "Стамбул": ("Галатская башня", "Каракёй", "Султанахмет", "Кадыкёй"),
    "Барселона": ("Эшампле", "Готический квартал", "Монжуик", "Борн"),
    "Париж": ("Маре", "набережная Сены", "д'Орсэ", "Пантеон"),
    "Лондон": ("Британский музей", "Саутбанк", "Блумсбери", "Сохо"),
    "Токио": ("Янака", "Уэно", "Киёсуми", "Сибуя"),
    "Нижний Новгород": ("Кремль", "Рождественская", "Стрелка", "Чкаловская лестница"),
    "Санкт-Петербург": ("Эрмитаж", "Васильевский", "Коломна", "Петропавловка"),
}

_CITY_YEAR = {
    "Казань": "1767",
    "Стамбул": "1453",
    "Барселона": "1888",
    "Париж": "1852",
    "Лондон": "1753",
    "Токио": "1923",
    "Нижний Новгород": "1515",
    "Санкт-Петербург": "1703",
}


def _city_asides(city: str, a: str, b: str, c: str, d: str) -> list[str]:
    year = _CITY_YEAR.get(city, "XIX")
    specific = {
        "Казань": [
            f"{a} в Казани стоит на мысу и прежде всего остаётся крепостью, а не "
            f"универсальной «главной площадью». {year} год у мечети аль-Марджани — "
            "дата постройки, не следствие указа 1773 года.",
            f"На {b} много витрин и вечерней подсветки; эта торговая улица не заменяет {c}. "
            "Легенду Сююмбике оставляйте легендой: гиды её любят, архив не подтверждает прыжок.",
            f"{d} даёт дворы и мечети как действующие институции, не «комнаты чтобы согреться». "
            f"Кабан ({c}) — второй берег дня, если вы уже закрыли кремлёвский мыс.",
        ],
        "Стамбул": [
            f"{a} смотрит на Золотой Рог; {year} год — падение Константинополя, "
            f"не причина каждой башни. {b} внизу работает портом и кофе, "
            "не обязательным «аутентичным кварталом».",
            f"{c} на историческом полуострове требует отдельного светового окна. "
            f"Переправа к {d} — развилка, если ноги и паром совпали, "
            "а не галочка «обязательно посетите».",
            "Аудиогид по одной линии — 1,5–2 часа ходьбы, не программа обоих берегов. "
            "Легенды района остаются фольклором.",
        ],
        "Нижний Новгород": [
            f"{a} стоит на высоком берегу; {year} год у стен — возраст кладки, "
            "не причина каждого бастиона. "
            f"{b} внизу — купеческая улица к реке, по которой удобно идти после Кремля.",
            f"{c} собирает Оку и Волгу в одну точку: это география, не «обязательная панорама». "
            f"{d} 1940-х — лестница-памятник, её не надо выдавать за весь второй день.",
            "Дальний остров или Болгары в эти два дня не влезают. "
            "Точные часы кассы здесь не названы: без даты проверки это гадание.",
        ],
        "Париж": [
            f"{a} — плотный еврейский и особняковый квартал, не «весь правый берег». "
            f"{year} год у многих фасадов указывает на возраст квартала, а не часы кассы {c}.",
            f"{b} даёт горизонталь реки; {c} на ней — бывший вокзал, превращённый в музей. "
            f"{d} на холме Латинского квартала — другая задача, не соседний зал.",
            "Оплата зарубежного билета российской картой — только если конкретный checkout "
            "это показывает. Универсального «любой билет» нет.",
        ],
        "Лондон": [
            f"{a} основан в {year} году: это возраст собрания, не расписание сегодняшнего визита. "
            f"{c} вокруг него — жилая сетка, {b} — выход к реке, {d} — другая плотность вечером.",
            "Именной зал называйте залом, а не «шедевры вообще». "
            "Споры о статусе отдельных предметов — споры, не приговор в путеводителе.",
            "Текущие выставки и дни закрытия без даты проверки не пишем. "
            "Билет WeGoTrip закрывает вход, только если это во включениях карточки.",
        ],
        "Токио": [
            f"{a} остаётся жилым храмовым склоном, а не декорацией «настоящей Японии». "
            f"{year} год — след землетрясения как фон города, не причина каждого переулка.",
            f"Рядом с {b} находятся парк и музеи; {c} — тихий сад с водой. "
            f"{d} в эту прогулку не приплетать: это другой масштаб толпы.",
            "Без обобщений «все местные делают так». Легенда района остаётся легендой.",
        ],
        "Санкт-Петербург": [
            f"Город заложили в {year} году. Это дата основания, не причина каждого фасада у {a}. "
            f"{b} — остров с кунсткамерой и биржей, другая сетка, не «тот же Эрмитаж сбоку».",
            f"{c} у канала — жилой район с легендами, которые так и надо называть легендами. "
            f"{d} на зайчике — крепость-основание, её не путать с музейным маршрутом {a}.",
            f"Сравнивать {a} с соседним музеем можно только по критериям: "
            "плотность, касса, запас часов.",
        ],
        "Барселона": [
            f"{year} год всемирной выставки — фон Монжуика, не причина каждого дома в {b}. "
            f"{a} — кварталы Эшампле с прямыми улицами, совсем не похожие на средневековый {b}.",
            f"У моря в {d} сохранились мастерские; {c} на холме — парк и виды, "
            "не «ещё один Готический». "
            "Входной билет входит, только если это во включениях выбранной карточки.",
            "Дальний Фигерас в дневной каркас города не влезает.",
        ],
    }
    fallback = [
        f"С {a} удобно начать знакомство с {city}; {year} год относится к истории места, "
        "не к часам кассы.",
        f"{b} и {c} — разные оси, их не склеивать в один круг. {d} остаётся запасом.",
        "Легенды слушайте как фольклор. Точные часы и цены без даты проверки не названы. "
        "Покупка не обязательна.",
    ]
    return specific.get(city, fallback)


def _dzen_article(context: dict[str, Any]) -> dict[str, Any]:
    city = context.get("city") or "Стамбул"
    products = context.get("products") or []
    media = context.get("media") or []
    cover = (media[0] or {}).get("id") if media else None
    product_id = str(products[0]["id"]) if products else None
    fmt = context.get("format") or "dzen_city_guide"
    a, b, c, d = _LANDMARKS.get(city, ("Центр", "Набережная", "Старый рынок", "Холм"))
    fmt_l = f"{fmt} {context.get('genre') or ''}"
    if "itinerary" in fmt_l or "weekend" in fmt_l:
        headline = f"{city} за два дня: {a}, {b} и районы в стороне от центра"
        lead = (
            f"В {city} легко попытаться обойти всё за один круг. Здесь маршрут разделён "
            f"на два дня: в первый пройдите от {a} к {b}, во второй отправляйтесь к {c} "
            f"и {d}. Если выберете аудиогид, отведите ему несколько часов, а остальное "
            "время оставьте на еду, интерьеры и остановки."
        )
        blocks = [
            _b("heading", f"День первый: {a} и {b} (утро и день)"),
            _b(
                "paragraph",
                f"Начните с {a}: это якорь {city} с XVIII–XIX века, и его лучше не оставлять "
                f"на вечерний свет. Заложите 60–90 минут, затем переход к {b} пешком, без "
                "попытки обойти весь центр. В 1767 году город уже строился в камне — даты "
                "здесь для масштаба, не как причина каждого фасада.",
            ),
            _b(
                "paragraph",
                f"{b} даёт плотный поток и короткие паузы. 40–50 минут хватит, чтобы понять "
                "ритм улицы и не застрять в сувенирах. Если есть аудиогид на 1,5–2 часа, "
                "он покрывает эту линию, а не «весь первый день»: еда, интерьеры и фото — "
                "отдельное время.",
            ),
            _b("heading", f"День второй: {c}, {d} и прогулка вдали от первого маршрута"),
            _b(
                "paragraph",
                f"Второй день не повторяет {a}. {c} показывает другой масштаб: вода, дворы, "
                f"университетский шаг. 40 минут на короткий отрезок, затем {d} как панорама "
                "на полчаса. Легенды здешних мест слушайте как фольклор, не как архив.",
            ),
            _b(
                "paragraph",
                f"Во второй день достаточно попробовать одно местное блюдо — заказывать "
                f"всё меню не нужно. Вечером можно "
                f"вернуться к подсветке {b} на пятнадцать минут и не проходить заново всю "
                f"дорогу от {a}. Так вы увидите не только открыточную часть города.",
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
            f"ниже — зачем именно эти места и чем {d} отличается как запас."
        )
        blocks = [
            _b("heading", f"{a}: с чего начать в {city}"),
            _b(
                "paragraph",
                f"Начните с {a}, чтобы без спешки рассмотреть главное место в {city}, "
                "а не потому, что так пишут все гиды. Заложите спокойный час. Год вроде "
                "1767 или 1852 относится к истории города, а не к часам работы кассы.",
            ),
            _b("heading", f"От {b} к {c} без гонки"),
            _b(
                "paragraph",
                f"На {b} обычно многолюдно, поэтому не отдавайте ей сутки. У {c} тише: "
                "рядом вода и дворы, где можно идти медленнее. Легенда района остаётся легендой.",
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
        *_city_asides(city, a, b, c, d),
        (
            f"Переход между {a} и {b} в {city} лучше закладывать диапазоном, "
            "а не точными минутами: без маршрутизатора цифра была бы выдумкой."
        ),
        (
            f"{c} в этом тексте — отдельная задача, не «ещё один {a}». "
            f"Если свет кончился, переносите {d} без чувства долга."
        ),
        (
            "Практический совет один раз: правила входа сверяйте на официальной "
            "странице места в день поездки. Здесь часов нет."
        ),
        (
            f"Истории гидов про {a} бывают ярче документов. "
            "Если нет источника — это версия, не факт."
        ),
        (
            f"Товар WeGoTrip в {city} уместен, только когда карточка про тот же объект, "
            "locale=ru, и место уже описано своими словами."
        ),
        f"Редакция не была «там лично»: это собранный гид по открытым фактам и каталогу {city}.",
        "Покупка не обязательна. Если товара нет в тексте — так и задумано.",
    ]
    blocks.append(_b("heading", f"Что в {city} не стоит выдумывать"))
    for sentence in extra:
        blocks.append(_b("paragraph", sentence))
    floor = [
        (
            f"В {city} {a} и {b} не подменяют друг друга: одно задаёт высоту, "
            "другое — поток улицы, и склеивать их в одну галочку нельзя."
        ),
        (
            f"{c} требует отдельного светового окна. {d} остаётся необязательным "
            "хвостом дня, если ноги или паром не совпали."
        ),
        (
            f"Календарный год в тексте про {city} — фон камня, не расписание кассы "
            "и не причина каждого фасада."
        ),
        (
            f"Если аудиогид в {city} есть, его длительность закрывает одну линию "
            f"у {a}, а не обе оси сразу."
        ),
    ]
    body_len = (
        len(lead)
        + len(takeaway)
        + sum(
            len(block.get("text") or "") + sum(len(item) for item in block.get("items") or [])
            for block in blocks
        )
    )
    for sentence in floor:
        if body_len >= 2600:
            break
        blocks.append(_b("paragraph", sentence))
        body_len += len(sentence)
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
