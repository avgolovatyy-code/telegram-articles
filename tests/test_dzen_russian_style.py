from __future__ import annotations

import pytest

from app.ai.mock_provider import _dzen_article
from app.dzen.editorial import evaluate_editorial
from app.dzen.editorial_ast import kazan_winter_weekend_ast
from app.dzen.prompts import DZEN_CRITIC_V2_BODY, DZEN_WRITER_BODY
from app.dzen.quality import body_text, run_gates
from app.dzen.russian_style import russian_style_issues
from app.dzen.schemas import DzenArticleAST, DzenBlock

EDITOR_EXAMPLES = (
    "На снегу это три разных скорости.",
    "Первый день лучше собрать в одну линию.",
    "Юнусовская площадь держит купеческий масштаб.",
    "Мечети сидят в жилой ткани.",
    "Еду второго дня держите татарской, но без экзамена.",
)


@pytest.mark.parametrize("phrase", EDITOR_EXAMPLES)
def test_editor_examples_are_detected_as_awkward_russian(phrase: str):
    issues = russian_style_issues(phrase)
    assert issues, phrase
    assert any(issue.span.casefold() in phrase.casefold() for issue in issues)
    assert all(issue.proposed_fix for issue in issues)


@pytest.mark.parametrize("phrase", EDITOR_EXAMPLES)
def test_editor_examples_block_handoff(phrase: str):
    ast = kazan_winter_weekend_ast()
    ast.blocks.append(DzenBlock(type="paragraph", text=phrase))
    result = run_gates(
        ast,
        products=[],
        image_urls=["https://cdn.example/kazan.jpg"],
        cover_url="https://cdn.example/kazan.jpg",
    )
    assert result.ok is False
    assert any("awkward_russian" in issue for issue in result.issues)

    decision = evaluate_editorial(
        ast,
        products=[],
        image_urls=["https://cdn.example/kazan.jpg"],
        cover_url="https://cdn.example/kazan.jpg",
    )
    assert decision.decision == "revise"
    assert any(issue.code == "awkward_russian" for issue in decision.blocking_issues)


def test_kazan_rewrite_uses_concrete_idiomatic_russian():
    text = body_text(kazan_winter_weekend_ast())
    assert not russian_style_issues(text)
    for phrase in EDITOR_EXAMPLES:
        assert phrase.casefold() not in text.casefold()
    assert "мечети стоят среди жилых домов" in text
    assert "попробуйте одно татарское блюдо" in text
    assert "на еду и посещение Кремля понадобится дополнительное время" in text


@pytest.mark.parametrize(
    ("fmt", "genre", "city"),
    (
        ("dzen_city_guide", "city_guide", "Стамбул"),
        ("dzen_weekend_itinerary", "itinerary", "Нижний Новгород"),
        ("dzen_attraction_guide", "museum", "Лондон"),
        ("dzen_travel_hack", "howto", "Париж"),
    ),
)
def test_mock_writer_does_not_teach_translated_russian(fmt: str, genre: str, city: str):
    payload = _dzen_article({"city": city, "format": fmt, "country": "RU", "genre": genre})
    ast = DzenArticleAST.model_validate(payload)
    assert not russian_style_issues(body_text(ast))


def test_writer_and_critic_prompts_treat_native_russian_as_a_gate():
    assert "Пиши так, как изначально пишут по-русски" in DZEN_WRITER_BODY
    assert "на снегу это три разных скорости" in DZEN_CRITIC_V2_BODY.casefold()
    assert "awkward_russian" in DZEN_CRITIC_V2_BODY
