from __future__ import annotations

from app.dzen.quality import run_gates
from app.dzen.schemas import DzenArticleAST, DzenBlock


def test_generic_stroll_fails_concreteness_gate():
    ast = DzenArticleAST(
        headline="Отличный уикенд в любом городе мира сегодня",
        lead=("Погуляйте по центру и посетите музей, потом зайдите в кафе. " * 8)[:400],
        format="dzen_city_guide",
        pillar="city_guides",
        audience="russian_speaking_global",
        destination_city="Город",
        blocks=[
            DzenBlock(type="heading", text="Зачем это читать"),
            DzenBlock(type="heading", text="Как спланировать день"),
            DzenBlock(type="heading", text="На что смотреть"),
            DzenBlock(type="paragraph", text=("Погуляйте и посетите музей. " * 120)),
        ],
        practical_takeaway="Зайдите в кафе.",
    )
    result = run_gates(
        ast,
        products=[],
        image_urls=["https://cdn.example/a.jpg"],
        cover_url="https://cdn.example/a.jpg",
    )
    assert result.ok is False
    assert any(
        "fluff" in issue or "named places" in issue or "headings" in issue
        for issue in result.issues
    )
