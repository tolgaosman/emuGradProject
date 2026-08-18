""" test_winnowing.py — WinnowingModel fingerprint similarity. """
import pytest
from src.models.winnowing import WinnowingModel


@pytest.fixture
def model():
    return WinnowingModel(k=3, w=2)


def test_tc13_identical_tokens_one(model):
    """TC-13: identical token streams yield similarity 1.0."""
    tokens = ["a", "b", "c", "d", "e", "f", "g"]
    assert model.compute(tokens, list(tokens)) == pytest.approx(1.0)


def test_tc14_short_input_zero(model):
    """TC-14: input shorter than k produces an empty fingerprint -> 0.0."""
    short = ["a", "b"]  # len < k (3)
    assert model.compute(short, short) == 0.0


def test_disjoint_tokens_low(model):
    a = ["a", "b", "c", "d", "e", "f"]
    b = ["u", "v", "w", "x", "y", "z"]
    assert model.compute(a, b) == pytest.approx(0.0)
