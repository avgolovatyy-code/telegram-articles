"""Claim classification and the VERIFY-OR-OMIT rule (spec §12, §13, §16)."""

from __future__ import annotations

from app.db.enums import CRITICAL_CLAIM_CATEGORIES, ClaimCategory
from app.generation.claims import classify_sentence, scan_document, strip_unverified
from app.generation.research import (
    TIER_OFFICIAL_VENUE,
    TIER_SECONDARY,
    TIER_UNTRUSTED,
    classify_source,
)
from app.generation.schemas import ArticleBlock, ArticleDocument, ArticleSection, FAQItem


def document(*paragraphs: str) -> ArticleDocument:
    return ArticleDocument(
        title="Title",
        intro=paragraphs[0] if paragraphs else "Intro",
        sections=[
            ArticleSection(
                heading="Section",
                blocks=[ArticleBlock(type="paragraph", text=text) for text in paragraphs],
            )
        ],
    )


def test_opening_hours_are_flagged():
    assert classify_sentence("The museum is open from 09:00 until 18:00.") == (
        ClaimCategory.OPENING_HOURS
    )
    assert classify_sentence("Музей работает с 10:00.") == ClaimCategory.OPENING_HOURS


def test_closing_days_are_flagged():
    assert classify_sentence("The Louvre is closed on Tuesdays.") == ClaimCategory.CLOSING_DAYS
    assert classify_sentence("Музей закрыт по понедельникам.") == ClaimCategory.CLOSING_DAYS


def test_ticket_price_is_flagged():
    assert classify_sentence("Tickets cost €22 for adults.") == ClaimCategory.TICKET_PRICE
    assert classify_sentence("Билет стоит 700 рублей.") == ClaimCategory.TICKET_PRICE


def test_skip_the_line_is_flagged():
    assert classify_sentence("The pass gives you skip-the-line entry.") == (
        ClaimCategory.SKIP_THE_LINE
    )


def test_transport_and_accessibility_are_flagged():
    assert classify_sentence("Take metro line 1 to the entrance.") == ClaimCategory.TRANSPORT
    assert classify_sentence("The entrance is wheelchair accessible.") == (
        ClaimCategory.ACCESSIBILITY
    )


def test_narrative_sentences_are_not_flagged():
    assert classify_sentence("The building has a quiet courtyard at the back.") is None
    assert classify_sentence("Здесь приятно просто пройтись без плана.") is None


def test_all_flagged_categories_are_critical_except_soft_ones():
    critical = set(CRITICAL_CLAIM_CATEGORIES)
    assert str(ClaimCategory.OPENING_HOURS) in critical
    assert str(ClaimCategory.TICKET_PRICE) in critical
    assert str(ClaimCategory.HISTORICAL) not in critical


def test_scan_marks_api_backed_numbers_as_trusted():
    doc = document("The tour lasts 90 minutes and costs 18.52 EUR.")
    result = scan_document(
        doc,
        api_facts=["Tour: duration 90 min (WeGoTrip API)", "Tour: from 18.52 EUR (WeGoTrip API)"],
    )
    assert result.claims
    assert all(claim.supported_by_api for claim in result.claims)
    assert not result.critical


def test_scan_marks_unsupported_numbers_as_needing_verification():
    doc = document("Tickets cost €22 and the museum is closed on Tuesdays.")
    result = scan_document(doc, api_facts=["Tour: duration 90 min (WeGoTrip API)"])
    assert result.critical


def test_strip_removes_the_sentence_carrying_an_unverified_claim():
    sentence = "The Louvre is closed on Tuesdays."
    doc = document(f"Plan your visit. {sentence} Bring water.")
    cleaned, removed = strip_unverified(doc, [sentence])
    assert removed >= 1
    assert sentence not in cleaned.plain_text()
    assert "Bring water." in cleaned.plain_text()


def test_strip_removes_list_items_and_faq_answers():
    doc = ArticleDocument(
        title="T",
        intro="Intro paragraph.",
        sections=[
            ArticleSection(
                heading="S",
                blocks=[ArticleBlock(type="list", items=["Tickets cost €22.", "Bring shoes."])],
            )
        ],
        faq=[FAQItem(question="Price?", answer="Tickets cost €22.")],
    )
    cleaned, removed = strip_unverified(doc, ["Tickets cost €22."])
    assert removed >= 2
    assert "€22" not in cleaned.plain_text()
    assert "Bring shoes." in cleaned.plain_text()


def test_strip_drops_sections_that_become_empty():
    doc = document("Tickets cost €22.")
    cleaned, _ = strip_unverified(doc, ["Tickets cost €22."])
    assert cleaned.sections == []


def test_strip_is_a_no_op_without_targets():
    doc = document("Nothing to remove here.")
    cleaned, removed = strip_unverified(doc, [])
    assert removed == 0
    assert cleaned.plain_text() == doc.plain_text()


# ------------------------------------------------------------- source tiers
def test_official_venue_beats_a_blog():
    assert classify_source("https://www.louvre.fr/en/visit") <= TIER_OFFICIAL_VENUE + 1
    assert classify_source("https://www.tripadvisor.com/x") == TIER_UNTRUSTED
    assert classify_source("https://random-travel-blog.wordpress.com/x") == TIER_UNTRUSTED


def test_government_and_tourism_sources_are_trusted():
    assert classify_source("https://www.paris.gouv.fr/x") <= TIER_SECONDARY
    assert classify_source("https://en.parisinfo.com/visit") <= TIER_SECONDARY


def test_missing_source_is_untrusted():
    assert classify_source(None) == TIER_UNTRUSTED
