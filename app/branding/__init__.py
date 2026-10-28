"""Channel identity drafts for Telegram (and later Max sync).

Proposed title/description/pinned texts live here for admin preview.
**Never** apply to live chats unless ``Settings.channel_branding_apply_enabled``
is true *and* a human approval record exists — see
``CHANNEL_BRANDING_PROPOSAL.md`` and Editorial Engine v2.2 §0.1.
"""

from app.branding.apply import (
    BrandingApplyReport,
    ChannelApplyResult,
    apply_approved_branding,
    apply_channel_branding,
)
from app.branding.proposal import (
    CHANNEL_BRANDING_VERSION,
    TELEGRAM_CHAT_LIMITS,
    proposed_branding_for,
    validate_branding_lengths,
)

__all__ = [
    "CHANNEL_BRANDING_VERSION",
    "TELEGRAM_CHAT_LIMITS",
    "BrandingApplyReport",
    "ChannelApplyResult",
    "apply_approved_branding",
    "apply_channel_branding",
    "proposed_branding_for",
    "validate_branding_lengths",
]
