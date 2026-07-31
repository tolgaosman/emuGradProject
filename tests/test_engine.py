""" test_engine.py — ScanEngine pairwise computation. """
import pytest
from src.engine import ScanEngine


def _file_data():
    return {
        "a.txt": {
            "raw": "word " * 60,
            "tokens": ["word"] * 60,
            "kgrams": [],
            "language": "text",
        },
        "b.txt": {
            "raw": "word " * 60,
            "tokens": ["word"] * 60,
            "kgrams": [],
            "language": "text",
        },
        "c.txt": {
            "raw": "delta epsilon zeta",
            "tokens": ["delta", "epsilon", "zeta"],
            "kgrams": [],
            "language": "text",
        },
    }


def test_tc18_compute_builds_full_matrix():
    """TC-18: compute() returns a result whose matrix is sized to the number of files."""
    engine = ScanEngine(mode="text_similarity")
    result = engine.compute(_file_data())
    assert result.matrix is not None
    assert result.matrix.n == 3
    # identical token files -> 1.0
    i = result.matrix.names.index("a.txt")
    j = result.matrix.names.index("b.txt")
    assert result.matrix.get(i, j) == pytest.approx(1.0)


def test_code_similarity_on_non_python_pair():
    """Non-Python code (no language == 'python') falls back to winnowing alone."""
    engine = ScanEngine(mode="code_similarity")
    result = engine.compute(_file_data())
    assert result.matrix is not None
    i = result.matrix.names.index("a.txt")
    j = result.matrix.names.index("b.txt")
    assert result.matrix.get(i, j) == pytest.approx(1.0)  # winnowing fallback on identical text


def test_code_similarity_python_pair_uses_ast():
    """Both files Python -> AST + winnowing blend, not the winnowing-only fallback."""
    code = "def add(a, b):\n    return a + b\n"
    # Winnowing needs >= k + w - 1 (5 + 4 - 1 = 8) tokens to produce any
    # fingerprint at all; fewer than that and it silently returns 0.0.
    tokens = ["def", "add", "a", "b", "return", "a", "plus", "b"]
    file_data = {
        "a.py": {"raw": code, "tokens": tokens, "language": "python"},
        "b.py": {"raw": code, "tokens": tokens, "language": "python"},
    }
    engine = ScanEngine(mode="code_similarity")
    result = engine.compute(file_data)
    assert result.matrix is not None
    assert result.matrix.get(0, 1) == pytest.approx(1.0)


def test_compute_with_preprocessor_populates_similarity_index():
    """When a preprocessor is supplied, per-document similarity indices and
    source breakdowns are computed alongside the matrix."""
    from src.preprocessor import Preprocessor

    pre = Preprocessor(exclusions_path="__no_such_file__")
    shared = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    shared_tokens = pre.process(shared, language="text")[0]
    file_data = {
        "a.txt": {"raw": shared, "tokens": shared_tokens, "language": "text"},
        "b.txt": {"raw": shared, "tokens": shared_tokens, "language": "text"},
    }
    engine = ScanEngine(mode="text_similarity")
    result = engine.compute(file_data, preprocessor=pre)
    assert result.similarity_indices["a.txt"] > 0.0
    assert "b.txt" in result.source_breakdowns["a.txt"][0]["source"]


def test_compute_without_preprocessor_skips_similarity_index():
    """Similarity index computation is optional and skipped without a preprocessor."""
    engine = ScanEngine(mode="text_similarity")
    result = engine.compute(_file_data())
    assert result.similarity_indices == {}
    assert result.source_breakdowns == {}


def test_algorithm_auto_is_default_and_echoed_on_result():
    engine = ScanEngine(mode="text_similarity")
    result = engine.compute(_file_data())
    assert engine.algorithm == "auto"
    assert result.algorithm == "auto"


def test_forced_cosine_differs_from_auto_blend():
    """Forcing a single algorithm produces a different score than the mode's
    default blend, proving the override actually bypasses the blend logic."""
    file_data = {
        "a.txt": {
            "raw": "the quick brown fox jumps over the lazy dog",
            "tokens": ["quick", "brown", "fox", "jump", "lazi", "dog"],
            "kgrams": [],
            "language": "text",
        },
        "b.txt": {
            "raw": "a swift brown fox leaps above a lazy dog",
            "tokens": ["swift", "brown", "fox", "leap", "abov", "lazi", "dog"],
            "kgrams": [],
            "language": "text",
        },
    }
    auto_matrix = ScanEngine(mode="text_similarity").compute(file_data).matrix
    cosine_matrix = ScanEngine(mode="text_similarity", algorithm="cosine").compute(file_data).matrix
    assert auto_matrix is not None
    assert cosine_matrix is not None
    assert auto_matrix.get(0, 1) != pytest.approx(cosine_matrix.get(0, 1))


def test_forced_ast_on_non_python_pair_scores_zero_not_raises():
    """AST needs raw Python source; forcing it on non-Python input degrades
    to 0.0 instead of raising, since ast.parse() rejects non-Python syntax."""
    file_data = {
        "a.java": {
            "raw": "public class A {}",
            "tokens": ["public", "class", "a"],
            "language": "java",
        },
        "b.java": {
            "raw": "public class B {}",
            "tokens": ["public", "class", "b"],
            "language": "java",
        },
    }
    result = ScanEngine(mode="code_similarity", algorithm="ast").compute(file_data)
    assert result.matrix is not None
    assert result.matrix.get(0, 1) == pytest.approx(0.0)


def test_forced_algorithm_recorded_on_result():
    engine = ScanEngine(mode="code_similarity", algorithm="winnowing")
    result = engine.compute(_file_data())
    assert result.algorithm == "winnowing"
