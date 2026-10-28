"""Max messenger — secondary RU publish surface (Telegram stays primary).

Audience policy (addendum v1.1): Max is for people **in Russia**, not all
Russian speakers worldwide. Public URL: https://max.ru/channel_wegotrip
"""

from app.max.adapter import AdaptedMaxPost, adapt_for_max
from app.max.audience import MaxAudienceDecision, MaxRussiaAudienceGate
from app.max.chat_id import CANONICAL_PUBLIC_SLUG, CANONICAL_PUBLIC_URL
from app.max.policy import MaxRussiaEditorialPolicy
from app.max.publisher import MaxPublisher, maybe_publish_ru_to_max

__all__ = [
    "CANONICAL_PUBLIC_SLUG",
    "CANONICAL_PUBLIC_URL",
    "AdaptedMaxPost",
    "MaxAudienceDecision",
    "MaxPublisher",
    "MaxRussiaAudienceGate",
    "MaxRussiaEditorialPolicy",
    "adapt_for_max",
    "maybe_publish_ru_to_max",
]
