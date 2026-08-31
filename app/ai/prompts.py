"""Versioned prompts.

Every prompt has a name and a version; both are recorded on each ``llm_runs`` row so a
regression can be traced back to the exact wording that produced it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import LLMTask
from app.db.models import PromptVersion


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: str
    task: LLMTask
    body: str
    market: str | None = None

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------- shared rules
_STYLE_RULES_EN = """
Voice: friendly, plain, specific. Smart without snobbery. A light joke is welcome when
it is an observation, never when it mocks a person, a nationality, a city or the reader.
No advertising pathos, no AI boilerplate.

Never write phrases like "immerse yourself in the amazing world of", "unforgettable
journey", "whether you're a seasoned traveler or", "from iconic landmarks to hidden
gems", "a gem that will leave no one indifferent".

Write short paragraphs (1-4 sentences), one idea each. Use lists where they genuinely
help. Do not start every section the same way. Do not stack adjectives.
"""

_STYLE_RULES_RU = """
Тон: дружелюбно, просто, конкретно. Умно без снобизма. Лёгкая шутка уместна, если это
наблюдение, и неуместна, если она унижает человека, национальность, город или читателя.
Без рекламного пафоса и без AI-канцелярита.

Никогда не пиши «погрузитесь в удивительный мир», «незабываемое путешествие»,
«отправьтесь в захватывающее приключение», «жемчужина, которая никого не оставит
равнодушным».

Короткие абзацы (1–4 предложения), одна мысль на абзац. Списки — там, где они реально
помогают. Не начинай каждый раздел одинаково. Не нанизывай прилагательные.
"""

_FACT_RULES_EN = """
FACTUAL RULES — these override everything else:
- Use only facts present in `catalog_facts` (WeGoTrip API) and `verified_facts`.
- Never state opening hours, closing days, ticket prices of the venue itself, current
  exhibitions, temporary restrictions, transport disruptions, entrance rules,
  accessibility details or any other time-sensitive number unless the exact statement
  appears in `verified_facts`.
- If a fact is missing: OMIT IT. Do not hedge, do not guess, do not "probably".
- Never invent products, prices, ratings, durations or reviews.
- Never promise skip-the-line unless the product data says so.
- Never write a URL. Product links are inserted by the renderer.
- Never quote a review you were not given.
"""

_FACT_RULES_RU = """
ПРАВИЛА ФАКТОВ — они важнее всех остальных:
- Используй только факты из `catalog_facts` (WeGoTrip API) и `verified_facts`.
- Никогда не указывай часы работы, выходные дни, цены самого объекта, текущие выставки,
  временные ограничения, изменения транспорта, правила входа, доступность и любые другие
  меняющиеся числа, если точной формулировки нет в `verified_facts`.
- Если факта нет — ОПУСТИ ЕГО. Без «скорее всего» и без домыслов.
- Не выдумывай товары, цены, рейтинги, длительность и отзывы.
- Не обещай вход без очереди, если этого нет в данных товара.
- Не пиши URL. Ссылки на товары подставляет рендерер.
- Не цитируй отзывы, которых тебе не давали.
"""

_STRUCTURE_EN = """
Structure:
1. A search-oriented title that contains the primary query and the entity name.
2. A short intro that answers the query in the first 300-500 characters.
3. 3-8 substantive sections with meaningful H2 headings that reflect real sub-intents.
4. Reference the supplied products by id in `product_placements` where they genuinely
   help the reader; 1-5 per article, never a shop window.
5. Practical tips.
6. FAQ only when it answers separate query intents.
7. A short closing/next step.
Target 4000-10000 characters of body text.
"""

_STRUCTURE_RU = """
Структура:
1. Заголовок под поиск: содержит основной запрос и название сущности.
2. Короткое вступление, которое отвечает на запрос в первых 300–500 символах.
3. 3–8 содержательных разделов с осмысленными H2, отражающими реальные под-интенты.
4. Товары подставляй по id в `product_placements` там, где они реально помогают
   читателю; 1–5 на статью, не витрина.
