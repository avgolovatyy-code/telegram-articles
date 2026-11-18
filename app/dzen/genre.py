"""Genre contracts: the article type, not the city, decides the structure."""

from __future__ import annotations

from dataclasses import dataclass

from app.db.enums import DzenFormat

Genre = str

GENRE_ITINERARY = "itinerary"
GENRE_CITY_GUIDE = "city_guide"
GENRE_MUSEUM = "museum"
GENRE_STORY = "story"
GENRE_HOWTO = "howto"
GENRE_NEWS = "news"
GENRE_COMPARISON = "comparison"
GENRE_INTERVIEW = "interview"
GENRE_CULTURE = "culture"

FORMAT_TO_GENRE = {
    DzenFormat.WEEKEND_ITINERARY.value: GENRE_ITINERARY,
    DzenFormat.CITY_GUIDE.value: GENRE_CITY_GUIDE,
    DzenFormat.ATTRACTION_GUIDE.value: GENRE_MUSEUM,
    DzenFormat.MUSEUM_EXHIBITION.value: GENRE_MUSEUM,
    DzenFormat.TRAVEL_HACK.value: GENRE_HOWTO,
    DzenFormat.FACT_STORY.value: GENRE_STORY,
    DzenFormat.COMPARISON.value: GENRE_COMPARISON,
    DzenFormat.FIRST_PERSON_REPORT.value: GENRE_INTERVIEW,
    DzenFormat.INTERVIEW.value: GENRE_INTERVIEW,
    DzenFormat.CULTURAL_FEATURE.value: GENRE_CULTURE,
    DzenFormat.PRODUCT_EXPLAINER.value: GENRE_HOWTO,
}


@dataclass(frozen=True, slots=True)
class GenreContract:
    genre: str
    must_contain: str
    reject_if: str
    writer_brief: str


CONTRACTS: dict[str, GenreContract] = {
    GENRE_ITINERARY: GenreContract(
        genre=GENRE_ITINERARY,
        must_contain="каждый обещанный день с местами, порядком и окнами времени",
        reject_if="пустой день или «выберите что-нибудь сами»",
        writer_brief=(
            "Это маршрут. Распиши каждый обещанный день: конкретные места, порядок, "
            "переходы, окна времени. Время аудиогида не выдавай за весь день. "
            "Религиозный объект — действующая институция, не «комната чтобы согреться»."
        ),
    ),
    GENRE_CITY_GUIDE: GenreContract(
        genre=GENRE_CITY_GUIDE,
        must_contain="подборка мест с «почему именно это» и как сгруппировать",
        reject_if="список популярных названий без открытия",
        writer_brief=(
            "Это гид по городу. У каждого места — зачем оно читателю, для кого, "
            "как добраться логично. Не пересказывай витрину достопримечательностей."
        ),
    ),
    GENRE_MUSEUM: GenreContract(
        genre=GENRE_MUSEUM,
        must_contain="конкретные залы/экспонаты/истории и как спланировать визит",
        reject_if="«посмотрите шедевры» без имён и непроверенная экспозиция",
        writer_brief=(
            "Это музейный/объектный гид. Назови конкретные залы, вещи или сюжеты. "
            "Точные часы и цены — только если они есть в досье. Иначе опусти."
        ),
    ),
    GENRE_STORY: GenreContract(
        genre=GENRE_STORY,
        must_contain="проверяемая хронология и явное разделение факта и легенды",
        reject_if="легенда как доказательство, перепутанная причинность дат",
        writer_brief=(
            "Это исторический сюжет. Даты и причины только из досье. Легенду так и "
            "называй легендой. Не пиши «после указа», если стройка началась раньше."
        ),
    ),
    GENRE_HOWTO: GenreContract(
        genre=GENRE_HOWTO,
        must_contain="проблема, проверенные условия, шаги, ограничения, дата актуальности",
        reject_if="категоричный платёжный/визовый совет без подтверждения",
        writer_brief=(
            "Это how-to. Одна проблема, шаги, ограничения. Не обещай оплату любой "
            "зарубежной покупки российской картой. Нет подтверждения — сузь формулировку."
        ),
    ),
    GENRE_NEWS: GenreContract(
        genre=GENRE_NEWS,
        must_contain="что/где/когда, статус (анонс/план/факт), источник, срок актуальности",
        reject_if="анонс как уже действующая норма без даты",
        writer_brief=(
            "Это новость. Отдели «обсуждается / объявлено / действует». Дата обязательна. "
            "Не выдавай анонс за вступивший в силу порядок."
        ),
    ),
    GENRE_COMPARISON: GenreContract(
        genre=GENRE_COMPARISON,
        must_contain="явные критерии, варианты и честные trade-offs",
        reject_if="рейтинг без критериев",
        writer_brief=(
            "Это сравнение. Сначала критерии, потом варианты, потом кому что подходит. "
            "Без произвольного «лучший город»."
        ),
    ),
    GENRE_INTERVIEW: GenreContract(
        genre=GENRE_INTERVIEW,
        must_contain="реальная запись или явное указание, что материала нет",
        reject_if="вымышленное «я приехал» без evidencе",
        writer_brief=(
            "Первое лицо и интервью запрещены без реальных заметок в досье. "
            "Если заметок нет — смени жанр, не выдумывай поездку."
        ),
    ),
    GENRE_CULTURE: GenreContract(
        genre=GENRE_CULTURE,
        must_contain="предметные факты, контекст, локальная деталь",
        reject_if="стереотип «все местные делают так»",
        writer_brief=(
            "Это культурный материал. Конкретные блюда, здания, обычаи — с контекстом. "
            "Без экзотизации и без «все местные всегда»."
        ),
    ),
}


def genre_from_format(fmt: str | None) -> str:
    if not fmt:
        return GENRE_CITY_GUIDE
    return FORMAT_TO_GENRE.get(fmt, GENRE_CITY_GUIDE)


def contract_for(genre: str | None, fmt: str | None = None) -> GenreContract:
    key = genre or genre_from_format(fmt)
    return CONTRACTS.get(key, CONTRACTS[GENRE_CITY_GUIDE])


__all__ = [
    "CONTRACTS",
    "GENRE_CITY_GUIDE",
    "GENRE_COMPARISON",
    "GENRE_CULTURE",
    "GENRE_HOWTO",
    "GENRE_INTERVIEW",
    "GENRE_ITINERARY",
    "GENRE_MUSEUM",
    "GENRE_NEWS",
    "GENRE_STORY",
    "GenreContract",
    "contract_for",
    "genre_from_format",
]
