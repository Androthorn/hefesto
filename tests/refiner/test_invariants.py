from hefesto.refiner.invariants import check_invariants


def test_passes_when_all_present():
    assert check_invariants("foo BAR baz", ["BAR"]) is True


def test_fails_when_altered():
    assert check_invariants("foo Bar baz", ["BAR"]) is False


def test_empty_invariants_pass():
    assert check_invariants("anything", []) is True
