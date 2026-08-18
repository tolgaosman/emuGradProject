""" test_cosine.py — CosineModel (TF-IDF cosine similarity). """
import pytest
from src.models.cosine import CosineModel


@pytest.fixture
def model():
    return CosineModel()


def test_tc10_identical_tokens_high_similarity(model):
    """TC-10: identical token streams yield similarity close to 1.0."""
    tokens = ["alpha", "beta", "gamma", "delta"]
    score = model.compute(tokens, list(tokens))
    assert score == pytest.approx(1.0, abs=1e-6)


def test_tc11_disjoint_tokens_zero_similarity(model):
    """TC-11: token streams with no shared vocabulary yield 0.0."""
    score = model.compute(["alpha", "beta"], ["gamma", "delta"])
    assert score == pytest.approx(0.0, abs=1e-6)


def test_empty_input_returns_zero(model):
    assert model.compute([], ["a", "b"]) == 0.0
    assert model.compute(["a"], []) == 0.0


def test_single_char_tokens_empty_vocabulary_returns_zero(model):
    """Single-character tokens fall outside TfidfVectorizer's default token
    pattern, so the vocabulary is empty and compute() must return 0.0
    instead of propagating the ValueError."""
    assert model.compute(["a"], ["b"]) == 0.0