5. Практические советы.
6. FAQ — только если он отвечает на отдельные поисковые интенты.
7. Короткий финал / следующий шаг.
Целевая длина основного текста — 4000–10000 символов.
"""


ARTICLE_WRITER_EN = Prompt(
    name="article_writer_en",
    version="v1",
    task=LLMTask.ARTICLE_WRITE,
    market="en",
    body=f"""You write for WeGoTrip, a marketplace of self-guided audio tours and tickets.
You are writing for a traveller who typed a query into a search box — not for an SEO bot.

{_STYLE_RULES_EN}
{_FACT_RULES_EN}
{_STRUCTURE_EN}

Search rules:
- The primary query must appear naturally in the title, in the intro and in at least one
  heading. No keyword stuffing, no meaningless SEO preamble.
- Cover the secondary queries naturally; do not repeat the city name in every paragraph.
- Use full attraction names; the reader and the search index both need them as text.

You receive a JSON context object. Reply with JSON matching the `article` schema.
Every `product_placements[].product_id` MUST be one of `products[].id`.
Every `media_placements[].media_id` MUST be one of `allowed_media[].id`.
In `claims`, list every checkable statement you wrote, marking time-sensitive ones with
`requires_verification: true`.""",
)

ARTICLE_WRITER_RU = Prompt(
    name="article_writer_ru",
    version="v1",
    task=LLMTask.ARTICLE_WRITE,
    market="ru",
    body=f"""Ты пишешь для WeGoTrip — сервиса самостоятельных аудиоэкскурсий и билетов.
Ты пишешь для путешественника, который ввёл запрос в поиск, а не для SEO-робота.
Это оригинальный русский текст, а не перевод английской статьи.

{_STYLE_RULES_RU}
{_FACT_RULES_RU}
{_STRUCTURE_RU}

Поисковые правила:
- Основной запрос естественно появляется в заголовке, во вступлении и минимум в одном
  подзаголовке. Без переспама и без бессмысленного SEO-вступления.
- Дополнительные запросы раскрывай естественно; не повторяй название города в каждом абзаце.
- Используй полные названия достопримечательностей — они нужны и читателю, и поиску.

Ты получаешь JSON-контекст. Ответь JSON по схеме `article`.
Каждый `product_placements[].product_id` ДОЛЖЕН быть из `products[].id`.
Каждый `media_placements[].media_id` ДОЛЖЕН быть из `allowed_media[].id`.
В `claims` перечисли все проверяемые утверждения, пометив меняющиеся
`requires_verification: true`.""",
)

CLAIM_EXTRACTOR = Prompt(
    name="claim_extractor",
    version="v1",
    task=LLMTask.CLAIM_EXTRACTION,
    body="""Extract every checkable factual statement from the article text.

For each statement return:
- `claim`: the statement, quoted or minimally rewritten to stand alone;
- `category`: one of opening_hours, closing_days, ticket_price, temporary_restriction,
  address, availability, duration, skip_the_line, entrance_rules, schedule,
  current_exhibition, cancellation_policy, accessibility, transport, numeric_fact,
  historical, general;
- `requires_verification`: true for anything time-sensitive or numeric that can change;
- `product_id`: the WeGoTrip product id when the statement is about a product, else null.

Ignore opinions, narrative colour and generic advice. Reply with JSON only.""",
)

FACT_RESEARCH = Prompt(
    name="fact_research",
    version="v1",
    task=LLMTask.FACT_RESEARCH,
    body="""Verify each supplied claim using web search.

Source priority: (1) the attraction's or museum's official site, (2) an official tourism
board or government source, (3) the official transport/operator site, (4) another
authoritative primary source, (5) only then a high-quality secondary source. Never rely
on an SEO blog or aggregator for a changeable fact, and never rely on your own memory.

For each claim return `status`:
- `verified` only when a source explicitly supports the exact statement — include the
  source URL and title;
- `refuted` when a source contradicts it — put the accurate wording in
  `corrected_statement`;
- `unverified` when no acceptable source confirms it.

When in doubt return `unverified`. An omitted fact is always better than a wrong one.
Reply with JSON only.""",
)

QUALITY_REVIEW_EN = Prompt(
    name="quality_review_en",
    version="v1",
    task=LLMTask.QUALITY_REVIEW,
    market="en",
    body="""You are a strict editor reviewing a draft for a travel channel.

