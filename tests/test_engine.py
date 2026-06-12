""" test_engine.py — AlgorithmEngine pairwise computation. """
import pytest

from src.engine import AlgorithmEngine


def _file_data():
    return {
        "a.txt": {
            "raw": "alpha beta gamma",
            "tokens": ["alpha", "beta", "gamma"],
            "kgrams": [],
            "is_python": False,
        },
        "b.txt": {
            "raw": "alpha beta gamma",
            "tokens": ["alpha", "beta", "gamma"],
            "kgrams": [],
            "is_python": False,
        },
        "c.txt": {
            "raw": "delta epsilon zeta",
            "tokens": ["delta", "epsilon", "zeta"],
            "kgrams": [],
            "is_python": False,
        },
    }


def test_tc18_compute_builds_full_matrix():
    """TC-18: compute() returns a matrix sized to the number of files."""
    engine = AlgorithmEngine(algorithm="jaccard")
    matrix = engine.compute(_file_data())
    assert matrix.n == 3
    # identical token files -> 1.0
    i = matrix.names.index("a.txt")
    j = matrix.names.index("b.txt")
    assert matrix.get(i, j) == pytest.approx(1.0)


def test_ast_on_non_python_pair_zero():
    engine = AlgorithmEngine(algorithm="ast")
    matrix = engine.compute(_file_data())
    i = matrix.names.index("a.txt")
    j = matrix.names.index("b.txt")
    assert matrix.get(i, j) == 0.0


def test_all_algorithm_averages():
    engine = AlgorithmEngine(algorithm="all")
    matrix = engine.compute(_file_data())
    i = matrix.names.index("a.txt")
    j = matrix.names.index("c.txt")
    score = matrix.get(i, j)
    assert 0.0 <= score <= 1.0
