from __future__ import annotations

from app.db.models import City, Product
from app.dzen.media import collect_catalog_images, image_fingerprint
from app.dzen.products import (
    human_duration,
    listen_in_browser,
    match_products,
    playback_discrepancy,
    product_is_free,
    reader_pitch,
)


def _city(session, external_id: str, name: str) -> City:
    row = City(market="ru", external_id=external_id, slug=name.lower(), name=name)
    session.add(row)
    session.flush()
    return row


def _product(session, *, external_id: str, title: str, city_id: str, rank: int = 1) -> Product:
    row = Product(
        market="ru",
        external_id=external_id,
        slug=title.lower().replace(" ", "-")[:40],
        title=title,
        locale="ru",
        available=True,
        published=True,
        city_external_id=city_id,
        popularity_rank=rank,
        canonical_url=f"https://wegotrip.ru/p{external_id}/",
        cover=f"https://cdn.example/product/{external_id}/cover.jpg",
    )
    session.add(row)
    session.flush()
    return row


def test_human_duration_does_not_split_hours():
    assert human_duration("1.5 – 2 hours") == "1,5–2 часа"
    assert human_duration("1h 30min - 2h") == "1 ч 30 мин–2 ч"
    assert human_duration("1ч 30мин - 2ч") == "1 ч 30 мин–2 ч"


def test_reader_pitch_prefers_web_player_and_skips_ops_notes(session):
    kazan = _city(session, "551487", "Казань")
    product = _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    product.price = 0
    product.duration_text = "1.5 – 2 hours"
    product.distance = "4 км"
    product.description = (
        "Экскурсия начнется с посещения старо-татарской слободы, затем улица Баумана."
    )
    product.inclusions = ["Аудиоэкскурсия для вашего смартфона в приложении WeGoTrip"]
    product.important_info = [
        "Аудиоэкскурсия доступна только в приложении WeGoTrip.",
        "входной билет может быть отдельно — проверьте карточку товара",
    ]
    session.flush()
    assert product_is_free(product) is True
    assert listen_in_browser(product) is False
    assert playback_discrepancy(product) is False
    pitch = reader_pitch(product)
    assert "бесплатная аудиоэкскурсия" in pitch
    assert "1,5–2 часа" in pitch
    assert "браузер" not in pitch
    assert "4 км" in pitch
    assert "ч ours" not in pitch
    assert "проверьте карточку" not in pitch.casefold()
    assert "входной билет может быть отдельно" not in pitch.casefold()


def test_reader_pitch_web_player_only_when_unambiguous(session):
    kazan = _city(session, "551487", "Казань")
    product = _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    product.description = "Слушайте в браузере, приложение не обязательно."
    session.flush()
    assert listen_in_browser(product) is True
    assert playback_discrepancy(product) is False
    assert "браузер" in reader_pitch(product)


def test_reader_pitch_omits_browser_when_faq_disagrees(session):
    kazan = _city(session, "551487", "Казань")
    product = _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    product.description = "Listen online in your browser. No app is required."
    product.important_info = ["Аудиоэкскурсия доступна только в приложении WeGoTrip."]
    session.flush()
    assert listen_in_browser(product) is False
    assert playback_discrepancy(product) is True
    assert "браузер" not in reader_pitch(product)
    assert "ставить не обязательно" not in reader_pitch(product)


def test_kazan_is_not_resolved_as_kazanlak(session, settings):
    kazan = _city(session, "551487", "Казань")
    kazan.country_name = "Россия"
    kazanlyk = _city(session, "730496", "Казанлык")
    kazanlyk.country_name = "Болгария"
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
        rank=1,
    )
    _product(
        session,
        external_id="9",
        title="Казанлык: розовая долина",
        city_id=kazanlyk.external_id,
        rank=1,
    )
    picks = match_products(
        session,
        article_id="art-kazan",
        topic_slug="kazan",
        city_name="Казань",
        country_code="RU",
        article_text="Казань на зимний уикенд: Кремль, Баумана, озеро Кабан.",
        settings=settings,
    )
    assert [p.external_id for p in picks] == ["1526"]


def test_kazan_article_does_not_get_sviyazhsk(session, settings):
    kazan = _city(session, "551487", "Казань")
    legends = _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
        rank=1,
    )
    legends.description = "По Казани и, если захотите, однодневный выезд в Свияжск."
    _product(
        session,
        external_id="25427",
        title="Свияжск: обзорная аудиоэкскурсия по острову-граду",
        city_id=kazan.external_id,
        rank=2,
    )
    _product(
        session,
        external_id="25508",
        title="Свияжск: комплексный билет и обзорная аудиоэкскурсия",
        city_id=kazan.external_id,
        rank=3,
    )
    article = (
        "Казань на зимний уикенд: два дня от Кремля до тёплых вечерних улиц. "
        "Кремль, улица Баумана, озеро Кабан и Старо-Татарская слобода."
    )
    picks = match_products(
        session,
        article_id="art1",
        topic_slug="kazan",
        city_name="Казань",
        country_code="RU",
        article_text=article,
        settings=settings,
    )
    titles = [p.title for p in picks]
    assert any("Казани" in title for title in titles)
    assert all("Свияжск" not in title for title in titles)
    assert 1 <= len(picks) <= 3
    assert all(p.affiliate_url.count("coupon=435") == 1 for p in picks)
    assert all("utm_source=dzen" in p.affiliate_url for p in picks)