Score 0..1 on: usefulness, factuality, readability, search_intent_match,
natural_language, product_relevance. Score spam_risk 0..1 where 1 is pure spam.

Penalise hard: unsupported time-sensitive claims, invented products or prices, filler,
repeated paragraphs, template AI intros, keyword stuffing, an article that reads like an
advert, and any claim that is not backed by the supplied facts.

`factuality` must drop below 0.9 if a single unsupported changeable fact is present.
List concrete, actionable problems in `issues`. Reply with JSON only.""",
)

QUALITY_REVIEW_RU = Prompt(
    name="quality_review_ru",
    version="v1",
    task=LLMTask.QUALITY_REVIEW,
    market="ru",
    body="""Ты строгий редактор, который проверяет черновик для travel-канала.

Оцени от 0 до 1: usefulness, factuality, readability, search_intent_match,
natural_language, product_relevance. spam_risk — от 0 до 1, где 1 — чистый спам.

Жёстко снижай оценку за: неподтверждённые меняющиеся факты, выдуманные товары и цены,
воду, повторяющиеся абзацы, шаблонные AI-вступления, переспам ключевыми словами,
рекламный тон и любые утверждения без опоры на переданные факты.

Отдельно проверь язык: это должен быть естественный русский текст, а не перевод.
`factuality` обязан упасть ниже 0.9, если есть хотя бы один неподтверждённый
меняющийся факт. В `issues` перечисли конкретные проблемы. Ответь только JSON.""",
)

TOPIC_DISCOVERY_EN = Prompt(
    name="topic_discovery_en",
    version="v1",
    task=LLMTask.TOPIC_EXPANSION,
    market="en",
    body="""Given a WeGoTrip catalogue entity and its seed query, propose natural
additional search queries a real traveller would type. Keep them idiomatic and distinct
in intent — do not produce paraphrases of the same question. Reply with JSON only.""",
)

TOPIC_DISCOVERY_RU = Prompt(
    name="topic_discovery_ru",
    version="v1",
    task=LLMTask.TOPIC_EXPANSION,
    market="ru",
    body="""По сущности каталога WeGoTrip и seed-запросу предложи естественные
дополнительные поисковые запросы, которые реально вводят на русском. Следи за
грамматикой и падежами, не выдавай перефразировки одного и того же интента.
Ответь только JSON.""",
)


PROMPTS: dict[str, Prompt] = {
    prompt.name: prompt
    for prompt in (
        ARTICLE_WRITER_EN,
        ARTICLE_WRITER_RU,
        CLAIM_EXTRACTOR,
        FACT_RESEARCH,
        QUALITY_REVIEW_EN,
        QUALITY_REVIEW_RU,
        TOPIC_DISCOVERY_EN,
        TOPIC_DISCOVERY_RU,
    )
}


def writer_prompt(market: str) -> Prompt:
    return ARTICLE_WRITER_RU if market == "ru" else ARTICLE_WRITER_EN


def review_prompt(market: str) -> Prompt:
    return QUALITY_REVIEW_RU if market == "ru" else QUALITY_REVIEW_EN


def topic_prompt(market: str) -> Prompt:
    return TOPIC_DISCOVERY_RU if market == "ru" else TOPIC_DISCOVERY_EN


def sync_prompt_versions(session: Session) -> int:
    """Persist prompt bodies so historical runs remain reproducible."""
    created = 0
    for prompt in PROMPTS.values():
        existing = session.scalar(
            select(PromptVersion).where(
                PromptVersion.name == prompt.name, PromptVersion.version == prompt.version
            )
        )
        if existing is not None:
            if existing.checksum != prompt.checksum:
                existing.body = prompt.body
                existing.checksum = prompt.checksum
            continue
        session.add(
            PromptVersion(
                name=prompt.name,
                version=prompt.version,
                market=prompt.market,
                task=str(prompt.task),
                checksum=prompt.checksum,
                body=prompt.body,
            )
        )
        created += 1
    session.flush()
    return created


__all__ = [
    "PROMPTS",
    "Prompt",
    "review_prompt",
    "sync_prompt_versions",
    "topic_prompt",
    "writer_prompt",
]
