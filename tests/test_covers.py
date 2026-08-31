"""Generated covers are a controlled exception (spec §28)."""

from __future__ import annotations

from app.ai.budget import BudgetManager
from app.generation.covers import GeneratedCoverService


class StubImageProvider:
    name = "stub"

    def __init__(self, payload: bytes | None = b"PNGDATA") -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, request):
        raise NotImplementedError

    def generate_image(self, prompt: str, *, size: str = "1024x1024") -> bytes | None:
        self.prompts.append(prompt)
        return self.payload


def service(session, settings, tmp_path, provider=None) -> GeneratedCoverService:
    return GeneratedCoverService(
        provider or StubImageProvider(),
        BudgetManager(session, settings),
        settings=settings,
        output_dir=tmp_path / "generated",
    )


def test_disabled_by_default(session, settings, tmp_path):
    assert settings.allow_generated_covers is False
    decision = service(session, settings, tmp_path).evaluate(api_media_available=False)
    assert not decision.allowed
    assert "disabled" in decision.reason


def test_never_replaces_an_api_photo(session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allow_generated_covers", True)
    decision = service(session, settings, tmp_path).evaluate(api_media_available=True)
    assert not decision.allowed
    assert "API" in decision.reason


def test_blocked_when_the_budget_is_gone(session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allow_generated_covers", True)
    BudgetManager(session, settings).record(amount_usd=3.0, market="en")
    decision = service(session, settings, tmp_path).evaluate(api_media_available=False)
    assert not decision.allowed
    assert "budget" in decision.reason


def test_generates_and_charges_the_budget(session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allow_generated_covers", True)
    provider = StubImageProvider()
    budget = BudgetManager(session, settings)
    covers = GeneratedCoverService(
        provider, budget, settings=settings, output_dir=tmp_path / "generated"
    )

    candidate = covers.generate(market="en", entity_name="Paris", api_media_available=False)

    assert candidate is not None
    assert candidate.role == "cover"
    assert candidate.source_entity_type == "generated"
    assert candidate.url.endswith(".png")
    assert budget.spent() > 0
    # The prompt must not ask for a photograph of a real landmark.
    prompt = provider.prompts[0]
    assert "Do not depict any identifiable building" in prompt


def test_returns_none_when_generation_fails(session, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "allow_generated_covers", True)
    covers = service(session, settings, tmp_path, StubImageProvider(payload=None))
    assert covers.generate(market="ru", entity_name="Москва", api_media_available=False) is None