def test_passing_mention_does_not_attach_other_city(session, settings):
    kazan = _city(session, "551487", "Казань")
    spb = _city(session, "498817", "Санкт-Петербург")
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
        rank=1,
    )
    _product(
        session,
        external_id="2702",
        title="Петербургский крафт: тур по барам местных пивоварен",
        city_id=spb.external_id,
        rank=1,
    )
    article = (
        "Казань на зимний уикенд: Кремль, Баумана и слобода. "
        "Это не Петербург и не его бары — остаёмся в Казани."
    )
    picks = match_products(
        session,
        article_id="art-mix",
        topic_slug="kazan",
        city_name="Казань",
        country_code="RU",
        article_text=article,
        settings=settings,
    )
    titles = [p.title for p in picks]
    assert titles == ["Городские легенды Казани"]
    assert all("Петербург" not in title for title in titles)


def test_zero_products_when_nothing_matches(session, settings):
    _city(session, "1", "Казань")
    _product(
        session,
        external_id="9",
        title="Свияжск: обзорная аудиоэкскурсия по острову-граду",
        city_id="1",
    )
    picks = match_products(
        session,
        article_id="art2",
        topic_slug="kazan",
        city_name="Казань",
        country_code="RU",
        article_text="Казань: Кремль и улица Баумана без выезда из города.",
        settings=settings,
    )
    assert picks == []


def test_negated_sviyazhsk_aside_does_not_attach_products(session, settings):
    kazan = _city(session, "551487", "Казань")
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
        rank=1,
    )
    _product(
        session,
        external_id="25427",
        title="Свияжск: обзорная аудиоэкскурсия по острову-граду",
        city_id=kazan.external_id,
        rank=2,
    )
    picks = match_products(
        session,
        article_id="art-neg",
        topic_slug="kazan",
        city_name="Казань",
        country_code="RU",
        article_text=("Казань на зимний уикенд: Кремль и слобода. В этот раз не едем в Свияжск."),
        focus_text="Казань на зимний уикенд Кремль Слобода Баумана",
        settings=settings,
    )
    assert [p.title for p in picks] == ["Городские легенды Казани"]


def test_sviyazhsk_allowed_when_article_names_it(session, settings):
    _city(session, "1", "Казань")
    _product(
        session,
        external_id="25427",
        title="Свияжск: обзорная аудиоэкскурсия по острову-граду",
        city_id="1",
        rank=1,
    )
    picks = match_products(
        session,
        article_id="art3",
        topic_slug="sviyazhsk",
        city_name="Казань",
        country_code="RU",
        article_text="День в Свияжске: остров-град, как добраться из Казани.",
        settings=settings,
    )
    assert len(picks) == 1
    assert "Свияжск" in picks[0].title


def test_catalog_images_stay_with_matched_products(session):
    kazan = _city(session, "551487", "Казань")
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
        rank=1,
    )
    _product(
        session,
        external_id="25427",
        title="Свияжск: обзорная аудиоэкскурсия по острову-граду",
        city_id=kazan.external_id,
        rank=2,
    )
    assets = collect_catalog_images(
        session,
        product_ids=["1526"],
        city_name="Казань",
        headings=["Кремль", "Баумана", "Слобода"],
        limit=5,
    )
    assert assets
    assert all("25427" not in (asset.url or "") for asset in assets)
    assert all("1526" in (asset.url or "") for asset in assets)


def test_images_ignore_other_city_product_ids(session):
    kazan = _city(session, "551487", "Казань")
    spb = _city(session, "498817", "Санкт-Петербург")
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    _product(
        session,
        external_id="2702",
        title="Петербургский крафт: тур по барам местных пивоварен",
        city_id=spb.external_id,
    )
    assets = collect_catalog_images(
        session,
        product_ids=["2702", "1526"],
        city_name="Казань",
        headings=["Кремль"],
        limit=5,
    )
    assert assets
    assert all("2702" not in (asset.url or "") for asset in assets)
    assert all("1526" in (asset.url or "") for asset in assets)


def test_fallback_images_skip_nearby_city_in_title(session):
    kazan = _city(session, "551487", "Казань")
    _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    _product(
        session,
        external_id="25427",
        title="Свияжск из Казани: обзорная аудиоэкскурсия",
        city_id=kazan.external_id,
    )
    assets = collect_catalog_images(
        session,
        product_ids=[],
        city_name="Казань",
        headings=["Кремль", "Баумана", "Слобода"],
        limit=5,
    )
    assert assets
    assert all("25427" not in (asset.url or "") for asset in assets)
    assert all("1526" in (asset.url or "") for asset in assets)


def test_sviyazhsk_filename_skipped_for_kazan_article(session):
    kazan = _city(session, "551487", "Казань")
    product = _product(
        session,
        external_id="1526",
        title="Городские легенды Казани",
        city_id=kazan.external_id,
    )
    product.cover = "https://cdn.example/product/1526/sviyazhskfirelookouttower.jpg"
    product.images = ["https://cdn.example/product/1526/kremlin-kazan.jpg"]
    assets = collect_catalog_images(
        session,
        product_ids=["1526"],
        city_name="Казань",
        headings=["Кремль"],
        limit=5,
    )
    assert assets
    assert all("sviyazh" not in (asset.url or "").lower() for asset in assets)
    assert any("kremlin-kazan" in (asset.url or "") for asset in assets)


def test_image_fingerprint_collapses_cdn_cache_variants():
    a = "https://wgt-prod-storage.s3.amazonaws.com/media/products/product/1526/d09ad0b0.jpg"
    b = (
        "https://wgt-prod-storage.s3.amazonaws.com/media/CACHE/images/products/product/"
        "1526/d09ad0b0/24f97970af558dd6756e1494ffea2b5f.jpg"
    )
    assert image_fingerprint(a) == image_fingerprint(b)
