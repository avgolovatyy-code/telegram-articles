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
                        "claim": claim,
                        "status": "verified",
                        "corrected_statement": None,
                        "source_url": "https://example.org/official",
                        "source_title": "Official source",
                        "confidence": 0.98,
                    }
                    for claim in context.get("claims", [])
                ]
            }
        return {}


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

    sentence_case = primary_query[:1].upper() + primary_query[1:]
    if market == "ru":
        title = f"{sentence_case}: практический путеводитель"
        intro = (
            f"Коротко о главном: {primary_query}. Ниже — что успеть, сколько это занимает "
            f"и на чём не стоит терять время. Ориентир — {entity_name}."
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
            f"and what is worth skipping. The anchor point is {entity_name}."
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
                "placement": "hero" if index == 0 else "compact",
                "after_section": min(index, len(sections) - 1),
                "pitch": product.get("title", "")[:120],
            }
        )

    media_placements = [
        {"media_id": str(item.get("id")), "after_section": 0, "caption": None} for item in media[:1]
    ]

    hashtags = [f"#{re.sub(r'[^0-9A-Za-zА-Яа-яЁё]', '', entity_name)}"] if entity_name else []

    return {
        "title": title,
        "intro": intro,
        "sections": sections,
        "product_placements": placements,
        "media_placements": media_placements,
        "audio_placements": [],
        "faq": [{"question": q, "answer": f"{q} — {intro}"} for q in secondary[:2]],
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


__all__ = ["MockLLMProvider"]
