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
    """Non-Python input with no preprocessor uses the winnowing fallback."""
    engine = ScanEngine(mode="code_similarity")
    result = engine.compute(_file_data())
    assert result.matrix is not None
    i = result.matrix.names.index("a.txt")
    j = result.matrix.names.index("b.txt")
    assert result.matrix.get(i, j) == pytest.approx(1.0)  # winnowing fallback on identical text


def test_auto_without_preprocessor_degrades_to_winnowing():
    """Coverage scoring needs the stemmer/stopword set to find spans, so with
    no preprocessor `auto` falls back to winnowing. Library/test path only —
    both real callers (app.py, plagcheck.py) always pass one."""
    # Winnowing needs >= k + w - 1 (5 + 4 - 1 = 8) tokens to produce any
    # fingerprint at all; fewer than that and it silently returns 0.0.
    file_data = {
        "a.py": {
            "raw": "def add(a, b):\n    return a + b\n",
            "tokens": ["def", "add", "a", "b", "return", "a", "plus", "b"],
            "language": "python",
        },
        "b.py": {
            "raw": "def total(x, y):\n    return x + y\n",
            "tokens": ["def", "total", "x", "y", "return", "x", "plus", "y"],
            "language": "python",
        },
    }
    auto_matrix = ScanEngine(mode="code_similarity").compute(file_data).matrix
    winnowing_engine = ScanEngine(mode="code_similarity", algorithm="winnowing")
    winnowing_matrix = winnowing_engine.compute(file_data).matrix
    assert auto_matrix is not None
    assert winnowing_matrix is not None
    assert auto_matrix.get(0, 1) == pytest.approx(winnowing_matrix.get(0, 1))


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


def test_forced_cosine_differs_from_auto():
    """Forcing cosine produces a different score than auto, proving the
    override actually bypasses auto's default scoring."""
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


def _pre():
    from src.preprocessor import Preprocessor

    return Preprocessor(exclusions_path="__no_such_file__")


def _prose(raw: str) -> dict:
    pre = _pre()
    tokens, kgrams = pre.process(raw, language="text")
    return {"raw": raw, "tokens": tokens, "kgrams": kgrams, "language": "text"}


def test_identical_short_documents_score_high_not_zero():
    """Regression: `auto` used to be winnowing alone, which emits no
    fingerprint below k + w - 1 (8) tokens. A short sentence compared with
    itself scored 0.0 while the report still highlighted it."""
    pre = _pre()
    raw = "The quick brown fox jumps over the lazy dog today."
    file_data = {"x.txt": _prose(raw), "y.txt": _prose(raw)}
    result = ScanEngine(mode="text_similarity").compute(file_data, preprocessor=pre)
    assert result.matrix is not None
    assert len(file_data["x.txt"]["tokens"]) < 8  # the case that used to fail
    assert result.matrix.get(0, 1) > 0.8


def test_auto_score_equals_highlighted_coverage():
    """`auto` is defined as the share of the document that gets highlighted,
    so it must equal what `matched_spans` covers — not merely correlate."""
    from src.reporter import matched_spans
    from src.similarity_index import _coverage_ratio

    pre = _pre()
    raw_a = (
        "Machine learning models require careful validation before deployment "
        "in production systems, otherwise silent failures accumulate."
    )
    raw_b = (
        "Machine learning models require careful validation before deployment "
        "in production systems, according to a completely different follow-up."
    )
    file_data = {"a.txt": _prose(raw_a), "b.txt": _prose(raw_b)}
    result = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, min_match_words=0
    )

    spans_a, spans_b = matched_spans(raw_a, raw_b, "text", "text", pre)
    expected = max(_coverage_ratio(raw_a, spans_a), _coverage_ratio(raw_b, spans_b))
    assert result.matrix is not None
    assert result.matrix.get(0, 1) == pytest.approx(expected)


def test_renamed_python_copy_scores_high_via_structural_spans():
    """A pure rename defeats literal k-gram matching, so coverage alone would
    miss the most common form of code plagiarism. Structurally identical
    functions count as evidence — and are highlightable, unlike a raw AST
    score."""
    pre = _pre()
    original = (
        "def compute_average(numbers):\n"
        "    total = 0\n"
        "    for value in numbers:\n"
        "        total = total + value\n"
        "    return total / len(numbers)\n"
    )
    renamed = (
        "def mean_of(items):\n"
        "    running = 0\n"
        "    for element in items:\n"
        "        running = running + element\n"
        "    return running / len(items)\n"
    )

    def py(raw):
        tokens, kgrams = pre.process(raw, language="python")
        return {"raw": raw, "tokens": tokens, "kgrams": kgrams, "language": "python"}

    file_data = {"a.py": py(original), "b.py": py(renamed)}
    result = ScanEngine(mode="code_similarity").compute(file_data, preprocessor=pre)
    assert result.matrix is not None
    assert result.matrix.get(0, 1) > 0.8


def test_structurally_unrelated_python_stays_near_zero():
    """The structural-span path must not flag every Python file as similar."""
    pre = _pre()

    def py(raw):
        tokens, kgrams = pre.process(raw, language="python")
        return {"raw": raw, "tokens": tokens, "kgrams": kgrams, "language": "python"}

    file_data = {
        "a.py": py("def parse_config(path):\n    with open(path) as f:\n        return f.read()\n"),
        "b.py": py("class Widget:\n    def __init__(self, w):\n        self.w = w\n"),
    }
    result = ScanEngine(mode="code_similarity").compute(file_data, preprocessor=pre)
    assert result.matrix is not None
    assert result.matrix.get(0, 1) == pytest.approx(0.0)
