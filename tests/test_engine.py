""" test_engine.py — ScanEngine pairwise computation. """
import pytest
from src.engine import ScanEngine
from src.preprocessor import Preprocessor
from src.websearch import SearchResult, WebSearchError


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
    assert result.is_ai is False


def test_ai_mode_returns_ai_assessments():
    engine = ScanEngine(mode="ai_text")
    result = engine.compute(_file_data())
    assert result.is_ai is True
    assert result.matrix is None
    assert set(result.ai_assessments) == {"a.txt", "b.txt", "c.txt"}
    assessment = result.ai_assessments["a.txt"]
    assert 0.0 <= assessment.overall_probability <= 1.0
    assert assessment.band in ("low", "possible", "likely")


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


# -- web-source comparison ---------------------------------------------------


class _FakeWebClient:
    """Test double standing in for a real WebSearchClient.

    `pages_by_query` maps each query string to a list of (url, title, text)
    tuples; `search()`/`fetch_page_text()` never touch the network.
    """

    def __init__(self, pages_by_query: dict, raise_search_for: set[str] | None = None):
        self.pages_by_query = pages_by_query
        self.raise_search_for = raise_search_for or set()
        self.fetched_urls: list[str] = []

    def search(self, query, max_results=5):
        if query in self.raise_search_for:
            raise WebSearchError(f"no results for {query!r}")
        return [
            SearchResult(url=url, title=title, snippet="")
            for url, title, _text in self.pages_by_query.get(query, [])
        ][:max_results]

    def fetch_page_text(self, url, max_bytes=2_000_000):
        self.fetched_urls.append(url)
        for pages in self.pages_by_query.values():
            for page_url, _title, text in pages:
                if page_url == url:
                    return text
        raise WebSearchError(f"no such page {url!r}")


def _web_file_data():
    # Tokens are generated via the real Preprocessor, not hand-picked, so a
    # fetched web page containing the exact same raw text tokenizes
    # identically and scores 1.0 — a hand-written token list would silently
    # diverge from what the pipeline actually produces for that text.
    # Winnowing also needs >= k + w - 1 (5 + 4 - 1 = 8) tokens to produce any
    # fingerprint at all (see test_code_similarity_python_pair_uses_ast for
    # the same gotcha), so each sentence uses 8+ distinct content words.
    pre = Preprocessor(exclusions_path="__no_such_file__")
    a_raw = "This distinctive sentence describes foxes rivers mountains valleys forests deserts."
    b_raw = "This unrelated document explains quantum mechanics particles waves energy fields."
    a_tokens, a_kgrams = pre.process(a_raw, language="text")
    b_tokens, b_kgrams = pre.process(b_raw, language="text")
    return {
        "a.txt": {"raw": a_raw, "tokens": a_tokens, "kgrams": a_kgrams, "language": "text"},
        "b.txt": {"raw": b_raw, "tokens": b_tokens, "kgrams": b_kgrams, "language": "text"},
    }


def test_web_matches_populated_and_scored():
    file_data = _web_file_data()
    a_query = "This distinctive sentence describes foxes rivers mountains valleys forests deserts."
    web_client = _FakeWebClient(
        {a_query: [("https://example.com/foxes", "Foxes", file_data["a.txt"]["raw"])]}
    )
    pre = Preprocessor(exclusions_path="__no_such_file__")

    result = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, web_client=web_client, max_web_queries=5
    )

    assert result.web_matches["a.txt"]
    assert result.web_matches["a.txt"][0].url == "https://example.com/foxes"
    assert result.web_matches["a.txt"][0].score == pytest.approx(1.0)
    assert result.web_matches["b.txt"] == []


def test_web_matches_do_not_leak_between_files():
    """File A's web results must not affect file B's similarity index or
    source breakdown — each file gets its own per-file merge."""
    file_data = _web_file_data()
    a_query = "This distinctive sentence describes foxes rivers mountains valleys forests deserts."
    web_client = _FakeWebClient(
        {a_query: [("https://example.com/foxes", "Foxes", file_data["a.txt"]["raw"])]}
    )
    pre = Preprocessor(exclusions_path="__no_such_file__")

    result = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, web_client=web_client, max_web_queries=5
    )

    b_sources = [s["source"] for s in result.source_breakdowns.get("b.txt", [])]
    assert "https://example.com/foxes" not in b_sources


def test_uploaded_matrix_unaffected_by_web_client():
    """The uploaded-vs-uploaded matrix must be identical whether or not a
    web_client is supplied — web pages never enter it."""
    file_data = _web_file_data()
    pre = Preprocessor(exclusions_path="__no_such_file__")

    without_web = ScanEngine(mode="text_similarity").compute(file_data, preprocessor=pre)
    web_client = _FakeWebClient({})
    with_web = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, web_client=web_client
    )

    assert without_web.matrix is not None and with_web.matrix is not None
    assert without_web.matrix.get(0, 1) == pytest.approx(with_web.matrix.get(0, 1))


def test_web_search_error_degrades_to_empty_matches_not_raise():
    file_data = _web_file_data()
    a_query = "This distinctive sentence describes foxes rivers mountains valleys forests deserts."
    web_client = _FakeWebClient({}, raise_search_for={a_query})
    pre = Preprocessor(exclusions_path="__no_such_file__")

    result = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, web_client=web_client, max_web_queries=5
    )

    assert result.web_matches["a.txt"] == []
    assert any("Web search failed" in w for w in result.warnings)


def test_web_client_without_preprocessor_is_a_noop_with_warning():
    file_data = _web_file_data()
    web_client = _FakeWebClient({})
    result = ScanEngine(mode="text_similarity").compute(file_data, web_client=web_client)
    assert result.web_matches == {}
    assert any("without a preprocessor" in w for w in result.warnings)


def test_web_client_ignored_for_ai_modes():
    file_data = _web_file_data()
    web_client = _FakeWebClient({})
    pre = Preprocessor(exclusions_path="__no_such_file__")
    result = ScanEngine(mode="ai_text").compute(file_data, preprocessor=pre, web_client=web_client)
    assert result.web_matches == {}


def test_on_query_callback_invoked_per_query():
    file_data = _web_file_data()
    a_query = "This distinctive sentence describes foxes rivers mountains valleys forests deserts."
    web_client = _FakeWebClient(
        {a_query: [("https://example.com/foxes", "Foxes", file_data["a.txt"]["raw"])]}
    )
    pre = Preprocessor(exclusions_path="__no_such_file__")
    calls: list[tuple[str, int]] = []

    ScanEngine(mode="text_similarity").compute(
        file_data,
        preprocessor=pre,
        web_client=web_client,
        max_web_queries=5,
        on_query=lambda q, n: calls.append((q, n)),
    )

    assert (a_query, 1) in calls


def test_web_budget_exceeded_skips_remaining_work():
    file_data = _web_file_data()
    web_client = _FakeWebClient({})
    pre = Preprocessor(exclusions_path="__no_such_file__")

    result = ScanEngine(mode="text_similarity").compute(
        file_data, preprocessor=pre, web_client=web_client, web_budget_seconds=-1
    )

    assert any("budget exceeded" in w for w in result.warnings)
