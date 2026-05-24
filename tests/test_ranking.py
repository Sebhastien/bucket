from bucket.ranking import choose_pivot, next_bounds


def test_strict_pivot_uses_midpoint():
    assert choose_pivot(0, 10, randomize=False) == 5
    assert choose_pivot(2, 5, randomize=False) == 3


def test_randomized_pivot_stays_inside_bounds():
    for _ in range(100):
        pivot = choose_pivot(3, 20, randomize=True)
        assert 3 <= pivot < 20


def test_next_bounds():
    assert next_bounds(0, 10, 5, candidate_wins=True) == (0, 5)
    assert next_bounds(0, 10, 5, candidate_wins=False) == (6, 10)
