""" test_jaccard.py — JaccardModel (set intersection / union). """
import pytest

from src.models.jaccard import JaccardModel


@pytest.fixture
def model():
    return JaccardModel()


def test_tc12_known_set_ratio(model):
    """TC-12: Jaccard index equals |intersection| / |union|."""
    a = ["a", "b", "c", "d"]
    b = ["c", "d", "e", "f"]
    # intersection {c,d}=2, union {a,b,c,d,e,f}=6 -> 2/6
    assert model.compute(a, b) == pytest.approx(2 / 6)


def test_identical_sets_one(model):
    assert model.compute(["x", "y"], ["y", "x"]) == pytest.approx(1.0)


def test_empty_input_returns_zero(model):
    assert model.compute([], ["a"]) == 0.0
    assert model.compute(["a"], []) == 0.0
