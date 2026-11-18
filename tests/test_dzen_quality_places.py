from __future__ import annotations

from app.dzen.pipeline import _critic_blocks_handoff
from app.dzen.quality import run_gates
from app.dzen.schemas import DzenArticleAST, DzenBlock, DzenCriticReport


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


def test_critic_notes_do_not_block_handoff():
    notes = DzenCriticReport(
        pass_gate=False,
        quality_score=0.82,
        issues=["Часть фактов стоит сверить на официальном сайте музея."],
    )
    assert _critic_blocks_handoff(notes) is False
    bad = DzenCriticReport(pass_gate=False, quality_score=0.9, issues=["это клише и clickbait"])
    assert _critic_blocks_handoff(bad) is True
