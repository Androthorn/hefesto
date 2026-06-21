from hefesto.diff.text_diff import text_diff


def test_identical_is_empty():
    assert text_diff("same\n", "same\n") == ""


def test_shows_added_and_removed_lines():
    d = text_diff("a\nb\n", "a\nc\n")
    assert "-b" in d and "+c" in d
