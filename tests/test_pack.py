from pitchkitchen.pack import render_pack

from fakes import PACK

TALK = {
    "kind": "conversation",
    "who": "Marta",
    "role": "seller",
    "spoken_on": "2026-10-01",
    "today_they": "Posts in WhatsApp",
    "paid": "Lost 70 euros",
    "quote": "Took weeks",
    "source": "",
}
FACT = {"kind": "fact", "who": "menu.example", "role": "", "spoken_on": "2026-10-02", "quote": "Lunch costs 12 euros.", "source": "https://menu.example"}


def test_a_draft_pack_copies_the_evidence_from_the_logs():
    text = render_pack("We help X", "Ada", [TALK, FACT], PACK, False, "2026-10-04")

    assert text.startswith("# Starter pack: We help X\n")
    assert "**Draft.** Not proven yet (1 of 3 real conversations logged, not served)" in text
    assert '- **Marta**, seller, 2026-10-01: "Took weeks" Does today: Posts in WhatsApp. Pays today: Lost 70 euros.' in text
    assert "- Lunch costs 12 euros. ([menu.example](https://menu.example), 2026-10-02)" in text
    assert "- Buyers will pay a small listing fee" in text
    assert "1. **List a book**: Marta waited three weeks to sell hers" in text
    assert "| books | id, title, course, price |" in text
    assert "````markdown\n# We help X\n" in text
    assert "- Build only the version-one features; ask before adding anything else." in text
    assert "```text\nBuild a small Flask app where students list textbooks for next term's courses.\n```" in text


def test_a_log_that_already_ends_in_a_full_stop_gets_only_one():
    talk = dict(TALK, today_they="Posts in WhatsApp.", paid="Lost 70 euros.")
    text = render_pack("We help X", "Ada", [talk], PACK, False, "2026-10-04")

    assert "Does today: Posts in WhatsApp. Pays today: Lost 70 euros." in text
    assert ".." not in text


def test_a_verified_pack_says_so_and_an_empty_log_says_none():
    assert "**Verified.** Served on Pitch Kitchen with 1 logged conversations" in render_pack("We help X", "Ada", [TALK], PACK, True, "2026-10-04")

    bare = dict(PACK, first_customer="", assumptions=[], not_yet=[], user_stories=[], screens=[], data_model=[], stack="")
    text = render_pack("We help X", "Ada", [], bare, False, "2026-10-04", needed=5)
    assert "0 of 5 real conversations" in text
    assert text.count("None logged yet.") == 2
    assert "None listed." in text
    assert "## Data model" not in text
