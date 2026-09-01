"""Helpers for matching catalogue attraction names in article bodies."""

from __future__ import annotations

from app.topics.dedup import normalize_text

#: Tokens that appear in many attraction names and must not count as a "named place".
GENERIC_ATTRACTION_TOKENS = {
    "museum",
    "museu",
    "museo",
    "музей",
    "музея",
    "park",
    "parc",
    "парк",
    "palace",
    "palau",
    "palacio",
    "дворец",
    "castle",
    "castell",
    "замок",
    "cathedral",
    "basilica",
    "basílica",
    "собор",
    "church",
    "церковь",
    "square",
    "plaza",
    "площадь",
    "house",
    "casa",
    "дом",
    "market",
    "mercat",
    "рынок",
    "gallery",
    "галерея",
    "pavilion",
    "павильон",
    "bridge",
    "мост",
    "tower",
    "башня",
    "garden",
    "gardens",
    "сад",
    "сады",
    "modern",
    "современного",
    "современный",
    "искусства",
    "art",
    "arts",
    "major",
    "reial",
    "royal",
    "santa",
    "saint",
    "santo",
    "святого",
    "святой",
    "де",
    "del",
    "de",
    "la",
    "las",
    "los",
    "el",
    "the",
    "and",
    "и",
    "van",
    "der",
}

#: Latin catalogue tokens → common Cyrillic spellings travellers use in RU copy.
ATTRACTION_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "sagrada": ("саграда",),
    "familia": ("фамилия",),
    "guell": ("гуэль", "гуель", "гюэль"),
    "gaudi": ("гауди",),
    "picasso": ("пикассо",),
    "rambla": ("рамбла", "рамблас"),
    "boqueria": ("бокерия",),
    "montjuic": ("монтжуик", "монжуик"),
    "batllo": ("батльо", "батло"),
    "mila": ("мила",),
    "born": ("борн",),
    "gracia": ("грасия", "грасиа"),
    "triomf": ("триумф",),
    "miro": ("миро",),
    "musica": ("музыка", "музыки"),
    "catalana": ("каталонии", "каталонской"),
}


def attraction_match_needles(name: str) -> list[str]:
    """Distinctive needles that prove a specific catalogue place was named."""
    norm = normalize_text(name)
    needles: list[str] = []
    if len(norm) >= 6:
        needles.append(norm)
    for token in norm.split():
        if len(token) <= 3 or token in GENERIC_ATTRACTION_TOKENS:
            continue
        needles.append(token)
        for alias in ATTRACTION_TOKEN_ALIASES.get(token, ()):
            needles.append(normalize_text(alias))
    seen: set[str] = set()
    out: list[str] = []
    for needle in needles:
        if needle and needle not in seen:
            seen.add(needle)
            out.append(needle)
    return out


def attraction_mentioned(name: str, body_norm: str, *, aliases: list[str] | None = None) -> bool:
    needles = list(attraction_match_needles(name))
    for alias in aliases or []:
        needles.extend(attraction_match_needles(alias))
    return any(_needle_in_body(needle, body_norm) for needle in needles)


def _needle_in_body(needle: str, body_norm: str) -> bool:
    if not needle:
        return False
    if needle in body_norm:
        return True
    # Soft match for Russian case endings on single tokens only:
    # саграда ↔ саграды, фамилия ↔ фамилии.
    if " " in needle or len(needle) < 5:
        return False
    stem = needle[:-1]
    for token in body_norm.split():
        if len(token) < 5 or abs(len(token) - len(needle)) > 2:
            continue
        token_stem = token[:-1]
        if token.startswith(stem) or needle.startswith(token_stem):
            return True
    return False


def mention_forms_for(name: str, *, market: str) -> list[str]:
    """Human-facing forms the writer may use; always includes the catalogue name."""
    forms = [name]
    if market != "ru":
        return forms
    # Suggest compact Cyrillic glosses built from known aliases of distinctive tokens.
    gloss_parts: list[str] = []
    for token in normalize_text(name).split():
        if token in GENERIC_ATTRACTION_TOKENS or len(token) <= 3:
            continue
        aliases = ATTRACTION_TOKEN_ALIASES.get(token)
        if aliases:
            gloss_parts.append(aliases[0].capitalize() if aliases[0].islower() else aliases[0])
    if gloss_parts:
        gloss = " ".join(gloss_parts)
        if normalize_text(gloss) != normalize_text(name):
            forms.append(gloss)
    return forms


__all__ = [
    "ATTRACTION_TOKEN_ALIASES",
    "GENERIC_ATTRACTION_TOKENS",
    "attraction_match_needles",
    "attraction_mentioned",
    "mention_forms_for",
]
