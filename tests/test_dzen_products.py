from __future__ import annotations

from app.db.models import City, Product
from app.dzen.media import collect_catalog_images, image_fingerprint
from app.dzen.products import match_products


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


def test_image_fingerprint_collapses_cdn_cache_variants():
    a = "https://wgt-prod-storage.s3.amazonaws.com/media/products/product/1526/d09ad0b0.jpg"
    b = (
        "https://wgt-prod-storage.s3.amazonaws.com/media/CACHE/images/products/product/"
        "1526/d09ad0b0/24f97970af558dd6756e1494ffea2b5f.jpg"
    )
    assert image_fingerprint(a) == image_fingerprint(b)
