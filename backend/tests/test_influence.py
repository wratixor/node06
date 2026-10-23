import pytest
from node06_service.influence import SCALE, calculate


def test_t1_conservation_delegation_and_point_split():
    result = calculate(["a", "b"], [("a", "b")], [("a", "p"), ("a", "q"), ("b", "p")])
    assert result["weights"]["a"] / SCALE == pytest.approx(2 / 3, abs=1e-9)
    assert result["weights"]["b"] / SCALE == pytest.approx(4 / 3, abs=1e-9)
    assert sum(result["weights"].values()) == 2 * SCALE
    assert result["people_units"] == SCALE
    assert result["idle_units"] == 0
    assert sum(sum(a.values()) for a in result["allocations"].values()) == SCALE
    assert abs(result["allocations"]["a"]["p"] - result["allocations"]["a"]["q"]) <= 1
    assert result == calculate(["b", "a"], [("a", "b")], [("b", "p"), ("a", "q"), ("a", "p")])


def test_empty_isolated_cycles_star_and_inactive_edges():
    for ids, edges in [
        ([], []),
        (["a"], []),
        (["a", "b"], [("a", "b"), ("b", "a")]),
        (list("abcdefgh"), [(x, "a") for x in "bcdefgh"]),
    ]:
        result = calculate(ids, edges, [])
        assert sum(result["weights"].values()) == len(ids) * SCALE
        assert result["idle_units"] == result["people_units"] == len(ids) * SCALE // 2
    assert calculate(["a"], [("missing", "a"), ("a", "missing")], []) == calculate(["a"], [], [])
