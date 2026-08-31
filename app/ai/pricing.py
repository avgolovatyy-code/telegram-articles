"""Model pricing.

Prices are USD per 1M tokens, taken from the OpenAI model catalogue (checked
2026-08-27). They live in configuration-shaped data rather than in business logic so a
price change is a one-line edit, and unknown models fall back to a conservative
estimate instead of silently costing $0.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.logging_setup import get_logger

log = get_logger("ai.pricing")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_mtok: float
    output_per_mtok: float
    cached_input_per_mtok: float | None = None

    def cost(self, *, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
        billable_input = max(0, input_tokens - cached_input_tokens)
        cached_rate = (
            self.cached_input_per_mtok
            if self.cached_input_per_mtok is not None
            else self.input_per_mtok * 0.1
        )
        return (
            billable_input * self.input_per_mtok
            + cached_input_tokens * cached_rate
            + output_tokens * self.output_per_mtok
        ) / 1_000_000


MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-5.6-sol": ModelPrice(4.00, 20.00),
    "gpt-5.6": ModelPrice(4.00, 20.00),
    "gpt-5.6-terra": ModelPrice(2.00, 12.00),
    "gpt-5.6-luna": ModelPrice(0.20, 1.20),
}

#: Used when a model id is not in the table — deliberately pessimistic so the budget
#: manager errs on the side of generating fewer articles rather than overspending.
FALLBACK_PRICE = ModelPrice(4.00, 20.00)

#: Billed per tool call by the Responses API web search tool.
WEB_SEARCH_CALL_USD = 0.01

#: Approximate price of one generated cover (gpt-image-2, 1024x1024, standard quality).
IMAGE_GENERATION_USD = 0.04


def get_price(model: str) -> ModelPrice:
    price = MODEL_PRICES.get(model)
    if price is None:
        base = model.rsplit("-", 1)[0]
        price = MODEL_PRICES.get(base)
    if price is None:
        log.warning("pricing.unknown_model", model=model)
        return FALLBACK_PRICE
    return price


def estimate_cost(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    web_search_calls: int = 0,
    generated_images: int = 0,
) -> float:
    total = get_price(model).cost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
    )
    total += web_search_calls * WEB_SEARCH_CALL_USD
    total += generated_images * IMAGE_GENERATION_USD
    return round(total, 6)


def approx_tokens(text: str) -> int:
    """Rough token count used only for pre-flight cost estimates.

    ~3.6 characters per token averages EN and RU reasonably; actual spend is always
    recorded from the API's ``usage`` object.
    """
    return max(1, int(len(text) / 3.6))


__all__ = [
    "FALLBACK_PRICE",
    "IMAGE_GENERATION_USD",
    "MODEL_PRICES",
    "WEB_SEARCH_CALL_USD",
    "ModelPrice",
    "approx_tokens",
    "estimate_cost",
    "get_price",
]
