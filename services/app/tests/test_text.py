from catalog.text import snippet


def test_short_text_is_returned_whole_without_ellipsis():
    assert snippet("<p>Short and sweet.</p>") == "Short and sweet."


def test_tags_become_spaces_so_paragraphs_do_not_run_together():
    assert snippet("<p>One</p><p>Two</p>") == "One Two"


def test_entities_are_decoded_and_whitespace_collapsed():
    assert snippet("<p>Fish &amp;   chips\n\nplease</p>") == "Fish & chips please"


def test_long_text_is_cut_at_a_word_boundary():
    text = "word " * 50

    result = snippet(text, limit=22)

    assert result == "word word word word…"
    assert len(result) <= 22


def test_text_exactly_at_the_limit_is_not_cut():
    assert snippet("a" * 10, limit=10) == "a" * 10


def test_cut_that_lands_on_a_space_keeps_the_whole_words():
    assert snippet("aaaa bbbb cccc", limit=9) == "aaaa bbbb…"


def test_one_unbroken_word_is_hard_cut():
    assert snippet("x" * 50, limit=10) == "x" * 10 + "…"


def test_default_limit_is_about_140_characters():
    result = snippet("lorem ipsum " * 40)

    assert 100 < len(result) <= 141
    assert result.endswith("…")
