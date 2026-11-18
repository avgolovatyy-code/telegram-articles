"""Universal Dzen editorial quality: 12 scenarios, negatives, four sample kits."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from app.ai.mock_provider import _dzen_article
from app.dzen.chronology import chronology_conflicts, venue_framing_issues
from app.dzen.editorial import evaluate_editorial
from app.dzen.editorial_ast import kazan_winter_weekend_ast
from app.dzen.genre import contract_for, genre_from_format
from app.dzen.itinerary import itinerary_issues, promised_days
from app.dzen.kit import clipboard_html
from app.dzen.planner import plan_dzen_week
from app.dzen.portfolio import portfolio_report
from app.dzen.products import DzenProductPick
from app.dzen.quality import body_text, run_gates
from app.dzen.redundancy import redundancy_report
from app.dzen.schemas import DzenArticleAST, DzenBlock

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "audit/dzen_quality/samples"
SCENARIOS = ROOT / "audit/dzen_quality/scenarios.json"


def _product(**overrides: object) -> DzenProductPick:
    payload = {
        "external_id": "1526",
        "title": "Городские легенды Казани",
        "slug": "legendy",
        "affiliate_url": (
            "https://wegotrip.ru/kazan-d551487/gorodskie-legendy-kazani-p1526/"
            "?coupon=435&utm_source=dzen&utm_medium=editorial&utm_campaign=dzen_ru"
        ),
        "inclusions": ["аудиогид"],
        "exclusions": [],
        "ticket_included": False,
        "cover": None,
        "city_name": "Казань",
        "snapshot": {},
        "is_free": True,
        "duration_label": "1,5–2 часа",
        "distance_label": "4 км",
        "listen_in_browser": False,
        "playback_discrepancy": True,
        "locale": "ru",
        "reader_pitch": (
            "Городские легенды Казани — бесплатная аудиоэкскурсия, 1,5–2 часа, маршрут около 4 км"
        ),
    }
    payload.update(overrides)
    return DzenProductPick(**payload)  # type: ignore[arg-type]


_FILL_SEQ = 0
_FLAVORS = (
    "купеческий",
    "ярмарочный",
    "университетский",
    "набережный",
    "крепостной",
    "трамвайный",
    "монастырский",
    "театральный",
)


def _fill(*places: str, city: str = "Казань", tag: str | None = None) -> str:
    global _FILL_SEQ
    _FILL_SEQ += 1
    flavor = tag or _FLAVORS[_FILL_SEQ % len(_FLAVORS)]
    lines = []
    for index, place in enumerate(places):
        neighbor = places[(index + 1) % len(places)]
        lines.append(
            f"{city} {flavor}-{index}: {place} раскрывается иначе, чем {neighbor}. "
            f"Легенда {place} остаётся фольклором, не архивом. "
            f"Год {1810 + _FILL_SEQ + index} задаёт возраст камня, не часы кассы. "
            f"Отдельный сюжет {flavor} про {place} не повторяет соседний абзац."
        )
        lines.append(
            f"Практика {flavor} {index}: к {place} идут пешком, без выдуманных минут, "
            f"и не путают {neighbor} с обязательной кассой."
        )
        lines.append(
            f"Контекст {flavor} {index}: {place} в {city} читается деталью, "
            f"а не слоганом. {neighbor} остаётся соседней осью."
        )
    return " ".join(lines)


def _ast(
    *, headline: str, city: str, fmt: str, headings: list[str], paras: list[str]
) -> DzenArticleAST:
    blocks: list[DzenBlock] = []
    for heading, para in zip(headings, paras, strict=False):
        blocks.append(DzenBlock(type="heading", text=heading))
        blocks.append(DzenBlock(type="paragraph", text=para))
    while len([b for b in blocks if b.type == "heading"]) < 3:
        blocks.append(DzenBlock(type="heading", text=f"Ещё про {city}"))
        blocks.append(
            DzenBlock(
                type="paragraph", text=_fill("Кремль", "Баумана", "Кабан", "Слобода", city=city)
            )
        )
    lead = (
        f"{headline}. Текст обещает конкретную пользу в {city}, а не каркас "
        "«музей-кафе-прогулка», и держит одно ограничение без выдуманных часов."
    )
    if len(lead) < 200:
        lead += " Читатель узнаёт порядок мест и что нельзя утверждать без источника."
    return DzenArticleAST(
        headline=headline,
        lead=lead[:500],
        format=fmt,
        pillar="city_guides",
        audience="russian_speaking_global",
        destination_city=city,
        blocks=blocks,
        practical_takeaway="Сверяйте правила входа в день поездки. Покупка не обязательна.",
    )


def _gates(ast: DzenArticleAST, product: DzenProductPick | None = None):
    products = [] if product is None else [product]
    return run_gates(
        ast,
        products=products,
        image_urls=["https://cdn.example/a.jpg"],
        cover_url="https://cdn.example/a.jpg",
    )


def _decision(ast: DzenArticleAST, product: DzenProductPick | None = None) -> str:
    products = [] if product is None else [product]
    return evaluate_editorial(
        ast,
        products=products,
        image_urls=["https://cdn.example/a.jpg"],
        cover_url="https://cdn.example/a.jpg",
    ).decision


def test_kazan_itinerary_regression_passes_after_factual_fixes():
    ast = kazan_winter_weekend_ast()
    text = body_text(ast)
    assert promised_days(ast.headline) == 2
    assert not chronology_conflicts(text)
    assert not venue_framing_issues(text)
    assert not any("route_infeasible" in item for item in itinerary_issues(ast, [_product()]))
    assert "ставить не обязательно" not in text
    assert "это и есть весь первый день" not in text.casefold()
    result = _gates(ast, _product(listen_in_browser=False, playback_discrepancy=True))
    assert result.ok, result.issues
    assert _decision(ast, _product(listen_in_browser=False, playback_discrepancy=True)) == "accept"


def test_barcelona_museum_ticket_inclusion_and_ru_locale():
    ast = _ast(
        headline="Пикассо в Барселоне: три зала без гонки и без выдуманной кассы",
        city="Барселона",
        fmt="dzen_attraction_guide",
        headings=[
            "Зачем именно музей Пикассо",
            "Готический квартал как вход",
            "Что нельзя выдумать про билет",
        ],
        paras=[
            _fill("Пикассо", "Борн", "Раваль", "Монжуик", city="Барселона")
            + " В 1963 году музей уже собирал линию, это масштаб, не часы кассы.",
            _fill("Готический", "Эшампле", "Пикассо", "Борн", city="Барселона"),
            "Входной билет входит, только если это во включениях. Легенда района — легенда.",
        ],
    )
    product = _product(
        external_id="9001",
        title="Музей Пикассо: аудиогид",
        city_name="Барселона",
        ticket_included=True,
        is_free=False,
        listen_in_browser=False,
        playback_discrepancy=False,
        locale="ru",
        duration_label="1 ч",
        distance_label=None,
        reader_pitch="Музей Пикассо: аудиогид, 1 ч",
    )
    result = _gates(ast, product)
    assert result.ok, result.issues


def test_paris_culture_no_false_travel_ban():
    ast = _ast(
        headline="Маре в Париже: еврейский квартал без запрета «из России нельзя»",
        city="Париж",
        fmt="dzen_cultural_feature",
        headings=["Почему Маре", "д'Орсэ как сосед", "Что не выдумывать про въезд"],
        paras=[
            _fill("Маре", "Сена", "Пантеон", "Орсэ", city="Париж"),
            _fill("Орсэ", "Маре", "Лувр", "Пантеон", city="Париж"),
            "Правила въезда не названы: без даты проверки это гадание. Легенда остаётся легендой.",
        ],
    )
    assert "нельзя" not in body_text(ast).split("въезд")[0][-40:]
    result = _gates(ast)
    assert result.ok, result.issues


def test_istanbul_season_not_replaced_by_audio():
    ast = _ast(
        headline="Стамбул за два дня: Каракёй, Султанахмет и другая ось",
        city="Стамбул",
        fmt="dzen_weekend_itinerary",
        headings=[
            "День первый: Каракёй и Галатская башня",
            "День второй: Султанахмет и Кадыкёй",
            "Аудиогид — слой, не весь день",
        ],
        paras=[
            _fill("Каракёй", "Галата", "Пера", "Золотой", city="Стамбул"),
            _fill("Султанахмет", "Кадыкёй", "Босфор", "Галата", city="Стамбул"),
            "Аудиогид на 1,5–2 часа — одна линия, а не весь первый день. Легенда — фольклор.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues
    assert not any("route_infeasible" in item for item in itinerary_issues(ast))


def test_tokyo_culture_without_exotic_cliche():
    ast = _ast(
        headline="Янака в Токио: тихий храмовый склон без экзотизации",
        city="Токио",
        fmt="dzen_cultural_feature",
        headings=["Янака как жилая ткань", "Уэно рядом", "Киёсуми как пауза"],
        paras=[
            _fill("Янака", "Уэно", "Киёсуми", "Сибуя", city="Токио"),
            _fill("Уэно", "Янака", "Асакуса", "Киёсуми", city="Токио"),
            "Без экзотизации и без обобщений про жителей. Легенда района — легенда. 1923 год.",
        ],
    )
    assert "все местные" not in body_text(ast)
    result = _gates(ast)
    assert result.ok, result.issues


def test_nizhny_weekend_both_days_named():
    ast = _ast(
        headline="Нижний Новгород за два дня: Кремль, Стрелка и Рождественская",
        city="Нижний Новгород",
        fmt="dzen_weekend_itinerary",
        headings=[
            "День первый: Кремль и Рождественская",
            "День второй: Стрелка и Чкаловская лестница",
            "Как не сломать два дня",
        ],
        paras=[
            _fill("Кремль", "Рождественская", "Покровка", "Болгары", city="Нижний Новгород"),
            _fill("Стрелка", "Чкаловская", "Казанская", "Кремль", city="Нижний Новгород"),
            "Переходы пешком, без выдуманных минут. Легенда Стрелки — легенда.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_london_museum_rules_need_asof_or_omission():
    ast = _ast(
        headline="Британский музей без гонки: три опоры и никаких выдуманных часов",
        city="Лондон",
        fmt="dzen_museum_exhibition",
        headings=["Зачем Британский музей", "Саутбанк как выход", "Что нельзя выдумать"],
        paras=[
            _fill("Британский", "Блумсбери", "Сохо", "Саутбанк", city="Лондон"),
            _fill("Саутбанк", "Блумсбери", "Темза", "Сохо", city="Лондон"),
            "Выставки и часы не названы. Легенда Эльгина — спор, не приговор. 1753 — основание.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_spb_architecture_story_verified_year():
    ast = _ast(
        headline="Коломна в Петербурге: петровский след без путаницы дат",
        city="Санкт-Петербург",
        fmt="dzen_fact_story",
        headings=["Что известно про Коломну", "Васильевский рядом", "Легенда отдельно"],
        paras=[
            _fill("Коломна", "Васильевский", "Эрмитаж", "Петропавловка", city="Санкт-Петербург")
            + " Город заложили в 1703 году. Это дата основания, не причина каждого фасада.",
            _fill("Эрмитаж", "Коломна", "Мойка", "Васильевский", city="Санкт-Петербург"),
            "Легенду Медного всадника слушайте как легенду. Документ и фольклор не путаем.",
        ],
    )
    assert not chronology_conflicts(body_text(ast))
    result = _gates(ast)
    assert result.ok, result.issues


def test_payment_howto_scoped_not_universal():
    ast = _ast(
        headline="Как оплатить музей в Париже российской картой — только проверенный путь",
        city="Париж",
        fmt="dzen_travel_hack",
        headings=["Какая проблема", "Что сделать", "Ограничения"],
        paras=[
            _fill("Лувр", "Орсэ", "Маре", "Сена", city="Париж")
            + " Обход — не любой билет, а конкретный checkout WeGoTrip.",
            " ".join(
                f"Шаг {index} в Париже: валюту и карту смотрят на странице заказа {index}, "
                "не в пересказе гида."
                for index in range(1, 7)
            ),
            " ".join(
                f"Ограничение {index}: утверждение не шире выбранного товара {index} "
                "и не живёт дольше дня checkout."
                for index in range(1, 7)
            ),
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_news_status_is_announced_not_in_force():
    ast = _ast(
        headline="Виза в Британию: что объявлено, а что ещё не действует",
        city="Лондон",
        fmt="dzen_fact_story",
        headings=["Что объявили", "Что ещё обсуждается", "Как не перепутать статус"],
        paras=[
            _fill("Вестминстер", "Саутбанк", "Сохо", "Блумсбери", city="Лондон")
            + " На 18.11.2026 это объявление, не вступившая норма.",
            _fill("Темза", "Вестминстер", "Камден", "Сохо", city="Лондон"),
            "Статус: объявлено. Не пишем «уже действует». Легенда очередей — не закон.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_comparison_has_criteria():
    ast = _ast(
        headline="Эрмитаж или Русский музей: кому какой темп в Петербурге",
        city="Санкт-Петербург",
        fmt="dzen_comparison",
        headings=["Критерии", "Эрмитаж против Русского", "Кому что"],
        paras=[
            _fill("Эрмитаж", "Русский", "Невский", "Мойка", city="Санкт-Петербург")
            + " Три оси: плотность, касса, запас по времени.",
            _fill("Русский", "Эрмитаж", "Коломна", "Васильевский", city="Санкт-Петербург"),
            "Короткий слот — одна петля. День без кассы — набережная. Рейтинга нет. 1764 — фон.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_legend_separated_from_document():
    ast = _ast(
        headline="Сююмбике в Казани: легенда прыжка и то, что известно иначе",
        city="Казань",
        fmt="dzen_fact_story",
        headings=["Что говорит легенда", "Что не подтверждают историки", "Башня как место"],
        paras=[
            _fill("Сююмбике", "Кремль", "Казанка", "Слобода", city="Казань")
            + " Это легенда, не архивная справка.",
            _fill("Кремль", "Сююмбике", "Баумана", "Кабан", city="Казань"),
            "Историки легенду не подтверждают. Смотровая щель объясняет, почему её рассказывают.",
        ],
    )
    result = _gates(ast)
    assert result.ok, result.issues


def test_negative_hollow_day_is_hard_fail():
    ast = _ast(
        headline="Барселона за два дня: готовый маршрут без спешки",
        city="Барселона",
        fmt="dzen_weekend_itinerary",
        headings=[
            "День первый: Готический квартал и Борн",
            "День второй: как получится",
            "Короткий список",
        ],
        paras=[
            _fill("Готический", "Борн", "Эшампле", "Монжуик", city="Барселона"),
            "Выберите что-нибудь тёплое и спокойное.",
            _fill("Монжуик", "Борн", "Раваль", "Эшампле", city="Барселона"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("headline_promise_gap" in item or "day 2" in item for item in result.issues)


def test_negative_chronology_conflict():
    text = (
        "Храм заложили в 1767 году после указа 1773 года о веротерпимости, "
        "строительство стало следствием этого указа."
    )
    assert chronology_conflicts(text)


def test_negative_audio_as_whole_day():
    ast = _ast(
        headline="Стамбул за два дня: Каракёй и Султанахмет",
        city="Стамбул",
        fmt="dzen_weekend_itinerary",
        headings=[
            "День первый: Каракёй и Галата",
            "День второй: Султанахмет и Кадыкёй",
            "Аудиогид",
        ],
        paras=[
            _fill("Каракёй", "Галата", "Пера", "Золотой", city="Стамбул")
            + " Это и есть весь первый день: аудиогид заменяет весь туристический день.",
            _fill("Султанахмет", "Кадыкёй", "Босфор", "Галата", city="Стамбул"),
            _fill("Кадыкёй", "Султанахмет", "Галата", "Пера", city="Стамбул"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("route_infeasible" in item for item in result.issues)


def test_negative_mosque_as_warming_room():
    ast = _ast(
        headline="Казань без спешки: слобода, Баумана и Кремль",
        city="Казань",
        fmt="dzen_city_guide",
        headings=["Слобода", "Баумана", "Кул-Шариф"],
        paras=[
            _fill("Слобода", "Баумана", "Кремль", "Кабан"),
            _fill("Баумана", "Кремль", "Кабан", "Слобода"),
            _fill("Кремль", "Кабан", "Слобода", "Баумана")
            + " Мечеть Кул-Шариф — бесплатная комната для согревания туристов.",
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("unsuitable_venue" in item for item in result.issues)


def test_negative_universal_payment():
    ast = _ast(
        headline="Билеты за границей российской картой без сюрпризов кассы",
        city="Париж",
        fmt="dzen_travel_hack",
        headings=["Проблема", "Совет", "Ограничения"],
        paras=[
            _fill("Лувр", "Орсэ", "Маре", "Сена", city="Париж")
            + " Можно оплатить любой билет за границей российской картой.",
            _fill("Орсэ", "Лувр", "Пантеон", "Сена", city="Париж"),
            _fill("Маре", "Лувр", "Орсэ", "Пантеон", city="Париж"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("payment" in item for item in result.issues)


def test_negative_first_person_without_notes():
    ast = _ast(
        headline="Рим глазами гостя: форум, Трастевере и один холм",
        city="Рим",
        fmt="dzen_city_guide",
        headings=["Форум", "Трастевере", "Холм"],
        paras=[
            _fill("Форум", "Трастевере", "Палатин", "Тибр", city="Рим")
            + " Я впервые приехал в Рим и мы проверили на месте.",
            _fill("Трастевере", "Форум", "Колизей", "Палатин", city="Рим"),
            _fill("Палатин", "Тибр", "Форум", "Трастевере", city="Рим"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("first-person" in item for item in result.issues)


def test_negative_hours_without_asof():
    ast = _ast(
        headline="Эрмитаж без гонки: три опоры визита в Петербурге",
        city="Санкт-Петербург",
        fmt="dzen_museum_exhibition",
        headings=["Залы", "Дворцовая", "Ограничения"],
        paras=[
            _fill("Эрмитаж", "Дворцовая", "Мойка", "Невский", city="Санкт-Петербург")
            + " Музей открыт с 10:00, часы работы: 10–18.",
            _fill("Дворцовая", "Эрмитаж", "Васильевский", "Коломна", city="Санкт-Петербург"),
            _fill("Мойка", "Эрмитаж", "Невский", "Дворцовая", city="Санкт-Петербург"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("hours" in item for item in result.issues)


def test_negative_false_free_and_en_locale():
    ast = _ast(
        headline="Барселона без спешки: Готический квартал и Борн",
        city="Барселона",
        fmt="dzen_city_guide",
        headings=["Готический квартал", "Борн", "Монжуик"],
        paras=[
            _fill("Готический", "Борн", "Эшампле", "Монжуик", city="Барселона")
            + " Музей Пикассо: аудиогид бесплатно.",
            _fill("Борн", "Раваль", "Эшампле", "Монжуик", city="Барселона"),
            _fill("Монжуик", "Борн", "Раваль", "Готический", city="Барселона"),
        ],
    )
    paid = _product(
        title="Музей Пикассо: аудиогид",
        is_free=False,
        locale="en",
        listen_in_browser=False,
        playback_discrepancy=False,
    )
    result = _gates(ast, paid)
    blob = " ".join(result.issues)
    assert result.ok is False
    assert "misleading_product" in blob or "locale=" in blob


def test_negative_repetition_is_soft_revise():
    para = _fill("Кремль", "Баумана", "Кабан", "Слобода")
    ast = _ast(
        headline="Казань без спешки: слобода, Баумана и озеро Кабан",
        city="Казань",
        fmt="dzen_city_guide",
        headings=["Слобода", "Баумана", "Кабан"],
        paras=[para, para, para],
    )
    report = redundancy_report(ast)
    assert report.issues
    decision = evaluate_editorial(
        ast,
        products=[],
        image_urls=["https://cdn.example/a.jpg"],
        cover_url="https://cdn.example/a.jpg",
    )
    assert decision.decision == "revise"
    assert any(item.code == "repetition" for item in decision.non_blocking_issues)


def test_playback_discrepancy_blocks_categorical_browser():
    ast = kazan_winter_weekend_ast()
    ast.blocks.append(
        DzenBlock(
            type="paragraph",
            text="Слушать можно в браузере, приложение ставить не обязательно, хотя FAQ спорит.",
        )
    )
    result = _gates(ast, _product(playback_discrepancy=True, listen_in_browser=False))
    assert result.ok is False
    assert any("playback" in item or "misleading_product" in item for item in result.issues)


def test_genre_contracts_are_not_city_bound():
    assert genre_from_format("dzen_weekend_itinerary") == "itinerary"
    assert "аудиогид" in contract_for("itinerary").writer_brief.casefold()
    assert "Казань" not in contract_for("itinerary").writer_brief
    assert "Казань" not in contract_for("howto").reject_if


def test_four_sample_kits_are_genre_distinct():
    SAMPLES.mkdir(parents=True, exist_ok=True)
    specs = [
        ("dzen_city_guide", "city_guide", "Стамбул"),
        ("dzen_travel_hack", "howto", "Париж"),
        ("dzen_weekend_itinerary", "itinerary", "Нижний Новгород"),
        ("dzen_attraction_guide", "museum", "Лондон"),
    ]
    saved: dict[str, str] = {}
    for fmt, genre, city in specs:
        payload = _dzen_article({"city": city, "format": fmt, "country": "RU", "genre": genre})
        ast = DzenArticleAST.model_validate(payload)
        result = _gates(ast)
        assert result.ok, (genre, result.issues)
        html = clipboard_html(ast, [])
        (SAMPLES / f"{genre}.html").write_text(html, encoding="utf-8")
        saved[genre] = html
        assert "{d}" not in html
        assert "слой 1" not in html
        assert "рядом с купеческий тканью" not in html
    assert len({text[:180] for text in saved.values()}) == 4
    assert "день первый" in saved["itinerary"].casefold()
    assert "checkout" in saved["howto"].casefold() or "карт" in saved["howto"].casefold()
    assert "именной зал" in saved["museum"].casefold() or "зал" in saved["museum"].casefold()
    assert saved["city_guide"].casefold().count("день первый") == 0


def test_format_placeholder_is_hard_fail():
    ast = _ast(
        headline="Стамбул без спешки: Каракёй, Галата и другой берег",
        city="Стамбул",
        fmt="dzen_city_guide",
        headings=["Каракёй", "Галата", "Кадыкёй"],
        paras=[
            _fill("Каракёй", "Галата", "Пера", "Золотой", city="Стамбул")
            + " Затем {d} как панорама на полчаса.",
            _fill("Галата", "Каракёй", "Султанахмет", "Кадыкёй", city="Стамбул"),
            _fill("Кадыкёй", "Султанахмет", "Галата", "Пера", city="Стамбул"),
        ],
    )
    result = _gates(ast)
    assert result.ok is False
    assert any("placeholder" in item for item in result.issues)


def test_numbered_filler_layers_are_repetition():
    ast = _ast(
        headline="Казань без спешки: слобода, Баумана и озеро Кабан",
        city="Казань",
        fmt="dzen_city_guide",
        headings=["Слобода", "Баумана", "Кабан"],
        paras=[
            "Купеческий слой 1 в Казани: Кремль рядом с тканью.",
            "Ярмарочный слой 2 в Казани: Баумана рядом с тканью.",
            "Университетский слой 3 в Казани: Кабан рядом с тканью. " + _fill("Кремль", "Баумана"),
        ],
    )
    report = redundancy_report(ast)
    assert any("filler" in item or "слой" in item for item in report.issues)


def test_portfolio_counts_genres(synced_session, settings):
    plan_dzen_week(synced_session, settings=settings, run_date=dt.date(2026, 11, 18))
    report = portfolio_report(synced_session)
    assert report["article_count"] >= 1
    assert report["genres"]
    assert "cost_usd" in report
    assert "heavy_genre" in report


def test_write_scenarios_table():
    SCENARIOS.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id": 1,
            "genre": "itinerary",
            "place": "Казань",
            "gate": "accept",
            "check": "Marjani chronology; audio ≠ day",
        },
        {
            "id": 2,
            "genre": "museum",
            "place": "Барселона",
            "gate": "accept",
            "check": "ticket inclusion; locale=ru",
        },
        {
            "id": 3,
            "genre": "culture",
            "place": "Париж",
            "gate": "accept",
            "check": "no false travel ban",
        },
        {
            "id": 4,
            "genre": "itinerary",
            "place": "Стамбул",
            "gate": "accept",
            "check": "audio not whole day",
        },
        {
            "id": 5,
            "genre": "culture",
            "place": "Токио",
            "gate": "accept",
            "check": "no exotic cliché",
        },
        {
            "id": 6,
            "genre": "itinerary",
            "place": "Нижний Новгород",
            "gate": "accept",
            "check": "both days named",
        },
        {"id": 7, "genre": "museum", "place": "Лондон", "gate": "accept", "check": "hours omitted"},
        {
            "id": 8,
            "genre": "story",
            "place": "Санкт-Петербург",
            "gate": "accept",
            "check": "1703 not causal clash",
        },
        {"id": 9, "genre": "howto", "place": "Париж", "gate": "accept", "check": "scoped payment"},
        {
            "id": 10,
            "genre": "news",
            "place": "Лондон",
            "gate": "accept",
            "check": "announced ≠ in force",
        },
        {
            "id": 11,
            "genre": "comparison",
            "place": "Санкт-Петербург",
            "gate": "accept",
            "check": "criteria first",
        },
        {
            "id": 12,
            "genre": "story",
            "place": "Казань",
            "gate": "accept",
            "check": "legend vs document",
        },
    ]
    SCENARIOS.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    assert json.loads(SCENARIOS.read_text(encoding="utf-8"))
